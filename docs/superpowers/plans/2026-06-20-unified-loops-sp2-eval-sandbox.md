# Unified Loops — Sub-project #2: Eval-in-the-loop + Sandbox — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Formalize the loop quality-gate (test/metric/llm-judge with rubric+version+confidence), sandbox the eval boundary by default, and wire dynamic early-termination — on top of sub-project #1's `LoopSpec`/executor.

**Architecture:** Add a `QualityGate` struct to `LoopSpec.exit` (back-compat via `from_legacy_config`), extend `GoalJudgeService` to carry rubric/version/confidence and to run `check_cmd` inside an isolated, env-scrubbed workspace snapshot (default on), record the new telemetry (migration 170), and require `min_confidence` for a "met" to terminate.

**Tech Stack:** Python 3.10 (msgspec + dataclass, Ruff line-length=100), SQLite migration (`v07_features.py`), pytest (`isolated_db`). Frontend: Vue 3 + TS, Vitest, vue-i18n (en/ko/ja/zh).

**Spec:** `docs/superpowers/specs/2026-06-20-unified-loops-sp2-eval-sandbox-design.md`

---

## File structure

| File | Responsibility | Action |
|---|---|---|
| `backend/app/models/loop_spec.py` | `QualityGate` struct; `LoopExit.quality_gate`; `LoopState.sandbox`; legacy mapping | **Modify** |
| `backend/app/services/sandbox_eval.py` | Isolated, env-scrubbed workspace-snapshot check runner | **Create** |
| `backend/app/services/goal_judge_service.py` | `JudgeVerdict.confidence/judge_version`; `judge(quality_gate=…)`; sandboxed `_run_deterministic`; rubric/version/confidence in LLM judge | **Modify** |
| `backend/app/db/migrations/v07_features.py` | Migration 170: `confidence` + `judge_version` cols | **Modify** |
| `backend/app/db/goal_loop.py` | `record_iteration_complete` persists `confidence`/`judge_version` | **Modify** |
| `backend/app/services/goal_loop_runner.py` | Pass `quality_gate`+sandbox to judge; record telemetry; `min_confidence` met-gate | **Modify** |
| `frontend/src/services/api/grd.ts` | quality-gate + sandbox config fields | **Modify** |
| `frontend/src/locales/{en,ko,ja,zh}.json` | `loopConfig.*` additions | **Modify** |
| Tests | per task | **Create** |

---

## Task 1: `QualityGate` + `LoopExit.quality_gate` + `LoopState.sandbox`

**Files:**
- Modify: `backend/app/models/loop_spec.py`
- Test: `backend/tests/test_loop_spec_quality_gate.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_loop_spec_quality_gate.py
from app.models.loop_spec import LoopSpec, QualityGate


def test_check_cmd_maps_to_test_pass_gate_and_sandbox_default_isolated():
    spec = LoopSpec.from_legacy_config({"goal": "g", "check_cmd": "pytest -q"}, execution_type="goal_loop")
    assert spec.exit.quality_gate is not None
    assert spec.exit.quality_gate.kind == "test_pass"
    assert spec.state.sandbox == "isolated"  # default ON


def test_metric_spec_maps_to_metric_gate():
    spec = LoopSpec.from_legacy_config(
        {"goal": "g", "metric_spec": {"name": "f1", "target": 0.8}}, execution_type="goal_loop")
    assert spec.exit.quality_gate.kind == "metric"
    assert spec.exit.quality_gate.metric_name == "f1"
    assert spec.exit.quality_gate.threshold == 0.8


def test_goal_loop_default_is_llm_judge_gate():
    spec = LoopSpec.from_legacy_config({"goal": "g"}, execution_type="goal_loop")
    assert spec.exit.quality_gate.kind == "llm_judge"


def test_explicit_quality_gate_and_sandbox_inherit_parse():
    spec = LoopSpec.from_legacy_config({
        "goal": "g",
        "quality_gate": {"kind": "llm_judge", "rubric": "be strict", "judge_version": "v2", "min_confidence": 0.7},
        "sandbox": "inherit",
    }, execution_type="goal_loop")
    qg = spec.exit.quality_gate
    assert qg.rubric == "be strict" and qg.judge_version == "v2" and qg.min_confidence == 0.7
    assert spec.state.sandbox == "inherit"


def test_ralph_default_sandbox_isolated_no_gate_when_no_check():
    spec = LoopSpec.from_legacy_config({"task_description": "do"}, execution_type="ralph")
    assert spec.state.sandbox == "isolated"
    assert spec.exit.quality_gate is None  # ralph has no check_cmd → no eval gate
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_loop_spec_quality_gate.py -q`
Expected: FAIL (`ImportError: QualityGate`).

