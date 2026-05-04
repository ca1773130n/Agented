# v0.5.13 — Deploy story

Spec: `docs/superpowers/specs/2026-05-04-v0.5.13-deploy-story-design.md`
Plan: `docs/superpowers/plans/2026-05-04-v0.5.13-deploy-story.md`

E-B piece. Make Agented production-deployable on (a) a single host
(macOS launchd / Linux systemd) and (b) a container runtime, with a
runbook, env-var validator, healthcheck CLI, and CI/CD release
workflow that produces a tagged image at GHCR.

After v0.5.13, the B piece of E (deploy story) is done. Next: D
(rate limiting, v0.5.14), then E (backups, v0.5.15).
