/**
 * The single HTTP entry point. Every command goes through `request()`.
 *
 * Service routing: Agented is two servers. `/api/v1/*` is the ai-accounts
 * sidecar on :20001; everything else (`/admin`, `/api`, `/health`, `/schema`) is
 * the Litestar backend on :20000 — the same split the Vite dev proxy uses. A
 * `--service` override exists because the sidecar has its own `/health` and
 * `/schema` that the prefix rule would otherwise send to the backend.
 *
 * Auth: the backend takes `X-API-Key` (verified in
 * `backend/app_litestar/middleware.py`); `/health*` and `/schema*` bypass auth
 * entirely, which is what lets `ag ping` and `ag find` work before a key exists.
 */

import type { Resolved } from './config.ts';

export type Service = 'backend' | 'sidecar' | 'auto';

export interface RequestOpts {
  method: string;
  path: string;
  query?: Record<string, string>;
  body?: unknown;
  profile: Resolved;
  service?: Service;
  timeoutMs?: number;
  /** Build the request and return it without sending — powers `--dry-run`. */
  dryRun?: boolean;
}

export interface Response {
  status: number;
  body: unknown;
  requestId?: string;
  url: string;
  method: string;
}

export interface DryRun {
  method: string;
  url: string;
  headers: Record<string, string>;
  body: unknown;
}

export function routeService(path: string, explicit?: Service): 'backend' | 'sidecar' {
  if (explicit && explicit !== 'auto') return explicit;
  return path.startsWith('/api/v1/') ? 'sidecar' : 'backend';
}

export function baseFor(p: Resolved, svc: 'backend' | 'sidecar'): string {
  return svc === 'sidecar' ? p.sidecar : p.backend;
}

/** Auth-exempt on the backend — mirrors `_path_requires_auth` in middleware.py. */
export function needsAuth(path: string): boolean {
  if (!(path.startsWith('/admin') || path.startsWith('/api'))) return false;
  for (const prefix of ['/health', '/docs', '/openapi', '/schema', '/api/oauth-callback']) {
    if (path === prefix || path.startsWith(prefix + '/')) return false;
  }
  return true;
}

export function buildRequest(o: RequestOpts): DryRun & { service: 'backend' | 'sidecar' } {
  const service = routeService(o.path, o.service);
  const base = baseFor(o.profile, service);
  const qs = o.query && Object.keys(o.query).length ? '?' + new URLSearchParams(o.query).toString() : '';
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (o.body !== undefined) headers['Content-Type'] = 'application/json';
  if (o.profile.key && needsAuth(o.path)) headers['X-API-Key'] = o.profile.key;
  return {
    service,
    method: o.method.toUpperCase(),
    url: base + o.path + qs,
    headers,
    body: o.body,
  };
}

export async function request(o: RequestOpts): Promise<Response> {
  const built = buildRequest(o);
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), o.timeoutMs ?? 30_000);
  try {
    const res = await fetch(built.url, {
      method: built.method,
      headers: built.headers,
      body: built.body === undefined ? undefined : JSON.stringify(built.body),
      signal: ctl.signal,
    });
    const text = await res.text();
    let body: unknown = text;
    if (text) {
      try {
        body = JSON.parse(text);
      } catch {
        /* non-JSON (html error page, plain text) — pass through as a string */
      }
    } else {
      body = null;
    }
    return {
      status: res.status,
      body,
      requestId: res.headers.get('x-request-id') ?? undefined,
      url: built.url,
      method: built.method,
    };
  } catch (e) {
    if (e instanceof Error && e.name === 'AbortError') {
      throw new TransportError(`timed out after ${o.timeoutMs ?? 30_000}ms: ${built.method} ${built.url}`, 5);
    }
    throw new TransportError(
      `cannot reach ${built.url} — is the server running? (just dev-backend)\n  ${(e as Error).message}`,
      4,
    );
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Exit codes. A CLI meant to be scripted needs these to be stable and
 * meaningful, so a caller can branch without parsing text.
 *   0 ok · 2 usage · 3 auth · 4 unreachable · 5 timeout
 *   6 not found · 7 server error · 8 operation failed
 */
export function exitCodeForStatus(status: number): number {
  if (status < 400) return 0;
  if (status === 401 || status === 403) return 3;
  if (status === 404) return 6;
  if (status >= 500) return 7;
  return 8;
}

export class TransportError extends Error {
  // Plain field + assignment, NOT a TypeScript parameter property: Node's
  // type-stripping runs in "strip-only" mode, which erases annotations but
  // cannot emit the assignment a parameter property implies
  // (ERR_UNSUPPORTED_TYPESCRIPT_SYNTAX). Same reason this CLI avoids `enum`
  // and `namespace` — anything that compiles to runtime code is off-limits.
  code: number;

  constructor(message: string, code: number) {
    super(message);
    this.code = code;
  }
}

/** Pull a human message out of the backend's `{error: {code, message}}` envelope. */
export function errorMessage(body: unknown): string {
  if (body && typeof body === 'object') {
    const o = body as Record<string, unknown>;
    const err = o.error;
    if (err && typeof err === 'object') {
      const e = err as Record<string, unknown>;
      if (typeof e.message === 'string') return e.message;
    }
    if (typeof o.detail === 'string') return o.detail;
    if (typeof o.message === 'string') return o.message;
  }
  if (typeof body === 'string' && body.trim()) return body.slice(0, 400);
  return '(no message)';
}
