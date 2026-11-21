/**
 * Typed API client — the only bridge between the web app and FastAPI (ADR-003).
 *
 * Every call to the backend goes through this module so request/response shapes
 * stay typed in one place. In the Compose stack Caddy routes `/api` to the api
 * service, so by default requests are same-origin relative to `/api`.
 * `NEXT_PUBLIC_API_BASE_URL` can override the base (e.g. for local dev against a
 * directly exposed backend).
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

/** Shape of `GET /api/health` (mirrors the FastAPI `HealthResponse`, spec 2.9). */
export interface HealthResponse {
  db: string;
  openai: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}/api${path}`, {
    headers: { Accept: "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    throw new ApiError(`Request to ${path} failed`, res.status);
  }
  return (await res.json()) as T;
}

/** Liveness of the backing services. */
export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}
