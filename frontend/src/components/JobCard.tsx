import { useState } from "react";
import { isRuledOut, type JobResult } from "../types/job";

interface Props {
  job: JobResult;
  state?: "saved" | "ignored";
  onSave: () => void;
  onIgnore: () => void;
  onOpenDetails: () => void;
}

function scoreTone(score: number, ruledOut: boolean): string {
  // A job you are barred from never gets a confident colour, however well
  // you would have fitted it.
  if (ruledOut) return "text-faint";
  if (score >= 80) return "text-signal";
  if (score >= 60) return "text-ink";
  return "text-faint";
}

/** The signature: two independent measurements, stacked and aligned.
 *
 * Fit is the model's judgement of whether you'd do well here. Coverage is
 * the dumb literal count of the posting's own words that appear in your
 * resume. They answer different questions and routinely disagree - a high
 * fit with low coverage means "good job, wrong words on the page" - so the
 * card shows them together rather than averaging them into one number.
 */
function Meter({
  label,
  value,
  tone,
  unknown = false,
}: {
  label: string;
  value: number;
  tone: string;
  unknown?: boolean;
}) {
  return (
    <div className="flex items-center gap-2.5">
      <span className="eyebrow w-[62px] shrink-0 text-faint">{label}</span>
      <span className="meter-track flex-1">
        <span
          className={`meter-fill ${tone}`}
          style={{ width: unknown ? "0%" : `${Math.max(0, Math.min(100, value))}%` }}
        />
      </span>
      <span className="w-7 shrink-0 text-right font-mono text-[11px] font-medium text-body">
        {unknown ? "—" : value}
      </span>
    </div>
  );
}

export function JobCard({ job, state, onSave, onIgnore, onOpenDetails }: Props) {
  const [expandedSkills, setExpandedSkills] = useState(false);
  const ruledOut = isRuledOut(job);
  const matching = expandedSkills
    ? job.match.matching_skills
    : job.match.matching_skills.slice(0, 4);

  return (
    <article
      data-testid="job-card"
      data-job-url={job.job_url}
      onClick={onOpenDetails}
      className={`group cursor-pointer rounded-card border bg-surface transition-all
        hover:-translate-y-px hover:shadow-[0_2px_12px_rgba(16,20,24,0.07)]
        ${ruledOut ? "border-l-2 border-l-oxide border-y-edge border-r-edge" : "border-edge"}
        ${state === "saved" ? "ring-1 ring-signal" : ""}
        ${state === "ignored" ? "opacity-45" : ""}`}
    >
      <div className="p-4">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h3 className="truncate text-[15px] font-semibold tracking-tightest text-ink">
              {job.job_title}
            </h3>
            <p className="mt-0.5 truncate font-mono text-[11px] text-faint">
              {job.company}
              {job.location ? ` · ${job.location}` : ""}
              {job.employment_type ? ` · ${job.employment_type}` : ""}
            </p>
          </div>
          <div
            data-testid="match-score"
            title={`${job.match.overall_score}% fit`}
            className={`shrink-0 font-mono text-[26px] font-semibold leading-none tracking-tight ${scoreTone(
              job.match.overall_score,
              ruledOut
            )}`}
          >
            {job.match.overall_score}
            <span className="text-[13px] font-medium">%</span>
          </div>
        </div>

        {ruledOut ? (
          <ul
            data-testid="disqualifiers"
            className="mt-3 space-y-1 rounded-control border border-oxide-line bg-oxide-soft px-3 py-2"
          >
            {job.match.disqualifiers.map((reason) => (
              <li key={reason} className="flex gap-2 text-[12px] leading-snug text-oxide">
                <span aria-hidden className="font-mono">
                  ✕
                </span>
                {reason}
              </li>
            ))}
          </ul>
        ) : (
          <div className="mt-3.5 space-y-1.5" data-testid="keyword-coverage">
            <Meter label="Fit" value={job.match.overall_score} tone="bg-signal" />
            <Meter
              label="Keywords"
              value={job.match.keyword_coverage}
              tone="bg-ink"
              unknown={job.match.keyword_coverage === 0}
            />
          </div>
        )}

        {(matching.length > 0 || job.match.missing_skills.length > 0) && (
          <div className="mt-3 flex flex-wrap gap-1">
            {matching.map((skill) => (
              <span
                key={skill}
                className="rounded-[5px] bg-signal-soft px-1.5 py-0.5 font-mono text-[10px] text-signal"
              >
                {skill}
              </span>
            ))}
            {job.match.missing_skills.slice(0, 2).map((skill) => (
              <span
                key={skill}
                className="rounded-[5px] border border-edge px-1.5 py-0.5 font-mono text-[10px] text-faint line-through"
              >
                {skill}
              </span>
            ))}
            {job.match.matching_skills.length > 4 && !expandedSkills && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  setExpandedSkills(true);
                }}
                className="rounded-[5px] px-1.5 py-0.5 font-mono text-[10px] text-faint underline underline-offset-2 hover:text-ink"
              >
                +{job.match.matching_skills.length - 4} more
              </button>
            )}
          </div>
        )}

        {job.match.reason && (
          <p className="mt-3 line-clamp-2 text-[13px] leading-relaxed text-body">
            {job.match.reason}
          </p>
        )}

        {!ruledOut && job.match.missing_keywords.length > 0 && (
          <p
            title={`In the posting, not in your resume: ${job.match.missing_keywords.join(", ")}`}
            data-testid="missing-keywords"
            className="mt-2 truncate font-mono text-[10px] text-faint"
          >
            missing from resume: {job.match.missing_keywords.slice(0, 5).join(", ")}
          </p>
        )}
      </div>

      <div
        className="flex items-center gap-2 border-t border-edge px-4 py-2.5"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          data-testid="save-button"
          onClick={onSave}
          aria-pressed={state === "saved"}
          className={`rounded-control border px-2.5 py-1 text-[12px] font-medium transition-colors ${
            state === "saved"
              ? "border-signal-line bg-signal-soft text-signal"
              : "border-edge text-body hover:border-faint hover:text-ink"
          }`}
        >
          {state === "saved" ? "Saved ✓" : "Save"}
        </button>
        <button
          type="button"
          data-testid="ignore-button"
          onClick={onIgnore}
          aria-pressed={state === "ignored"}
          className="rounded-control border border-edge px-2.5 py-1 text-[12px] font-medium text-body transition-colors hover:border-faint hover:text-ink"
        >
          {state === "ignored" ? "Ignored" : "Ignore"}
        </button>
        <a
          href={job.job_url}
          target="_blank"
          rel="noopener noreferrer"
          data-testid="apply-link"
          className="ml-auto rounded-control bg-ink px-3 py-1 text-[12px] font-semibold text-white transition-opacity hover:opacity-85"
        >
          Apply ↗
        </a>
      </div>
    </article>
  );
}
