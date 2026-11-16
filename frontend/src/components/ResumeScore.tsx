import {
  SCORE_LEVEL_LABELS,
  type ResumeScore as Score,
  type ScoreLevel,
} from "../types/resume";

interface Props {
  level: ScoreLevel;
  onLevelChange: (level: ScoreLevel) => void;
  score: Score | null;
  scoring: boolean;
  error: string | null;
  disabledReasons: string[];
  onScore: () => void;
}

function Notes({ title, tone, children }: { title: string; tone: string; children: React.ReactNode }) {
  return (
    <div>
      <p className={`text-[17px] font-semibold ${tone}`}>{title}</p>
      <div className="caption mt-2 text-body">{children}</div>
    </div>
  );
}

/** How a recruiter's rubric reads the resume - independent of any one job. */
export function ResumeScore({
  level,
  onLevelChange,
  score,
  scoring,
  error,
  disabledReasons,
  onScore,
}: Props) {
  const disabled = scoring || disabledReasons.length > 0;

  return (
    <>
      <div className="card p-6">
        <div className="flex flex-wrap items-center gap-4">
          <button
            type="button"
            data-testid="score-button"
            onClick={onScore}
            disabled={disabled}
            className="btn-primary"
          >
            {scoring && (
              <span
                aria-hidden
                className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white"
              />
            )}
            {scoring ? "Scoring..." : score ? "Score again" : "Score resume"}
          </button>
          <label className="flex items-center gap-2">
            <span className="caption text-faint">Experience</span>
            <select
              value={level}
              onChange={(e) => onLevelChange(e.target.value as ScoreLevel)}
              disabled={scoring}
              aria-label="Experience level for scoring"
              data-testid="level-select"
              className="control disabled:opacity-40"
            >
              {(Object.keys(SCORE_LEVEL_LABELS) as ScoreLevel[]).map((key) => (
                <option key={key} value={key}>
                  {SCORE_LEVEL_LABELS[key]}
                </option>
              ))}
            </select>
          </label>
        </div>
        <p className="caption mt-4 text-faint">
          Open source, projects, production experience and skills, weighted for your
          level. Reads your public GitHub if the resume links it.
        </p>
        {!scoring && disabledReasons.length > 0 && (
          <ul className="mt-4 space-y-1.5 border-t border-divider pt-4">
            {disabledReasons.map((reason) => (
              <li key={reason} className="caption flex gap-2 text-body">
                <span aria-hidden className="text-faint">
                  →
                </span>
                {reason}
              </li>
            ))}
          </ul>
        )}
        {error && (
          <p role="alert" className="caption mt-4 text-alert">
            {error}
          </p>
        )}
      </div>

      {score && (
        <div className="card rise p-6 sm:p-10" data-testid="score-report">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="font-display text-[80px] font-semibold leading-none tracking-hero text-ink">
                {score.total}
                <span className="text-[28px] font-normal text-faint"> / {score.base_max}</span>
              </p>
              <p className="caption mt-3 text-faint">
                Scored as {SCORE_LEVEL_LABELS[score.level]}
              </p>
            </div>
            {score.github && (
              <a
                href={`https://github.com/${score.github.username}`}
                target="_blank"
                rel="noreferrer"
                className="link caption"
              >
                github.com/{score.github.username} · {score.github.public_repos ?? 0} repos ·{" "}
                {score.github.followers ?? 0} followers ↗
              </a>
            )}
          </div>

          <ul className="mt-10 space-y-7">
            {score.categories.map((cat) => (
              <li key={cat.key}>
                <div className="flex items-baseline justify-between gap-4">
                  <span className="text-[17px] font-semibold text-ink">{cat.label}</span>
                  <span className="text-[17px] text-body">
                    {cat.score}
                    <span className="text-faint"> / {cat.max}</span>
                  </span>
                </div>
                <span className="meter-track mt-2.5 block">
                  <span
                    className="meter-fill bg-primary"
                    style={{ width: `${(cat.score / cat.max) * 100}%` }}
                  />
                </span>
                <p className="caption mt-2.5 text-body">{cat.evidence}</p>
              </li>
            ))}
          </ul>

          <div className="mt-10 grid gap-8 border-t border-divider pt-8 sm:grid-cols-2">
            <Notes title={`+${score.bonus.total} bonus`} tone="text-primary">
              {score.bonus.breakdown || "None."}
            </Notes>
            <Notes title={`−${score.deductions.total} deductions`} tone="text-ink">
              {score.deductions.reasons || "None."}
            </Notes>
            <Notes title="Strengths" tone="text-ink">
              <ul className="list-disc space-y-1 pl-4">
                {score.key_strengths.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </Notes>
            <Notes title="To improve" tone="text-ink">
              <ul className="list-disc space-y-1 pl-4">
                {score.areas_for_improvement.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </Notes>
          </div>
        </div>
      )}
    </>
  );
}
