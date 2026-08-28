import { useRef, useState } from "react";
import type { Company } from "../types/company";
import { parseCompaniesJson } from "../types/company";

interface Props {
  companies: Company[];
  enabled: Record<string, boolean>;
  onChangeEnabled: (name: string, value: boolean) => void;
  /** Enable or disable every company at once. A separate callback rather
   *  than a loop over onChangeEnabled: those calls all read the same state
   *  snapshot, so the last one would win and the rest would be lost. */
  onSetAllEnabled: (value: boolean) => void;
  onClear: () => void;
  onImport: (companies: Company[], errors: string[]) => void;
}

export function CompanyList({
  companies,
  enabled,
  onChangeEnabled,
  onSetAllEnabled,
  onClear,
  onImport,
}: Props) {
  const fileInput = useRef<HTMLInputElement>(null);
  // Clearing the list throws away an import; ask once rather than firing a
  // native confirm() dialog, which some embedded contexts suppress entirely.
  const [confirmingClear, setConfirmingClear] = useState(false);

  async function handleFile(file: File | undefined | null) {
    if (!file) return;
    const text = await file.text();
    const { companies: parsed, errors } = parseCompaniesJson(text);
    onImport(parsed, errors);
  }

  const enabledCount = companies.filter((c) => enabled[c.name] !== false).length;

  return (
    <section aria-label="Companies" data-testid="company-list" className="rail-section">
      <div className="flex items-center justify-between">
        <h2 className="rail-label">Companies</h2>
        <span
          className={`token ${companies.length === 0 ? "text-ink-faint" : "text-signal"}`}
          data-testid="enabled-count"
        >
          {companies.length === 0 ? "none imported" : `${enabledCount}/${companies.length} enabled`}
        </span>
      </div>

      {companies.length === 0 ? (
        <p className="mt-3 text-[12px] leading-relaxed text-ink-muted">
          Import a <code className="font-mono text-ink-text">companies.json</code> file to
          get started. See <code className="font-mono text-ink-text">companies.example.json</code>{" "}
          in the project root for the format.
        </p>
      ) : (
        <ul className="mt-3 max-h-64 overflow-y-auto">
          {companies.map((company) => {
            const isEnabled = enabled[company.name] !== false; // default on
            return (
              <li key={company.name}>
                <label className="flex cursor-pointer items-start gap-2.5 rounded-control px-1.5 py-2 transition-colors hover:bg-ink-raised">
                  <input
                    type="checkbox"
                    checked={isEnabled}
                    onChange={(e) => onChangeEnabled(company.name, e.target.checked)}
                    aria-label={`Enable ${company.name}`}
                    className="mt-0.5 h-3.5 w-3.5 shrink-0 rounded-sm border-ink-line bg-ink accent-signal"
                  />
                  <span className="min-w-0">
                    <span
                      className={`block truncate text-[13px] font-medium ${
                        isEnabled ? "text-ink-text" : "text-ink-faint line-through"
                      }`}
                    >
                      {company.name}
                    </span>
                    <span className="block truncate font-mono text-[10px] text-ink-faint">
                      {company.careers_url.replace(/^https?:\/\//, "")}
                    </span>
                  </span>
                </label>
              </li>
            );
          })}
        </ul>
      )}

      {companies.length > 0 && (
        <div className="mt-3 flex items-center gap-3">
          <button
            type="button"
            data-testid="select-all-companies"
            onClick={() => onSetAllEnabled(true)}
            disabled={enabledCount === companies.length}
            className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-faint underline underline-offset-2 transition-colors hover:text-ink-text disabled:no-underline disabled:opacity-40 disabled:hover:text-ink-faint"
          >
            Select all
          </button>
          <button
            type="button"
            data-testid="unselect-all-companies"
            onClick={() => onSetAllEnabled(false)}
            disabled={enabledCount === 0}
            className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-faint underline underline-offset-2 transition-colors hover:text-ink-text disabled:no-underline disabled:opacity-40 disabled:hover:text-ink-faint"
          >
            Unselect all
          </button>
        </div>
      )}

      <input
        ref={fileInput}
        type="file"
        accept=".json,application/json"
        className="hidden"
        data-testid="companies-file-input"
        onChange={(e) => handleFile(e.target.files?.[0])}
      />

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          data-testid="import-companies-button"
          onClick={() => fileInput.current?.click()}
          className="btn-rail"
        >
          {companies.length === 0 ? "Import companies.json" : "Import more"}
        </button>

        {companies.length > 0 &&
          (confirmingClear ? (
            <>
              <button
                type="button"
                data-testid="confirm-clear-companies"
                onClick={() => {
                  onClear();
                  setConfirmingClear(false);
                }}
                className="rounded-control border border-oxide px-3 py-2 text-[13px] font-medium text-oxide transition-colors hover:bg-oxide/10"
              >
                Delete {companies.length}
              </button>
              <button
                type="button"
                data-testid="cancel-clear-companies"
                onClick={() => setConfirmingClear(false)}
                className="btn-rail"
              >
                Cancel
              </button>
            </>
          ) : (
            <button
              type="button"
              data-testid="clear-companies-button"
              onClick={() => setConfirmingClear(true)}
              className="btn-rail"
            >
              Delete list
            </button>
          ))}
      </div>
    </section>
  );
}
