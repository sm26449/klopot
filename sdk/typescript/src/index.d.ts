import type { components, paths } from "./schema";

export type FireRequest = components["schemas"]["FireRequest"];
export type FireResponse = components["schemas"]["FireResponse"];
export type { components, paths };

export declare class KlopotError extends Error {
  readonly status: number;
  readonly body: unknown;
}

export interface ClientOptions {
  baseUrl: string;
  apiKey?: string;
  fetch?: typeof fetch;
  timeoutMs?: number;
}

export interface KlopotClient {
  request<T = unknown>(method: string, path: string, init?: { query?: Record<string, unknown>; body?: unknown }): Promise<T>;
  fire(type: string, context?: Record<string, unknown>, options?: Omit<FireRequest, "type" | "context">): Promise<FireResponse>;
  resolve(type: string, idempotencyKey: string, context?: Record<string, unknown>): Promise<FireResponse>;
  health(): Promise<Record<string, unknown>>;
}

export declare function createClient(options: ClientOptions): KlopotClient;
