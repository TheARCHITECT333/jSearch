import { useEffect, useState } from "react";
import { Layout } from "../components/Layout";
import { ResumeUpload } from "../components/ResumeUpload";
import { ResumeProfile } from "../components/ResumeProfile";
import { CompanyList } from "../components/CompanyList";
import { LLMSettingsPanel } from "../components/LLMSettings";
import { SearchButton } from "../components/SearchButton";
import { LocationPicker } from "../components/LocationPicker";
import { SearchProgress } from "../components/SearchProgress";
import { JobList } from "../components/JobList";
import {
  JobFilters,
  applyFilters,
  type FilterState,
} from "../components/JobFilters";
import { JobDetails } from "../components/JobDetails";

import { useAppState } from "../storage/localStore";
import { extractProfile, getSearch, startSearch, streamSearchProgress } from "../api/search";
import { isRuledOut } from "../types/job";
import type { CandidateProfile } from "../types/resume";
import type { Company } from "../types/company";
import type { JobResult, JobStateMap } from "../types/job";
import type { LLMSettings, SearchStatus } from "../types/search";
import type { AppState } from "../storage/localStore";

const POLL_INTERVAL_MS = 1500;

export default function Home() {
  const [state, setState] = useAppState();

  // The API key lives ONLY in memory - never localStorage.
  const [apiKey, setApiKey] = useState("");

  const [extracting, setExtracting] = useState(false);
  const [profileError, setProfileError] = useState<string | null>(null);

  const [searchId, setSearchId] = useState<string | null>(null);
  const [searchStatus, setSearchStatus] = useState<SearchStatus | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);

  const [detailsJob, setDetailsJob] = useState<JobResult | null>(null);
  const [filters, setFilters] = useState<FilterState>({
    company: "all",
    minScore: 0,
    savedOnly: false,
    showIgnored: false,
    location: "",
    sortBy: "score",
  });

  const llmSettings: LLMSettings = {
    provider: state.llmProvider,
    base_url: state.llmBaseUrl,
    model: state.llmModel,
  };

  const enabledCompanies = state.companies.filter(
    (c) => state.companyEnabled[c.name] !== false
  );

  // ---------------------------------------------------------------------
  // Resume + profile
  // ---------------------------------------------------------------------

  async function handleResumeLoaded(latex: string) {
    setState({ resumeLatex: latex });
    setProfileError(null);
    setExtracting(true);
    try {
      const profile = await extractProfile(latex, {
        ...llmSettings,
        api_key: apiKey || undefined,
      });
      setState({ candidateProfile: profile });
    } catch (error) {
      setProfileError(error instanceof Error ? error.message : "Unknown error.");
      setState({ candidateProfile: null });
    } finally {
      setExtracting(false);
    }
  }

  function handleProfileEdited(profile: CandidateProfile) {
    setState({ candidateProfile: profile });
  }

  function handleCompaniesImported(companies: Company[], errors: string[]) {
    if (errors.length > 0 && companies.length === 0) return;
    const merged = [...state.companies];
    for (const company of companies) {
      if (!merged.some((existing) => existing.name === company.name)) {
        merged.push(company);
      }
    }
    setState({ companies: merged });
  }

  // ---------------------------------------------------------------------
  // Search lifecycle
  // ---------------------------------------------------------------------

  function validateBeforeSearch(): string[] {
    const reasons: string[] = [];
    if (!state.resumeLatex?.trim()) reasons.push("Load your resume first.");
    if (!state.candidateProfile)
      reasons.push("No candidate profile — load a resume so it can be analyzed.");
    if (enabledCompanies.length === 0)
      reasons.push("Enable at least one company.");
    if (!llmSettings.model.trim()) reasons.push("Set an LLM model.");
    if (!llmSettings.base_url.trim()) reasons.push("Set the LLM base URL.");
    if (llmSettings.provider === "openai-compatible" && !apiKey.trim()) {
      reasons.push("Enter your API key for the OpenAI-compatible provider.");
    }
    return reasons;
  }

  async function handleStartSearch() {
    setSearchError(null);
    try {
      const id = await startSearch({
        resume_latex: state.resumeLatex ?? "",
        companies: enabledCompanies.map(({ name, careers_url }) => ({
          name,
          careers_url,
        })),
        freshness: state.freshness,
        locations: state.searchLocations,
        llm: {
          ...llmSettings,
          api_key: apiKey || undefined,
        },
      });
      setSearchId(id);
      setSearchStatus({
        id,
        status: "running",
        companies: enabledCompanies.map((company) => ({
          company: company.name,
          status: "pending" as const,
        })),
        results: [],
      });
    } catch (error) {
      setSearchError(
        error instanceof Error ? error.message : "Could not start search."
      );
    }
  }

  // Live progress: SSE first, polling as automatic fallback.
  useEffect(() => {
    if (!searchId) return;
    let cancelled = false;
    let pollTimer: ReturnType<typeof setTimeout> | null = null;
    let received = false;

    const apply = (status: SearchStatus) => {
      setSearchStatus(status);
      // Persist on any terminal state, not just success: a search stopped by
      // its time budget still carries every company that finished, and those
      // results are worth keeping.
      const finished =
        status.status === "completed" ||
        status.status === "failed" ||
        status.status === "cancelled";
      if (finished && status.results.length > 0) {
        setState({ latestResults: status.results });
      }
    };

    const startPolling = () => {
      if (cancelled || pollTimer) return;
      const tick = async () => {
        try {
          const status = await getSearch(searchId);
          if (cancelled) return;
          apply(status);
          if (status.status === "queued" || status.status === "running") {
            pollTimer = setTimeout(tick, POLL_INTERVAL_MS);
          }
        } catch (error) {
          if (!cancelled) {
            setSearchError(
              error instanceof Error
                ? error.message
                : "Lost contact with the backend."
            );
          }
        }
      };
      tick();
    };

    const closeStream = streamSearchProgress(searchId, {
      onUpdate: (status) => {
        received = true;
        if (!cancelled) apply(status);
      },
      onFallback: () => {
        if (!cancelled) startPolling();
      },
    });

    // Safety net: if SSE never delivers anything (buffering proxy, hung
    // connection), switch to polling after a short grace period.
    const safetyTimer = setTimeout(() => {
      if (!cancelled && !received) {
        closeStream();
        startPolling();
      }
    }, 4000);

    return () => {
      cancelled = true;
      clearTimeout(safetyTimer);
      if (pollTimer) clearTimeout(pollTimer);
      closeStream();
    };
  }, [searchId, setState]);

  // ---------------------------------------------------------------------
  // Saved / ignored / results
  // ---------------------------------------------------------------------

  const jobStates: JobStateMap = { ...state.ignoredJobs, ...state.savedJobs };

  function handleSave(url: string) {
    const next = { ...state.savedJobs };
    if (next[url]) delete next[url];
    else next[url] = "saved";
    setState({ savedJobs: next });
  }

  function handleIgnore(url: string) {
    const next = { ...state.ignoredJobs };
    if (next[url]) delete next[url];
    else next[url] = "ignored";
    setState({ ignoredJobs: next });
  }

  // Results arrive company by company, so show them as they land rather than
  // holding everything back until the last site finishes. On a long list that
  // is the difference between a blank page for an hour and a list that fills
  // in. Once a search exists it owns the view - falling back to the previous
  // run's results mid-search would show stale jobs as if they were new.
  const results = searchStatus ? searchStatus.results : state.latestResults;
  // Partition AFTER filtering and sorting: "sort by company" would otherwise
  // float a job you are barred from straight back to the top of the list.
  const filteredJobs = applyFilters(results ?? [], filters, jobStates);
  const visibleJobs = filteredJobs.filter((job) => !isRuledOut(job));
  const ruledOutJobs = filteredJobs.filter(isRuledOut);
  // What the agents actually opened, not how many survived - the two differ
  // sharply once location filtering kicks in, and "1 examined" next to a
  // company row reading "8 jobs examined" is just wrong.
  const examinedCount = (searchStatus?.companies ?? []).reduce(
    (total, company) => total + (company.jobs_examined ?? 0),
    0
  );
  const filterCompanies = [
    ...new Set((results ?? []).map((job) => job.company)),
  ];

  const running = searchStatus?.status === "running";

  return (
    <Layout
      rail={
        <>
          <ResumeUpload resumeLatex={state.resumeLatex} onLoaded={handleResumeLoaded} />
          <ResumeProfile
            profile={state.candidateProfile}
            extracting={extracting}
            error={profileError}
            onEdit={handleProfileEdited}
          />
          <CompanyList
            companies={state.companies}
            enabled={state.companyEnabled}
            onChangeEnabled={(name, value) =>
              setState({
                companyEnabled: { ...state.companyEnabled, [name]: value },
              })
            }
            onSetAllEnabled={(value) =>
              setState({
                companyEnabled: Object.fromEntries(
                  state.companies.map((c) => [c.name, value])
                ),
              })
            }
            onClear={() =>
              // Drop the toggles with the list: leaving them behind means a
              // re-import silently inherits whatever was disabled last time.
              setState({ companies: [], companyEnabled: {} })
            }
            onImport={handleCompaniesImported}
          />
          <LocationPicker
            locations={state.searchLocations}
            onChange={(locations) => setState({ searchLocations: locations })}
          />
          <LLMSettingsPanel
            settings={llmSettings}
            apiKey={apiKey}
            onChange={(patch) => {
              const next: Partial<AppState> = {};
              if (patch.provider) next.llmProvider = patch.provider;
              if (patch.base_url !== undefined) next.llmBaseUrl = patch.base_url;
              if (patch.model !== undefined) next.llmModel = patch.model;
              setState(next);
            }}
            onApiKeyChange={setApiKey}
          />
        </>
      }
    >
      <SearchButton
        disabledReasons={validateBeforeSearch()}
        running={Boolean(running)}
        freshness={state.freshness}
        onFreshnessChange={(value) => setState({ freshness: value })}
        onStart={handleStartSearch}
      />

      {(searchStatus || searchError) && (
        <SearchProgress
          state={searchStatus?.status ?? (searchError ? "failed" : null)}
          companies={searchStatus?.companies ?? []}
          error={
            searchError ??
            (searchStatus?.status === "failed" ? searchStatus.error ?? null : null)
          }
        />
      )}

      {results && results.length > 0 && (
        <>
          <div className="flex items-baseline justify-between gap-4 pt-1">
            <h2
              className="text-[17px] font-semibold tracking-tightest text-ink"
              data-testid="results-heading"
            >
              {visibleJobs.length} job{visibleJobs.length === 1 ? "" : "s"} worth
              considering{running ? " so far" : ""}
            </h2>
            <span className="token shrink-0 text-faint">
              {examinedCount} examined
            </span>
          </div>

          <JobFilters
            filters={filters}
            companies={filterCompanies}
            onChange={(patch) => setFilters({ ...filters, ...patch })}
          />

          <JobList
            jobs={visibleJobs}
            jobStates={jobStates}
            onSave={handleSave}
            onIgnore={handleIgnore}
            onOpenDetails={setDetailsJob}
          />

          {ruledOutJobs.length > 0 && (
            <details data-testid="ruled-out" className="group">
              <summary className="flex cursor-pointer items-center gap-2 rounded-card border border-edge bg-surface px-4 py-3 text-[13px] font-medium text-body transition-colors hover:border-faint">
                <span
                  aria-hidden
                  className="font-mono text-[11px] text-oxide transition-transform group-open:rotate-90"
                >
                  ▶
                </span>
                {ruledOutJobs.length} ruled out by a stated requirement
              </summary>
              <p className="px-4 py-3 text-[12px] leading-relaxed text-faint">
                Each of these states a hard bar your resume does not clear. Shown so you
                can disagree — the posting is not always the whole truth.
              </p>
              <JobList
                jobs={ruledOutJobs}
                jobStates={jobStates}
                onSave={handleSave}
                onIgnore={handleIgnore}
                onOpenDetails={setDetailsJob}
              />
            </details>
          )}
        </>
      )}

      {!running && (results === null || results.length === 0) && !searchStatus && (
        <div className="rounded-card border border-dashed border-edge bg-surface px-6 py-16 text-center">
          <p className="text-[15px] font-semibold tracking-tightest text-ink">
            No search yet
          </p>
          <p className="mx-auto mt-2 max-w-sm text-[13px] leading-relaxed text-body">
            Load your resume, import a company list and point the app at a model — then
            run a search. Results appear here, ranked, with anything you are barred from
            kept separately.
          </p>
        </div>
      )}

      <JobDetails
        job={detailsJob}
        jobStates={jobStates}
        onClose={() => setDetailsJob(null)}
        onSave={handleSave}
        onIgnore={handleIgnore}
      />
    </Layout>
  );
}
