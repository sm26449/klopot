// @klopot/client — a small fetch wrapper over the Klopot HTTP API.
// Types: ./index.d.ts (request/response shapes come from the generated
// ./schema.d.ts). Works in browsers, Node ≥ 18, Deno and Bun.
//
//   import { createClient } from "@klopot/client";
//   const klopot = createClient({ baseUrl: "https://alerts.example.com", apiKey: process.env.KLOPOT_KEY });
//   await klopot.fire("disk_full", { host: "nas" }, { idempotency_key: "nas-disk" });
//   await klopot.resolve("disk_full", "nas-disk");

export class KlopotError extends Error {
  constructor(status, body) {
    const detail = body && (body.detail ?? body.error);
    super(`Klopot API ${status}: ${typeof detail === "string" ? detail : JSON.stringify(detail ?? body)}`);
    this.name = "KlopotError";
    this.status = status;
    this.body = body;
  }
}

/**
 * Create a Klopot HTTP client on fetch.
 * @param {object} options
 * @param {string} options.baseUrl Absolute API base URL (required).
 * @param {string} [options.apiKey] Machine key, sent as `X-API-Key`.
 * @param {typeof fetch} [options.fetch=globalThis.fetch] Fetch implementation.
 * @param {number} [options.timeoutMs=10000] Request timeout, where `AbortSignal.timeout` exists.
 * @returns {{request: Function, fire: Function, resolve: Function, health: Function}}
 *   Methods returning promises of the parsed JSON body, or `null` for an empty body.
 * @throws {TypeError} When `baseUrl` is missing.
 * Rejects with `KlopotError` (status, body) on a non-2xx response with a JSON or
 * empty body; a non-JSON body rejects with the JSON parse error; network
 * failures and timeouts reject with fetch's error.
 */
export function createClient({ baseUrl, apiKey, fetch: fetchImpl = globalThis.fetch, timeoutMs = 10000 }) {
  if (!baseUrl) throw new TypeError("baseUrl is required");
  const root = baseUrl.replace(/\/+$/, "");

  async function request(method, path, { query, body } = {}) {
    const url = new URL(root + path);
    for (const [k, v] of Object.entries(query || {})) if (v !== undefined && v !== null) url.searchParams.set(k, String(v));
    const headers = { Accept: "application/json" };
    if (apiKey) headers["X-API-Key"] = apiKey;
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const signal = typeof AbortSignal !== "undefined" && AbortSignal.timeout ? AbortSignal.timeout(timeoutMs) : undefined;
    const res = await fetchImpl(url.toString(), { method, headers, body: body === undefined ? undefined : JSON.stringify(body), signal });
    const text = await res.text();
    const data = text ? JSON.parse(text) : null;
    if (!res.ok) throw new KlopotError(res.status, data);
    return data;
  }

  return {
    request,
    /** POST /v1/fire. `options`: test, source, idempotency_key, resolved_type. */
    fire: (type, context = {}, options = {}) => request("POST", "/v1/fire", { body: { type, context, ...options } }),
    /** Close the episode opened with `idempotencyKey`. */
    resolve: (type, idempotencyKey, context = {}) =>
      request("POST", "/v1/fire", { body: { type, context, idempotency_key: idempotencyKey, status: "resolved" } }),
    /** GET /v1/health/ready (no key needed). */
    health: () => request("GET", "/v1/health/ready"),
  };
}
