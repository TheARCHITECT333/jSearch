/** All backend communication lives in this layer.
 * Components never call fetch directly. */

export const API_BASE = import.meta.env.VITE_API_BASE ?? "";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new ApiError(
      "Could not reach the backend. Is it running on port 8000?",
      0
    );
  }

  if (!response.ok) {
    let message = `Request failed (HTTP ${response.status}).`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") message = body.detail;
    } catch {
      // keep default message
    }
    throw new ApiError(message, response.status);
  }
  return response.json() as Promise<T>;
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path);
}

export function apiPost<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "POST", body: JSON.stringify(body) });
}

/** Send a file as the raw request body (no multipart parsing needed server-side). */
export function apiPostFile<T>(path: string, file: Blob): Promise<T> {
  return request<T>(path, {
    method: "POST",
    body: file,
    headers: { "Content-Type": file.type || "application/octet-stream" },
  });
}
