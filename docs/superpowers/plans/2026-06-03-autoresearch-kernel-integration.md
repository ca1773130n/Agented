# Agented × autoresearch-core Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`). **All work on a branch; `AUTORESEARCH_KERNEL_ENABLED` defaults OFF so behavior is byte-identical until enabled.** Tests are SQLite — no DB server needed.

**Goal:** Add a deterministic metric/comparator/target verdict to Agented's goal/Ouroboros loop by binding `autoresearch-core` as a new `source="kernel"` verdict inside `GoalJudgeService.judge`, reusing the loop/ledger/dead-ends/scheduler/KG/RRF.

**Architecture:** When the operator sets a goal-level `metric_spec`, the kernel becomes the authoritative judge (parses `__RESULT__` from the agent turn, compares to target) — never touching the `shell=True` `check_cmd` path. Behind `AUTORESEARCH_KERNEL_ENABLED`.

**Tech Stack:** Python 3.11, Litestar/Flask backend, SQLite, pytest. Kernel: `autoresearch-core` 0.1.0 (editable local dep via `uv`).

**Design:** `docs/superpowers/specs/2026-06-03-autoresearch-kernel-integration-design.md`. **Recon spans are embedded verbatim in each task.**

---

## File Structure
```
backend/pyproject.toml             # + autoresearch-core dep + [tool.uv.sources]
Dockerfile                         # + COPY autoresearch-core
backend/app/config.py              # + AUTORESEARCH_KERNEL_ENABLED
backend/app/services/goal_judge_service.py   # JudgeVerdict fields + judge() kernel branch
backend/app/services/goal_loop_runner.py     # metric_spec plumbing + dead-end + prompt + stale-check gate
backend/tests/test_autoresearch_kernel.py    # new (SQLite)
```

---

## Task 1: Dependency + flag + Docker

**Files:** `backend/pyproject.toml`, `Dockerfile`, `backend/app/config.py`.

- [ ] **Step 1: Add the dep** — in `backend/pyproject.toml`, add to `dependencies` (after `"ai-accounts-litestar",`):
```toml
    "autoresearch-core",
```
and to `[tool.uv.sources]`:
```toml
autoresearch-core = { path = "../../autoresearch-core", editable = true }
```

- [ ] **Step 2: Docker COPY** — in `Dockerfile` (backend-builder stage, next to the `COPY ai-accounts/ /build/ai-accounts/` line at ~L50), add:
```dockerfile
COPY autoresearch-core/ /build/autoresearch-core/
```
(`uv sync` then resolves the `../../autoresearch-core` source; the relative path holds because WORKDIR is `/build/Agented/backend`.)

- [ ] **Step 3: Flag** — in `backend/app/config.py`, next to the other `os.environ.get` constants:
```python
AUTORESEARCH_KERNEL_ENABLED = os.environ.get("AUTORESEARCH_KERNEL_ENABLED", "0") == "1"
```

