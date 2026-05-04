# v0.5.14 — Rate limiting

Spec: `docs/superpowers/specs/2026-05-04-v0.5.14-rate-limiting-design.md`
Plan: `docs/superpowers/plans/2026-05-04-v0.5.14-rate-limiting.md`

E-D piece. Extend `RateLimitMiddleware` to cover all `/api/*` and
`/admin/*` with per-API-key keying (fall back to per-IP), per-route
overrides via `requires_rate_limit` guard, and env-var-tunable
defaults. Anti-bruteforce on auth endpoints (login=5/min/IP,
forgot-password=3/min/IP) and anti-DoS on subprocess-install routes
(10/hour/key).

After v0.5.14 the D piece of E is done. Next: E (backups, v0.5.15).
