# Hardening Audit 02 — Auth, Authorization, Secrets, Rate-Limiting

Scope: `backend/app/services/{rbac,secret_vault,webhook_validation,rate_limit,permission_prompt,audit_log,audit,model_auth_constraints}_service.py`, `app_litestar/middleware.py`, `app_litestar/routes/{auth,auth_management,rbac}.py`, plus supporting `auth.py`, `auth_guards.py`, `rate_limit_guard.py`, `routes/admin_tooling.py`, `routes/webhooks.py`, `db/sessions.py` (followed for verification).

Severity counts: **CRITICAL 1 · HIGH 4 · MEDIUM 5 · LOW 3**

---

## CRITICAL

### C1 — Secret-vault reveal/list endpoints gated only by coarse role, not admin
**`app_litestar/routes/admin_tooling.py:301-367` (router) + `auth_guards.py:33-37` (ROLE_REQUIRED)**

The secrets router (`/admin/secrets`) registers `list_secrets_endpoint`, `get_secret_detail`, and crucially `reveal_secret` (`admin_tooling.py:320-329`, returns **plaintext** secret value) with **no per-route `requires_role` guard**. Enforcement falls back entirely to the coarse `ROLE_REQUIRED` table:
- `GET /admin/` → `viewer` ⇒ any **viewer** can enumerate all secret metadata (`GET /admin/secrets`, `GET /admin/secrets/{id}`).
- `POST /admin/` → `editor` ⇒ any **editor** can call `/admin/secrets/{id}/reveal` and read decrypted plaintext, and `create`/`update` secrets.

The single most sensitive operation in the system (decrypt-and-return plaintext) is reachable by a non-admin role. The codebase already has the mechanism (`requires_role("admin")` guard, used on `auth_management.py:34,53`) but it is not applied here.

**Fix:** Add `guards=[requires_role("admin")]` to the `secrets_router` (or per-handler on `reveal_secret`, `create_secret`, `update_secret`, `delete_secret`, `get_secret_detail`, `list_secrets_endpoint`). Reveal in particular should arguably require a step-up / re-auth. Add a coarse-table safety net entry for `/admin/secrets` → admin so a missing decorator can never silently downgrade.

---

## HIGH

### H1 — Rate-limited auth endpoints keyed on spoofable client IP; in-memory only
**`app_litestar/middleware.py:422-447` (`_client_ip`, `_resolve_rate_key`) + `routes/auth.py:50,94,191,216`**

`login`, `signup`, `forgot-password`, `reset-password` are in `_AUTH_BYPASS_PREFIXES` (`middleware.py:57-60`), so no principal is ever stashed; `_resolve_rate_key` falls to `("ip", _client_ip(scope))`. `_client_ip` trusts `X-Forwarded-For`/`X-Real-IP` **unconditionally** (`middleware.py:427-432`), taking the left-most value. An attacker rotates `X-Forwarded-For` per request to get unlimited fresh buckets, fully bypassing the 5/min login throttle → unthrottled credential stuffing / password-reset enumeration.

Compounding: the limiter is process-local in-memory (`_FixedWindowLimiter`, `middleware.py:360-384`). The docstring asserts `workers=1` so it is "safe," but `gunicorn.conf.py` workers is a config value; any scale-out silently multiplies every limit by N and resets on restart/deploy.

**Fix:** Only trust `X-Forwarded-For` when behind a known proxy (configurable trusted-proxy count; take the right-most untrusted hop), else use `scope["client"]`. Add an additional per-email throttle on login/reset. Move the limiter to a shared store (Redis) before any workers>1 deployment and gate startup if workers>1 with the in-memory limiter.

### H2 — Webhook replay protection disabled by default and not enabled at any call site
**`webhook_validation_service.py:139,168` + `routes/webhooks.py:101-126` + `trigger_dispatcher.py:90-92`**

`validate_webhook`/`validate_github` default `require_timestamp=False`. The GitHub route (`webhooks.py:119`) and the generic trigger dispatcher (`trigger_dispatcher.py:92`) both call `validate_signature` **only** — never `validate_timestamp` — so a captured valid request (correct HMAC) can be **replayed indefinitely**. The replay machinery exists but is dead code in production paths.

