# v0.5.11 — agent_memory observability UI

Spec: docs/superpowers/specs/2026-05-04-v0.5.11-agent-memory-observability-ui-design.md
Plan: docs/superpowers/plans/2026-05-04-v0.5.11-agent-memory-observability-ui.md

Second sub-piece of E-C (observability). Per-agent surface for memory:
working memory rendered as markdown, FTS5 recall search, threads list
with deep-linkable thread detail page. Read-only. Window-focus refresh
instead of SSE.

Zero new backend routes — agent_memory API was already complete.
After v0.5.11 the C piece of E is done; v0.5.12 begins A (auth depth).
