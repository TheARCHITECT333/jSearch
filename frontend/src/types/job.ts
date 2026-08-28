export interface MatchResult {
  overall_score: number;
  role_fit: number;
  skill_fit: number;
  experience_fit: number;
  location_fit: number;
  matching_skills: string[];
  missing_skills: string[];
  reason: string;

  /** Hard bars the posting states and this candidate fails. Empty = eligible. */
  disqualifiers: string[];
  seniority_band?: string | null;
  required_years?: number | null;

  /** Literal resume-vs-posting word overlap. 0 can mean "nothing to check". */
  keyword_coverage: number;
  missing_keywords: string[];
}

export interface JobResult {
  company: string;
  company_url?: string | null;
  careers_url?: string | null;

  job_title: string;
  job_url: string;

  location?: string | null;
  employment_type?: string | null;

  description: string;
  requirements: string[];
  preferred_qualifications: string[];

  match: MatchResult;
}

/** A stated hard requirement this candidate fails - shown apart, never ranked. */
export function isRuledOut(job: JobResult): boolean {
  return (job.match.disqualifiers?.length ?? 0) > 0;
}

/** job_url -> state */
export type JobStateMap = Record<string, "saved" | "ignored">;