- [ ] **Step 3: Implement**

In `loop_spec.py` add the struct (after `LoopBody`):

```python
GateKind = Literal["test_pass", "metric", "llm_judge"]
SandboxMode = Literal["isolated", "inherit"]


class QualityGate(msgspec.Struct, frozen=True):
    kind: GateKind
    metric_name: Optional[str] = None
    threshold: Optional[float] = None
    comparator: str = ">="
    rubric: Optional[str] = None
    judge_version: Optional[str] = None
    min_confidence: float = 0.0
```

Add to `LoopExit`: `quality_gate: Optional[QualityGate] = None`.
Add to `LoopState`: `sandbox: SandboxMode = "isolated"`.

Add a builder + wire it into both branches of `from_legacy_config`:

```python
def _gate_from_legacy(c: dict) -> Optional[QualityGate]:
    explicit = c.get("quality_gate")
    if isinstance(explicit, dict) and explicit.get("kind"):
        return QualityGate(
            kind=explicit["kind"],
            metric_name=explicit.get("metric_name"),
            threshold=explicit.get("threshold"),
            comparator=explicit.get("comparator", ">="),
            rubric=explicit.get("rubric"),
            judge_version=explicit.get("judge_version"),
            min_confidence=float(explicit.get("min_confidence") or 0.0),
        )
    if c.get("check_cmd"):
        return QualityGate(kind="test_pass")
    ms = c.get("metric_spec")
    if isinstance(ms, dict):
        return QualityGate(kind="metric", metric_name=ms.get("name"),
                           threshold=ms.get("target") if ms.get("target") is not None else ms.get("threshold"))
    return None
```

In the **ralph** branch: `quality_gate = _gate_from_legacy(c)` (None unless a check_cmd was given); `state = LoopState(context_policy=..., sandbox=c.get("sandbox") or "isolated")`.
In the **goal_loop** branch: `gate = _gate_from_legacy(c) or QualityGate(kind="llm_judge", rubric=(c.get("quality_gate") or {}).get("rubric"), judge_version=(c.get("quality_gate") or {}).get("judge_version"), min_confidence=float((c.get("quality_gate") or {}).get("min_confidence") or 0.0))`; set `LoopExit(..., quality_gate=gate)` and `LoopState(..., sandbox=c.get("sandbox") or "isolated")`.

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && uv run pytest tests/test_loop_spec_quality_gate.py tests/test_loop_spec.py -q`
Expected: PASS (new + the #1 LoopSpec suite still green).

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/loop_spec.py backend/tests/test_loop_spec_quality_gate.py
git commit -m "feat(loops): QualityGate on LoopExit + sandbox mode on LoopState (default isolated)"
```

---

## Task 2: Migration 170 — `confidence` + `judge_version` on iterations

**Files:**
- Modify: `backend/app/db/migrations/v07_features.py` (add `_migrate_170_iteration_confidence`; register after `(169, ...)`)
- Modify: `backend/app/db/goal_loop.py` (`record_iteration_complete` gains `confidence`/`judge_version`; `list_iterations`/`_row_to_dict` expose them)
- Test: `backend/tests/test_migration_170_iteration_confidence.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_migration_170_iteration_confidence.py
def test_columns_exist(isolated_db):
    from app.db.connection import get_connection
    with get_connection() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(goal_loop_iterations)")}
    assert "confidence" in cols and "judge_version" in cols


def test_record_persists_confidence_and_version(isolated_db):
    from app.db.goal_loop import record_iteration_start, record_iteration_complete, list_iterations
    rid = record_iteration_start("s", 1)
    record_iteration_complete(rid, verdict="met", judge_source="llm", judge_reason="r",
                              judge_stdout="", tokens_in=1, tokens_out=2, cost_usd=0.0,
                              confidence=0.91, judge_version="v2")
    row = list_iterations("s")[0]
    assert row["confidence"] == 0.91 and row["judge_version"] == "v2"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_migration_170_iteration_confidence.py -q`
Expected: FAIL (cols missing / unexpected kwarg).

- [ ] **Step 3: Implement**

In `v07_features.py`:

