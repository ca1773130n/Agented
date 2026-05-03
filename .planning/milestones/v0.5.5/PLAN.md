# v0.5.5 — Restore Agented chat components (path B, local half)

Spec: `docs/superpowers/specs/2026-05-03-v0.5.5-restore-and-upstream-chat-components-design.md`
Plan: `docs/superpowers/plans/2026-05-03-v0.5.5-restore-and-upstream-chat-components.md`
Recon: `.planning/milestones/v0.5.5/RECON.md`
Audit: `.planning/milestones/v0.5.5/AUDIT.md`

Path B (restore + upstream + parallel) — **local half only.** v0.5.5
restores the 8 chat components deleted in `b2ee00d` from `b2ee00d~1`,
deletes the v0.5.4 translation wrapper, and audits each restored
component for upstream PR candidacy. Upstream PR dispatch deferred
to v0.5.6 as a dedicated milestone (8 cross-repo PRs each deserve
careful design review).
