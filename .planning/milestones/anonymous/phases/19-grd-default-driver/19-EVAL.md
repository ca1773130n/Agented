# Evaluation Plan: Phase 19 — GRD Default Driver

**Designed:** 2026-06-13
**Designer:** Claude (grd-eval-planner)
**Method(s) evaluated:** Driver resolver (resolve_execution_driver), turn classifier (classify_turn), GrdChatSessionHandler + PSM bridge, funnel integration, cwd/backend bug fixes, frontend driver selector
**Reference plans:** 19-01 through 19-06 (resolver / classifier / cwd-fixes / handler+bridge / funnel / frontend)

---

## Evaluation Overview

Phase 19 is a behavioral/correctness phase — there are no score deltas to measure. The evaluation is entirely pass/fail: either a code path produces the correct routing decision, SSE event sequence, or UI state, or it does not. All six plans have named test files and explicit pass/fail conditions drawn from the REQ-10..REQ-13 requirements.

The critical risk is the cliproxy regression: any modification to `run_streaming_response` that disturbs the byte-identical conversational path is a silent correctness break that cannot be detected by unit tests that only cover the new GRD branch. This risk is explicitly isolated in plan 19-05 and gets its own Tier-2 regression check below.

No external benchmarks, datasets, or score thresholds exist. Evaluation is entirely test-suite-based with three deferred real-integration validations.

### Known Baselines (carve-outs for pass/fail judgement)

| Baseline defect | Carve-out rule |
|---|---|
| 7 pre-existing frontend test failures (RateLimitGauge, MarkdownContent, WorkingMemoryView, useTourMachine) | Gate is NO NEW failures vs these 7. A green run may still report 7 failures. |
| AnswerGroundednessCard.vue TS error (pre-existing, not in phase 19 files_modified) | `just build` failure attributed to phase 19 ONLY if the error appears in a file listed in plans 01-06. |
| `uv run pytest` full-suite hang at ~40-48% | Use watchdog substitution procedure (see Tier-2 §P6). Never present targeted runs as the full suite — disclose substitution. |

### Verification Level Summary

| Level | Count | Purpose |
|---|---|---|
| Sanity (L1) | 7 checks | Fast deterministic — resolver imports, unit tests per plan, ruff, frontend component tests, i18n parity |
| Proxy (L2) | 6 behavioral checks | Integration approximating real quality — precedence matrix, handler fake-PSM, SSE ordering, cliproxy regression, delegation cwd, watchdog procedure |
| Deferred (L3) | 3 validations | Requires live integration — real PSM spawn, operator UI observation, cross-backend LLM classifier |

---

## Level 1: Sanity Checks

**Purpose:** Fast deterministic checks (seconds). ALL must pass before progression.

### S1: resolve_execution_driver imports and returns a valid driver

- **Plan:** 19-01
- **What:** The function exists, is importable, and returns one of the three legal strings.
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "
  from app.services.cli_agent_runner_service import resolve_execution_driver
  result = resolve_execution_driver(backend='claude')
  assert result in ('cliproxy', 'cli_agent', 'grd'), f'Unexpected: {result}'
  print('OK:', result)
  "
  ```
- **Expected:** Prints `OK: grd` (global default) without error.
- **Failure means:** resolver not yet written, import error, or invalid return value — plan 19-01 Task 2 incomplete.

### S2: Migration 158 is registered

- **Plan:** 19-01
- **What:** The `(158, "driver_columns", _migrate_158_driver_columns)` tuple is present in `V07_MIGRATIONS`.
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "
  from app.db.migrations.v07_features import V07_MIGRATIONS
  assert any(t[0] == 158 for t in V07_MIGRATIONS), 'Migration 158 not registered'
  print('OK: migration 158 registered')
  "
  ```
- **Expected:** Prints `OK: migration 158 registered`.
- **Failure means:** Migration task in 19-01 Task 1 not complete; columns will be absent from DB.

### S3: test_cli_agent_runner.py precedence + degrade suite

- **Plan:** 19-01
- **What:** All precedence-matrix and degrade-path tests pass.
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_cli_agent_runner.py -q
  ```
- **Expected:** All tests collected and passing; no failures, no errors.
- **Failure means:** Resolver logic incorrect at one or more precedence levels, or degrade injection broken.

### S4: test_turn_classifier.py keyword + LLM-fallback tests

- **Plan:** 19-02
- **What:** classify_turn() returns correct shape/grd_command for keyword-clear and ambiguous turns; LLM fallback uses backend_kind/model_override.
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_turn_classifier.py -q
  ```