- [ ] **Step 4: Install + verify** (from `backend/`, with the repo's uv venv):
```bash
cd backend && uv sync 2>&1 | tail -3
uv run python -c "import autoresearch_core as ac; print(ac.__version__, hasattr(ac,'measure'))"
```
Expected: `0.1.0 True`

- [ ] **Step 5: Commit**
```bash
git checkout -b feat/autoresearch-kernel
git add backend/pyproject.toml backend/uv.lock Dockerfile backend/app/config.py
git commit -m "chore(goal-loop): add autoresearch-core dep + AUTORESEARCH_KERNEL_ENABLED flag (default off)"
```

---

## Task 2: JudgeVerdict fields + `judge()` kernel branch

The stateless judge — **no DB needed**, pure unit test.

**Files:** Modify `backend/app/services/goal_judge_service.py`; Test `backend/tests/test_autoresearch_kernel.py`.

- [ ] **Step 1: Write the failing test**
```python
# backend/tests/test_autoresearch_kernel.py
from app.services.goal_judge_service import GoalJudgeService, JudgeVerdict

_SPEC = {"metric_key": "acc", "comparator": ">=", "target": 0.8}

def _judge(text, **kw):
    return GoalJudgeService.judge("goal", text, metric_spec=_SPEC, **kw)

def test_kernel_supported(monkeypatch):
    monkeypatch.setattr("app.services.goal_judge_service.AUTORESEARCH_KERNEL_ENABLED", True)
    v = _judge('work...\n__RESULT__ {"acc": 0.9}\n')
    assert v.source == "kernel" and v.met is True and v.kernel_record.verdict == "supported"

def test_kernel_refuted(monkeypatch):
    monkeypatch.setattr("app.services.goal_judge_service.AUTORESEARCH_KERNEL_ENABLED", True)
    v = _judge('__RESULT__ {"acc": 0.5}')
    assert v.source == "kernel" and v.met is False and v.kernel_record.verdict == "refuted"

def test_kernel_inconclusive_without_result(monkeypatch):
    monkeypatch.setattr("app.services.goal_judge_service.AUTORESEARCH_KERNEL_ENABLED", True)
    v = _judge('no result line yet')
    assert v.source == "kernel" and v.met is False and v.kernel_record.verdict == "inconclusive"

def test_flag_off_ignores_metric_spec(monkeypatch):
    monkeypatch.setattr("app.services.goal_judge_service.AUTORESEARCH_KERNEL_ENABLED", False)
    v = GoalJudgeService.judge("goal", "x", metric_spec=_SPEC, check_cmd="true")
    assert v.source == "deterministic"   # check_cmd path, kernel skipped

def test_kernel_wins_over_check_cmd(monkeypatch):
    # flag on + metric_spec → kernel decides; check_cmd (shell) is NEVER invoked.
    monkeypatch.setattr("app.services.goal_judge_service.AUTORESEARCH_KERNEL_ENABLED", True)
    called = {"n": 0}
    monkeypatch.setattr(GoalJudgeService, "_run_deterministic",
                        classmethod(lambda cls, *a, **k: called.__setitem__("n", 1)))
    v = _judge('__RESULT__ {"acc": 0.9}', check_cmd="false")
    assert v.source == "kernel" and called["n"] == 0

def test_kernel_invalid_spec_stays_in_kernel(monkeypatch):
    monkeypatch.setattr("app.services.goal_judge_service.AUTORESEARCH_KERNEL_ENABLED", True)
    v = GoalJudgeService.judge("g", "x", metric_spec={"bad": 1}, check_cmd="true")
    assert v.source == "kernel" and v.met is False   # config error → did NOT reach check_cmd
```

- [ ] **Step 2: Run → fail** `cd backend && uv run pytest tests/test_autoresearch_kernel.py -q` → `TypeError: judge() got an unexpected keyword argument 'metric_spec'`.

- [ ] **Step 3: Add the kernel imports** at the top of `goal_judge_service.py` (after `from .cliproxy_manager import CLIProxyManager`):
```python
from autoresearch_core import ExperimentResult, MetricSpec, measure
from autoresearch_core import parse_metrics_line, validate_metric_spec
from app.config import AUTORESEARCH_KERNEL_ENABLED
```

- [ ] **Step 4: Extend `JudgeVerdict`** — add two fields (after `ouroboros_verdict`):
```python
    metric_spec: Optional[dict] = None
    kernel_record: Optional[object] = None   # transient autoresearch_core.VerdictRecord; not persisted
```

- [ ] **Step 5: Add `metric_spec` param + the kernel branch** in `judge()` — new param in the signature:
```python
        metric_spec: Optional[dict] = None,
```
and insert this **before** the `if check_cmd:` line:
```python
        if AUTORESEARCH_KERNEL_ENABLED and metric_spec:
            # metric_spec is authoritative — this branch ALWAYS returns; it never
            # falls through to check_cmd (shell=True) or the LLM judges.
            try:
                spec = MetricSpec(**metric_spec)
                validate_metric_spec(spec)
            except (TypeError, ValueError) as exc:
                return JudgeVerdict(
                    met=False, source="kernel",
                    reason=f"invalid metric_spec: {exc}", metric_spec=metric_spec,
                )
            rec = measure(spec, ExperimentResult(
                metrics=parse_metrics_line(last_assistant_text), exit_code=0))
            return JudgeVerdict(
                met=(rec.verdict == "supported"), source="kernel", reason=rec.detail,
                metric_spec=metric_spec, kernel_record=rec,
                stdout=json.dumps({
                    "verdict": rec.verdict, "evidence_level": rec.evidence_level,
                    "strategy": rec.strategy, "detail": rec.detail,
                }),
            )
```

- [ ] **Step 6: Run → pass.** `uv run pytest tests/test_autoresearch_kernel.py -q`

- [ ] **Step 7: Commit**
```bash
git add backend/app/services/goal_judge_service.py backend/tests/test_autoresearch_kernel.py
git commit -m "feat(goal-loop): kernel deterministic verdict source in GoalJudgeService.judge"
```

---

## Task 3: Runner — plumb `metric_spec`, gate stale-check, promote dead-ends, prompt `__RESULT__`

**Files:** Modify `backend/app/services/goal_loop_runner.py`; extend the test file (SQLite via `isolated_db`).

- [ ] **Step 1: Write the failing test** (SQLite)
```python
# append to backend/tests/test_autoresearch_kernel.py
import json as _json
from app.db.goal_loop import list_goal_loop_dead_ends
from app.services.goal_judge_service import JudgeVerdict
from app.services import goal_loop_runner as glr

def test_kernel_dead_end_promotion_helper(isolated_db, monkeypatch):
    # The runner promotes a dead-end when a kernel verdict is a deterministic refutation.
    monkeypatch.setattr("app.services.goal_loop_runner.AUTORESEARCH_KERNEL_ENABLED", True)
    from autoresearch_core import DeterministicVerdict, MetricSpec, ExperimentResult
    rec = DeterministicVerdict().evaluate(
        MetricSpec("acc", ">=", 0.8), ExperimentResult(metrics={"acc": 0.5}, exit_code=0))
    verdict = JudgeVerdict(met=False, source="kernel", reason=rec.detail, kernel_record=rec)
    glr._maybe_promote_kernel_dead_end("sess1", 1, "cache the tokenizer", verdict, "turn text")
    rows = list_goal_loop_dead_ends("sess1")
    assert len(rows) == 1 and rows[0]["approach"] == "cache the tokenizer"
    # idempotent
    glr._maybe_promote_kernel_dead_end("sess1", 2, "cache the tokenizer", verdict, "turn text")
    assert len(list_goal_loop_dead_ends("sess1")) == 1

def test_prompt_result_block_gated():
    # __RESULT__ instruction only present when a metric_spec result_block is passed
    assert "__RESULT__" not in glr._initial_prompt("g", ouroboros=True)
    assert "__RESULT__" in glr._initial_prompt("g", ouroboros=True, result_block=glr._result_instruction({"metric_key":"acc"}))
```

- [ ] **Step 2: Add the kernel imports** to `goal_loop_runner.py` (top):
```python
from autoresearch_core import should_promote_dead_end
from app.config import AUTORESEARCH_KERNEL_ENABLED
```

- [ ] **Step 3: Add `metric_spec` to config read** (in `_run()`, next to `check_cmd = config.get("check_cmd")` at ~L248):
```python
    metric_spec = config.get("metric_spec")
```

- [ ] **Step 4: Thread `metric_spec` into the judge call** (~L327) — add the kwarg:
```python
                metric_spec=metric_spec,
```

- [ ] **Step 5: Gate the stale-check in kernel mode** — at the `_maybe_stale_check(...)` call site (~L405), wrap so it does NOT fire when the kernel owns the verdict:
```python
            if not (AUTORESEARCH_KERNEL_ENABLED and metric_spec):
                _maybe_stale_check(session_id, state, check_cmd, goal, turn_text,
                                   backend_kind, model_override)
```

- [ ] **Step 6: Add the dead-end promotion helper + call** — define near `_approach_hash`:
```python
def _maybe_promote_kernel_dead_end(session_id, iteration_no, hypothesis, verdict, turn_text):
    """Promote a deterministic-refutation kernel verdict to the dead-end registry."""
    if not (AUTORESEARCH_KERNEL_ENABLED and verdict.source == "kernel" and hypothesis):
        return
    if verdict.kernel_record is None or not should_promote_dead_end(verdict.kernel_record):
        return
    add_goal_loop_dead_end(
        session_id=session_id, iteration=iteration_no, approach=hypothesis,
        reason=verdict.reason, evidence=(turn_text or "")[-1024:] or None,
        approach_hash=_approach_hash(hypothesis),
    )
```
and call it right after the existing ouroboros dead-end block (~L400):
```python
            _maybe_promote_kernel_dead_end(session_id, iteration_no, hypothesis, verdict, turn_text)
```

- [ ] **Step 7: Add the `__RESULT__` prompt instruction** — module-level constant + helper near `_OUROBOROS_HYPOTHESIS_BLOCK`:
```python
def _result_instruction(metric_spec) -> str:
    key = (metric_spec or {}).get("metric_key", "<metric>")
    return (f"\n\nWhen you have measured the target metric, print it as a final line "
            f'exactly: `__RESULT__ {{"{key}": <number>}}`.')
```
Add a keyword-only `result_block: str = ""` to `_initial_prompt` and `_continue_prompt` and include it in their `return` f-strings. **The runner calls them through `_send_initial()` (~L274) and `_send_continue()` (~L450), not directly** — add `result_block: str = ""` to those two wrappers and forward it to the prompt helper. In `_run()`, build it once: `result_block = _result_instruction(metric_spec) if (AUTORESEARCH_KERNEL_ENABLED and metric_spec) else ""` and pass it into the `_send_initial(...)` / `_send_continue(...)` calls.

- [ ] **Step 8: Run → pass.** `uv run pytest tests/test_autoresearch_kernel.py -q`

- [ ] **Step 9: Commit**
```bash
git add backend/app/services/goal_loop_runner.py backend/tests/test_autoresearch_kernel.py
git commit -m "feat(goal-loop): plumb metric_spec, gate stale-check, promote kernel dead-ends, prompt __RESULT__"
```

---

## Task 4: Flag-off regression test

**Files:** extend the test file.

- [ ] **Step 1: Write the test** — with the flag OFF, `judge` ignores `metric_spec` and the runner adds no kernel dead-ends; existing `test_goal_loop_ouroboros.py` semantics are untouched:
```python
def test_flag_off_no_kernel_behavior(isolated_db, monkeypatch):
    monkeypatch.setattr("app.services.goal_loop_runner.AUTORESEARCH_KERNEL_ENABLED", False)
    from app.services.goal_judge_service import JudgeVerdict
    v = JudgeVerdict(met=False, source="kernel", reason="r", kernel_record=None)
    glr._maybe_promote_kernel_dead_end("s2", 1, "approach", v, "t")
    assert list_goal_loop_dead_ends("s2") == []

def test_flag_off_prompts_have_no_result_block():
    # result_block defaults to "" → prompts byte-identical to pre-integration
    assert "__RESULT__" not in glr._initial_prompt("g", ouroboros=True)
    assert "__RESULT__" not in glr._continue_prompt("g", "r", ouroboros=True)
```

- [ ] **Step 2: Run the full new suite + the existing ouroboros suite**
```bash
cd backend && uv run pytest tests/test_autoresearch_kernel.py tests/test_goal_loop_ouroboros.py -q
```
Expected: all pass.

- [ ] **Step 3: Commit** `git commit -am "test(goal-loop): flag-off regression for kernel verdict"`

---

## Self-Review

**Spec coverage (design §2–§3):** dep+flag (T1) ✓ · JudgeVerdict fields + judge kernel branch authoritative-before-check_cmd (T2) ✓ · runner metric_spec plumbing + stale-check gate + dead-end promotion + `__RESULT__` prompt (T3) ✓ · flag-off regression (T4) ✓ · Docker COPY (T1) ✓ · no subprocess/shell in the kernel path ✓ · reuse-not-port (loop/ledger/dead-ends/scheduler/KG/RRF untouched) ✓ · `failure_class` correctly absent ✓.

**Placeholder scan:** none — every step has concrete code. The exact line of the `_maybe_stale_check` call (T3-S5) must be confirmed against the file (recon put it ~L405); the implementer wraps the real call site.

**Type consistency:** `metric_spec` dict `{metric_key,comparator,target}` flows config→runner→judge→`MetricSpec(**...)`; `verdict.kernel_record` set in T2, read in T3's `should_promote_dead_end`; `_maybe_promote_kernel_dead_end` signature identical in def (T3) and tests (T3/T4).

**Codex plan-review (2026-06-03) incorporated:** kernel branch always returns when flag+`metric_spec` (never falls through to `shell=True`); `validate_metric_spec` added; `kernel_record is None` guard; prompt `result_block` threaded through the real `_send_initial`/`_send_continue` wrappers; added kernel-beats-`check_cmd`, invalid-spec, and flag-off-prompt tests. **Validated by Codex:** kernel imports exist in `autoresearch_core.__all__`; `metric_spec` is in scope at the single `_maybe_stale_check` trigger (`:402`); `record_iteration_complete` is aliased `record_goal_loop_iteration_complete` (`db/__init__.py:573`); the prompt helpers have only wrapper/test callers (the `result_block=""` default is safe).
