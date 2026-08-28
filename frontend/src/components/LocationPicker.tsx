import { useState } from "react";

interface Props {
  locations: string[];
  onChange: (locations: string[]) => void;
}

/** Chip-style editor for the search's target locations.
 * Empty list = anywhere. */
export function LocationPicker({ locations, onChange }: Props) {
  const [draft, setDraft] = useState("");

  function addLocation(raw: string) {
    const value = raw.trim().replace(/,+$/, "");
    if (!value) return;
    const exists = locations.some(
      (loc) => loc.toLowerCase() === value.toLowerCase()
    );
    if (!exists) onChange([...locations, value]);
    setDraft("");
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      addLocation(draft);
    } else if (e.key === "Backspace" && !draft && locations.length > 0) {
      onChange(locations.slice(0, -1));
    }
  }

  return (
    <section
      aria-label="Target locations"
      data-testid="location-picker"
      className="rail-section"
    >
      <div className="flex items-center justify-between">
        <h2 className="rail-label">Locations</h2>
        <span
          className={`token ${locations.length === 0 ? "text-ink-faint" : "text-signal"}`}
          data-testid="location-mode"
        >
          {locations.length === 0
            ? "searching anywhere"
            : `only ${locations.length} location${locations.length === 1 ? "" : "s"}`}
        </span>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-1.5 rounded-control border border-ink-line bg-ink p-1.5 transition-colors focus-within:border-signal">
        {locations.map((loc) => (
          <span
            key={loc}
            data-testid={`location-chip-${loc.toLowerCase().replace(/\s+/g, "-")}`}
            className="inline-flex items-center gap-1.5 rounded-[5px] bg-ink-raised px-2 py-1 font-mono text-[11px] text-ink-text"
          >
            {loc}
            <button
              type="button"
              aria-label={`Remove ${loc}`}
              onClick={() => onChange(locations.filter((l) => l !== loc))}
              className="text-ink-faint transition-colors hover:text-oxide"
            >
              ✕
            </button>
          </span>
        ))}
        <input
          value={draft}
          data-testid="location-input"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={() => addLocation(draft)}
          placeholder={
            locations.length === 0 ? "e.g. Bangalore, Remote — press Enter to add" : "Add another..."
          }
          aria-label="Add a target location"
          className="min-w-[8rem] flex-1 bg-transparent px-1 py-1 font-mono text-[12px] text-ink-text placeholder:text-ink-faint/70 focus:outline-none"
        />
      </div>

      <p className="mt-2 text-[11px] leading-relaxed text-ink-faint">
        Postings clearly located elsewhere are dropped before matching. Remote always
        fits. Empty searches everywhere.
      </p>
    </section>
  );
}