- **Expected:** All tests collected and passing.
- **Failure means:** Classifier keyword seeds, threshold, or LLM fallback wiring broken.

### S5: Ruff format check (all modified backend files)

- **Plan:** All backend plans (19-01 through 19-05)
- **What:** No ruff formatting violations across modified files (line-length=100, py310).
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && uv run ruff format --check app/services/cli_agent_runner_service.py app/services/turn_classifier_service.py app/services/execution_type_handler.py app/services/grd_chat_bridge.py app/services/streaming_helper.py app/services/sketch_execution_service.py app_litestar/routes/grd_routes.py app/db/projects.py app/db/project_sa_instances.py app/db/migrations/v07_features.py
  ```
- **Expected:** Exit code 0, no reformatting needed.
- **Failure means:** Ruff will reformat; run `uv run ruff format .` and re-commit.

### S6: Frontend component test — DriverSelector default + transcript linkage

- **Plan:** 19-06
- **What:** `DriverSelector.test.ts` passes: selector defaults to `grd`, offers three options, transcript renders GRD linkage.
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/frontend && npm run test:run -- --reporter=verbose src/components/projects/__tests__/DriverSelector.test.ts
  ```
- **Expected:** All tests in `DriverSelector.test.ts` pass. Failures in the 7 known-baseline files are acceptable and must NOT be counted against this check.
- **Failure means:** SuperAgentDriverSelector.vue or transcript linkage not correctly wired.

### S7: i18n 4-locale key parity for driver.* namespace

- **Plan:** 19-06
- **What:** All four locale files carry an identical set of `driver.*` keys.
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/frontend && node -e "
  const fs = require('fs');
  const locales = ['en', 'ko', 'ja', 'zh'].map(l => [l, JSON.parse(fs.readFileSync('src/locales/' + l + '.json', 'utf8'))]);
  const enKeys = Object.keys(locales[0][1]).filter(k => k.startsWith('driver'));
  for (const [l, obj] of locales.slice(1)) {
    const keys = Object.keys(obj).filter(k => k.startsWith('driver'));
    const missing = enKeys.filter(k => !keys.includes(k));
    const extra = keys.filter(k => !enKeys.includes(k));
    if (missing.length || extra.length) { console.error(l, 'missing:', missing, 'extra:', extra); process.exit(1); }
  }
  console.log('OK: all 4 locales have identical driver.* keys:', enKeys);
  "
  ```
- **Expected:** Prints `OK: all 4 locales have identical driver.* keys: [...]`.
- **Failure means:** A locale is missing driver.* entries; plan 19-06 i18n task incomplete.

**Sanity gate:** ALL seven checks must pass. Any failure blocks progression to Tier-2.

---

## Level 2: Proxy Metrics

**Purpose:** Behavioral integration tests approximating real quality. These run against fake/mocked dependencies; they do not require a live GRD binary or real PSM session.

**IMPORTANT:** These proxy checks are behavioral pass/fail, not score metrics. They are not validated substitutes for the real integration (see Tier-3). Treat a Tier-2 pass as "structurally correct" — not "end-to-end verified."

### P1: Resolver precedence matrix — all 7 levels, including degrade

- **Plan:** 19-01
- **What:** Each precedence level wins in order; degrade paths return `cli_agent`; read failures do not crash.
- **Command:** (covered by S3 — `uv run pytest tests/test_cli_agent_runner.py -q`; listed separately as proxy because it is the primary behavioral gate for REQ-10)
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_cli_agent_runner.py -v -k "precedence or degrade or read_failure"
  ```
- **Pass condition:** Every parametrized precedence case asserts the correct winner; `_grd_available=lambda: {"grd_tools_available": False}` returns `cli_agent`; `_resolve_workspace` raising `ValueError` returns `cli_agent`; monkeypatched accessor raising returns `cli_agent` (not an exception).
- **Blind spots:** Tests inject degrade callables directly — real binary availability is NOT tested here (deferred to D1).
- **Correlation with real quality:** HIGH for routing logic correctness; does not cover DB migration idempotency under concurrent writes.

### P2: GrdChatSessionHandler with fake PSM — cmd, cwd, forwarding

