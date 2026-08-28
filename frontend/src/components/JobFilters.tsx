import type { JobResult } from "../types/job";

export interface FilterState {
  company: string; // "all" or company name
  minScore: number;
  savedOnly: boolean;
  showIgnored: boolean;
  location: string;
  sortBy: "score" | "company" | "title";
}

interface Props {
  filters: FilterState;
  companies: string[];
  onChange: (patch: Partial<FilterState>) => void;
}

const CONTROL =
  "rounded-control border border-edge bg-surface px-2.5 py-1.5 font-mono text-[12px] " +
  "text-ink transition-colors hover:border-faint";

export function JobFilters({ filters, companies, onChange }: Props) {
  return (
    <div
      data-testid="job-filters"
      className="flex flex-wrap items-center gap-2 rounded-card border border-edge bg-surface p-3"
    >
      <select
        aria-label="Filter by company"
        value={filters.company}
        onChange={(e) => onChange({ company: e.target.value })}
        className={CONTROL}
      >
        <option value="all">All companies</option>
        {companies.map((company) => (
          <option key={company} value={company}>
            {company}
          </option>
        ))}
      </select>

      <select
        aria-label="Minimum match score"
        value={filters.minScore}
        onChange={(e) => onChange({ minScore: Number(e.target.value) })}
        className={CONTROL}
      >
        <option value={0}>Any match</option>
        <option value={50}>50%+ match</option>
        <option value={70}>70%+ match</option>
        <option value={85}>85%+ match</option>
      </select>

      <input
        aria-label="Filter by location"
        placeholder="Location..."
        value={filters.location}
        onChange={(e) => onChange({ location: e.target.value })}
        className={`${CONTROL} w-28 placeholder:text-faint`}
      />

      <label className="flex cursor-pointer items-center gap-1.5 text-[12px] text-body">
        <input
          type="checkbox"
          checked={filters.savedOnly}
          onChange={(e) => onChange({ savedOnly: e.target.checked })}
          className="h-3.5 w-3.5 rounded-sm accent-signal"
        />
        Saved only
      </label>

      <label className="flex cursor-pointer items-center gap-1.5 text-[12px] text-body">
        <input
          type="checkbox"
          checked={filters.showIgnored}
          onChange={(e) => onChange({ showIgnored: e.target.checked })}
          className="h-3.5 w-3.5 rounded-sm accent-signal"
        />
        Show ignored
      </label>

      <label className="ml-auto flex items-center gap-2">
        <span className="eyebrow text-faint">Sort</span>
        <select
          aria-label="Sort jobs"
          value={filters.sortBy}
          onChange={(e) =>
            onChange({ sortBy: e.target.value as FilterState["sortBy"] })
          }
          className={CONTROL}
        >
          <option value="score">Match score</option>
          <option value="company">Company</option>
          <option value="title">Title</option>
        </select>
      </label>
    </div>
  );
}

export function applyFilters(
  jobs: JobResult[],
  filters: FilterState,
  jobStates: Record<string, string>
): JobResult[] {
  let filtered = jobs.filter((job) => {
    if (filters.company !== "all" && job.company !== filters.company) return false;
    if (job.match.overall_score < filters.minScore) return false;

    const state = jobStates[job.job_url];
    if (filters.savedOnly && state !== "saved") return false;
    if (!filters.showIgnored && state === "ignored") return false;

    if (filters.location.trim()) {
      const needle = filters.location.trim().toLowerCase();
      const haystack = `${job.location ?? ""} ${job.description}`.toLowerCase();
      if (!haystack.includes(needle)) return false;
    }
    return true;
  });

  filtered = [...filtered].sort((a, b) => {
    switch (filters.sortBy) {
      case "company":
        return a.company.localeCompare(b.company);
      case "title":
        return a.job_title.localeCompare(b.job_title);
      default:
        return b.match.overall_score - a.match.overall_score;
    }
  });
  return filtered;
}
