# Phase 4: Security Hardening - Research

**Researched:** 2026-02-28
**Domain:** Flask HTTP security headers, rate limiting, and sensitive data exposure prevention
**Confidence:** HIGH

## Summary

Phase 4 adds three security layers to the Agented backend: (1) HTTP security headers via flask-talisman, (2) per-route rate limiting via flask-limiter, and (3) health endpoint redaction to prevent sensitive data leakage to unauthenticated callers.

All three requirements map cleanly to well-maintained, officially-documented Flask extensions with straightforward integration paths. The main implementation concern is ensuring flask-talisman's `force_https` redirect and CSP header do not interfere with SSE streaming endpoints (20+ routes return `text/event-stream`) or the Swagger UI at `/docs`. The `force_https=False` setting and a permissive CSP for the `/docs` path resolve this. Flask-limiter's in-memory storage backend is appropriate for this project's single-worker Gunicorn deployment (documented constraint in `gunicorn.conf.py`), and its blueprint-level limit application maps directly to the existing route registration pattern.

**Primary recommendation:** Use flask-talisman 1.1.0+ for security headers (SEC-01), flask-limiter 3.x with `storage_uri="memory://"` for rate limiting (SEC-02), and a conditional response builder in the health endpoint for sensitive field redaction (SEC-03).

## User Constraints (from CONTEXT.md)

No CONTEXT.md exists for this phase. All implementation decisions are at the planner's discretion, guided by the requirements in the roadmap (SEC-01, SEC-02, SEC-03).

## Paper-Backed Recommendations

### Recommendation 1: Security Headers via flask-talisman

**Recommendation:** Use flask-talisman to inject CSP, HSTS, X-Frame-Options, and X-Content-Type-Options headers on every response.

**Evidence:**
- OWASP Secure Headers Project (2024) -- lists Content-Security-Policy, Strict-Transport-Security, X-Frame-Options, and X-Content-Type-Options as mandatory response headers for web applications. The project maintains a continuously-updated reference of recommended header values.
- Google Cloud Platform maintains flask-talisman (GitHub: GoogleCloudPlatform/flask-talisman) with 16 documented configuration snippets, HIGH source reputation per Context7.
- Flask-Talisman constructor defaults align with OWASP recommendations: `strict_transport_security=True`, `frame_options='SAMEORIGIN'`, `content_security_policy="default-src: 'self'"`.

**Confidence:** HIGH -- flask-talisman is the de facto standard for Flask security headers, maintained by Google Cloud Platform, and its defaults match OWASP guidance.

**Expected improvement:** All four required headers (CSP, HSTS, X-Frame-Options: DENY, X-Content-Type-Options: nosniff) present on every HTTP response with a single extension initialization.

**Caveats:**
- `force_https=True` (default) will redirect HTTP to HTTPS in non-debug mode. For local development behind no TLS terminator, this must be set to `False` or conditioned on an environment variable.
- CSP `default-src: 'self'` will block Swagger UI's inline scripts and external CDN resources. The `/docs` blueprint needs a relaxed per-route CSP or exemption.
- SSE endpoints return `text/event-stream` -- Talisman adds headers via Flask's `after_request` hook, which runs on streaming responses too. This is benign (security headers on SSE responses are harmless and even beneficial), but the CSP header on event streams is wasted bytes. No functional issue.

### Recommendation 2: Rate Limiting via flask-limiter with In-Memory Storage

**Recommendation:** Use flask-limiter 3.x with `storage_uri="memory://"` and `get_remote_address` key function, applying blueprint-level and per-route rate limits.

**Evidence:**
- Flask-Limiter official documentation (Context7: /alisaifee/flask-limiter, 61 code snippets, HIGH reputation) demonstrates blueprint-level limits via `limiter.limit("60/hour")(blueprint)` and per-route limits via `@limiter.limit("1 per day")`.
- Flask-Limiter GitHub Discussion #373 confirms: in-memory storage is safe for single-process deployments; with `workers>1` limits are per-process (effectively N x limit). This project's `gunicorn.conf.py` mandates `workers=1`, making in-memory storage correct.
- Flask-Limiter supports `strategy="fixed-window"` (default), `"moving-window"`, and `"sliding-window-counter"`. Fixed-window is simplest and appropriate for the success criteria (20 requests in 10 seconds = "2/second" or "20/10seconds").

