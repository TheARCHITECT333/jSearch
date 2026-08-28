import { FRESHNESS_LABELS, type Freshness } from "../types/search";

interface Props {
  disabledReasons: string[];
  running: boolean;
  freshness: Freshness;
  onFreshnessChange: (value: Freshness) => void;
  onStart: () => void;
}

export function SearchButton({
  disabledReasons,
  running,
  freshness,
  onFreshnessChange,
  onStart,
}: Props) {
  const disabled = running || disabledReasons.length > 0;

  return (
    <div className="card p-4">
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          data-testid="find-jobs-button"
          onClick={onStart}
          disabled={disabled}
          className="rounded-control bg-ink px-6 py-2.5 text-[14px] font-semibold tracking-tight
                     text-white transition-opacity hover:opacity-85
                     disabled:cursor-not-allowed disabled:opacity-25"
        >
          {running ? (
            <span className="flex items-center gap-2">
              <span
                aria-hidden
                className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/30 border-t-white"
              />
              Searching...
            </span>
          ) : (
            "Find jobs"
          )}
        </button>

        <label className="flex items-center gap-2">
          <span className="eyebrow text-faint">Posted within</span>
          <select
            value={freshness}
            onChange={(e) => onFreshnessChange(e.target.value as Freshness)}
            disabled={running}
            aria-label="Job posting age limit"
            data-testid="freshness-select"
            className="rounded-control border border-edge bg-surface px-2.5 py-1.5 font-mono text-[12px] text-ink
                       transition-colors hover:border-faint disabled:opacity-40"
          >
            {(Object.keys(FRESHNESS_LABELS) as Freshness[]).map((key) => (
              <option key={key} value={key}>
                {FRESHNESS_LABELS[key]}
              </option>
            ))}
          </select>
        </label>
      </div>

      {disabledReasons.length > 0 && !running && (
        <ul
          className="mt-3 space-y-1 border-t border-edge pt-3"
          data-testid="disabled-reasons"
        >
          {disabledReasons.map((reason) => (
            <li key={reason} className="flex gap-2 text-[12px] text-body">
              <span aria-hidden className="font-mono text-faint">
                →
              </span>
              {reason}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
