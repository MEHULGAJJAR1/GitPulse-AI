/**
 * Typed client for the GitPulse REST API.
 * - Credentials: the API key lives in sessionStorage and is sent as X-API-Key (never in URLs).
 * - All paths are relative (/api/...) and proxied by Vite / the reverse proxy to the FastAPI server.
 */

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : `Request failed with HTTP ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

const KEY_STORAGE = "gitpulse.apiKey";
let apiKey: string | null = typeof sessionStorage !== "undefined" ? sessionStorage.getItem(KEY_STORAGE) : null;
const listeners = new Set<() => void>();

export function getApiKey(): string | null {
  return apiKey;
}

export function setApiKey(key: string | null): void {
  apiKey = key;
  if (typeof sessionStorage !== "undefined") {
    if (key) sessionStorage.setItem(KEY_STORAGE, key);
    else sessionStorage.removeItem(KEY_STORAGE);
  }
  listeners.forEach((fn) => fn());
}

export function onAuthChange(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function headers(extra?: Record<string, string>): Record<string, string> {
  const h: Record<string, string> = { Accept: "application/json", ...extra };
  if (apiKey) h["X-API-Key"] = apiKey;
  return h;
}

async function parseError(res: Response): Promise<ApiError> {
  let detail: unknown = res.statusText;
  try {
    const body = await res.json();
    detail = body.detail ?? body;
  } catch {
    /* non-JSON error body */
  }
  return new ApiError(res.status, detail);
}

/** Upper bound for any single API call, so a stalled server surfaces as an error instead of an endless skeleton. */
export const REQUEST_TIMEOUT_MS = 25_000;

/**
 * Runs fetch with a timeout. A caller abort (React Query cancelling a stale query) is re-thrown unchanged;
 * a timeout or a network failure becomes an ApiError with status 0 and an actionable message.
 */
async function fetchWithTimeout(url: string, init: RequestInit, callerSignal?: AbortSignal): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort("timeout"), REQUEST_TIMEOUT_MS);
  const onCallerAbort = () => controller.abort(callerSignal?.reason);
  callerSignal?.addEventListener("abort", onCallerAbort);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } catch (err) {
    if (callerSignal?.aborted) throw err;
    if (controller.signal.aborted) {
      throw new ApiError(0, "The request timed out. The server may be busy computing analytics; retry in a moment.");
    }
    throw new ApiError(0, "Cannot reach the GitPulse API. Check that the backend is running and the dev proxy points to it.");
  } finally {
    clearTimeout(timer);
    callerSignal?.removeEventListener("abort", onCallerAbort);
  }
}

async function request<T>(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const res = await fetchWithTimeout(
    `/api${path}`,
    {
      method,
      headers: headers(body !== undefined ? { "Content-Type": "application/json" } : undefined),
      body: body !== undefined ? JSON.stringify(body) : undefined,
    },
    signal,
  );
  if (res.status === 401) {
    // Only an authentication failure ends the session. Server errors and timeouts never log the user out.
    setApiKey(null);
  }
  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  get: <T,>(path: string, signal?: AbortSignal) => request<T>("GET", path, undefined, signal),
  post: <T,>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  patch: <T,>(path: string) => request<T>("PATCH", path),
  del: (path: string) => request<void>("DELETE", path),
};

/** Downloads an export as a file. Uses the same auth header; the browser never sees the key in a URL. */
export async function downloadExport(path: string, fallbackName: string): Promise<void> {
  const res = await fetch(`/api${path}`, { headers: headers() });
  if (!res.ok) throw await parseError(res);
  const blob = await res.blob();
  const disposition = res.headers.get("content-disposition") ?? "";
  const match = /filename="([^"]+)"/.exec(disposition);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = match?.[1] ?? fallbackName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export interface SSEEvent {
  event: string;
  data: unknown;
}

/**
 * Consumes a Server-Sent Events stream with fetch (EventSource cannot send custom headers).
 * Resolves when the stream closes or the signal aborts.
 */
export async function streamEvents(path: string, onEvent: (e: SSEEvent) => void, signal: AbortSignal): Promise<void> {
  const res = await fetch(`/api${path}`, { headers: headers({ Accept: "text/event-stream" }), signal });
  if (!res.ok || !res.body) throw await parseError(res);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      let event = "message";
      const dataLines: string[] = [];
      for (const line of block.split("\n")) {
        if (line.startsWith(":")) continue;
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      }
      if (dataLines.length) {
        let data: unknown = dataLines.join("\n");
        try {
          data = JSON.parse(data as string);
        } catch {
          /* keep raw string */
        }
        onEvent({ event, data });
      }
    }
  }
}
