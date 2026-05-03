# v0.5.6 — Upstream PR dispatch (path B, upstream half)

Spec: `docs/superpowers/specs/2026-05-03-v0.5.5-restore-and-upstream-chat-components-design.md`
Audit: `.planning/milestones/v0.5.5/AUDIT.md`

Path B (restore + upstream + parallel) — **upstream half.** v0.5.5
restored Agented's 8 chat components from `b2ee00d~1` and audited
each for project-independence. v0.5.6 dispatches the per-component
PRs against `~/Developer/Projects/ai-accounts/packages/vue-styled/`.

7 of 8 PRs dispatched. The 8th (`AiChatPanel` orchestrator) is
deferred — its presentational-vs-orchestration extraction boundary
is opinionated and benefits from human review of the cut before
the PR opens.

This milestone has **zero local Agented source changes**. Its
deliverable is the cross-repo PRs and the documentation of what
shipped.
