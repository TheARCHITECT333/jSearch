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
  completed: "text-signal",
  failed: "text-oxide",
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
      <div className="flex items-center justify-between border-b border-edge px-4 py-3">
        <h2 className="flex items-center gap-2 text-[13px] font-semibold tracking-tight text-ink">
          {state === "running" && (
            <span
              aria-hidden
              className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-edge border-t-signal"
            />
          )}
          {HEADING[state] ?? "Search failed"}
        </h2>
        {companies.length > 0 && (
          <span className="token text-faint">
            {settled}/{companies.length} sites
          </span>
        )}
      </div>

      {state === "queued" && (
        <p className="px-4 py-3 text-[12px] text-body">
          Waiting for a free search slot...
        </p>
      )}

      {error && (
        <p className="border-b border-oxide-line bg-oxide-soft px-4 py-3 text-[13px] leading-relaxed text-oxide">
          {error}
        </p>
      )}

      {companies.length > 0 && (
        <ul className="divide-y divide-edge">
          {companies.map((progress) => (
            <li
              key={progress.company}
              data-testid={`company-progress-${progress.company}`}
              className="flex gap-3 px-4 py-2.5"
            >
              <span
                aria-hidden
                className={`mt-px w-3 shrink-0 text-center font-mono text-[12px] ${TONE[progress.status]} ${
                  progress.status === "running" ? "animate-pulse" : ""
                }`}
              >
                {GLYPH[progress.status]}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-3">
                  <span
                    className={`truncate text-[13px] font-medium ${
                      progress.status === "pending" ? "text-faint" : "text-ink"
                    }`}
                  >
                    {progress.company}
                  </span>
                  {progress.status === "completed" && (
                    <span className="shrink-0 font-mono text-[11px] text-signal">
                      {progress.jobs_found ?? 0} kept
                    </span>
                  )}
                </div>
                <div
                  className="truncate font-mono text-[11px] text-faint"
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