```python
def _migrate_170_iteration_confidence(conn) -> None:
    """v0.6.0 sub-project #2: record judge confidence + judge_version per
    iteration (dynamic early-termination + judge-drift auditing)."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(goal_loop_iterations)")}
    if "confidence" not in cols:
        conn.execute("ALTER TABLE goal_loop_iterations ADD COLUMN confidence REAL")
    if "judge_version" not in cols:
        conn.execute("ALTER TABLE goal_loop_iterations ADD COLUMN judge_version TEXT")
```

Register: `    (170, "iteration_confidence", _migrate_170_iteration_confidence),`

In `goal_loop.py` `record_iteration_complete`: add kwargs `confidence: Optional[float] = None, judge_version: Optional[str] = None`; include both in the UPDATE SET. Add both to `list_iterations` SELECT + `_row_to_dict`.

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && uv run pytest tests/test_migration_170_iteration_confidence.py tests/test_migrations_split.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/migrations/v07_features.py backend/app/db/goal_loop.py backend/tests/test_migration_170_iteration_confidence.py
git commit -m "feat(loops): migration 170 — confidence + judge_version on iterations"
```

---

## Task 3: `sandbox_eval` — isolated, env-scrubbed check runner

**Files:**
- Create: `backend/app/services/sandbox_eval.py`
- Test: `backend/tests/services/test_sandbox_eval.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/services/test_sandbox_eval.py
import os
from pathlib import Path
from app.services.sandbox_eval import run_isolated_check


def test_runs_check_against_a_snapshot_not_the_live_dir(tmp_path):
    (tmp_path / "marker.txt").write_text("hi")
    # check verifies the file exists in the snapshot cwd (proves the copy happened)
    res = run_isolated_check("test -f marker.txt", str(tmp_path), timeout=10)
    assert res.returncode == 0
    # the snapshot temp dir is cleaned up (no stray dirs left in tmp_path)
    assert [p.name for p in tmp_path.iterdir()] == ["marker.txt"]


def test_env_is_scrubbed(tmp_path):
    os.environ["SECRET_TOKEN_XYZ"] = "leak"
    try:
        res = run_isolated_check('test -z "$SECRET_TOKEN_XYZ"', str(tmp_path), timeout=10)
        assert res.returncode == 0  # secret NOT present in the scrubbed env
    finally:
        os.environ.pop("SECRET_TOKEN_XYZ", None)


def test_nonzero_exit_propagates(tmp_path):
    res = run_isolated_check("exit 3", str(tmp_path), timeout=10)
    assert res.returncode == 3