**Fix:** Enforce a timestamp header with `require_timestamp=True` on webhook receivers where the sender supports it (custom triggers), and add nonce/delivery-id dedup for GitHub (`X-GitHub-Delivery`) since GitHub does not send a timestamp header. At minimum reject deliveries whose `X-GitHub-Delivery` was already processed.

### H3 — Env API key principal silently elevated to admin
**`app_litestar/middleware.py:195-198`**

When `AGENTED_API_KEY` matches (`hmac.compare_digest`, good), the principal is hard-assigned `role="admin"`. The env key is a single shared static credential with no rotation, no per-user attribution (`principal_user_id` stays `None`), and grants the highest role. Combined with C1, holding the env key reveals every secret. Audit events for env-key actions have `actor=None`/no user, undermining traceability.

**Fix:** Treat the env key as a break-glass bootstrap credential only: scope it down (e.g. `operator`), require it be unset in production, or map it to a named service identity for audit. Log a startup warning when `AGENTED_API_KEY` is set in a non-bootstrap deployment.

### H4 — Password-reset token logged in clear to application log
**`routes/auth.py:204-208`**

`forgot_password` logs the live reset token into the `app.auth` logger ("link: /reset-password?token=%s"). Anyone with log read access (operators, log-aggregation sinks, SIEM, shared dev consoles) obtains a valid account-takeover token. Tokens in logs persist far longer than their intended short TTL and outside any access-controlled channel.

**Fix:** Do not log the token value. Log only "reset requested for <user_id>" and deliver the token via the intended out-of-band channel (email/SMS). If no mailer exists yet, write the token to a restricted-permission, short-retention file or admin-only endpoint, never the general app log.

---

## MEDIUM

### M1 — Bootstrap mode fails OPEN: zero roles ⇒ everyone is admin
**`app_litestar/middleware.py:155-161` + `auth.py:81-85` (`provide_caller`) + `rbac_service.py:81-83`**

Three independent code paths grant full access when no roles/keys exist: `ApiKeyMiddleware` lets every request through (`middleware.py:158-160`), `provide_caller` returns `role="admin"` (`auth.py:82-83`), and the legacy `require_role` decorator allows all (`rbac_service.py:82-83`). This is fail-open. A production DB that loses its `user_roles` rows (bad migration, restore from empty, manual error) instantly becomes fully unauthenticated-admin with no signal.

**Fix:** Make bootstrap mode require an explicit opt-in flag (e.g. `AGENTED_ALLOW_BOOTSTRAP=1`) that is off in production, mirroring the `AI_ACCOUNTS_ALLOW_NOAUTH` pattern already used for the sidecar. Emit a loud warning whenever bootstrap mode is active.

### M2 — `_path_requires_auth` allowlist matches any sub-path of webhook/oauth prefixes
**`app_litestar/middleware.py:47-70`**

`_AUTH_BYPASS_PREFIXES` includes `/api/webhooks/github` and `/api/oauth-callback`, matched via `path == prefix or path.startswith(prefix + "/")`. Any future handler mounted under those prefixes is silently unauthenticated. The webhook route itself is correctly HMAC-gated, but the broad prefix bypass is a latent footgun (e.g. an added `/api/webhooks/github/replay` debug route would be public).

**Fix:** Pin bypass to exact paths/methods (`POST /api/webhooks/github` only), or document and lint that nothing else may mount under these prefixes.

### M3 — `validate_timestamp` returns True for missing timestamp (fail-open by default)
**`webhook_validation_service.py:101-103`**

`if not timestamp_header: return True`. Combined with H2's `require_timestamp=False`, the default posture provides zero replay protection while appearing to validate. The fail-open default should at least be paired with an enforced caller contract.

**Fix:** Keep the helper as-is but flip production call sites to `require_timestamp=True` (see H2); add a test asserting receivers reject missing timestamps.

### M4 — `reveal_secret` re-fetches secret without re-checking existence ordering / IDOR by name
**`admin_tooling.py:320-329` + `secret_vault_service.py:218-236` (`get_secret_value`)**

