# Phase 3: API Authentication - Research

**Researched:** 2026-02-28
**Domain:** API key authentication, SSE auth, CORS lockdown for Flask/Vue SPA
**Confidence:** HIGH

## Summary

Phase 3 adds API key authentication to all `/admin/*` and `/api/*` routes via Flask's `app.before_request` middleware, with an explicit bypass allowlist for webhooks, health, and docs. The critical entanglement is SSE authentication: the native browser `EventSource` API cannot send custom headers, so SSE endpoints must authenticate via short-lived query-string tokens generated from the existing `itsdangerous` library (a Flask dependency) or the frontend must replace `EventSource` with `@microsoft/fetch-event-source` which supports custom headers. CORS must be hardened from the current permissive `origins: "*"` fallback to a fail-closed posture that rejects all cross-origin requests when `CORS_ALLOWED_ORIGINS` is unset.

The codebase currently has zero authentication on any route. There are 20+ SSE endpoints across the application using `new EventSource(url)` in the frontend. The existing `apiFetch()` wrapper in `frontend/src/services/api/client.ts` is the single point where the `X-API-Key` header should be injected for all REST calls. For SSE, two viable approaches exist: (A) short-lived query-string tokens minted by the backend via `itsdangerous.URLSafeTimedSerializer`, or (B) replacing native `EventSource` with `@microsoft/fetch-event-source` which can send arbitrary headers including `X-API-Key`. Both approaches are well-documented and production-proven.

**Primary recommendation:** Use `app.before_request` middleware for API key validation, `@microsoft/fetch-event-source` for SSE authentication (it supports custom headers, eliminating query-string token complexity), and set Flask-CORS to reject all origins when `CORS_ALLOWED_ORIGINS` is empty.

## Paper-Backed Recommendations

Every recommendation below cites specific evidence.

### Recommendation 1: Flask `before_request` Middleware for API Key Validation

**Recommendation:** Use `app.before_request` to intercept all requests and validate `X-API-Key` header against a server-side secret, returning HTTP 401 for unauthorized requests.

**Evidence:**
- Flask official documentation (2024) -- `before_request` hooks run before every request handler and can short-circuit by returning a response. This is the canonical Flask pattern for cross-cutting authentication concerns.
- flask-openapi3 documentation (Context7, luolingchun/flask-openapi3) -- flask-openapi3 extends Flask core; `before_request` hooks work identically. The `@validate_request` decorator example in the docs shows `login_required()` decorators wrapping route handlers, confirming compatibility.
- Miguel Grinberg, "RESTful Authentication with Flask" (2013, updated 2023) -- Established the pattern of `before_request` for token verification in Flask APIs, widely adopted across the ecosystem.

**Confidence:** HIGH -- Flask's `before_request` is the standard, well-documented approach. flask-openapi3 inherits this behavior directly.

**Implementation detail:** The middleware must check `request.path` against an allowlist before validating the key. The allowlist paths are: `/` (webhook), `/api/webhooks/github/` (GitHub webhook), `/health/*` (probes), `/docs/*` and `/openapi/*` (API docs).

**Caveats:** The `before_request` hook runs for ALL requests including static files and error handlers. The path-matching logic must be precise to avoid accidentally blocking health checks or letting API routes through.

### Recommendation 2: `@microsoft/fetch-event-source` for SSE Authentication

**Recommendation:** Replace native `EventSource` with `@microsoft/fetch-event-source` in the frontend to send the `X-API-Key` header on SSE connections.

**Evidence:**
- MDN Web Docs, "Using server-sent events" (2024) -- Documents that the native `EventSource` API does not support setting custom HTTP headers. This is a W3C specification limitation, not a browser bug.
- `@microsoft/fetch-event-source` README (Context7, azure/fetch-event-source) -- Explicitly designed to solve the custom-header limitation: "Provides a more flexible API for Server-Sent Events using the Fetch API, allowing custom requests, error handling, and integration with the Page Visibility API." Supports `method`, `headers`, `body`, `signal` parameters.
- HAHWUL, "How to Securing SSE" (2025) -- Documents that query-string tokens for SSE auth are not recommended because tokens appear in server logs, proxy logs, and browser history. Custom header via fetch-based client is the preferred approach.

