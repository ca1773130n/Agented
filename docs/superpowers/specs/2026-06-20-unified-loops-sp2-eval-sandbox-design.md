# v0.6.0 Unified Loops — Sub-project #2: Eval-in-the-loop + Sandbox — Design

**Parent:** [v0.6.0 Unified Loop Control Surface](2026-06-19-v0.6.0-unified-loops-design.md) — sub-project #2 of 3 (MVP).
**Builds on:** #1 (merged, PR #232) — `LoopSpec`, the single executor, `GoalJudgeService`.
**Date:** 2026-06-20
**Decisions baked in (user-chosen):** sandbox **default-ON for all loops**; **include dynamic early-termination** (confidence) in #2.

## 1. Recon findings (post-#1) that shape this

- `GoalJudgeService.judge()` (`goal_judge_service.py:146`) → `JudgeVerdict` (`:112`) with `met/source/reason/stdout/tokens_in/out/cost_usd/ouroboros_verdict/metric_spec`. Four decision branches (`:172–227`): kernel(metric_spec) → deterministic(check_cmd) → ouroboros → llm. **No rubric/version on the LLM judge; no confidence anywhere.**
- `_run_deterministic` (`:234`) runs `check_cmd` with `shell=True, cwd=cwd` (**the agent's editable workspace**), inheriting full parent env, 30s timeout. **This is the unguarded reward-hacking surface (research F9).**
- `LoopExit` (`loop_spec.py:27`) has budgets + convergence + stagnation but **no `quality_gate`**.
- `WorktreeService` (`worktree_service.py`) exists (plan/Ralph/team isolation) but is **not** used for eval isolation; `worktree_path` is stored on the session but never used as the eval cwd.
- Highest migration = **169** → new = **170**.

## 2. Deliverables

### 2a. `QualityGate` on `LoopSpec.exit` (formalize the gate)
New struct in `backend/app/models/loop_spec.py`:

```
QualityGate (frozen):
  kind: "test_pass" | "metric" | "llm_judge"
  # metric:
  metric_name: str | None
  threshold: float | None
  comparator: ">=" | "<=" | ">" | "<" | "==" = ">="
  # llm_judge:
  rubric: str | None
  judge_version: str | None            # F6 — versioned judge
  # dynamic early-termination (F7):
  min_confidence: float = 0.0          # a "met" must clear this to terminate
```

Add `quality_gate: QualityGate | None = None` to `LoopExit`. `from_legacy_config` maps: `check_cmd` present → `test_pass`; `metric_spec` present → `metric` (name/threshold from the spec); else (goal-loop default) → `llm_judge`. **Default None preserves today's behavior** for callers that don't set it.

### 2b. Judge: rubric + versioning + confidence (F6, F7)
- `JudgeVerdict` gains `confidence: float = 1.0` and `judge_version: str | None = None`.
- `judge()` gains `quality_gate: QualityGate | None = None`.
- `_run_llm_judge`: when the gate carries a `rubric`, inject it into `_JUDGE_USER_TEMPLATE`; stamp `judge_version` on the verdict; parse a `confidence` (0–1) from the judge's structured reply (extend the JSON the judge returns). **Validate the judge, don't trust by default (F6):** record `judge_version` on each iteration so drift is auditable.
- `_run_deterministic`: `confidence = 1.0` on exit-0, `0.0` otherwise.
- metric path: honor `comparator`/`threshold` from the gate (the kernel path already compares to target; expose the comparator).

### 2c. Sandbox the eval boundary — **default ON** (F9, the headline)
New `backend/app/services/sandbox_eval.py`:

```
run_isolated_check(check_cmd, workspace_cwd, *, timeout) -> CompletedProcess-like:
  1. snapshot the workspace into a throwaway temp dir
     (copytree, ignoring .git, node_modules, .venv, __pycache__, .worktrees, dist;
      size-guarded — fall back to inherit + WARN if the snapshot would be huge)
  2. run check_cmd shell=True in the SNAPSHOT dir with a SCRUBBED env
     (allowlist: PATH, HOME, LANG, LC_*, TERM — no inherited secrets)
  3. capture stdout/stderr/returncode; always rm the temp dir (finally)
```

- `LoopSpec.state` gains `sandbox: "isolated" | "inherit" = "isolated"` — **default isolated**.
- `GoalJudgeService._run_deterministic` routes through `run_isolated_check` when `sandbox=="isolated"`, else the current in-place run (escape hatch).
- **What this buys (be precise):** the running eval is isolated from the live agent session — no mid-eval file races, no eval-process interference, no env/secret leakage into the grader. (Pinning *trusted test sources* so the agent can't pre-edit its own tests is a deeper, post-MVP hardening — noted, not built.)
- **Accepted tradeoff (user-chosen default-on):** every loop's `check_cmd` now runs against a fresh snapshot copy. Mitigations: the ignore-list + size guard keep copies cheap; the `inherit` escape hatch restores old behavior per-loop. Frontend surfaces the toggle.

### 2d. Migration 170
Add `confidence REAL` + `judge_version TEXT` columns to `goal_loop_iterations` (idempotent PRAGMA-guarded ALTERs), persisted by `record_iteration_complete`. (quality_gate + sandbox live in the JSON `goal_loop_config` blob — no column needed.)

### 2e. Runner wiring
`goal_loop_runner._run` passes `state.spec.exit.quality_gate` into `judge(...)`, records `confidence`/`judge_version`, and the "met" termination requires `verdict.met and verdict.confidence >= gate.min_confidence` (a low-confidence met continues — more verification; F4/F6 "don't trust the gate by default"). Budgets remain the hard fallback (F4).

### 2f. Frontend
Loop-config types + UI: quality-gate kind (test_pass/metric/llm_judge), rubric + judge_version (judge), metric name/threshold/comparator, `min_confidence`, and the `sandbox` toggle. i18n `loopConfig.*` additions in en/ko/ja/zh.

## 3. Out of scope (later / post-MVP)
- Per-iteration trace UI / live status / stop-intervene / human gates → **sub-project #3**.
- Trusted-test-source pinning + container/mount isolation (deeper F9) → post-MVP.
- Cyclic workflows, Loop Builder polish → post-MVP.

## 4. Risks & mitigations
- **Sandbox default-on changes behavior** (eval now runs on a snapshot copy) → size-guarded snapshot with WARN-fallback to inherit; per-loop `inherit` escape hatch; parity tests that an isolated run reaches the same verdict as in-place for a clean repo.
- **Snapshot cost on large repos** → ignore-list (`.git`/`node_modules`/`.venv`/`.worktrees`/`dist`/`__pycache__`) + a max-bytes guard that falls back to inherit with a logged warning.
- **Judge confidence is fuzzy** → `min_confidence` defaults 0.0 (off) so it never *blocks* a met unless explicitly configured; deterministic checks are always confidence 1.0.

## 5. Open questions (resolve in plan)
- Snapshot mechanism: `shutil.copytree` (simple, portable) vs `git worktree`/`git archive` (faster, tracked-only). Plan picks copytree+ignore for MVP (handles uncommitted edits, no git assumptions), with the size guard.
- Confidence parsing: extend the LLM judge's reply JSON with a `confidence` field; deterministic/metric synthesize it. Confirm the judge prompt change is backward-safe (older replies without the field → default 1.0).

## 6. Verification
`just build`; backend targeted pytest (QualityGate parse + legacy mapping; judge rubric/version/confidence; metric comparator; `sandbox_eval` isolation incl. env-scrub + temp cleanup + size-guard fallback; migration 170; runner min_confidence gate) + the #1 + goal-judge/goal-loop regression suites green; frontend `npm run test:run` at the 7-failure baseline.

---
**Next:** on approval → writing-plans → execute (TDD, per-task commits), same cadence as #1.
