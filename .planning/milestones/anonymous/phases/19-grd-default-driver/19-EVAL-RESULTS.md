---
phase: 19-grd-default-driver
evaluated: 2026-06-13
tiers_run: [sanity, proxy]
verdict: pass
---

# Phase 19 Eval Results — grd-default-driver

## Tier 1 (Sanity) + Tier 2 (Proxy) — Behavioral test suites

Command:
```
cd backend && uv run pytest \
  tests/test_cli_agent_runner.py \
  tests/test_turn_classifier.py \
  tests/test_sketch_execution.py \
  tests/test_grd_chat_handler.py \
  tests/test_grd_chat_bridge.py \
  tests/test_streaming_helper_driver.py -q
```

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Phase-19 suite pass rate | 100% | 83/83 | PASS |
| cliproxy regression (byte-identical fallthrough) | identical | proven by regression test in test_streaming_helper_driver.py | PASS |
| Resolver precedence matrix | all branches | covered (test_cli_agent_runner.py) | PASS |
| Turn classifier (keyword + LLM fallback, 4 backends) | all kinds | covered (test_turn_classifier.py) | PASS |
| grd_chat handler + PSM→chat-SSE bridge ordering/error | covered | covered (test_grd_chat_handler/bridge) | PASS |

**Verdict:** Met target — all sanity + proxy checks green (83 passed, 1 unrelated Litestar warning).

## Notes / Deferred
- Tier 3 (real GRD binary end-to-end PSM session) deferred to integration per EVAL.md — no live `grd` workspace exercised in unit tier (degrade callables injected).
- Frontend transcript "View GRD session" link is forward-compatible; backend `grd_chat_bridge` does not yet emit a session id on `finish` (follow-up backend change makes it render live).