**Confidence:** HIGH -- `@microsoft/fetch-event-source` has 2.5k+ GitHub stars, is maintained by Microsoft Azure, and is the de facto standard for authenticated SSE in modern web applications.

**Expected improvement:** Eliminates the need for a separate token-minting endpoint and the complexity of token expiration/refresh for SSE connections. All auth uses a single mechanism (X-API-Key header).

**Caveats:**
- The existing `createBackoffEventSource()` wrapper in `client.ts` must be rewritten to use `fetchEventSource` instead of `new EventSource()`. The backoff and backpressure queue logic should be preserved.
- All 20+ sites in the frontend that call `new EventSource(url)` must be migrated to use the new wrapper.
- `fetchEventSource` uses the Fetch API internally, so it respects CORS preflight -- the backend must include `X-API-Key` in `Access-Control-Allow-Headers`.

### Recommendation 3: Short-Lived Query-String Tokens as Fallback (Alternative)

**Recommendation:** If `@microsoft/fetch-event-source` is not adopted, use `itsdangerous.URLSafeTimedSerializer` to mint short-lived (60-120 second) tokens that SSE endpoints accept via `?token=` query parameter.

**Evidence:**
- itsdangerous documentation (2.2.x, palletsprojects.com) -- `URLSafeTimedSerializer` generates URL-safe tokens with configurable expiration. The `loads(token, max_age=120)` method handles both validation and expiry in one call.
- itsdangerous is already installed in the backend environment (v2.2.0) as a Flask dependency -- no new package required.

**Confidence:** MEDIUM -- This approach works but adds complexity: a new `/api/auth/sse-token` endpoint, token expiration handling, and reconnection logic when tokens expire mid-stream.

**Why this is the backup, not primary:** Query-string tokens appear in server access logs and proxy logs. The token expiration creates a race condition on long-lived SSE streams. `@microsoft/fetch-event-source` is cleaner.

### Recommendation 4: Flask-CORS Fail-Closed Configuration

**Recommendation:** When `CORS_ALLOWED_ORIGINS` is unset or empty, pass an empty list `[]` (not `"*"`) to Flask-CORS origins, causing it to omit the `Access-Control-Allow-Origin` header entirely and reject all cross-origin requests.

**Evidence:**
- Flask-CORS documentation (Context7, corydolphin/flask-cors) -- When `origins` is set to a specific list, Flask-CORS only includes `Access-Control-Allow-Origin` for matching origins. If no origin matches (or the list is empty), the header is omitted, and browsers block the response.
- Flask-CORS API docs (flask-cors.readthedocs.io) -- Confirms that the `origins` parameter accepts a list of strings or regex patterns. An empty list means no origin is allowed.
- Current codebase (`backend/app/__init__.py` lines 72-83) -- Currently falls back to `{"origins": "*"}` when `CORS_ALLOWED_ORIGINS` is empty. This is the exact code that must change.

**Confidence:** HIGH -- Flask-CORS behavior is well-documented and deterministic. An empty origins list = no `Access-Control-Allow-Origin` header = browser blocks all cross-origin requests.

**Implementation detail:** The fix is a one-line change in `create_app()`:
```python
# BEFORE (permissive fallback)
cors_config = {"origins": allowed_origins} if allowed_origins else {"origins": "*"}

# AFTER (fail-closed)
cors_config = {"origins": allowed_origins} if allowed_origins else {"origins": []}
```

Additionally, `X-API-Key` must be added to `Access-Control-Allow-Headers` for preflight requests to succeed when the frontend sends the auth header.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Flask `before_request` | built-in | Request-level auth middleware | Native Flask hook, zero dependencies, works with flask-openapi3 |
| `itsdangerous` | 2.2.0 (installed) | Token signing for SSE fallback | Already a Flask dependency; `URLSafeTimedSerializer` is production-proven |
| `flask-cors` | 4.0.0+ (installed) | CORS policy enforcement | Already in use; only configuration change needed |
| `@microsoft/fetch-event-source` | 2.6.x | Authenticated SSE from browser | Enables custom headers on SSE; replaces native `EventSource` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `hmac` / `secrets` | stdlib | API key generation and comparison | Generate initial API key; constant-time comparison in middleware |

### Alternatives Considered