- **Plan:** 19-04
- **What:** Handler builds the correct `/grd:quick` command, resolves cwd, forwards `forge_bundle` and `super_agent_id` to `create_session`.
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_grd_chat_handler.py -v
  ```
- **Pass condition:** `create_session` is called with a `cmd` list containing `/grd:quick`, a non-None resolved cwd, and the correct `forge_bundle`/`super_agent_id` values; `HANDLER_REGISTRY['grd_chat']` returns the handler; `get_handler('grd_chat')` succeeds.
- **Blind spots:** Fake PSM — does not verify actual PSM process lifecycle or stream-json parsing against a real binary.

### P3: SSE bridge delta ordering + error propagation

- **Plan:** 19-04
- **What:** `bridge_psm_to_chat` emits `push_delta` events in the correct order and maps error events to `('error', ...)` + `push_status('error')`.
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_grd_chat_bridge.py -v
  ```
- **Pass condition:** Given a fake PSM event sequence `[text, tool_use, result]`, observed `push_delta` calls are in order `content_delta → tool_use → finish`; `push_status('complete')` is called; an injected `error` event produces `('error', ...)` call and `push_status('error')`.
- **Blind spots:** Uses in-memory event feed, not a real subprocess pipe. Real stream-json line parsing is not tested.

### P4: Cliproxy regression — byte-identical delta sequence (TOP RISK)

