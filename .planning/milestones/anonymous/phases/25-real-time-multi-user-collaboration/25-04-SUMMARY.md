# 25-04 SUMMARY — optional OIDC SSO

**Status:** DONE. `app/services/oidc_service.py` (authlib code-flow), `app_litestar/routes/oidc.py` (start/callback), `app/db/oidc_identities.py` + `app/db/schema/_oidc_identities.py` + `V08_MIGRATIONS`, `app_litestar/routes/health.py` (provider list), `app_litestar/main.py` registration, `pyproject.toml`/`uv.lock` (authlib pin), frontend `LoginPage.vue` (SSO buttons) + `api/auth.ts` + `api/system.ts` + 4 locales. Tests: `tests/test_oidc_auth.py` (11, green).

- Authorization-code flow (Google/GitHub/Okta/Microsoft): maps the verified `(issuer, subject)` to a user via the `oidc_identities` table, then issues a session through the EXISTING `create_session` + litestar-cookie path — the X-API-Key auth path is literally untouched.
- authlib performs JWT/JWKS validation (locked decision #3 — no hand-rolled signature verification; vendored httpx alone was insufficient). State + nonce are mandatory against code interception/replay; state reuses `generate_csrf_token`.
- `registration_open()`/`AGENTED_DISABLE_SIGNUP` semantics preserved — SSO never auto-provisions past a closed instance (locked decision #6). `/health/auth-status` surfaces the configured provider list; `LoginPage` renders SSO buttons; sso/oidc strings key-identical across en/ko/ja/zh.

No Phase-25 security-hardening fix was attributed to this plan — the callback only adds a new way to arrive at the same session cookie, and the subject-mapping/signup-gate interaction was in scope from the start.