| Instead of | Could Use | Tradeoff | Rationale |
|------------|-----------|----------|-----------|
| `@microsoft/fetch-event-source` | `itsdangerous` query-string tokens | Token expiry complexity, log exposure | fetch-event-source is cleaner; tokens are fallback only |
| `app.before_request` | Per-route decorators | Repetitive, easy to miss a route | `before_request` is centralized, one enforcement point |
| Static API key in env | JWT/OAuth2 | Over-engineered for single-user local tool | This is a local dev platform, not a multi-tenant SaaS |

**Installation:**
```bash
# Backend: no new packages needed (itsdangerous already installed via Flask)
# Frontend:
cd frontend && npm install @microsoft/fetch-event-source
```

## Architecture Patterns

### Recommended Project Structure

```
backend/app/
  __init__.py          # Add before_request hook in create_app()
  middleware/           # NEW directory (optional, can inline in __init__.py)
    auth.py            # API key validation logic
frontend/src/
  services/api/
    client.ts          # Modify apiFetch() + replace createBackoffEventSource()
    sse.ts             # NEW: authenticated SSE wrapper using fetchEventSource
```

### Pattern 1: Centralized `before_request` Auth Middleware

**What:** A single `app.before_request` function that validates `X-API-Key` on every request, with a path-based allowlist for unauthenticated endpoints.

**When to use:** Always -- this is the primary enforcement point.

**Example:**
```python
# Source: Flask official docs + flask-openapi3 Context7
import hmac
import os
from flask import request, jsonify

# Allowlist of paths that do NOT require authentication
AUTH_BYPASS_PREFIXES = (
    "/health/",
    "/docs/",
    "/openapi/",
)
AUTH_BYPASS_EXACT = {
    "/",                        # Webhook receiver
    "/api/webhooks/github",     # GitHub webhook (with or without trailing slash)
    "/api/webhooks/github/",
}

def _require_api_key():
    """before_request hook: reject unauthenticated requests to protected routes."""
    path = request.path

    # Allow bypassed paths
    if path in AUTH_BYPASS_EXACT:
        return None
    if path.startswith(AUTH_BYPASS_PREFIXES):
        return None

    # Only protect /admin/* and /api/* routes
    if not (path.startswith("/admin/") or path.startswith("/api/")):
        return None

    # Validate API key
    api_key = os.environ.get("AGENTED_API_KEY", "")
    if not api_key:
        # No key configured = auth disabled (dev convenience)
        return None

    request_key = request.headers.get("X-API-Key", "") or request.args.get("token", "")
    if not request_key or not hmac.compare_digest(request_key, api_key):
        return jsonify({"error": "Unauthorized"}), 401

    return None
```

### Pattern 2: Authenticated SSE with `fetchEventSource`

**What:** Replace all `new EventSource(url)` calls with a wrapper that uses `@microsoft/fetch-event-source`, automatically injecting the `X-API-Key` header.

**When to use:** Every SSE connection in the frontend.

**Example:**
```typescript
// Source: @microsoft/fetch-event-source README (Context7)
import { fetchEventSource } from '@microsoft/fetch-event-source';

function getApiKey(): string {
  // Read from localStorage, environment, or config
  return localStorage.getItem('agented-api-key') || '';
}

export function createAuthenticatedSSE(
  url: string,
  options: {
    onMessage: (event: { event: string; data: string }) => void;
    onError?: (err: Error) => void;
    onOpen?: () => void;
    signal?: AbortSignal;
  }
): AbortController {
  const ctrl = new AbortController();

  fetchEventSource(url, {
    method: 'GET',
    headers: {
      'X-API-Key': getApiKey(),
    },
    signal: options.signal ?? ctrl.signal,
    onmessage(ev) {
      options.onMessage({ event: ev.event, data: ev.data });
    },
    onerror(err) {
      if (options.onError) options.onError(err);
    },
    onopen: async (response) => {
      if (response.ok) {
        if (options.onOpen) options.onOpen();
        return;
      }
      if (response.status === 401) {
        throw new Error('Unauthorized');
      }
    },
  });

  return ctrl;
}
```

### Anti-Patterns to Avoid

