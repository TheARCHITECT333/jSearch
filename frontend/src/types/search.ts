import type { JobResult } from "./job";

export type LLMProvider = "ollama" | "openai-compatible";

/** How old a job posting may be. */
export type Freshness = "any" | "24h" | "3d" | "1w" | "2w" | "1m";

export const FRESHNESS_LABELS: Record<Freshness, string> = {
  any: "Any time",
  "24h": "Last 24 hours",
  "3d": "Last 3 days",
  "1w": "Last week",
  "2w": "Last 2 weeks",
  "1m": "Last month",
};

export interface LLMSettings {
  provider: LLMProvider;
  base_url: string;
  model: string;
}

export interface CompanyProgress {
  company: string;
  status: "pending" | "running" | "completed" | "failed";
  jobs_examined?: number;
  jobs_found?: number;
  message?: string | null;
}

export type SearchState = "queued" | "running" | "completed" | "failed" | "cancelled";

export interface SearchStatus {
  id: string;
  status: SearchState;
  companies: CompanyProgress[];
  results: JobResult[];
  error?: string | null;
}

/** Full request the frontend sends when starting a search. */
export interface StartSearchRequest {
  resume_latex: string;
  companies: { name: string; careers_url: string }[];
  freshness: Freshness;
  /** Target locations; empty means anywhere. */
  locations: string[];
  llm: {
    provider: LLMProvider;
    base_url: string;
    model: string;
    api_key?: string;
  };
}
