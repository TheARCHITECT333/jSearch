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
  if (score >= 80) return "text-primary";
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
    <div className="flex items-center gap-3">
      <span className="token w-[64px] shrink-0 text-faint">{label}</span>
      <span className="meter-track flex-1">
        <span
          className={`meter-fill ${tone}`}
          style={{ width: unknown ? "0%" : `${Math.max(0, Math.min(100, value))}%` }}
        />
      </span>
      <span className="w-8 shrink-0 text-right text-[12px] font-semibold text-body">
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
      className={`cursor-pointer overflow-hidden rounded-lg border bg-surface transition-colors
        ${ruledOut ? "border-alert-line" : state === "saved" ? "border-primary" : "border-edge hover:border-[#c7c7cc]"}
        ${state === "ignored" ? "opacity-50" : ""}`}
    >
      <div className="p-6">
        <div className="flex items-start justify-between gap-5">
          <div className="min-w-0">
            <h3 className="truncate text-[21px] font-semibold leading-[1.19] text-ink">
              {job.job_title}
            </h3>
            <p className="caption mt-1 truncate text-faint">
              {job.company}
              {job.location ? ` · ${job.location}` : ""}
              {job.employment_type ? ` · ${job.employment_type}` : ""}
            </p>
          </div>
          <div
            data-testid="match-score"
            title={`${job.match.overall_score}% fit`}
            className={`shrink-0 font-display text-[34px] font-semibold leading-none tracking-hero ${scoreTone(
              job.match.overall_score,
              ruledOut
            )}`}
          >
            {job.match.overall_score}
            <span className="text-[17px]">%</span>
          </div>
        </div>

        {ruledOut ? (
          <ul data-testid="disqualifiers" className="mt-4 space-y-1">
            {job.match.disqualifiers.map((reason) => (
              <li key={reason} className="caption flex gap-2 text-alert">
                <span aria-hidden>✕</span>
                {reason}
              </li>
            ))}
          </ul>
        ) : (
          <div className="mt-5 space-y-2" data-testid="keyword-coverage">
            <Meter label="Fit" value={job.match.overall_score} tone="bg-primary" />
            <Meter
              label="Keywords"
              value={job.match.keyword_coverage}
              tone="bg-ink"
              unknown={job.match.keyword_coverage === 0}
            />
          </div>
        )}

        {(matching.length > 0 || job.match.missing_skills.length > 0) && (
          <div className="mt-4 flex flex-wrap gap-1.5">
            {matching.map((skill) => (
              <span key={skill} className="chip">
                {skill}
              </span>
            ))}
            {job.match.missing_skills.slice(0, 2).map((skill) => (
              <span key={skill} className="chip-muted line-through">
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
                className="link px-1 text-[12px]"
              >
                +{job.match.matching_skills.length - 4} more
              </button>
            )}
          </div>
        )}

        {job.match.reason && (
          <p className="mt-4 line-clamp-2 text-[17px] text-body">{job.match.reason}</p>
        )}

        {!ruledOut && job.match.missing_keywords.length > 0 && (
          <p
            title={`In the posting, not in your resume: ${job.match.missing_keywords.join(", ")}`}
            data-testid="missing-keywords"
            className="token mt-2 truncate text-faint"
          >
            Missing from resume: {job.match.missing_keywords.slice(0, 5).join(", ")}
          </p>
        )}
      </div>

      <div
        className="flex items-center gap-2 border-t border-divider px-6 py-4"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          data-testid="save-button"
          onClick={onSave}
          aria-pressed={state === "saved"}
          className={`btn ${state === "saved" ? "btn-selected" : ""}`}
        >
          {state === "saved" ? "Saved ✓" : "Save"}
        </button>
        <button
          type="button"
          data-testid="ignore-button"
          onClick={onIgnore}
          aria-pressed={state === "ignored"}
          className="btn"
        >
          {state === "ignored" ? "Ignored" : "Ignore"}
        </button>
        <a
          href={job.job_url}
          target="_blank"
          rel="noopener noreferrer"
          data-testid="apply-link"
          className="btn-primary-sm ml-auto"
        >
          Apply ↗
        </a>
      </div>
    </article>
  );
}