def test_oversize_workspace_falls_back_to_inherit(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.sandbox_eval._MAX_SNAPSHOT_BYTES", 1)  # force fallback
    (tmp_path / "big.txt").write_text("xxxxxxxxxx")
    res = run_isolated_check("test -f big.txt", str(tmp_path), timeout=10)
    assert res.returncode == 0  # ran in-place (fallback), still works
    assert res.sandboxed is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/services/test_sandbox_eval.py -q`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement**

```python
# backend/app/services/sandbox_eval.py
"""Isolated, env-scrubbed runner for loop quality-gate check commands.

Reward-hacking mitigation (research F9): run the grader against a throwaway
SNAPSHOT of the workspace with a minimal env, so the live agent session can't
race/tamper with the running eval or leak secrets into it. Oversized
workspaces fall back to an in-place run (logged) to bound copy cost.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_IGNORE = shutil.ignore_patterns(
    ".git", "node_modules", ".venv", "venv", "__pycache__", ".worktrees", "dist", ".mypy_cache"
)
_ENV_ALLOWLIST = ("PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "TMPDIR", "SHELL")
_MAX_SNAPSHOT_BYTES = 512 * 1024 * 1024  # 512 MB guard


@dataclass
class IsolatedResult:
    returncode: int
    stdout: str
    stderr: str
    sandboxed: bool


def _scrubbed_env() -> dict:
    env = {k: os.environ[k] for k in _ENV_ALLOWLIST if k in os.environ}
    env.setdefault("PATH", "/usr/bin:/bin:/usr/local/bin")
    return env


def _dir_size(root: Path) -> int:
    total = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in {
            ".git", "node_modules", ".venv", "venv", "__pycache__", ".worktrees", "dist", ".mypy_cache"}]
        for f in filenames:
            try:
                total += (Path(dirpath) / f).stat().st_size
            except OSError:
                pass
            if total > _MAX_SNAPSHOT_BYTES:
                return total
    return total


def run_isolated_check(check_cmd: str, workspace_cwd: str, *, timeout: int) -> IsolatedResult:
    src = Path(workspace_cwd)
    sandboxed = True
    run_cwd = workspace_cwd
    tmp_root: Optional[str] = None
    try:
        if not src.is_dir() or _dir_size(src) > _MAX_SNAPSHOT_BYTES:
            sandboxed = False
            logger.warning("sandbox_eval: workspace missing or too large — running in-place")
        else:
            tmp_root = tempfile.mkdtemp(prefix="agented-eval-")
            dst = Path(tmp_root) / "ws"
            shutil.copytree(src, dst, ignore=_IGNORE, symlinks=True)
            run_cwd = str(dst)
        try:
            proc = subprocess.run(
                check_cmd, shell=True, cwd=run_cwd, capture_output=True, text=True,
                timeout=timeout, env=_scrubbed_env(),
            )
            return IsolatedResult(proc.returncode, proc.stdout or "", proc.stderr or "", sandboxed)
        except subprocess.TimeoutExpired:
            return IsolatedResult(124, "", f"timed out after {timeout}s", sandboxed)
    finally:
        if tmp_root:
            shutil.rmtree(tmp_root, ignore_errors=True)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && uv run pytest tests/services/test_sandbox_eval.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/sandbox_eval.py backend/tests/services/test_sandbox_eval.py
git commit -m "feat(loops): sandbox_eval — isolated env-scrubbed snapshot check runner (F9)"
```

---

## Task 4: Judge carries confidence/version + sandboxed deterministic check

**Files:**
- Modify: `backend/app/services/goal_judge_service.py` (`JudgeVerdict` gains `confidence`/`judge_version`; `judge()` gains `quality_gate`/`sandbox`; `_run_deterministic` routes through `sandbox_eval` when isolated, sets `confidence`)
- Test: `backend/tests/services/test_goal_judge_sandbox.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/services/test_goal_judge_sandbox.py
from app.services.goal_judge_service import GoalJudgeService, JudgeVerdict
from app.models.loop_spec import QualityGate


def test_verdict_has_confidence_and_version_defaults():
    v = JudgeVerdict(met=True, source="deterministic", reason="ok")
    assert v.confidence == 1.0 and v.judge_version is None


def test_deterministic_pass_is_confidence_1(tmp_path):
    (tmp_path / "ok").write_text("")
    v = GoalJudgeService.judge("g", "", check_cmd="test -f ok", cwd=str(tmp_path),
                               quality_gate=QualityGate(kind="test_pass"), sandbox="isolated")
    assert v.met is True and v.confidence == 1.0 and v.source == "deterministic"


def test_deterministic_fail_is_confidence_0(tmp_path):
    v = GoalJudgeService.judge("g", "", check_cmd="test -f nope", cwd=str(tmp_path),
                               quality_gate=QualityGate(kind="test_pass"), sandbox="isolated")
    assert v.met is False and v.confidence == 0.0


def test_inherit_sandbox_runs_in_place(tmp_path):
    (tmp_path / "ok").write_text("")
    v = GoalJudgeService.judge("g", "", check_cmd="test -f ok", cwd=str(tmp_path),
                               quality_gate=QualityGate(kind="test_pass"), sandbox="inherit")
    assert v.met is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/services/test_goal_judge_sandbox.py -q`
Expected: FAIL (`JudgeVerdict` has no `confidence`; `judge()` has no `sandbox`).

- [ ] **Step 3: Implement**

`JudgeVerdict` (add fields): `confidence: float = 1.0` and `judge_version: Optional[str] = None`.

`judge(...)` signature: add `quality_gate: Optional["QualityGate"] = None, sandbox: str = "isolated"`. Pass `sandbox` + `quality_gate` to `_run_deterministic` and `_run_llm_judge`.

`_run_deterministic(check_cmd, cwd, *, sandbox="isolated")`: when `sandbox == "isolated"`, use `from .sandbox_eval import run_isolated_check; r = run_isolated_check(check_cmd, cwd or ".", timeout=_CHECK_TIMEOUT_SECONDS)` and read `r.returncode`/`r.stdout`; else the existing in-place `subprocess.run`. Set `confidence=1.0` when met, `0.0` otherwise on the returned `JudgeVerdict`.

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && uv run pytest tests/services/test_goal_judge_sandbox.py tests/services/test_goal_judge_service.py -q`
Expected: PASS (new + existing judge suite green).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/goal_judge_service.py backend/tests/services/test_goal_judge_sandbox.py
git commit -m "feat(loops): judge confidence/version + sandboxed deterministic check"
```

---

## Task 5: LLM judge — rubric injection + version stamp + confidence parse

**Files:**
- Modify: `backend/app/services/goal_judge_service.py` (`_run_llm_judge` accepts the gate; injects rubric; stamps `judge_version`; `_parse_judge_json` → `(met, reason, confidence)`)
- Test: `backend/tests/services/test_goal_judge_llm_rubric.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/services/test_goal_judge_llm_rubric.py
from app.services.goal_judge_service import _parse_judge_json


def test_parse_includes_confidence_when_present():
    assert _parse_judge_json('{"met": true, "reason": "ok", "confidence": 0.84}') == (True, "ok", 0.84)


def test_parse_defaults_confidence_when_absent():
    assert _parse_judge_json('{"met": false, "reason": "no"}') == (False, "no", 1.0)


def test_parse_none_on_garbage():
    assert _parse_judge_json("not json") is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/services/test_goal_judge_llm_rubric.py -q`
Expected: FAIL (`_parse_judge_json` returns a 2-tuple).

- [ ] **Step 3: Implement**

`_parse_judge_json` → return `(met, reason, confidence)` where `confidence = float(blob.get("confidence", 1.0))` clamped to `[0,1]`; callers updated.
`_run_llm_judge(cls, goal, text, backend_kind, model, *, quality_gate=None)`: when `quality_gate and quality_gate.rubric`, append `\n\nRubric:\n{rubric}` to the user content; on the returned verdict set `judge_version=quality_gate.judge_version if quality_gate else None` and `confidence` from the parsed tuple. Update the `_JUDGE_SYSTEM`/template note so the judge is asked to emit an optional `"confidence"` 0–1 (backward-safe: absent → 1.0).

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && uv run pytest tests/services/test_goal_judge_llm_rubric.py tests/services/test_goal_judge_service.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/goal_judge_service.py backend/tests/services/test_goal_judge_llm_rubric.py
git commit -m "feat(loops): LLM judge rubric injection + version stamp + confidence parse"
```

---

## Task 6: Runner wiring — pass gate/sandbox, record telemetry, min_confidence met-gate

**Files:**
- Modify: `backend/app/services/goal_loop_runner.py` (`_run` judge call passes `quality_gate`+`sandbox`; records `confidence`/`judge_version`; "met" requires `confidence >= min_confidence`)
- Test: `backend/tests/test_goal_loop_min_confidence.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_goal_loop_min_confidence.py
from app.services.goal_loop_runner import _met_terminates
from app.models.loop_spec import QualityGate


def test_high_confidence_met_terminates():
    assert _met_terminates(met=True, confidence=0.9, gate=QualityGate(kind="llm_judge", min_confidence=0.7)) is True


def test_low_confidence_met_does_not_terminate():
    assert _met_terminates(met=True, confidence=0.5, gate=QualityGate(kind="llm_judge", min_confidence=0.7)) is False


def test_not_met_never_terminates():
    assert _met_terminates(met=False, confidence=1.0, gate=QualityGate(kind="llm_judge", min_confidence=0.0)) is False


def test_no_gate_falls_back_to_met():
    assert _met_terminates(met=True, confidence=0.1, gate=None) is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_goal_loop_min_confidence.py -q`
Expected: FAIL (`_met_terminates` undefined).

- [ ] **Step 3: Implement**

Add helper to `goal_loop_runner.py`:

```python
def _met_terminates(*, met: bool, confidence: float, gate) -> bool:
    if not met:
        return False
    floor = getattr(gate, "min_confidence", 0.0) if gate else 0.0
    return confidence >= floor
```

In `_run`: build `gate = state.spec.exit.quality_gate`; call `GoalJudgeService.judge(..., quality_gate=gate, sandbox=state.spec.state.sandbox)`; replace the bare `if verdict.met:` terminal check with `if _met_terminates(met=verdict.met, confidence=verdict.confidence, gate=gate):`; pass `confidence=verdict.confidence, judge_version=verdict.judge_version` into `record_goal_loop_iteration_complete(...)`.

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && uv run pytest tests/test_goal_loop_min_confidence.py tests/services/test_goal_loop_runner.py tests/test_goal_loop_ouroboros.py -q`
Expected: PASS (new + runner regression green).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/goal_loop_runner.py backend/tests/test_goal_loop_min_confidence.py
git commit -m "feat(loops): runner wires quality_gate/sandbox + min_confidence met-gate"
```

---

## Task 7: Frontend — quality-gate + sandbox config

**Files:**
- Modify: `frontend/src/services/api/grd.ts` (extend `GoalLoopConfig` with `quality_gate?` + `sandbox?`)
- Modify: `frontend/src/locales/{en,ko,ja,zh}.json` (`loopConfig.*` keys)
- Test: `frontend/src/services/api/__tests__/grd.qualitygate.test.ts`

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/services/api/__tests__/grd.qualitygate.test.ts
import { describe, it, expectTypeOf } from 'vitest';
import type { GoalLoopConfig } from '../grd';

describe('GoalLoopConfig quality-gate + sandbox', () => {
  it('accepts a quality_gate + sandbox', () => {
    const c: GoalLoopConfig = {
      goal: 'g',
      quality_gate: { kind: 'llm_judge', rubric: 'strict', judge_version: 'v2', min_confidence: 0.7 },
      sandbox: 'isolated',
    } as GoalLoopConfig;
    expectTypeOf(c.sandbox).toEqualTypeOf<'isolated' | 'inherit' | undefined>();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run src/services/api/__tests__/grd.qualitygate.test.ts`
Expected: FAIL (fields absent).

- [ ] **Step 3: Implement**

In `grd.ts`, extend `GoalLoopConfig`:

```typescript
export interface QualityGate {
  kind: 'test_pass' | 'metric' | 'llm_judge';
  metric_name?: string;
  threshold?: number;
  comparator?: '>=' | '<=' | '>' | '<' | '==';
  rubric?: string;
  judge_version?: string;
  min_confidence?: number;
}
// add to GoalLoopConfig:
  quality_gate?: QualityGate;
  sandbox?: 'isolated' | 'inherit';
```

Add `loopConfig` i18n keys to all four locales (key-identical): `qualityGate`, `gateTestPass`, `gateMetric`, `gateLlmJudge`, `rubric`, `judgeVersion`, `minConfidence`, `sandbox`, `sandboxIsolated`, `sandboxInherit`.

- [ ] **Step 4: Run to verify it passes**

Run: `cd frontend && npx vitest run src/services/api/__tests__/grd.qualitygate.test.ts && npm run build`
Expected: PASS + typecheck clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/services/api/grd.ts frontend/src/services/api/__tests__/grd.qualitygate.test.ts frontend/src/locales/
git commit -m "feat(loops): surface quality_gate + sandbox in loop config types + i18n"
```

---

## Task 8: Full verification

- [ ] **Step 1: Backend targeted suite**

Run: `cd backend && uv run pytest -q tests/test_loop_spec_quality_gate.py tests/test_loop_spec.py tests/test_migration_170_iteration_confidence.py tests/services/test_sandbox_eval.py tests/services/test_goal_judge_sandbox.py tests/services/test_goal_judge_llm_rubric.py tests/services/test_goal_judge_service.py tests/test_goal_loop_min_confidence.py tests/services/test_goal_loop_runner.py tests/test_goal_loop_ouroboros.py tests/test_ralph_unified.py tests/test_migrations_split.py`
Expected: all PASS.

- [ ] **Step 2: Frontend build + suite**

Run: `cd frontend && npm run build && npm run test:run`
Expected: build clean; suite at the 7-failure baseline, no new failures.

- [ ] **Step 3: Finish the branch** (superpowers:finishing-a-development-branch).

---

## Self-review

**Spec coverage:** §2a QualityGate+sandbox field → T1. §2b judge rubric/version/confidence → T4 (verdict+deterministic), T5 (llm). §2c sandbox_eval default-on → T3 + wired T4/T6. §2d migration 170 → T2. §2e runner wiring + min_confidence → T6. §2f frontend → T7. Verify → T8. ✅

**Placeholder scan:** every code step has literal code + expected output. Soft spots: T4/T5/T6 say "callers updated" for the `_parse_judge_json` 2-tuple→3-tuple change and the `_run_deterministic`/`_run_llm_judge` signature changes — the implementer must update the call sites in `judge()` (the 3 branch returns) and `_run_ouroboros_judge` is untouched (it has its own parser). Flagged: run the existing `test_goal_judge_service.py` after T5 to catch any missed caller.

**Type consistency:** `QualityGate.kind` ∈ {test_pass, metric, llm_judge} (T1↔T7); `sandbox` ∈ {isolated, inherit} (T1↔T4↔T6↔T7); `JudgeVerdict.confidence: float`, `judge_version: Optional[str]` consistent T4↔T5↔T6↔T2; `_parse_judge_json` 3-tuple consistent T5↔T4; `record_iteration_complete(..., confidence=, judge_version=)` consistent T2↔T6. ✅