- **Plan:** 19-05
- **What:** A conversational turn routed through the GRD branch of `run_streaming_response` falls through `classify_turn()` back into the cliproxy block and produces a byte-identical delta sequence to the pre-change baseline.
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_streaming_helper_driver.py -v -k "cliproxy_regression"
  ```
- **Pass condition:** The test captures `push_delta` call arguments from both a pre-change baseline path and the new GRD-with-conversational-turn path; the two sequences are byte-identical (same type, same payload, same order). Any divergence is a failure — even a reordering of identical payloads.
- **Blind spots:** Fake LLM stream — does not detect timing-sensitive ordering issues that would only appear under real async I/O.
- **Correlation:** HIGH for the regression risk; this is the most important proxy check in the phase.

### P5: Delegation cwd and backend-derivation tests

- **Plan:** 19-03
- **What:** `execute_delegate`, `_scan_mentions_and_notify`, and `project_chat` pass a resolved (non-None) cwd; `project_chat` derives backend from SA `backend_type` (no literal `'claude'`).
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_sketch_execution.py -v
  ```
  Additionally, verify no literal `'claude'` hardcode at the patched sites:
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && grep -n "backend='claude'" app_litestar/routes/grd_routes.py app/services/sketch_execution_service.py
  ```
- **Pass condition:** All `test_sketch_execution.py` tests pass; `grep` returns no output (no `backend='claude'` literals remaining at the three patched call sites).
- **Blind spots:** Tests use a monkeypatched `ProjectWorkspaceService` — real workspace resolution against a cloned repo is deferred.

### P6: Backend targeted test suite with watchdog-substitution procedure

- **Plan:** All backend plans (19-01 through 19-05)
- **What:** All new and directly related test files pass; house gate compliance for the known full-suite hang.
- **Procedure:**
  1. Attempt the full suite under a 12-minute watchdog:
     ```bash
     cd /Users/neo/Developer/Projects/Agented/backend && timeout 720 uv run pytest -q 2>&1 | tail -20
     ```
  2. If the suite hangs (no output for >60s before the 12-min limit, consistent with the ~40-48% hang), kill it and run the comprehensive targeted set:
     ```bash
     cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_cli_agent_runner.py tests/test_turn_classifier.py tests/test_grd_chat_handler.py tests/test_grd_chat_bridge.py tests/test_sketch_execution.py tests/test_streaming_helper_driver.py -v
     ```
  3. Additionally run the broader harness regression set:
     ```bash
     cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_streaming_helper.py tests/test_execution_service.py tests/test_conversation_streaming.py -v 2>/dev/null || true
     ```
- **Pass condition:** All tests in the targeted set pass. When substituting the targeted run for the full suite, the substitution MUST be disclosed in the PR description — never present as a full suite pass.
- **Failure means:** A test newly fails in either set. Zero pre-existing failures in these files are expected (unlike the frontend).

---

## Level 3: Deferred Validations

**Purpose:** Full validation requiring a live GRD binary, a real PSM session, or human observation of the UI. Cannot be completed within Phase 19.

### D1: Real GRD binary spawns a live PSM session from a chat turn — DEFER-19-01

- **What:** A task-shaped chat turn, routed through the GRD driver, spawns an actual `GrdChatSessionHandler` session that runs `/grd:quick "<task>"` in a real project clone and streams its output into the chat SSE transcript end-to-end.
- **How:** Send a chat message to a project with a real workspace (`ProjectWorkspaceService.resolve_working_directory` returns a valid path); observe the chat SSE stream for a `grd_session_id` linkage and `content_delta` events originating from the PSM; confirm the `grd` binary actually ran via process list or GRD session log.
- **Why deferred:** Requires a live GRD binary (`GrdCliService.available()` = true), a cloned project workspace, and a running backend instance. Phase 19 unit tests use fake PSM and injected degrade callables.
- **Validates at:** phase-21-one-click-team-harness (or the next integration milestone where GRD is installed in the test environment).
- **Depends on:** GRD binary present on PATH in test environment; a project with `ProjectWorkspaceService.resolve_working_directory` returning a valid path.
- **Target:** Task turn produces at least one `content_delta` event from the GRD PSM session; chat transcript shows `grd_session_id` linkage; no orphan PSM process after chat abort.
- **Risk if unmet:** GRD binary integration may have subprocess/pty/stream-json parsing bugs not visible in unit tests. Fallback: extend fake-PSM coverage and debug against the binary directly before integration.

### D2: Operator selects driver in the UI and observes correct routing behavior — DEFER-19-02

- **What:** An operator opens project settings, changes the driver selector from GRD to cliproxy, sends a task-shaped message, and observes that the turn is handled by cliproxy (no GRD PSM session spawned). Then switches back to GRD and sends the same message — observes GRD session linkage in the transcript.
- **How:** Manual test against a running dev instance with both the frontend and backend from Phase 19 deployed.
- **Why deferred:** Requires integrated frontend + backend + real SSE streaming + a live operator. Cannot be automated in Phase 19.
- **Validates at:** Integration milestone immediately following Phase 19 merge (or Phase 21 as the natural integration point).
- **Depends on:** Phase 19 fully merged; `just deploy` producing a running instance; a project with workspace configured.
- **Target:** Driver selector persists the choice to `projects.default_driver` or `config_json.driver`; subsequent turns respect the chosen driver (verified by transcript linkage or absence of GRD session badge).
- **Risk if unmet:** API persistence or frontend↔backend driver-read mismatch. Budget one targeted fix cycle.

### D3: Cross-backend LLM fallback classifier behavior — DEFER-19-03

- **What:** `classify_turn()` LLM fallback invoked with `backend_kind='codex'`, `backend_kind='gemini'`, and `backend_kind='opencode'` selects per-kind default models (never the claude hardcode) and produces a valid classification.
- **How:** Run `test_turn_classifier.py` with live LLM backends (or monkeypatched completion that validates the model string matches the per-kind default for each backend); confirm no `claude` model string appears in the completion call for non-claude backends.
- **Why deferred:** Requires real or faithful stubs for multiple LLM backends; Phase 19 unit tests monkeypatch the completion call but may not cover the per-kind model selection exhaustively for all backends.
- **Validates at:** phase-21-one-click-team-harness (multi-backend testing environment).
- **Depends on:** Real or high-fidelity stubs for codex/gemini/opencode backends.
- **Target:** For each non-claude backend_kind, the completion call uses a model string matching the documented per-kind default (not `claude-*`); classification result is `task` or `conversational` (not an exception).
- **Risk if unmet:** Per-kind model selection bug could cause silent fallback to a wrong model. Fallback: add explicit per-kind assertions to `test_turn_classifier.py` before Phase 21.

---

## Ablation Plan

**No ablation plan** — Phase 19 implements a single behavioral change (3-way driver routing) with defined sub-components that are each independently tested. There are no performance tradeoffs to isolate; correctness is binary. The cliproxy regression check (P4) serves the ablation purpose for the highest-risk component.

---

## WebMCP Tool Definitions

WebMCP tool definitions skipped — phase does not modify frontend views that are live-testable via WebMCP browser checks. Plan 19-06 modifies settings pages and chat components, but correctness is verified via Vitest component tests (S6), not live browser validation. The backend SSE stream is not a rendered page.

---

## Baselines

| Baseline | Description | Expected Score | Source |
|---|---|---|---|
| Frontend test suite | Pre-existing failures allowed | Exactly 7 failures (RateLimitGauge, MarkdownContent, WorkingMemoryView, useTourMachine) | CLAUDE.md house gates |
| AnswerGroundednessCard.vue TS error | Pre-existing; not in phase 19 files | Does not block build if unrelated to phase 19 files | CLAUDE.md house gates |
| Backend full-suite hang | Hangs at ~40-48% | No failures before hang point | CLAUDE.md known issue |

---

## Evaluation Scripts

**Location of evaluation code:**
```
backend/tests/test_cli_agent_runner.py       # P1 / S3 — resolver precedence + degrade
backend/tests/test_turn_classifier.py        # S4 — classifier keyword + LLM fallback
backend/tests/test_grd_chat_handler.py       # P2 — handler fake-PSM
backend/tests/test_grd_chat_bridge.py        # P3 — SSE bridge ordering + error
backend/tests/test_sketch_execution.py       # P5 — delegation cwd + backend derivation
backend/tests/test_streaming_helper_driver.py # P4 — cliproxy regression + grd-task dispatch
frontend/src/components/projects/__tests__/DriverSelector.test.ts  # S6 — component test
```

**How to run full Tier-1 + Tier-2 backend check (single command):**
```bash
cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_cli_agent_runner.py tests/test_turn_classifier.py tests/test_grd_chat_handler.py tests/test_grd_chat_bridge.py tests/test_sketch_execution.py tests/test_streaming_helper_driver.py -v
```

**How to run full Tier-1 frontend check:**
```bash
cd /Users/neo/Developer/Projects/Agented/frontend && npm run test:run
```

---

## Results Template

*To be filled by grd-eval-reporter after phase execution.*

### Sanity Results

| Check | Status | Output | Notes |
|---|---|---|---|
| S1 — resolver import + return | PENDING | | |
| S2 — migration 158 registered | PENDING | | |
| S3 — test_cli_agent_runner.py | PENDING | | |
| S4 — test_turn_classifier.py | PENDING | | |
| S5 — ruff format check | PENDING | | |
| S6 — DriverSelector component test | PENDING | | |
| S7 — i18n 4-locale driver.* parity | PENDING | | |

### Proxy Results

| Check | Pass Condition | Status | Notes |
|---|---|---|---|
| P1 — precedence matrix full run | All 7 levels + degrade + read-failure pass | PENDING | |
| P2 — handler fake-PSM | cmd contains /grd:quick, cwd non-None, forge_bundle forwarded | PENDING | |
| P3 — SSE bridge ordering | content_delta→tool_use→finish; error maps correctly | PENDING | |
| P4 — cliproxy regression (TOP RISK) | Byte-identical delta sequence vs baseline | PENDING | |
| P5 — delegation cwd + no backend='claude' | Tests pass; grep returns no output | PENDING | |
| P6 — watchdog targeted suite | All targeted files pass; substitution disclosed if used | PENDING | |

### Deferred Status

| ID | Metric | Status | Validates At |
|---|---|---|---|
| DEFER-19-01 | Real GRD binary PSM spawn end-to-end | PENDING | phase-21-one-click-team-harness |
| DEFER-19-02 | Operator UI driver selector + live routing | PENDING | phase-21 integration milestone |
| DEFER-19-03 | Cross-backend LLM classifier model selection | PENDING | phase-21-one-click-team-harness |

---

## Evaluation Confidence

**Overall confidence in evaluation design:** HIGH

**Justification:**
- Sanity checks: adequate — 7 deterministic checks cover all six plans, each with an exact command and pass condition.
- Proxy metrics: well-evidenced — all 6 proxy checks map directly to the plans' named test files and REQ-10..REQ-13 behavioral requirements. The cliproxy regression check (P4) directly guards the TOP RISK. No invented or weakly-correlated proxies.
- Deferred coverage: comprehensive for what matters in Phase 19 — the three deferred items (live binary, operator UI, cross-backend classifier) are the only aspects that genuinely cannot be evaluated without integration.

**What this evaluation CAN tell us:**
- Whether the resolver honors all precedence levels and degrades safely (P1 + S3).
- Whether the GRD handler builds the correct PSM command and the bridge emits the correct SSE event sequence (P2 + P3).
- Whether the cliproxy conversational path is byte-identical after the refactor (P4 — the regression risk).
- Whether the cwd/backend bugs are fixed at the call sites (P5).
- Whether the frontend selector defaults to GRD, persists choices, and renders transcript linkage (S6).
- Whether all four locales carry the required i18n keys (S7).

**What this evaluation CANNOT tell us:**
- Whether the GRD binary actually runs correctly in a real project workspace (deferred to D1 / phase-21).
- Whether the operator UI correctly drives a real GRD task turn end-to-end (deferred to D2 / phase-21).
- Whether the LLM classifier model selection is correct for non-claude backends under real LLM calls (deferred to D3 / phase-21).

---

*Evaluation plan by: Claude (grd-eval-planner)*
*Design date: 2026-06-13*
