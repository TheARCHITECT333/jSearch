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
    <div className="card p-6">
      <div className="flex flex-wrap items-center gap-4">
        <button
          type="button"
          data-testid="find-jobs-button"
          onClick={onStart}
          disabled={disabled}
          className="btn-primary"
        >
          {running ? (
            <span className="flex items-center gap-2">
              <span
                aria-hidden
                className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white"
              />
              Searching...
            </span>
          ) : (
            "Find jobs"
          )}
        </button>

        <label className="flex items-center gap-2">
          <span className="caption text-faint">Posted within</span>
          <select
            value={freshness}
            onChange={(e) => onFreshnessChange(e.target.value as Freshness)}
            disabled={running}
            aria-label="Job posting age limit"
            data-testid="freshness-select"
            className="control disabled:opacity-40"
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
          className="mt-5 space-y-1.5 border-t border-divider pt-4"
          data-testid="disabled-reasons"
        >
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
    </div>
  );
}
