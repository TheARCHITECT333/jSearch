import type { CompanyProgress, SearchState } from "../types/search";

interface Props {
  state: SearchState | null;
  companies: CompanyProgress[];
  error: string | null;
}

const GLYPH: Record<CompanyProgress["status"], string> = {
  pending: "·",
  running: "▶",
  completed: "✓",
  failed: "✕",
};

const TONE: Record<CompanyProgress["status"], string> = {
  pending: "text-faint",
  running: "text-ink",
  completed: "text-primary",
  failed: "text-alert",
};

const HEADING: Record<SearchState, string> = {
  queued: "Queued...",
  running: "Searching...",
  completed: "Search complete",
  cancelled: "Search cancelled",
  failed: "Search failed",
};

export function SearchProgress({ state, companies, error }: Props) {
  if (!state) return null;

  const settled = companies.filter(
    (c) => c.status === "completed" || c.status === "failed"
  ).length;

  return (
    <section
      aria-label="Search progress"
      data-testid="search-progress"
      className="card overflow-hidden"
    >
      <div className="flex items-center justify-between border-b border-divider px-6 py-4">
        <h2 className="flex items-center gap-2.5 text-[17px] font-semibold text-ink">
          {state === "running" && (
            <span
              aria-hidden
              className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-edge border-t-primary"
            />
          )}
          {HEADING[state] ?? "Search failed"}
        </h2>
        {companies.length > 0 && (
          <span className="caption text-faint">
            {settled}/{companies.length} sites
          </span>
        )}
      </div>

      {state === "queued" && (
        <p className="caption px-6 py-4 text-body">
          Waiting for a free search slot...
        </p>
      )}

      {error && (
        <p className="caption border-b border-alert-line bg-alert-soft px-6 py-4 text-alert">
          {error}
        </p>
      )}

      {companies.length > 0 && (
        <ul className="divide-y divide-divider">
          {companies.map((progress) => (
            <li
              key={progress.company}
              data-testid={`company-progress-${progress.company}`}
              className="flex gap-3 px-6 py-3"
            >
              <span
                aria-hidden
                className={`mt-0.5 w-3 shrink-0 text-center text-[14px] ${TONE[progress.status]} ${
                  progress.status === "running" ? "animate-pulse" : ""
                }`}
              >
                {GLYPH[progress.status]}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-3">
                  <span
                    className={`truncate text-[14px] font-semibold tracking-caption ${
                      progress.status === "pending" ? "text-faint" : "text-ink"
                    }`}
                  >
                    {progress.company}
                  </span>
                  {progress.status === "completed" && (
                    <span className="caption shrink-0 text-primary">
                      {progress.jobs_found ?? 0} kept
                    </span>
                  )}
                </div>
                <div
                  className="token truncate text-faint"
                  data-testid={`company-detail-${progress.company}`}
                >
                  {progress.status === "completed" && (
                    <>
                      {progress.jobs_examined ?? 0} jobs examined ·{" "}
                      {progress.jobs_found ?? 0} relevant jobs
                      {progress.message ? ` · ${progress.message}` : ""}
                    </>
                  )}
                  {progress.status === "failed" &&
                    (progress.message || "Career site could not be navigated.")}
                  {progress.status === "running" &&
                    (progress.message || "Browsing careers site...")}
                  {progress.status === "pending" && "Waiting..."}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
