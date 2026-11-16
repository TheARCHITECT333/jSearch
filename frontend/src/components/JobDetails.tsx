import { useEffect } from "react";
import { isRuledOut, type JobResult, type JobStateMap } from "../types/job";

interface Props {
  job: JobResult | null;
  jobStates: JobStateMap;
  onClose: () => void;
  onSave: (url: string) => void;
  onIgnore: (url: string) => void;
}

function ScoreRow({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="token text-faint">{label}</span>
        <span
          className="text-[14px] font-semibold tracking-caption text-ink"
          data-testid={`score-${label.toLowerCase().replace(" ", "-")}`}
        >
          {value}%
        </span>
      </div>
      <span className="meter-track mt-1.5 block">
        <span
          className="meter-fill bg-ink"
          style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
        />
      </span>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-[17px] font-semibold text-ink">{title}</h3>
      <div className="mt-2">{children}</div>
    </div>
  );
}

export function JobDetails({ job, jobStates, onClose, onSave, onIgnore }: Props) {
  // Escape closes the panel: it covers the list, so there must be a way out
  // that does not require finding the button.
  useEffect(() => {
    if (!job) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [job, onClose]);

  if (!job) return null;
  const state = jobStates[job.job_url];
  const ruledOut = isRuledOut(job);

  return (
    <>
      <div
        aria-hidden
        onClick={onClose}
        className="frosted fixed inset-0 z-40 !mt-0 bg-black/30"
      />
      <aside
        role="dialog"
        aria-label={`Job details: ${job.job_title}`}
        data-testid="job-details"
        className="fixed inset-y-0 right-0 z-50 !mt-0 flex w-full max-w-xl flex-col bg-paper"
      >
        <header className="flex items-start justify-between gap-4 bg-surface px-6 py-5">
          <div className="min-w-0">
            <h2 className="text-[28px] font-semibold leading-[1.14] text-ink">
              {job.job_title}
            </h2>
            <p className="caption mt-1 text-faint">
              {job.company}
              {job.location ? ` · ${job.location}` : ""}
              {job.employment_type ? ` · ${job.employment_type}` : ""}
            </p>
          </div>
          <button
            type="button"
            aria-label="Close details"
            data-testid="close-details"
            onClick={onClose}
            title="Close (Esc)"
            className="btn-icon"
          >
            <span aria-hidden>✕</span>
          </button>
        </header>

        <div className="flex-1 space-y-8 overflow-y-auto px-6 py-6">
          {ruledOut && (
            <div className="rounded-lg border border-alert-line bg-alert-soft p-6">
              <h3 className="text-[17px] font-semibold text-alert">Ruled out by the posting</h3>
              <ul className="mt-2 space-y-1.5">
                {job.match.disqualifiers.map((reason) => (
                  <li key={reason} className="caption flex gap-2 text-alert">
                    <span aria-hidden>
                      ✕
                    </span>
                    {reason}
                  </li>
                ))}
              </ul>
              <p className="caption mt-3 text-alert/80">
                Postings overstate their requirements often enough to be worth a look
                anyway. This is a flag, not a lock.
              </p>
            </div>
          )}

          <div className="card p-6">
            <div className="flex items-end justify-between">
              <div>
                <span
                  className={`font-display text-[56px] font-semibold leading-none tracking-hero ${
                    ruledOut ? "text-faint" : "text-primary"
                  }`}
                  data-testid="details-overall-score"
                >
                  {job.match.overall_score}%
                </span>
                <p className="token mt-2 text-faint">Overall fit</p>
              </div>
              <div className="text-right">
                <span className="font-display text-[34px] font-semibold leading-none text-ink">
                  {job.match.keyword_coverage > 0 ? `${job.match.keyword_coverage}%` : "—"}
                </span>
                <p className="token mt-2 text-faint">Keywords verbatim</p>
              </div>
            </div>

            <div className="mt-6 grid gap-4 sm:grid-cols-2">
              <ScoreRow label="Role fit" value={job.match.role_fit} />
              <ScoreRow label="Skill fit" value={job.match.skill_fit} />
              <ScoreRow label="Experience fit" value={job.match.experience_fit} />
              <ScoreRow label="Location fit" value={job.match.location_fit} />
            </div>

            {job.match.seniority_band && (
              <p className="token mt-5 border-t border-divider pt-4 text-faint">
                Written for {job.match.seniority_band} level
                {job.match.required_years !== null &&
                job.match.required_years !== undefined
                  ? ` · asks for ${job.match.required_years}+ years`
                  : ""}
              </p>
            )}
          </div>

          {job.match.reason && (
            <p className="text-[17px] text-body">{job.match.reason}</p>
          )}

          <div className="grid gap-8 sm:grid-cols-2">
            <Section title="Matching skills">
              <ul className="flex flex-wrap gap-1.5">
                {job.match.matching_skills.map((skill) => (
                  <li
                    key={skill}
                    className="chip"
                  >
                    {skill}
                  </li>
                ))}
                {job.match.matching_skills.length === 0 && (
                  <li className="caption text-faint">None listed</li>
                )}
              </ul>
            </Section>
            <Section title="Missing skills">
              <ul className="flex flex-wrap gap-1.5">
                {job.match.missing_skills.map((skill) => (
                  <li
                    key={skill}
                    className="chip-muted line-through"
                  >
                    {skill}
                  </li>
                ))}
                {job.match.missing_skills.length === 0 && (
                  <li className="caption text-faint">Nothing important missing</li>
                )}
              </ul>
            </Section>
          </div>

          {job.match.missing_keywords.length > 0 && (
            <Section title="In the posting, not in your resume">
              <ul className="flex flex-wrap gap-1.5">
                {job.match.missing_keywords.map((word) => (
                  <li
                    key={word}
                    className="chip-muted !text-body"
                  >
                    {word}
                  </li>
                ))}
              </ul>
              <p className="caption mt-3 text-faint">
                A recruiter's search matches these literally. Worth adding wherever
                they are honestly true of your work.
              </p>
            </Section>
          )}

          {job.requirements.length > 0 && (
            <Section title="Requirements">
              <ul className="space-y-1.5">
                {job.requirements.map((req, index) => (
                  <li key={index} className="caption flex gap-2 text-body">
                    <span aria-hidden className="text-faint">
                      —
                    </span>
                    {req}
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {job.preferred_qualifications.length > 0 && (
            <Section title="Preferred (not required)">
              <ul className="space-y-1.5">
                {job.preferred_qualifications.map((qual, index) => (
                  <li key={index} className="caption flex gap-2 text-body">
                    <span aria-hidden className="text-faint">
                      —
                    </span>
                    {qual}
                  </li>
                ))}
              </ul>
            </Section>
          )}

          <Section title="Description">
            <p className="caption whitespace-pre-wrap text-body">
              {job.description || "No description captured."}
            </p>
          </Section>
        </div>

        <footer className="frosted flex items-center gap-2 border-t border-black/[0.08] bg-paper/80 px-6 py-3">
          <button
            type="button"
            data-testid="details-save"
            onClick={() => onSave(job.job_url)}
            className={`btn ${state === "saved" ? "btn-selected" : ""}`}
          >
            {state === "saved" ? "Saved ✓" : "Save"}
          </button>
          <button
            type="button"
            data-testid="details-ignore"
            onClick={() => onIgnore(job.job_url)}
            className="btn"
          >
            {state === "ignored" ? "Ignored" : "Ignore"}
          </button>
          <a
            href={job.job_url}
            target="_blank"
            rel="noopener noreferrer"
            data-testid="details-apply"
            className="btn-primary ml-auto"
          >
            Apply ↗
          </a>
        </footer>
      </aside>
    </>
  );
}
