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
        <span className="eyebrow text-faint">{label}</span>
        <span
          className="font-mono text-[12px] font-medium text-ink"
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
      <h3 className="eyebrow text-faint">{title}</h3>
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
        className="fixed inset-0 z-40 bg-ink/40 backdrop-blur-[2px]"
      />
      <aside
        role="dialog"
        aria-label={`Job details: ${job.job_title}`}
        data-testid="job-details"
        className="fixed inset-y-0 right-0 z-50 flex w-full max-w-xl flex-col bg-paper shadow-2xl"
      >
        <header className="flex items-start justify-between gap-4 border-b border-edge bg-surface px-5 py-4">
          <div className="min-w-0">
            <h2 className="text-[18px] font-semibold tracking-tightest text-ink">
              {job.job_title}
            </h2>
            <p className="mt-0.5 font-mono text-[11px] text-faint">
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
            className="shrink-0 rounded-control border border-edge px-2 py-1 font-mono text-[12px] text-faint transition-colors hover:border-faint hover:text-ink"
          >
            Esc
          </button>
        </header>

        <div className="flex-1 space-y-5 overflow-y-auto px-5 py-5">
          {ruledOut && (
            <div className="rounded-card border border-oxide-line bg-oxide-soft p-4">
              <h3 className="eyebrow text-oxide">Ruled out by the posting</h3>
              <ul className="mt-2 space-y-1.5">
                {job.match.disqualifiers.map((reason) => (
                  <li key={reason} className="flex gap-2 text-[13px] leading-snug text-oxide">
                    <span aria-hidden className="font-mono">
                      ✕
                    </span>
                    {reason}
                  </li>
                ))}
              </ul>
              <p className="mt-3 text-[12px] leading-relaxed text-oxide/80">
                Postings overstate their requirements often enough to be worth a look
                anyway. This is a flag, not a lock.
              </p>
            </div>
          )}

          <div className="card p-4">
            <div className="flex items-end justify-between">
              <div>
                <span
                  className={`font-mono text-[38px] font-semibold leading-none tracking-tight ${
                    ruledOut ? "text-faint" : "text-signal"
                  }`}
                  data-testid="details-overall-score"
                >
                  {job.match.overall_score}%
                </span>
                <p className="eyebrow mt-1.5 text-faint">Overall fit</p>
              </div>
              <div className="text-right">
                <span className="font-mono text-[20px] font-semibold leading-none text-ink">
                  {job.match.keyword_coverage > 0 ? `${job.match.keyword_coverage}%` : "—"}
                </span>
                <p className="eyebrow mt-1.5 text-faint">Keywords verbatim</p>
              </div>
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              <ScoreRow label="Role fit" value={job.match.role_fit} />
              <ScoreRow label="Skill fit" value={job.match.skill_fit} />
              <ScoreRow label="Experience fit" value={job.match.experience_fit} />
              <ScoreRow label="Location fit" value={job.match.location_fit} />
            </div>

            {job.match.seniority_band && (
              <p className="mt-4 border-t border-edge pt-3 font-mono text-[11px] text-faint">
                Written for {job.match.seniority_band} level
                {job.match.required_years !== null &&
                job.match.required_years !== undefined
                  ? ` · asks for ${job.match.required_years}+ years`
                  : ""}
              </p>
            )}
          </div>

          {job.match.reason && (
            <p className="text-[14px] leading-relaxed text-body">{job.match.reason}</p>
          )}

          <div className="grid gap-5 sm:grid-cols-2">
            <Section title="Matching skills">
              <ul className="flex flex-wrap gap-1">
                {job.match.matching_skills.map((skill) => (
                  <li
                    key={skill}
                    className="rounded-[5px] bg-signal-soft px-1.5 py-0.5 font-mono text-[10px] text-signal"
                  >
                    {skill}
                  </li>
                ))}
                {job.match.matching_skills.length === 0 && (
                  <li className="text-[13px] text-faint">None listed</li>
                )}
              </ul>
            </Section>
            <Section title="Missing skills">
              <ul className="flex flex-wrap gap-1">
                {job.match.missing_skills.map((skill) => (
                  <li
                    key={skill}
                    className="rounded-[5px] border border-edge px-1.5 py-0.5 font-mono text-[10px] text-faint line-through"
                  >
                    {skill}
                  </li>
                ))}
                {job.match.missing_skills.length === 0 && (
                  <li className="text-[13px] text-faint">Nothing important missing</li>
                )}
              </ul>
            </Section>
          </div>

          {job.match.missing_keywords.length > 0 && (
            <Section title="In the posting, not in your resume">
              <ul className="flex flex-wrap gap-1">
                {job.match.missing_keywords.map((word) => (
                  <li
                    key={word}
                    className="rounded-[5px] border border-edge px-1.5 py-0.5 font-mono text-[10px] text-body"
                  >
                    {word}
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-[12px] leading-relaxed text-faint">
                A recruiter's search matches these literally. Worth adding wherever
                they are honestly true of your work.
              </p>
            </Section>
          )}

          {job.requirements.length > 0 && (
            <Section title="Requirements">
              <ul className="space-y-1.5">
                {job.requirements.map((req, index) => (
                  <li key={index} className="flex gap-2 text-[13px] leading-relaxed text-body">
                    <span aria-hidden className="font-mono text-faint">
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
                  <li key={index} className="flex gap-2 text-[13px] leading-relaxed text-body">
                    <span aria-hidden className="font-mono text-faint">
                      —
                    </span>
                    {qual}
                  </li>
                ))}
              </ul>
            </Section>
          )}

          <Section title="Description">
            <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-body">
              {job.description || "No description captured."}
            </p>
          </Section>
        </div>

        <footer className="flex items-center gap-2 border-t border-edge bg-surface px-5 py-3">
          <button
            type="button"
            data-testid="details-save"
            onClick={() => onSave(job.job_url)}
            className={`rounded-control border px-3 py-1.5 text-[13px] font-medium transition-colors ${
              state === "saved"
                ? "border-signal-line bg-signal-soft text-signal"
                : "border-edge text-body hover:border-faint hover:text-ink"
            }`}
          >
            {state === "saved" ? "Saved ✓" : "Save"}
          </button>
          <button
            type="button"
            data-testid="details-ignore"
            onClick={() => onIgnore(job.job_url)}
            className="rounded-control border border-edge px-3 py-1.5 text-[13px] font-medium text-body transition-colors hover:border-faint hover:text-ink"
          >
            {state === "ignored" ? "Ignored" : "Ignore"}
          </button>
          <a
            href={job.job_url}
            target="_blank"
            rel="noopener noreferrer"
            data-testid="details-apply"
            className="ml-auto rounded-control bg-ink px-4 py-1.5 text-[13px] font-semibold text-white transition-opacity hover:opacity-85"
          >
            Apply ↗
          </a>
        </footer>
      </aside>
    </>
  );
}
