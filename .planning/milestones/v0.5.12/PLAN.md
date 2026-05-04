# v0.5.12 — Auth depth (RBAC enforcement + session lifecycle)

Spec: `docs/superpowers/specs/2026-05-04-v0.5.12-auth-depth-design.md`
Plan: `docs/superpowers/plans/2026-05-04-v0.5.12-auth-depth.md`

E-A piece. Coarse method+prefix RBAC enforcement at the middleware
level + per-route guard overrides for sensitive operations. Session
lifecycle hardening: idle timeout, sliding refresh (via existing
`last_used_at`), token rotation with 5-second grace window, revocation
hooks on role change / key rotation / explicit logout / admin revoke.
New `session_events` audit table.

After v0.5.12, the A piece of E (auth depth) is done. v0.5.13 begins
B (deploy story).
