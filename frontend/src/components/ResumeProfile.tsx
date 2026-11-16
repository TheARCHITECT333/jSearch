import { useState } from "react";
import type { CandidateProfile } from "../types/resume";

interface Props {
  profile: CandidateProfile | null;
  extracting: boolean;
  error: string | null;
  onEdit: (profile: CandidateProfile) => void;
}

function joinList(items: string[]): string {
  return items.join(", ");
}

function splitList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function ResumeProfile({ profile, extracting, error, onEdit }: Props) {
  const [editing, setEditing] = useState(false);
  const [showAllSkills, setShowAllSkills] = useState(false);
  const [draft, setDraft] = useState({
    roles: "",
    locations: "",
    years: "",
  });

  if (extracting) {
    return (
      <section className="rail-section">
        <h2 className="rail-label">Profile</h2>
        <p className="mt-3 flex items-center gap-2 text-[14px] tracking-caption text-ink-muted">
          <span
            aria-hidden
            className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-ink-line border-t-primary-dark"
          />
          Extracting your profile with the LLM...
        </p>
      </section>
    );
  }

  if (error) {
    return (
      <section className="rail-section">
        <h2 className="rail-label !text-alert-dark">Profile extraction failed</h2>
        <p className="mt-2 text-[14px] leading-[1.43] tracking-caption text-alert-dark">
          {error}
        </p>
      </section>
    );
  }

  if (!profile) return null;

  const skillGroups: [string, string[]][] = [
    ["Languages", profile.skills.languages],
    ["Frameworks", profile.skills.frameworks],
    ["Databases", profile.skills.databases],
    ["Cloud", profile.skills.cloud],
    ["Infrastructure", profile.skills.infrastructure],
    ["Tools", profile.skills.tools],
    ["Other", profile.skills.other],
  ];
  const allSkills = skillGroups.flatMap(([, items]) => items);

  function startEditing() {
    setDraft({
      roles: joinList(profile?.target_roles ?? []),
      locations: joinList(profile?.preferred_locations ?? []),
      years:
        profile?.years_experience === null || profile?.years_experience === undefined
          ? ""
          : String(profile.years_experience),
    });
    setEditing(true);
  }

  function saveEdits() {
    if (!profile) return;
    const years = draft.years.trim();
    onEdit({
      ...profile,
      target_roles: splitList(draft.roles),
      preferred_locations: splitList(draft.locations),
      years_experience: years
        ? Math.max(0, Math.min(60, Number(years) || 0))
        : null,
    });
    setEditing(false);
  }

  if (editing) {
    return (
      <section className="rail-section" data-testid="profile-editor">
        <h2 className="rail-label">Edit profile</h2>
        <div className="mt-3 space-y-3">
          <label className="block">
            <span className="rail-label mb-1 block">Target roles (comma-separated)</span>
            <input
              value={draft.roles}
              onChange={(e) => setDraft({ ...draft, roles: e.target.value })}
              className="field"
            />
          </label>
          <label className="block">
            <span className="rail-label mb-1 block">Locations (comma-separated)</span>
            <input
              value={draft.locations}
              onChange={(e) => setDraft({ ...draft, locations: e.target.value })}
              className="field"
            />
          </label>
          <label className="block">
            <span className="rail-label mb-1 block">Years of experience</span>
            <input
              type="number"
              min={0}
              max={60}
              value={draft.years}
              onChange={(e) => setDraft({ ...draft, years: e.target.value })}
              className="field"
            />
          </label>
        </div>
        <div className="mt-3 flex gap-2">
          <button type="button" onClick={saveEdits} className="btn-rail-primary">
            Save profile
          </button>
          <button
            type="button"
            onClick={() => setEditing(false)}
            className="btn-rail"
          >
            Cancel
          </button>
        </div>
      </section>
    );
  }

  return (
    <section data-testid="candidate-profile" className="rail-section">
      <div className="flex items-center justify-between">
        <h2 className="rail-label">Profile</h2>
        <button
          type="button"
          onClick={startEditing}
          className="rail-link"
        >
          Edit profile
        </button>
      </div>

      {profile.name && (
        <p className="mt-3 text-[21px] font-semibold leading-[1.19] text-ink-text">
          {profile.name}
        </p>
      )}

      <dl className="mt-3 space-y-3">
        <div>
          <dt className="rail-label">Target roles</dt>
          <dd data-testid="target-roles" className="mt-1 flex flex-wrap gap-1">
            {profile.target_roles.length
              ? profile.target_roles.map((role) => (
                  <span
                    key={role}
                    className="rounded-pill bg-ink-raised px-3 py-1 text-[12px] tracking-fine text-ink-text"
                  >
                    {role}
                  </span>
                ))
              : <span className="text-[12px] text-ink-faint">—</span>}
          </dd>
        </div>

        <div className="flex gap-6">
          <div>
            <dt className="rail-label">Experience</dt>
            <dd data-testid="experience" className="mt-1 text-[14px] tracking-caption text-ink-text">
              {profile.years_experience !== null
                ? `${profile.years_experience} year${profile.years_experience === 1 ? "" : "s"}`
                : "—"}
            </dd>
          </div>
          <div className="min-w-0">
            <dt className="rail-label">Resume locations</dt>
            <dd
              data-testid="locations"
              className="mt-1 truncate text-[14px] tracking-caption text-ink-text"
            >
              {profile.preferred_locations.length
                ? profile.preferred_locations.join(" · ")
                : "—"}
            </dd>
          </div>
        </div>

        <div>
          <dt className="rail-label">
            Skills{" "}
            <span className="tracking-normal text-ink-faint">({allSkills.length})</span>
          </dt>
          <dd data-testid="skills" className="mt-1">
            {allSkills.length ? (
              <>
                <span
                  className={`block text-[14px] leading-[1.43] tracking-caption text-ink-muted ${
                    showAllSkills ? "" : "line-clamp-2"
                  }`}
                >
                  {allSkills.join(" · ")}
                </span>
                {allSkills.length > 12 && (
                  <button
                    type="button"
                    onClick={() => setShowAllSkills((v) => !v)}
                    className="rail-link mt-1"
                  >
                    {showAllSkills ? "Show fewer" : "Show all"}
                  </button>
                )}
              </>
            ) : (
              <span className="text-[12px] text-ink-faint">—</span>
            )}
          </dd>
        </div>
      </dl>
    </section>
  );
}
