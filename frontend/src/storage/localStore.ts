/**
 * Browser-owned persistence.
 *
 * Everything the app remembers lives in localStorage. The LLM API key is
 * NEVER persisted - it stays in React memory only and is sent solely when
 * starting a search or extracting a profile.
 */

import { useSyncExternalStore } from "react";
import type { Company } from "../types/company";
import type { CandidateProfile } from "../types/resume";
import type { JobResult, JobStateMap } from "../types/job";
import type { Freshness, LLMProvider } from "../types/search";

const KEYS = {
  resumeLatex: "jobhunter.resumeLatex",
  candidateProfile: "jobhunter.candidateProfile",
  companies: "jobhunter.companies",
  companyEnabled: "jobhunter.companyEnabled",
  llmProvider: "jobhunter.llmProvider",
  llmBaseUrl: "jobhunter.llmBaseUrl",
  llmModel: "jobhunter.llmModel",
  freshness: "jobhunter.freshness",
  searchLocations: "jobhunter.searchLocations",
  latestResults: "jobhunter.latestResults",
  savedJobs: "jobhunter.savedJobs",
  ignoredJobs: "jobhunter.ignoredJobs",
} as const;

export interface AppState {
  resumeLatex: string | null;
  candidateProfile: CandidateProfile | null;
  companies: Company[];
  companyEnabled: Record<string, boolean>;
  llmProvider: LLMProvider;
  llmBaseUrl: string;
  llmModel: string;
  freshness: Freshness;
  searchLocations: string[];
  latestResults: JobResult[];
  savedJobs: JobStateMap; // job_url -> "saved"
  ignoredJobs: JobStateMap; // job_url -> "ignored"
}

function load<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    if (raw === null) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

function readState(): AppState {
  return {
    resumeLatex: load<string | null>(KEYS.resumeLatex, null),
    candidateProfile: load<CandidateProfile | null>(KEYS.candidateProfile, null),
    companies: load<Company[]>(KEYS.companies, []),
    companyEnabled: load<Record<string, boolean>>(KEYS.companyEnabled, {}),
    llmProvider: load<LLMProvider>(KEYS.llmProvider, "ollama"),
    llmBaseUrl: load<string>(KEYS.llmBaseUrl, ""),
    llmModel: load<string>(KEYS.llmModel, ""),
    freshness: load<Freshness>(KEYS.freshness, "1w"),
    searchLocations: load<string[]>(KEYS.searchLocations, []),
    latestResults: load<JobResult[]>(KEYS.latestResults, []),
    savedJobs: load<JobStateMap>(KEYS.savedJobs, {}),
    ignoredJobs: load<JobStateMap>(KEYS.ignoredJobs, {}),
  };
}

let state: AppState = typeof window === "undefined" ? ({} as AppState) : readState();
const listeners = new Set<() => void>();

function persist(state: AppState): void {
  const put = (key: string, value: unknown) => {
    try {
      window.localStorage.setItem(key, JSON.stringify(value));
    } catch {
      // Storage full / disabled: keep working in memory for this session.
    }
  };
  put(KEYS.resumeLatex, state.resumeLatex);
  put(KEYS.candidateProfile, state.candidateProfile);
  put(KEYS.companies, state.companies);
  put(KEYS.companyEnabled, state.companyEnabled);
  put(KEYS.llmProvider, state.llmProvider);
  put(KEYS.llmBaseUrl, state.llmBaseUrl);
  put(KEYS.llmModel, state.llmModel);
  put(KEYS.freshness, state.freshness);
  put(KEYS.searchLocations, state.searchLocations);
  put(KEYS.latestResults, state.latestResults);
  put(KEYS.savedJobs, state.savedJobs);
  put(KEYS.ignoredJobs, state.ignoredJobs);
}

export const store = {
  get(): AppState {
    return state;
  },

  set(patch: Partial<AppState>): void {
    state = { ...state, ...patch };
    persist(state);
    listeners.forEach((listener) => listener());
  },

  subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
};

export function useAppState(): [AppState, (patch: Partial<AppState>) => void] {
  const snapshot = useSyncExternalStore(store.subscribe, store.get);
  return [snapshot, store.set];
}