- **Per-route decorators for auth:** With 44+ blueprints and 100+ routes, using `@require_auth` on each route is error-prone. A single `before_request` hook with an allowlist is strictly better.
- **Storing API key in frontend JavaScript bundle:** The key should be in `localStorage` or read from a settings/config endpoint, never hardcoded in source.
- **Using `EventSource` with query-string API keys:** The full API key would appear in server logs, proxy logs, and browser history. Use `fetchEventSource` with headers instead.
- **CORS `origins: "*"` in production:** The current fallback to wildcard origins is insecure. Must fail closed.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Token signing for SSE | Custom HMAC token scheme | `itsdangerous.URLSafeTimedSerializer` | Handles serialization, signing, and expiry validation in one call; already installed |
| Authenticated SSE client | Custom XMLHttpRequest SSE parser | `@microsoft/fetch-event-source` | Handles reconnection, error handling, Fetch API integration; 2.5k+ stars |
| CORS configuration | Manual `Access-Control-*` headers | `flask-cors` | Already in use; handles preflight, origin matching, header whitelisting |
| Constant-time string comparison | `==` operator for key comparison | `hmac.compare_digest()` | Prevents timing attacks on API key validation |

**Key insight:** Every component of this phase uses existing, well-maintained libraries already in the dependency tree (Flask, itsdangerous, flask-cors) or adds exactly one new package (`@microsoft/fetch-event-source`). There is zero need for custom cryptography or protocol implementation.

## Common Pitfalls

### Pitfall 1: SSE Endpoints Silently Fail After Adding Auth

**What goes wrong:** Adding `before_request` auth breaks all SSE streams because `EventSource` cannot send custom headers. The execution log viewer shows a blank page with no error.
**Why it happens:** Native `EventSource` only sends cookies and standard headers. The `X-API-Key` header is never included.
**How to avoid:** Implement SSE auth migration (fetch-event-source or query-string tokens) in the SAME deployment as the `before_request` middleware. This is explicitly called out in the roadmap as a key constraint.
**Warning signs:** SSE endpoints return 401 in network tab; no log events appear in UI.

### Pitfall 2: Trailing Slash Mismatch in Bypass Allowlist

**What goes wrong:** Flask normalizes URLs with `strict_slashes`. The allowlist checks `/api/webhooks/github` but the request arrives at `/api/webhooks/github/` (or vice versa), causing a 401 on legitimate GitHub webhooks.
**Why it happens:** The GitHub webhook blueprint has `strict_slashes = False`, but the `before_request` path check is string-based.
**How to avoid:** Include both forms in the allowlist, or strip trailing slashes before comparison.
**Warning signs:** GitHub webhooks start returning 401 after auth is enabled.

### Pitfall 3: CORS Preflight Fails for X-API-Key Header

