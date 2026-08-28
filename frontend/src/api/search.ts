import { apiGet, apiPost, API_BASE } from "./client";
import type {
  LLMSettings,
  SearchStatus,
  StartSearchRequest,
} from "../types/search";
import type { CandidateProfile } from "../types/resume";

export async function extractProfile(
  resumeLatex: string,
  llm: LLMSettings & { api_key?: string }
): Promise<CandidateProfile> {
  const response = await apiPost<{ profile: CandidateProfile }>("/api/profile", {
    resume_latex: resumeLatex,
    llm,
  });
  return response.profile;
}

export async function startSearch(
  request: StartSearchRequest
): Promise<string> {
  const response = await apiPost<{ search_id: string }>(
    "/api/search",
    request
  );
  return response.search_id;
}

export function getSearch(searchId: string): Promise<SearchStatus> {
  return apiGet<SearchStatus>(`/api/search/${searchId}`);
}

export interface StreamHandlers {
  /** Called for every progress snapshot from the server. */
  onUpdate: (status: SearchStatus) => void;
  /** Called when SSE fails (proxy issues, disconnect before terminal);
   * the caller should fall back to polling. */
  onFallback?: () => void;
}

/** A search in any of these states will never produce another frame. */
const TERMINAL_STATES: ReadonlySet<SearchStatus["status"]> = new Set([
  "completed",
  "failed",
  "cancelled",
]);

/**
 * Subscribe to live search progress over Server-Sent Events.
 * Returns a close() function. Terminal states close the stream themselves.
 */
export function streamSearchProgress(
  searchId: string,
  handlers: StreamHandlers
): () => void {
  let gotTerminal = false;
  let receivedAny = false;

  const source = new EventSource(`${API_BASE}/api/search/${searchId}/events`);

  source.onmessage = (event) => {
    receivedAny = true;
    try {
      const status = JSON.parse(event.data) as SearchStatus;
      handlers.onUpdate(status);
      if (TERMINAL_STATES.has(status.status)) {
        gotTerminal = true;
        source.close();
      }
    } catch {
      // Malformed frame: ignore; heartbeats/comments don't reach onmessage.
    }
  };

  // The backend sends `event: gone` when a search vanished mid-stream (e.g.
  // it was pruned after a restart). Polling will surface the real 404.
  source.addEventListener("gone", () => {
    source.close();
    handlers.onFallback?.();
  });

  source.onerror = () => {
    // A clean server-side close after a terminal event also lands here.
    if (gotTerminal || receivedAny) {
      // If we have data but lost the stream mid-search, fall back to polling.
      if (!gotTerminal) handlers.onFallback?.();
      source.close();
      return;
    }
    source.close();
    handlers.onFallback?.();
  };

  return () => source.close();
}
