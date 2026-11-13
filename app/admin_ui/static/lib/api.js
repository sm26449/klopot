// Thin fetch wrapper for the alertd API.
//
// - same-origin cookies carry the session; the CSRF double-submit header
//   is added on every non-GET request from the `alertd_csrf` cookie;
// - 401 → the caller is logged out (event "auth:expired"); the router
//   sends the user to #/login;
// - 403 PASSWORD_CHANGE_REQUIRED → event "auth:must-change";
// - errors are normalised to ApiError {status, code, message, detail, traceId}.

const CSRF_COOKIE = "alertd_csrf";
const CSRF_HEADER = "X-CSRF-Token";

export class ApiError extends Error {
  constructor(status, code, message, detail, traceId) {
    super(message);
    this.status = status;
    this.code = code;
    this.detail = detail;
    this.traceId = traceId;
  }
}

export function readCookie(name) {
  const m = document.cookie.match(new RegExp("(?:^|; )" + name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "=([^;]*)"));
  return m ? decodeURIComponent(m[1]) : null;
}

const listeners = new Map();
export function on(event, fn) {
  if (!listeners.has(event)) listeners.set(event, new Set());
  listeners.get(event).add(fn);
  return () => listeners.get(event).delete(fn);
}
function emit(event, payload) {
  for (const fn of listeners.get(event) || []) fn(payload);
}

function normaliseError(status, body, traceId) {
  // FastAPI: {"detail": "..."} | {"detail": {"code","message",...}} | {"detail": [pydantic errors]}
  // Unhandled 500: {"error": {"code","message","details"}}
  let code = `HTTP_${status}`;
  let message = `Request failed (${status})`;
  let detail = null;
  if (body && typeof body === "object") {
    const d = body.detail ?? body.error;
    if (typeof d === "string") {
      message = d;
    } else if (Array.isArray(d)) {
      code = "VALIDATION_ERROR";
      message = d.map((e) => `${(e.loc || []).slice(1).join(".")}: ${e.msg}`).join("; ");
      detail = d;
    } else if (d && typeof d === "object") {
      code = d.code || code;
      message = d.message || message;
      detail = d;
    }
  }
  return new ApiError(status, code, message, detail, traceId);
}

export async function request(method, path, { body, query, raw, signal } = {}) {
  const url = new URL(path, window.location.origin);
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
    }
  }
  const headers = { Accept: "application/json" };
  const init = { method, headers, credentials: "same-origin" };
  if (signal) init.signal = signal;  // AbortController for cancelable loads (A28)
  if (method !== "GET" && method !== "HEAD") {
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf) headers[CSRF_HEADER] = csrf;
  }
  if (body !== undefined) {
    if (typeof body === "string") {
      headers["Content-Type"] = raw || "text/plain";
      init.body = body;
    } else {
      headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(body);
    }
  }

  let resp;
  try {
    resp = await fetch(url, init);
  } catch (e) {
    // A cancelled load (AbortController) rethrows as-is so callers can
    // ignore it rather than surfacing a spurious "unreachable" (A28).
    if (e && e.name === "AbortError") throw e;
    throw new ApiError(0, "NETWORK", `alertd unreachable: ${e.message}`, null, null);
  }
  const traceId = resp.headers.get("X-Trace-Id");
  if (resp.status === 204) {
    // Drain the (empty) body so the connection is released cleanly —
    // Chromium otherwise logs the fetch as aborted.
    await resp.arrayBuffer().catch(() => null);
    return null;
  }

  const ct = resp.headers.get("Content-Type") || "";
  const payload = ct.includes("application/json") ? await resp.json().catch(() => null) : await resp.text();

  if (resp.ok) return payload;

  const err = normaliseError(resp.status, payload, traceId);
  // A wrong *current password* on the change-password endpoint returns 401
  // INVALID_CREDENTIALS while the session is still valid — it must surface as a
  // field error, not log the user out (audit UX-011). Every other 401,
  // including a genuinely invalid/expired session, still ends the session.
  const isCurrentPasswordMismatch =
    resp.status === 401 && err.code === "INVALID_CREDENTIALS" && path.endsWith("/auth/password");
  if (resp.status === 401 && !path.startsWith("/v1/auth/login") && !isCurrentPasswordMismatch)
    emit("auth:expired", err);
  if (resp.status === 403 && err.code === "PASSWORD_CHANGE_REQUIRED") emit("auth:must-change", err);
  throw err;
}

export const api = {
  get: (path, query, opts) => request("GET", path, { query, ...opts }),
  post: (path, body, query) => request("POST", path, { body, query }),
  patch: (path, body) => request("PATCH", path, { body }),
  put: (path, body) => request("PUT", path, { body }),
  del: (path, query) => request("DELETE", path, { query }),

  // Auth
  login: (username, password) => request("POST", "/v1/auth/login", { body: { username, password } }),
  logout: () => request("POST", "/v1/auth/logout"),
  me: () => request("GET", "/v1/auth/me"),
  changePassword: (current_password, new_password) =>
    request("POST", "/v1/auth/password", { body: { current_password, new_password } }),
  sessions: () => request("GET", "/v1/auth/sessions"),
  revokeSession: (id) => request("DELETE", `/v1/auth/sessions/${id}`),
  revokeOtherSessions: () => request("DELETE", "/v1/auth/sessions"),

  // Health (no auth)
  health: () => request("GET", "/v1/health"),
  version: () => request("GET", "/v1/version"),
};