**Confidence:** HIGH -- single-worker constraint documented in `gunicorn.conf.py`; flask-limiter's in-memory backend is explicitly designed for this scenario.

**Expected improvement:** Webhook endpoint (`POST /`) returns HTTP 429 after exceeding the configured threshold. Admin routes get a separate, more generous limit to prevent accidental self-DOS during normal frontend usage.

**Caveats:**
- If the project ever moves to `workers>1`, rate limits will be per-process. The `gunicorn.conf.py` docstring already documents this constraint; the rate limiter config should add a comment referencing it.
- `get_remote_address` returns `request.remote_addr`, which may be the reverse proxy IP if behind a load balancer. For this project (local/single-machine deployment), this is correct. If a reverse proxy is added later, `request.access_route[0]` or `X-Forwarded-For` parsing would be needed.

### Recommendation 3: Health Endpoint Redaction for Unauthenticated Callers

**Recommendation:** Modify `/health/readiness` to check for authentication status (from Phase 3's auth middleware) and return a minimal response (`{"status": "ok", "timestamp": "..."}`) when unauthenticated, stripping execution IDs, process details, CLIProxy port numbers, and startup warning strings.

**Evidence:**
- OWASP API Security Top 10 (2023) -- API3:2023 Broken Object Property Level Authorization recommends endpoints return only the minimum required data for the caller's authorization level.
- The current health endpoint (at `backend/app/routes/health.py` lines 17-79) exposes: `active_execution_ids` (list of execution IDs), `active_executions` (count), CLIProxy port number, and startup warnings (which may include error messages with internal paths/service names).
- SEC-03 success criteria explicitly requires: "only `status: ok` and a timestamp" for unauthenticated responses.

**Confidence:** HIGH -- the current code is straightforward to modify; the redaction logic is a simple conditional branch.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| flask-talisman | >=1.1.0 | HTTP security headers (CSP, HSTS, X-Frame-Options, X-Content-Type-Options) | Google Cloud Platform maintained; de facto Flask security header standard; OWASP-aligned defaults |
| flask-limiter | >=3.0.0 | Per-route and blueprint-level rate limiting | Only maintained Flask rate limiter with active development; 61 Context7 snippets; supports in-memory, Redis, Memcached backends |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| limits | (transitive) | Rate limit parsing and storage backends | Installed automatically by flask-limiter; provides the `memory://` storage implementation |

### Alternatives Considered

| Instead of | Could Use | Tradeoff | Evidence |
|------------|-----------|----------|----------|
| flask-talisman | Manual `after_request` hook | Full control over headers, but error-prone (easy to miss headers, no nonce support, no per-view overrides) | flask-talisman handles edge cases like conditional HSTS and CSP nonce injection that manual hooks typically miss |
| flask-talisman (GoogleCloudPlatform) | talisman (wntrblm fork) | The wntrblm fork is a community continuation; both are functionally identical as of 2025. The GoogleCloudPlatform version is the original and more widely referenced | PyPI: both `flask-talisman` and `talisman` packages exist |
| flask-limiter in-memory | flask-limiter + Redis | Redis survives restarts and supports multi-worker; but adds an infrastructure dependency for a single-worker deployment | Flask-Limiter docs explicitly state in-memory is acceptable for single-process; `gunicorn.conf.py` documents `workers=1` constraint |

**Installation:**
```bash
cd backend && uv add flask-talisman flask-limiter
```

## Architecture Patterns

### Recommended Integration Points

```
backend/app/
  __init__.py         # Add Talisman(app, ...) and Limiter(app, ...) in create_app()
  routes/
    health.py         # Modify readiness() to check auth and redact sensitive fields
    webhook.py        # Rate limit applied via blueprint-level limiter.limit()
    __init__.py       # (no change -- blueprint registration order is correct)
```

### Pattern 1: Extension Initialization in App Factory

**What:** Initialize flask-talisman and flask-limiter in `create_app()` after CORS setup and before blueprint registration.
**When to use:** Always -- Flask extensions must be initialized with the app instance before routes are registered so that `before_request`/`after_request` hooks are in place.
**Example:**

```python
# Source: Context7 /googlecloudplatform/flask-talisman + /alisaifee/flask-limiter
from flask_talisman import Talisman
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

def create_app(config=None):
    app = OpenAPI(__name__, info=API_INFO, doc_prefix="/docs")
    # ... existing config loading ...

    # Security headers
    talisman = Talisman(
        app,
        force_https=os.environ.get("FORCE_HTTPS", "false").lower() == "true",
        frame_options="DENY",
        strict_transport_security=True,
        strict_transport_security_max_age=31536000,
        content_security_policy={
            "default-src": "'self'",
            "script-src": ["'self'", "'unsafe-inline'"],  # needed for Swagger UI
            "style-src": ["'self'", "'unsafe-inline'"],   # needed for Swagger UI
            "img-src": ["'self'", "data:"],
        },
        content_security_policy_report_only=False,
    )

    # Rate limiting
    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=[],  # No global default -- limits applied per-blueprint
        storage_uri="memory://",
        strategy="fixed-window",
    )

    # Store on app for blueprint-level access
    app.extensions["limiter"] = limiter

    # ... register blueprints ...
```

### Pattern 2: Blueprint-Level Rate Limits

**What:** Apply rate limits at the blueprint level for webhook and admin routes using `limiter.limit()(blueprint)`.
**When to use:** When an entire group of routes should share the same rate limit.
**Example:**

```python
# Source: Context7 /alisaifee/flask-limiter - Blueprint recipe
# In register_blueprints() or create_app() after blueprint imports:
limiter = app.extensions["limiter"]

# Webhook ingestion: 20 requests per 10 seconds per IP
limiter.limit("20/10seconds")(webhook_bp)

# GitHub webhook: 30 requests per minute per IP
limiter.limit("30/minute")(github_webhook_bp)

# Admin routes: 120 requests per minute per IP (generous for frontend SPA)
limiter.limit("120/minute")(triggers_bp)
# ... apply to other admin blueprints ...

# Exempt health and docs from rate limiting
limiter.exempt(health_bp)
```

### Pattern 3: Custom 429 JSON Response Handler

**What:** Override Flask's default HTML 429 response with a JSON response matching the project's error format.
**When to use:** Always -- the project's error handlers in `create_app()` return JSON.
**Example:**

```python
# Source: Context7 /alisaifee/flask-limiter - Custom 429 handler recipe
from flask import jsonify, make_response

@app.errorhandler(429)
def ratelimit_handler(e):
    return make_response(
        jsonify(error=f"Rate limit exceeded: {e.description}"),
        429,
    )
```

### Pattern 4: Health Endpoint Conditional Redaction

**What:** Check whether the request is authenticated (via the auth middleware from Phase 3) and return a minimal or full response accordingly.
**When to use:** On the `/health/readiness` endpoint only.
**Example:**

```python
# In health.py
from datetime import datetime, timezone

@health_bp.get("/readiness")
def readiness():
    # Phase 3 auth middleware sets this (or similar) on the request/g object
    is_authenticated = getattr(g, "authenticated", False)

    if not is_authenticated:
        # SEC-03: Unauthenticated callers get minimal response
        return {
            "status": "ok",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, 200

    # Full response for authenticated callers (existing logic)
    # ... existing health check code ...
```

### Anti-Patterns to Avoid

- **Setting CSP too strict on first deploy:** A `default-src: 'self'` CSP without `'unsafe-inline'` for scripts/styles will break Swagger UI (`/docs`). Either relax the global CSP to allow inline scripts/styles or use flask-talisman's per-view decorator to set a different CSP for the docs blueprint.
- **Applying rate limits to SSE endpoints:** Long-lived SSE connections should not be rate-limited on the initial request in the same way as API calls. The connection itself is a single request that stays open. If SSE endpoints are behind admin blueprints with rate limits, ensure the limit is generous enough that normal reconnect behavior (browser EventSource auto-reconnects) does not trigger 429s.
- **Using `force_https=True` without a TLS terminator:** The development setup uses plain HTTP. Enabling forced HTTPS redirect without a reverse proxy that terminates TLS will create infinite redirect loops. Use an environment variable to control this.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Security headers | Manual `after_request` hook setting 4+ headers | flask-talisman | Per-view overrides, nonce support, HSTS preload support, CSP dictionary syntax; manual hooks miss edge cases and are harder to audit |
| Rate limiting | In-memory dict with timestamps + `before_request` hook | flask-limiter | Handles sliding windows, fixed windows, per-IP keying, storage backend abstraction, Retry-After headers, blueprint exemptions; custom solutions invariably have race conditions under concurrent greenlets |
| IP extraction | `request.remote_addr` with custom proxy header parsing | `flask_limiter.util.get_remote_address` | Correctly handles proxy trust configuration; avoids IP spoofing via X-Forwarded-For when behind trusted proxies |

**Key insight:** Security primitives are deceptively simple to implement but notoriously hard to get right under edge conditions (concurrent requests, proxy chains, header injection). The Flask ecosystem has mature, audited extensions for all three requirements.

## Common Pitfalls

### Pitfall 1: flask-talisman Breaks Swagger UI

**What goes wrong:** Swagger UI at `/docs` uses inline JavaScript and CSS. A strict CSP (`default-src: 'self'`) blocks these, rendering the docs page blank or non-functional.
**Why it happens:** flask-talisman applies CSP globally to all responses by default.
**How to avoid:** Include `'unsafe-inline'` in `script-src` and `style-src` directives globally (acceptable for an internal tool), OR use the `@talisman()` per-view decorator to exempt or relax CSP on the docs blueprint.
**Warning signs:** Swagger UI loads but interactive features (Try It Out, response display) do not work; browser console shows CSP violation errors.

### Pitfall 2: force_https Redirect Loop in Development

**What goes wrong:** Local development uses `http://localhost:20000`. With `force_https=True`, flask-talisman redirects every request to `https://localhost:20000`, which has no TLS listener, causing a redirect loop or connection refused.
**Why it happens:** flask-talisman's default is `force_https=True`.
**How to avoid:** Set `force_https=False` by default and enable it via environment variable (`FORCE_HTTPS=true`) when deploying behind a TLS-terminating reverse proxy.
**Warning signs:** Browser shows ERR_TOO_MANY_REDIRECTS or connection refused after adding flask-talisman.

### Pitfall 3: Rate Limiter Returns HTML 429 Instead of JSON

**What goes wrong:** Flask-limiter's default 429 response is an HTML page (`<title>429 Too Many Requests</title>`). The frontend `apiFetch()` expects JSON error responses.
**Why it happens:** Flask's default error handler returns HTML for HTTP errors.
**How to avoid:** Register a custom `@app.errorhandler(429)` that returns `jsonify(error="...")` -- matching the project's existing error handler pattern (see `create_app()` lines 275-289).
**Warning signs:** Frontend shows "Failed to parse JSON" errors when rate limit is hit.

### Pitfall 4: Rate Limit on Admin Blueprints Blocks SSE Reconnect

**What goes wrong:** Browser's EventSource auto-reconnects every few seconds when a connection drops. If admin routes have a tight rate limit (e.g., 10/minute), SSE reconnection attempts quickly exhaust the limit, blocking all admin API calls from that IP for the remainder of the window.
**Why it happens:** Each SSE reconnect is a new HTTP request counted against the rate limit.
**How to avoid:** Set admin rate limits generously (120+/minute) or exempt specific SSE streaming endpoints from rate limiting via `@limiter.exempt` on the streaming routes.
**Warning signs:** After a brief network interruption, the frontend cannot load any admin pages; browser DevTools shows 429 responses.

### Pitfall 5: Health Endpoint Redaction Breaks Monitoring

**What goes wrong:** Internal monitoring tools (if any) that call `/health/readiness` without an API key get the redacted response and cannot see component health status.
**Why it happens:** SEC-03 requires unauthenticated responses to contain only status and timestamp.
**How to avoid:** Ensure internal monitoring is configured with a valid API key. Alternatively, keep `/health/liveness` fully open (it returns only `200 OK` with no body) for basic up/down monitoring, and require auth only for `/health/readiness`.
**Warning signs:** Monitoring dashboards show "healthy" for a degraded system because they only see `{"status": "ok"}`.

## Experiment Design

### Recommended Experimental Setup

This phase's changes are deterministic (header presence, HTTP status codes) rather than stochastic, so traditional experiment design (independent/dependent variables, statistical significance) does not apply. Instead, the verification approach is acceptance testing.

**Independent variables:** Request attributes (IP, rate, auth status, endpoint path)
**Dependent variables:** Response headers, HTTP status codes, response body content
**Controlled variables:** Server configuration (single-worker, in-memory storage, same CSP policy)

**Baseline comparison:**
- Method: Current behavior (no security headers, no rate limits, full health response)
- Expected performance: All requests succeed with 200, no security headers present, health endpoint exposes execution IDs and startup warnings
- Target: All four security headers present on every response; 429 after 20 webhook requests in 10 seconds; health endpoint returns minimal response without auth

**Acceptance test plan:**
1. `curl -I http://localhost:20000/admin/triggers` (with API key) -- verify CSP, HSTS, X-Frame-Options: DENY, X-Content-Type-Options: nosniff headers present
2. Loop 21 `curl -X POST http://localhost:20000/` requests in rapid succession -- verify 21st returns HTTP 429
3. `curl http://localhost:20000/health/readiness` (no API key) -- verify response contains only `status` and `timestamp`, no execution IDs or warnings
4. `curl http://localhost:20000/health/readiness` (with API key) -- verify full component details are still returned
5. Open `http://localhost:3000` in browser -- verify Swagger UI at `/docs` still works (no CSP blocking)
6. Start an execution and open the SSE stream in browser -- verify streaming still works with security headers

### Recommended Metrics

| Metric | Why | How to Compute | Baseline |
|--------|-----|----------------|----------|
| Security header presence | SEC-01 validation | Parse `curl -I` response headers; check for 4 required headers | 0 of 4 present |
| 429 threshold accuracy | SEC-02 validation | Send N requests in burst, record first 429 occurrence | No 429 ever returned |
| Health redaction completeness | SEC-03 validation | Parse JSON response body, check key set against allowlist | Full component data exposed |
| Swagger UI functionality | Regression check | Manually verify `/docs` page loads and "Try It Out" works | Working |
| SSE stream delivery | Regression check | Open execution stream, verify events arrive | Working |

## Verification Strategy

### Recommended Verification Tiers for This Phase

| Item | Recommended Tier | Rationale |
|------|-----------------|-----------|
| Security headers present on responses | Level 1 (Sanity) | `curl -I` immediately verifiable |
| Rate limit returns 429 after threshold | Level 2 (Proxy) | Requires burst test script; quick to run |
| Health endpoint redaction for unauthenticated callers | Level 1 (Sanity) | `curl` without API key, check JSON |
| Swagger UI still functional | Level 2 (Proxy) | Manual browser check |
| SSE streaming unaffected | Level 2 (Proxy) | Manual browser check or automated test |
| Rate limit does not break frontend normal usage | Level 3 (Deferred) | Requires full frontend interaction testing |

**Level 1 checks to always include:**
- Response to any endpoint includes `Content-Security-Policy` header
- Response to any endpoint includes `Strict-Transport-Security` header
- Response to any endpoint includes `X-Frame-Options: DENY`
- Response to any endpoint includes `X-Content-Type-Options: nosniff`
- `/health/readiness` without auth returns only `status` and `timestamp` keys
- `/health/liveness` still returns 200 with no auth required

**Level 2 proxy metrics:**
- 20 rapid `POST /` requests succeed; 21st returns 429
- `/docs` page renders and "Try It Out" button works in browser
- SSE streaming endpoint (`/admin/executions/{id}/stream`) delivers events after adding headers

**Level 3 deferred items:**
- Frontend end-to-end test confirms no regressions with security headers
- Load testing confirms admin rate limit does not interfere with normal multi-page SPA navigation
- Verify rate limit behavior after server restart (in-memory state resets -- acceptable for single-worker)

## Production Considerations (from KNOWHOW.md)

KNOWHOW.md is an empty placeholder. The following considerations are derived from codebase analysis:

### Known Failure Modes

- **In-memory rate limit state lost on restart:** If the server restarts, all rate limit counters reset to zero. An attacker who observes the restart has a window of full burst capacity. This is acceptable for a single-user internal deployment but would need Redis-backed storage for production-grade rate limiting.
  - Prevention: Document the limitation; plan Redis migration as part of the horizontal scaling work (referenced in `gunicorn.conf.py` docstring).
  - Detection: Monitor for rate limit 429 counts in access logs; a sudden drop to zero after restart is expected.

- **CORS and Talisman header interaction:** flask-talisman and flask-cors both modify response headers via `after_request` hooks. Both use standard Flask hook registration and do not conflict, but the order of initialization determines hook execution order. Initialize CORS before Talisman so that CORS headers are set first and Talisman's headers are added after (no overwrite conflict since they set different headers).
  - Prevention: In `create_app()`, keep the CORS initialization before Talisman initialization.
  - Detection: Check `curl -I` output for both CORS (`Access-Control-Allow-Origin`) and security headers coexisting.

### Scaling Concerns

- **At current scale (single-worker, single-machine):** In-memory rate limiting is correct and efficient. No external dependencies needed.
- **At production scale (multi-worker or multi-machine):** flask-limiter must be reconfigured with `storage_uri="redis://..."`. This is a one-line config change in `create_app()` plus a Redis infrastructure dependency. The `gunicorn.conf.py` already documents this constraint.

### Common Implementation Traps

- **Trap: Hardcoding CSP that breaks future frontend features.** If the frontend adds external CDN resources (fonts, scripts), the CSP must be updated to allow them. Use environment variables for CSP overrides or at minimum document the CSP policy clearly.
  - Correct approach: Define CSP as a Python dict in `create_app()` with comments explaining each directive. Consider making CSP configurable via environment variable for production flexibility.

- **Trap: Rate limiting the docs endpoint.** Swagger UI makes multiple XHR requests to load the OpenAPI spec. If the docs blueprint inherits a strict admin rate limit, the spec may fail to load.
  - Correct approach: Exempt the docs blueprint from rate limiting via `limiter.exempt(docs_bp)` or ensure it's not covered by any blueprint-level limit.

## Code Examples

Verified patterns from official sources:

### Initialize Talisman with Safe Defaults for API Backend

```python
# Source: Context7 /googlecloudplatform/flask-talisman - Constructor API
from flask_talisman import Talisman

talisman = Talisman(
    app,
    force_https=os.environ.get("FORCE_HTTPS", "false").lower() == "true",
    frame_options="DENY",
    strict_transport_security=True,
    strict_transport_security_max_age=31536000,  # 1 year
    strict_transport_security_include_subdomains=True,
    content_security_policy={
        "default-src": "'self'",
        "script-src": ["'self'", "'unsafe-inline'"],
        "style-src": ["'self'", "'unsafe-inline'"],
        "img-src": ["'self'", "data:"],
        "connect-src": ["'self'"],
    },
    referrer_policy="strict-origin-when-cross-origin",
)
```

### Initialize Flask-Limiter with In-Memory Storage

```python
# Source: Context7 /alisaifee/flask-limiter - Initialization recipe
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],  # Apply limits per-blueprint, not globally
    storage_uri="memory://",  # Safe for workers=1 (see gunicorn.conf.py)
    strategy="fixed-window",
)
```

### Apply Blueprint-Level Rate Limits

```python
# Source: Context7 /alisaifee/flask-limiter - Blueprint recipe
limiter.limit("20/10seconds")(webhook_bp)
limiter.limit("30/minute")(github_webhook_bp)
limiter.exempt(health_bp)
```

### Custom JSON 429 Error Handler

```python
# Source: Context7 /alisaifee/flask-limiter - Error handler recipe
from flask import jsonify, make_response

@app.errorhandler(429)
def ratelimit_handler(e):
    return make_response(
        jsonify(error=f"Rate limit exceeded: {e.description}"),
        429,
    )
```

### Conditional Health Endpoint Response

```python
# Application-specific pattern
from datetime import datetime, timezone
from flask import g

@health_bp.get("/readiness")
def readiness():
    is_authenticated = getattr(g, "authenticated", False)

    if not is_authenticated:
        return {
            "status": "ok",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, 200

    # Full diagnostics for authenticated callers
    health = {"status": "ok", "components": {}}
    # ... existing component checks ...
    return health, status_code
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact | Reference |
|--------------|------------------|--------------|--------|-----------|
| Manual security header setting via `after_request` | flask-talisman extension | 2017+ | Eliminates header-by-header management; provides per-view overrides and CSP nonce support | GoogleCloudPlatform/flask-talisman |
| Custom rate limit decorators with in-memory dicts | flask-limiter with pluggable storage | 2020+ (v2.0+) | Standardized rate limit syntax, storage abstraction, blueprint support, automatic Retry-After header | alisaifee/flask-limiter |
| X-Frame-Options header | CSP frame-ancestors directive | 2023+ | CSP `frame-ancestors` supersedes X-Frame-Options in modern browsers, but X-Frame-Options is still needed for IE11 compat | OWASP Secure Headers |

**Deprecated/outdated:**
- `X-XSS-Protection` header: Deprecated by modern browsers (Chrome removed it in 2019). Do NOT add this header -- it can cause information leakage in some implementations. flask-talisman does not set it by default, which is correct.
- `flask-talisman` GoogleCloudPlatform version vs. `talisman` wntrblm fork: Both are functionally identical. The GoogleCloudPlatform version is the original and more widely installed via pip. Use `flask-talisman` (PyPI package name).

## Open Questions

1. **flask-openapi3 `OpenAPI` class compatibility with flask-talisman**
   - What we know: `OpenAPI` inherits from `Flask` (flask-openapi3 docs show it used identically to Flask). Talisman expects a Flask app instance.
   - What's unclear: Whether `OpenAPI` has any custom response handling that could conflict with Talisman's `after_request` hook. No documentation addresses this directly.
   - Recommendation: Test during implementation. The `OpenAPI` class is a thin wrapper over Flask; there is no reason to expect incompatibility, but verify by running `curl -I` after integration.

2. **Phase 3 auth mechanism details**
   - What we know: Phase 3 (API Authentication) is a dependency and must be complete before Phase 4. The health endpoint redaction (SEC-03) depends on knowing whether a request is authenticated.
   - What's unclear: The exact mechanism Phase 3 uses (API key in header, `g.authenticated` flag, decorator pattern). SEC-03 implementation must reference Phase 3's auth state.
   - Recommendation: During planning, assume Phase 3 sets a flag on Flask's `g` object (e.g., `g.authenticated = True/False`) or provides a utility function like `is_authenticated()`. The exact integration point will be determined after Phase 3 planning.

3. **Rate limit values for admin blueprints**
   - What we know: SEC-02 specifies "20 requests to POST / within 10 seconds" for the webhook endpoint. No specific rate limit values are defined for admin routes.
   - What's unclear: The optimal rate limit for admin routes that won't interfere with frontend SPA usage (page loads, background polling, SSE reconnects).
   - Recommendation: Start with 120 requests/minute for admin blueprints (2 per second). This accommodates rapid page navigation, AJAX calls, and SSE reconnects. Can be tuned post-deployment based on access log analysis. Make the limit configurable via environment variable.

## Sources

### Primary (HIGH confidence)
- Context7 `/googlecloudplatform/flask-talisman` -- Constructor API, per-view overrides, CSP configuration, initialization patterns
- Context7 `/alisaifee/flask-limiter` -- Initialization, blueprint limits, shared limits, custom 429 handlers, storage backends
- Flask-Talisman GitHub README (GoogleCloudPlatform/flask-talisman) -- All configuration options verified
- Flask-Limiter GitHub Discussion #373 -- In-memory storage safety for single-process confirmed
- OWASP Secure Headers Project -- CSP, HSTS, X-Frame-Options, X-Content-Type-Options recommendations

### Secondary (MEDIUM confidence)
- OWASP API Security Top 10 (2023) -- API3:2023 on property-level authorization (health endpoint redaction justification)
- Codebase analysis of `backend/app/__init__.py`, `backend/app/routes/health.py`, `backend/app/routes/webhook.py`, `backend/gunicorn.conf.py` -- Current state verified by reading source code

### Tertiary (LOW confidence)
- WebSearch on flask-talisman + SSE compatibility -- No specific documentation found; assessed as benign based on Talisman's `after_request` hook mechanism (headers are added to all responses including streaming)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- flask-talisman and flask-limiter are the established Flask extensions for these concerns; no competing alternatives with comparable adoption
- Architecture: HIGH -- Integration points (app factory, blueprint registration) are well-documented patterns verified via Context7
- Paper recommendations: HIGH -- OWASP security header guidance is industry standard; flask extension APIs are verified via Context7
- Pitfalls: HIGH -- Each pitfall is derived from documented behavior (CSP blocking inline scripts, force_https redirect, rate limit on SSE reconnect) with concrete avoidance strategies

**Research date:** 2026-02-28
**Valid until:** 2026-04-28 (60 days -- stable domain; security header standards and Flask extension APIs change slowly)
