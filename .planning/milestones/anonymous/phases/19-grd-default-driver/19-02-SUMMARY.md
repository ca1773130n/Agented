---
phase: 19-grd-default-driver
plan: 02
subsystem: backend/turn-routing
tags: [grd, classifier, llm-fallback, multi-backend]
requires: []
provides:
  - "backend/app/services/turn_classifier_service.py:classify_turn"
  - "backend/app/services/turn_classifier_service.py:GRD_COMMAND_MAP"
affects:
  - "19-04 funnel GRD branch (consumer)"
tech-stack:
  added: []
  patterns:
    - "keyword->LLM->deterministic pipeline (mirrors SketchRoutingService.classify)"
    - "per-backend-kind default model map; model_override precedence"
key-files:
  created:
    - backend/app/services/turn_classifier_service.py
    - backend/tests/test_turn_classifier.py
  modified: []
decisions:
  - "Conversational openers match on word boundary (token set), not substring, to avoid 'somewhat'->'what' false positives; '?' kept as substring"
  - "Task keyword buckets keep substring matching (kw in lowered) consistent with SketchRoutingService reference"
  - "DEFAULT_MODELS keyed per backend_kind (claude/codex/gemini/opencode) + GENERIC_DEFAULT_MODEL fallback; never a claude-only default"
metrics:
  duration: ~12min
  completed: 2026-06-13
  tasks: 2
  tests: 14
---

# Phase 19 Plan 02: Turn Classifier Summary

Self-contained `classify_turn()` splits chat turns into task vs conversational
and maps task turns to the correct `/grd:` command, with a multi-backend LLM
fallback that honors `{backend_kind, model_override}` and never hardcodes claude.

## What Was Built

- **`turn_classifier_service.py`** — `classify_turn(text, *, backend_kind, model_override=None)`
  returns `{"shape": "task"|"conversational", "grd_command": str|None, "intent": str}`.
  Pipeline mirrors `SketchRoutingService.classify` SHAPE: keyword score
  (threshold-gated at 0.6) → LLM fallback for ambiguous turns → deterministic
  conversational fallback. Turn-specific keyword seeds (`TASK_RESEARCH`,
  `TASK_PLAN`, `TASK_GENERIC`, `CONVERSATIONAL`) — no sketch-domain dicts imported.
  `GRD_COMMAND_MAP = {research:/grd:research, plan:/grd:plan-phase, generic:/grd:quick}`.
  `_llm_classify` resolves the model via `_resolve_model(backend_kind, model_override)`:
  override wins, else a per-kind entry in `DEFAULT_MODELS`, never a constant claude.
  Calls `litellm.completion` exactly as the sketch service does; any error returns
  a safe conversational fallback.

- **`test_turn_classifier.py`** (14 tests) — keyword generic/research/plan cases;
  conversational cases; "keyword-clear makes no LLM call" guard; ambiguous-turn LLM
  fallback via a `completion` spy; `model_override` precedence; per-kind model matrix
  for {claude, codex, gemini} asserting non-constant-claude defaults; LLM-error
  degradation to conversational.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Conversational openers substring-matched mid-word**
- **Found during:** Task 2 (ambiguous-turn fallback tests failed — spy never called)
- **Issue:** `"what" in lowered` matched "some**what**", so the ambiguous probe turn
  was wrongly classified conversational with confidence 1.0 and never reached the LLM.
- **Fix:** Conversational openers now match against a punctuation-stripped token set
  (word boundary); `?` stays a substring check.
- **Files modified:** `backend/app/services/turn_classifier_service.py`
- **Commit:** 4b15955636

## Experiment Results

N/A — no `eval_metrics` defined; verification is behavioral (Level 1 sanity +
Level 2 proxy via the model-selection spy). Live multi-backend tiebreak quality
(Level 3) deferred to integration.

| Check | Expected | Result | Status |
|-------|----------|--------|--------|
| keyword task/research/plan/conversational | deterministic, no LLM | green | PASS |
| ambiguous → LLM fallback invoked | spy called once | green | PASS |
| per-kind default model (claude/codex/gemini) | non-constant-claude | green | PASS |
| model_override precedence | override used | green | PASS |
| LLM error | safe conversational fallback | green | PASS |

## Verification

- `classify_turn('plan the next phase', backend_kind='claude')` → `shape=task, /grd:plan-phase` (Level 1)
- `uv run pytest tests/test_turn_classifier.py -q` → 14 passed
- `ruff format` + `ruff check` clean on both files

## Self-Check: PASSED