`get_secret_value(secret_id_or_name, ...)` accepts an ID **or a name** (`secret_vault_service.py:224-228`). The route names the param `secret_id` but it is resolved by name fallback, so a caller can reveal a secret by guessing its name even without knowing its random ID — weakening the unguessable-ID protection. Low data-confidentiality impact only because of C1's missing authZ, but independently it broadens the lookup surface.

**Fix:** Have the reveal route resolve strictly by ID (`db_secrets.get_secret` only). Reserve name-based lookup for the internal execution path (`get_secrets_for_execution`), not the externally-reachable reveal endpoint.

### M5 — Secret decrypt failures during execution silently dropped (partial fail-open)
**`secret_vault_service.py:250-262` (`get_secrets_for_execution`)**

A secret that fails to decrypt (e.g. a key was rotated out of `AGENTED_VAULT_KEYS`) is logged at WARNING and **skipped**; the subprocess then runs with that env var absent. Depending on the downstream tool this can fail-open (tool proceeds with no credential / a default) rather than fail-closed (refuse to execute). No audit event is emitted for the decrypt failure.

**Fix:** Decide per-policy: either raise/abort the execution when a required secret can't be decrypted, or emit an audit event (`secret.decrypt_failed`) and surface it to the operator. Don't silently launch a job with missing secrets.

---

## LOW

### L1 — Audit SQLite-persist failure swallowed at DEBUG
**`audit_log_service.py:108-113`**

`except Exception: audit_logger.debug("Failed to persist audit event to SQLite: %s", exc)`. Security-relevant audit records can fail to persist with only a DEBUG line (invisible at default INFO). The in-memory ring + INFO log mitigate, but durable audit loss should be at least WARNING and ideally alertable.

**Fix:** Raise the level to WARNING/ERROR and add a metric/counter for audit-persist failures.

### L2 — Webhook `algorithm` allows sha1 fallback
**`webhook_validation_service.py:27,37-48,82`**

The `ALGORITHMS` map and prefix parsing accept `sha1`. SHA-1 HMAC is weak/deprecated; allowing the sender to select sha1 via header prefix lets a downgrade if a secret is short. (HMAC-SHA1 is not catastrophically broken, hence LOW.)

**Fix:** Drop sha1 from the accepted set; require sha256+. If a legacy sender needs sha1, gate it behind explicit per-trigger config rather than header-driven selection.

### L3 — `me` and reveal responses can leak existence; minor enumeration
**`routes/auth.py:128-137` + `admin_tooling.py:314-316`**

`me` returns a sentinel for api-key callers without a user; `get_secret_detail`/`reveal` distinguish 404 "not found" cleanly — acceptable, but combined with name-based reveal (M4) gives a name-enumeration oracle (200 vs 404). LOW given authZ should gate these.

**Fix:** Uniform 404 on both unknown-id and unauthorized once C1 is fixed.

---

## Things verified as CORRECT (no action)

- **Webhook HMAC uses `hmac.compare_digest`** (`webhook_validation_service.py:83`) — constant-time. Good.
- **Env-key check uses `hmac.compare_digest`** (`middleware.py:195`). Good (contrast: do NOT regress to `==`).
- **Session tokens**: `secrets.token_urlsafe(32)` = 256-bit (`db/sessions.py:45-47`); lookup is constant-time with fixed-length sentinel to avoid timing/length leak (`db/sessions.py:35-37,77-114`). Good.
- **Secrets at rest**: Fernet/MultiFernet (AES-CBC+HMAC) with key rotation, key never in DB, plaintext never logged in vault service (`secret_vault_service.py:1-94`). Good.
- **Audit diff redaction**: `_REDACTED_FIELDS = {webhook_secret, api_key, password, token, prompt_template}` excluded from field diffs (`audit_log_service.py:54-56,140-147`). Good — but note reveal endpoint still returns plaintext to the client (C1).
- **Permission-prompt registry** fails closed: timeout ⇒ `None` ⇒ caller falls back to claude's `ask`, never auto-allow (`permission_prompt_service.py:20-23,84-92`); `resolve` validates decision ∈ {allow,deny} and rejects double-resolve (`:101-109`). Good.
- **RBAC denials are audit-logged** with reason (`rbac_service.py:85-121`). Good.