**What goes wrong:** The browser sends an `OPTIONS` preflight request for any non-simple header. If `X-API-Key` is not in `Access-Control-Allow-Headers`, the preflight fails and the actual request is never sent.
**Why it happens:** Flask-CORS must be configured to allow the custom `X-API-Key` header. Also, `OPTIONS` preflight requests must bypass auth (they don't carry the API key).
**How to avoid:** Add `allow_headers=["Content-Type", "X-API-Key"]` to Flask-CORS config. Ensure `before_request` returns `None` for `OPTIONS` method requests.
**Warning signs:** All frontend requests fail with CORS errors in browser console; network tab shows failed OPTIONS requests.

### Pitfall 4: API Key Not Set = Locked Out

**What goes wrong:** If `AGENTED_API_KEY` is set but the frontend doesn't know it, all requests fail with 401.
**Why it happens:** The API key must be configured in both backend (env var) and frontend (localStorage or settings endpoint).
**How to avoid:** When `AGENTED_API_KEY` is not set, auth is disabled entirely (passthrough mode). This preserves backwards compatibility for existing users.
**Warning signs:** Fresh install with no `.env` file returns 401 on all routes.

### Pitfall 5: `fetchEventSource` Reconnection Drops Auth

**What goes wrong:** After a network interruption, `fetchEventSource` reconnects but may not include the latest API key if it changed.
**Why it happens:** The `headers` object is captured at call time. If the key rotates, reconnections use the stale key.
**How to avoid:** Use a function that returns headers lazily: `headers: () => ({ 'X-API-Key': getApiKey() })`. Note: check if `fetchEventSource` supports dynamic headers or use the `openWhenHidden: false` option to close on tab hide.

## Experiment Design

### Recommended Experimental Setup

**Independent variables:** Auth middleware enabled/disabled, SSE auth method (fetchEventSource vs query-string token vs none), CORS configuration (wildcard vs allowlist vs empty)

**Dependent variables:** HTTP status codes on protected/unprotected routes, SSE event delivery, CORS headers in responses

**Controlled variables:** Same server configuration, same test payloads, same browser

**Baseline comparison:**
- Method: Current state (no auth, CORS wildcard)
- Expected performance: All requests succeed regardless of origin or auth headers
- Our target: Only authenticated requests to protected routes succeed; bypass routes remain open; CORS blocks unlisted origins

**Ablation plan:**
1. Auth middleware only (no SSE fix) -- confirms SSE breaks as expected
2. Auth middleware + fetchEventSource -- confirms SSE works with auth
3. CORS lockdown only -- confirms cross-origin rejection
4. Full integration -- all three together

**Statistical rigor:**
- Number of runs: 3 per scenario (verify deterministic behavior)
- Verification: binary pass/fail per test case (no statistical tests needed for deterministic HTTP behavior)

### Recommended Metrics

| Metric | Why | How to Compute | Baseline |
|--------|-----|----------------|----------|
| Auth rejection rate (no key) | Confirms middleware works | curl without X-API-Key, check for 401 | 0% (currently no auth) |
| Bypass allowlist correctness | Confirms webhooks/health still work | curl bypass paths without key, check for non-401 | 100% (no auth to bypass) |
| SSE event delivery with auth | Confirms streaming works post-auth | Open execution detail page, run test trigger, count log events | 100% (currently works without auth) |
| CORS rejection for unlisted origin | Confirms fail-closed | curl with `Origin: https://evil.example.com`, check for missing ACAO header | 0% (currently allows all) |

## Verification Strategy

### Recommended Verification Tiers for This Phase

| Item | Recommended Tier | Rationale |
|------|-----------------|-----------|
| `before_request` returns 401 without key | Level 1 (Sanity) | Single curl command |
| `before_request` returns 200 with valid key | Level 1 (Sanity) | Single curl command |
| Bypass allowlist lets webhooks through | Level 1 (Sanity) | curl to `/` and `/api/webhooks/github/` |
| SSE stream delivers events after auth | Level 2 (Proxy) | Open browser, trigger execution, watch logs |
| CORS blocks unlisted origin | Level 1 (Sanity) | curl with `Origin` header, check response headers |
| Frontend `apiFetch()` sends X-API-Key | Level 2 (Proxy) | Browser DevTools network tab inspection |
| All 20+ SSE endpoints work after migration | Level 3 (Deferred) | Full E2E test of every SSE consumer |
| Auth disabled when no key configured | Level 1 (Sanity) | Unset env var, verify all routes accessible |

**Level 1 checks to always include:**
- `curl http://localhost:20000/admin/triggers` returns 401 (no key)
- `curl -H "X-API-Key: $KEY" http://localhost:20000/admin/triggers` returns 200
- `POST /` (webhook) returns 200 without key
- `POST /api/webhooks/github/` returns non-401 without API key (GitHub signature validation still applies)
- `/health/liveness` returns 200 without key
- `curl -H "Origin: https://evil.example.com" http://localhost:20000/admin/triggers` has no `Access-Control-Allow-Origin` header

**Level 2 proxy metrics:**
- Frontend loads and all API calls include `X-API-Key` header (DevTools check)
- Execution log SSE stream delivers live events during a test trigger run
- At least one conversation SSE stream delivers chat events

**Level 3 deferred items:**
- Comprehensive test of all 20+ SSE endpoints post-migration
- Load testing under concurrent SSE connections with auth
- Token rotation / key change behavior

## Production Considerations (from KNOWHOW.md)

KNOWHOW.md is empty (no prior production notes). The following considerations are derived from research:

### Known Failure Modes
- **API key leaked in logs:** If query-string tokens are used for SSE, the token appears in server access logs. Prevention: use `fetchEventSource` with headers instead. Detection: grep access logs for `?token=`.
- **Auth bypass on path traversal:** If the allowlist check uses `startswith("/health/")`, a crafted path like `/health/../admin/triggers` could bypass auth. Prevention: use `request.path` which Flask normalizes (removes `..` segments). Detection: test with path traversal payloads.
- **Locked out after key rotation:** Changing `AGENTED_API_KEY` requires both server restart and frontend reconfiguration. Prevention: expose a settings endpoint that returns whether auth is enabled, and provide UI for key entry.

### Scaling Concerns
- **At current scale:** Single API key in environment variable is sufficient. This is a local developer tool, not multi-tenant.
- **At production scale:** Would need per-user API keys, key rotation, and a key management endpoint. This is explicitly out of scope for v0.1.0.

### Common Implementation Traps
- **Timing attack on key comparison:** Using `==` for string comparison leaks key length via timing. Correct approach: `hmac.compare_digest()`.
- **CORS `allow_headers` omission:** Adding a custom header (`X-API-Key`) requires explicit `allow_headers` configuration in Flask-CORS, or preflight requests will fail silently.
- **SSE reconnection after auth failure:** `fetchEventSource` must be configured to NOT retry on 401 (fatal error), only retry on transient errors (429, 502, 503, 504). Default retry-on-error behavior would create an infinite 401 loop.

## Code Examples

Verified patterns from official sources and paper implementations:

### API Key Middleware in `create_app()`

```python
# Source: Flask docs + codebase pattern from backend/app/__init__.py
def create_app(config=None):
    app = OpenAPI(__name__, info=API_INFO, doc_prefix="/docs")
    # ... existing setup ...

    # API key authentication middleware
    @app.before_request
    def require_api_key():
        from flask import request, jsonify
        import hmac

        path = request.path.rstrip("/")

        # Skip auth for OPTIONS (CORS preflight)
        if request.method == "OPTIONS":
            return None

        # Bypass allowlist
        if path in ("", "/api/webhooks/github"):
            return None
        if path.startswith(("/health", "/docs", "/openapi")):
            return None

        # Only protect API routes
        if not (path.startswith("/admin") or path.startswith("/api")):
            return None

        api_key = os.environ.get("AGENTED_API_KEY", "")
        if not api_key:
            return None  # Auth disabled when no key configured

        request_key = request.headers.get("X-API-Key", "")
        if not request_key or not hmac.compare_digest(request_key, api_key):
            return jsonify({"error": "Unauthorized"}), 401

        return None

    # ... rest of create_app ...
```

### Flask-CORS Fail-Closed Configuration

```python
# Source: Flask-CORS docs (Context7) + current codebase
allowed_origins = os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",")
allowed_origins = [o.strip() for o in allowed_origins if o.strip()]

# Fail-closed: empty list = reject all cross-origin (was {"origins": "*"})
cors_config = {"origins": allowed_origins} if allowed_origins else {"origins": []}

CORS(
    app,
    resources={
        r"/api/*": cors_config,
        r"/admin/*": cors_config,
        r"/health/*": {"origins": "*"},   # Health probes always open
        r"/docs/*": {"origins": "*"},     # Swagger UI needs CORS
    },
    allow_headers=["Content-Type", "X-API-Key"],  # NEW: allow custom auth header
)
```

### Frontend `apiFetch()` with API Key Header

```typescript
// Source: existing client.ts pattern
async function apiFetchSingle<T>(url: string, options?: ApiFetchOptions): Promise<T> {
  // ... existing timeout setup ...

  const apiKey = localStorage.getItem('agented-api-key') || '';

  const response = await fetch(`${API_BASE}${url}`, {
    ...fetchOptions,
    signal: controller.signal,
    headers: {
      'Content-Type': 'application/json',
      ...(apiKey ? { 'X-API-Key': apiKey } : {}),
      ...fetchOptions?.headers,
    },
  });
  // ... rest unchanged ...
}
```

### Authenticated SSE with `fetchEventSource`

```typescript
// Source: @microsoft/fetch-event-source README (Context7)
import { fetchEventSource, EventStreamContentType } from '@microsoft/fetch-event-source';

class RetriableError extends Error {}
class FatalError extends Error {}

export function createAuthenticatedEventSource(
  url: string,
  handlers: {
    onMessage: (event: string, data: string) => void;
    onComplete?: () => void;
    onError?: (err: Error) => void;
  },
): AbortController {
  const ctrl = new AbortController();
  const apiKey = localStorage.getItem('agented-api-key') || '';

  fetchEventSource(`${API_BASE}${url}`, {
    headers: {
      'X-API-Key': apiKey,
    },
    signal: ctrl.signal,
    async onopen(response) {
      if (response.ok && response.headers.get('content-type')?.includes(EventStreamContentType)) {
        return; // Connected successfully
      }
      if (response.status === 401) {
        throw new FatalError('Unauthorized');
      }
      throw new RetriableError();
    },
    onmessage(ev) {
      handlers.onMessage(ev.event, ev.data);
    },
    onclose() {
      handlers.onComplete?.();
    },
    onerror(err) {
      if (err instanceof FatalError) {
        throw err; // Stop retrying
      }
      // Return undefined to use default retry
    },
  });

  return ctrl;
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Query-string tokens for SSE auth | `@microsoft/fetch-event-source` with headers | 2021+ | Eliminates token leakage in logs; single auth mechanism |
| `EventSource` polyfill (`eventsource` npm) | `@microsoft/fetch-event-source` | 2020+ | Better error handling, Fetch API integration, Page Visibility support |
| CORS `origins: "*"` default | Fail-closed (no origin = reject all) | OWASP best practice | Prevents unauthorized cross-origin access |

**Deprecated/outdated:**
- `event-source-polyfill` npm package: Older approach that patches `EventSource` to support headers. `@microsoft/fetch-event-source` is the modern replacement with better error handling and reconnection logic.

## Open Questions

1. **API key storage in frontend**
   - What we know: The key must be stored client-side to include in every request
   - What's unclear: Should it be in `localStorage` (persists across sessions) or `sessionStorage` (cleared on tab close)?
   - Recommendation: Use `localStorage` for developer convenience (this is a local tool), with a settings page to view/change the key. The API key is visible to anyone with physical access to the machine anyway.

2. **API key generation and initial setup**
   - What we know: The backend reads `AGENTED_API_KEY` from environment
   - What's unclear: Should the backend auto-generate a key (like `SECRET_KEY`) or require manual setup?
   - Recommendation: Auto-generate and persist to `.api_key` file if not set, similar to the existing `_get_secret_key()` pattern. Expose via a first-run setup flow or settings endpoint.

3. **Multiple API keys / key rotation**
   - What we know: Single key is sufficient for v0.1.0
   - What's unclear: Will future phases need per-user keys?
   - Recommendation: Design the middleware to be upgradeable (check against a set of valid keys) but implement with a single key for now. Out of scope for this phase.

## Sources

### Primary (HIGH confidence)
- Flask official documentation -- `before_request` hooks, request lifecycle
- Context7: `/corydolphin/flask-cors` -- CORS configuration, origins behavior
- Context7: `/luolingchun/flask-openapi3` -- Security schemes, `validate_request`, `before_request` compatibility
- Context7: `/azure/fetch-event-source` -- Custom headers SSE, error handling, reconnection
- MDN Web Docs, "Using server-sent events" -- EventSource API limitations
- itsdangerous documentation (2.2.x) -- `URLSafeTimedSerializer` for token signing

### Secondary (MEDIUM confidence)
- Miguel Grinberg, "RESTful Authentication with Flask" (2013, updated 2023) -- Established Flask auth patterns
- HAHWUL, "How to Securing SSE" (2025) -- SSE security best practices, query-string token risks
- Flask-CORS API docs (flask-cors.readthedocs.io) -- Detailed parameter reference

### Tertiary (LOW confidence)
- Various blog posts on Flask middleware patterns -- Consistent with official docs but not primary sources

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- All libraries already in use or well-established; versions confirmed via Context7
- Architecture: HIGH -- `before_request` pattern is canonical Flask; `fetchEventSource` is the standard SSE-with-headers solution
- Pitfalls: HIGH -- Derived from actual codebase analysis (20+ SSE endpoints, current CORS config, trailing slash behavior)
- Experiment design: HIGH -- All verification is deterministic HTTP behavior, not statistical

**Research date:** 2026-02-28
**Valid until:** 2026-03-28 (stable domain; libraries unlikely to change materially in 30 days)
