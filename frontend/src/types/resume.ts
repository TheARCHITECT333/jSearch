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
