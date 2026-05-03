# v0.5.10 — Traces observability UI

Spec: docs/superpowers/specs/2026-05-03-v0.5.10-traces-observability-ui-design.md
Plan: docs/superpowers/plans/2026-05-03-v0.5.10-traces-observability-ui.md

First sub-piece of E (production hardening), narrowed to traces only.
Standalone /traces list + /traces/:id detail with live SSE updates
while a trace is running. Backend gets one new SSE route; rest of
the trace API surface (10 routes) was already complete.

agent_memory observability is v0.5.11.
