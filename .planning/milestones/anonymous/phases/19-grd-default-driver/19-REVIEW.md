---
phase: 19-grd-default-driver
wave: all
plans_reviewed: [19-01, 19-02, 19-03, 19-04, 19-05, 19-06]
timestamp: 2026-06-13T00:00:00Z
blockers: 0
warnings: 2
info: 3
verdict: warnings_only
---

# Code Review: Phase 19 (all plans, all waves)

## Verdict: WARNINGS ONLY

Six plans across three waves implement the default-GRD driver spine end-to-end:
a precedence resolver + migration 158 (19-01), turn classifier (19-02), cwd/backend
fixes (19-03), GRD chat handler + PSM→chat-SSE bridge (19-04), the 3-way funnel
branch with byte-identical cliproxy isolation (19-05), and the operator frontend cap
(19-06). Every plan task maps 1:1 to feat+test+docs commits; the diff matches the
SUMMARY claims. No blockers. Two warnings concern a deferred-but-shipped frontend
binding and a watchdog-substituted full-suite gate.

## Stage 1: Spec Compliance

### Plan Alignment
No issues. 24 commits since merge-base eaccd62; each plan has a clean
feat → test → docs trio (19-01..19-06). All deviations in the SUMMARYs are real and
match git history:
- 19-02: conversational-opener substring bug fixed to word-boundary token match (4b15955).
- 19-03: third `backend:"claude"` literal in the `finish` delta caught and fixed (4c6192e).
- 19-05: pre-existing tests stubbed the removed `should_route_via_cli_agent` seam; re-pointed
  at `resolve_execution_driver` (0f74d6c) — correct, not scope creep.
- 19-06: `projectApi.update` type gap (`manager_super_agent_id`) and SA-surface
  reinterpretation (per-card on SuperAgentsPage) both documented.

### Research Methodology
Matches 19-RESEARCH.md. Resolver precedence (turn → SA → instance → project → global "grd"),
degrade requiring BOTH grd binary AND resolvable workspace, and the funnel branch point all
follow the research anchors. Bridge emits the wire strings `content_delta/tool_use/finish/error`
(NOT the `ChatDeltaType` enum `tool_call`) per §10 risk 2 — verified in grd_chat_bridge.py:129-161.

### Known Pitfalls
Both named risks mitigated: cliproxy regression (risk 1) isolated via the verbatim
`_run_cliproxy()` closure shared by the grd-conversational fallthrough; session leak (risk 5)
handled by `stop()` delegating to `ProjectSessionManager.stop_session`. `subscribe_raw` is
registered BEFORE `handler.start()` so early PSM events are not lost (streaming_helper.py).

### Eval Coverage
No issues. 19-EVAL.md S1-S7 / P1-P6 all map to test files that exist and were run.
Resolver, classifier, handler, bridge, funnel-regression, and DriverSelector suites are
all present and green per the SUMMARYs. EVAL is computable against the implementation.

## Stage 2: Code Quality

### Architecture
Consistent with existing patterns. `resolve_execution_driver` is additive beside
`should_route_via_cli_agent` (lazy intra-package imports for the DB accessors avoid cycles);
`GrdChatSessionHandler` mirrors the sibling goal_loop/grd_evolve handlers and reuses the real
`create_session(forge_bundle=, super_agent_id=)` kwargs; migration 158 uses the PRAGMA-guarded
idempotent ALTER convention and is registered as `(158,"driver_columns",...)` in V07_MIGRATIONS.
Symbol audit confirms `subscribe_raw`/`unsubscribe_raw`/`get_handler` all exist and the funnel's
`_last_user_content`/`_super_agent_id`/`_project_id`/`instance_id`/`model`/`on_complete` are all
in scope at the call site.

### Reproducibility
N/A — routing/UI feature, no stochastic experimental code. Degrade and read-failure paths are
default-safe (every DB read wrapped, outer guard returns the legacy choice on any exception).

### Documentation
Adequate-to-good. Resolver and bridge carry precedence/mapping tables in docstrings with
RESEARCH section references. The `_run_cliproxy` closure has an inline "do NOT edit — byte
identity is success-criterion-3" guard comment.

### Deviation Documentation
SUMMARY.md files match git history. 19-05 and 19-06 both transparently disclose the
watchdog substitution and the pre-existing unrelated build/test baselines.

## Findings Summary

| # | Severity | Stage | Area | Description |
|---|----------|-------|------|-------------|
| 1 | WARNING | 2 | Forward-compat binding | Transcript "View GRD session" link binds to `grd_session_id`/`psm_session_id`/`session_id` on the `finish` delta, but `bridge_psm_to_chat` emits only `finish_reason` — link never renders until a backend follow-up adds the session id to the finish payload. |
| 2 | WARNING | 1 | Full-suite gate | Backend full serial suite hung at the documented ~40-48% point; only a targeted 305-test substitution was run. Disclosed, but the full gate was not satisfied. |
| 3 | INFO | 1 | Anti-regression scope | `backend_type="claude"` remains at grd_routes.py:483, but it is in `_resolve_manager_agent` (default backend for a newly-created manager SA), NOT in `project_chat`. Out of REQ-12 scope and pre-existing; project_chat itself is claude-literal-free. |
| 4 | INFO | 2 | Pre-existing build error | `just build` fails only on the phase-17 `AnswerGroundednessCard.vue` TS2345 error; phase 19 touched zero lines of it. |
| 5 | INFO | 2 | grd_command source | Funnel passes `classification.get("grd_command")` into the handler, which also re-derives via `_resolve_grd_command`; harmless redundancy, single source of truth is GRD_COMMAND_MAP. |

## Recommendations

1. (W1) File a backend follow-up so `bridge_psm_to_chat` surfaces the PSM session id on the
   `finish` delta (e.g. `{"finish_reason":..., "grd_session_id": <psess-id>}`). Until then the
   transcript link is dormant by design — acceptable for this frontend-cap plan, but track it so
   success-criterion-5's "chat shows GRD session linkage" becomes live rather than forward-compatible-only.
2. (W2) Before merge, attempt the full backend suite once more under the 12-minute watchdog on a
   clean run; if it still hangs at the known point, the disclosed 305-test targeted substitution
   (execution/streaming/harness/classifier/cli_agent) is an acceptable stand-in per CLAUDE.md — keep
   the disclosure in the PR body.
3. (I3) Optional: when convenient, migrate the `_resolve_manager_agent` default off the `claude`
   literal toward a configured default backend, to fully honor the house "no claude-only default" rule
   beyond phase 19's scope.
