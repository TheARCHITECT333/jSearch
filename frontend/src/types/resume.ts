/** Candidate profile extracted from the LaTeX resume. */

export interface Skills {
  languages: string[];
  frameworks: string[];
  databases: string[];
  cloud: string[];
  infrastructure: string[];
  tools: string[];
  other: string[];
}

export interface ExperienceItem {
  company?: string | null;
  title?: string | null;
  duration?: string | null;
  highlights?: string[];
}

export interface EducationItem {
  institution?: string | null;
  degree?: string | null;
  year?: string | null;
}

export interface CandidateProfile {
  name: string | null;
  summary: string | null;
  target_roles: string[];
  skills: Skills;
  experience: ExperienceItem[];
  education: EducationItem[];
  years_experience: number | null;
  preferred_locations: string[];
}

export function emptyProfile(): CandidateProfile {
  return {
    name: null,
    summary: null,
    target_roles: [],
    skills: {
      languages: [],
      frameworks: [],
      databases: [],
      cloud: [],
      infrastructure: [],
      tools: [],
      other: [],
    },
    experience: [],
    education: [],
    years_experience: null,
    preferred_locations: [],
  };
}

export type ScoreLevel = "junior" | "mid" | "senior";

export const SCORE_LEVEL_LABELS: Record<ScoreLevel, string> = {
  junior: "0–1 yrs",
  mid: "2–5 yrs",
  senior: "5+ yrs",
};

/** 0-1 years -> junior, 2-5 -> mid, more than 5 -> senior. Unknown -> junior. */
export function levelForYears(years: number | null | undefined): ScoreLevel {
  if (years == null || years <= 1) return "junior";
  return years <= 5 ? "mid" : "senior";
}

/** Rubric score from POST /api/score (ported from hiring-agent). */
export interface ResumeScore {
  level: ScoreLevel;
  total: number;
  base_max: number;
  categories: { key: string; label: string; score: number; max: number; evidence: string }[];
  bonus: { total: number; breakdown: string };
  deductions: { total: number; reasons: string };
  key_strengths: string[];
  areas_for_improvement: string[];
  github: {
    username: string;
    name: string | null;
    avatar_url: string | null;
    public_repos: number | null;
    followers: number | null;
  } | null;
}
