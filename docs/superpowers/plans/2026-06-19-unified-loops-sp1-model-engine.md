# Unified Loops — Sub-project #1: Model + Engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a typed `LoopSpec` schema and make `goal_loop_runner` the single loop executor — adding token-budget + generic-stagnation circuit breakers and a `context_policy=reset` mode — then deep-unify Ralph onto it.

**Architecture:** `goal_loop_runner` already owns the termination ladder, per-iteration DB tracking, resume, and stop. We promote its untyped config dict to a `LoopSpec` struct (with a `from_legacy_config` adapter so every existing caller/route is untouched), read the termination ladder from the spec, add two new exits, add a fresh-session-per-iteration execution mode (reusing the existing `_spawn_resumed_session` recipe), and rewrite `RalphSessionHandler` to build a `LoopSpec` and drive the same executor (retiring `RalphMonitorService`).

**Tech Stack:** Python 3.10 (msgspec Struct + Pydantic, Ruff line-length=100), Litestar, raw SQLite migrations (`v07_features.py`), pytest (`isolated_db`). Frontend: Vue 3 + TS, Vitest, vue-i18n (en/ko/ja/zh).

**Spec:** `docs/superpowers/specs/2026-06-19-unified-loops-sp1-model-engine-design.md`

---

## File structure

| File | Responsibility | Action |
|---|---|---|
| `backend/app/models/loop_spec.py` | `LoopSpec` struct + `from_legacy_config()` + ordered-exit helpers | **Create** |
| `backend/app/services/loop_progress.py` | Shared no-progress signals (git-commit hash; verdict-unchanged) | **Create** |
| `backend/app/db/migrations/v07_features.py` | Migration 169: `body_kind` + `tokens_total` cols on `goal_loop_iterations` | **Modify** (~line 1325 reg list) |
| `backend/app/db/goal_loop.py` | record/list helpers accept `body_kind`, `tokens_total` | **Modify** |
| `backend/app/services/goal_loop_runner.py` | Consume `LoopSpec`; token + stagnation exits; `context_policy=reset` | **Modify** |
| `backend/app/services/execution_type_handler.py` | `RalphSessionHandler` → build `LoopSpec`, call `start_runner` | **Modify** (`:141`) |
| `backend/app/services/ralph_monitor_service.py` | Retire (logic moved to `loop_progress`) | **Modify/remove** |
| `frontend/src/services/api/grd.ts` | `LoopSpec` config fields on the session types | **Modify** |
| `frontend/src/locales/{en,ko,ja,zh}.json` | new loop-config i18n keys | **Modify** |
| Tests | per task below | **Create** |

---

## Task 1: `LoopSpec` model + `from_legacy_config`

**Files:**
- Create: `backend/app/models/loop_spec.py`
- Test: `backend/tests/test_loop_spec.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_loop_spec.py
from app.models.loop_spec import LoopSpec


def test_from_legacy_goal_loop_config_roundtrips():
    legacy = {
        "goal": "make tests pass",
        "check_cmd": "pytest -q",
        "max_iterations": 20,
        "max_wall_seconds": 1800,
        "max_cost_usd": 5.0,
        "ouroboros": True,
        "judge_backend_kind": "claude",
        "judge_model_override": None,
        "metric_spec": None,
    }
    spec = LoopSpec.from_legacy_config(legacy, execution_type="goal_loop")
    assert spec.body.goal == "make tests pass"
    assert spec.body.kind == "eval_refine"
    assert spec.exit.max_iterations == 20
    assert spec.exit.max_wall_seconds == 1800
    assert spec.exit.max_cost_usd == 5.0
    assert spec.exit.max_tokens == 0          # new field defaults off
    assert spec.exit.convergence is True       # maps from ouroboros
    assert spec.exit.stagnation_no_progress_for == 0  # off by default
    assert spec.state.context_policy == "carry"
    assert spec.meta_execution_type == "goal_loop"


def test_from_legacy_ralph_config_maps_to_agent_task_reset():
    legacy = {
        "task_description": "build the thing",
        "max_iterations": 50,
        "no_progress_threshold": 3,
        "completion_promise": "COMPLETE",
    }
    spec = LoopSpec.from_legacy_config(legacy, execution_type="ralph")
    assert spec.body.kind == "agent_task"
    assert spec.body.goal == "build the thing"
    assert spec.exit.max_iterations == 50
    assert spec.exit.stagnation_no_progress_for == 3   # ralph's git no-progress
    assert spec.state.context_policy == "reset"        # ralph-purist fresh context
    assert spec.meta_execution_type == "ralph"


def test_new_fields_parse_when_present():
    spec = LoopSpec.from_legacy_config(
        {"goal": "g", "max_tokens": 500000, "context_policy": "reset",
         "stagnation_no_progress_for": 4},
        execution_type="goal_loop",
    )
    assert spec.exit.max_tokens == 500000
    assert spec.state.context_policy == "reset"
    assert spec.exit.stagnation_no_progress_for == 4
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_loop_spec.py -q`
Expected: FAIL (`ModuleNotFoundError: app.models.loop_spec`).

- [ ] **Step 3: Implement `LoopSpec`**

```python
# backend/app/models/loop_spec.py
"""LoopSpec — the typed unifying schema for the v0.6.0 loop executor.

Promotes the previously-untyped goal-loop / ralph config dicts into one
struct. ``from_legacy_config`` adapts both legacy shapes so every existing
caller and route keeps passing plain dicts (the runner parses internally).
"""

from __future__ import annotations

from typing import Literal, Optional

import msgspec

BodyKind = Literal["agent_task", "eval_refine"]
ContextPolicy = Literal["carry", "reset"]


class LoopBody(msgspec.Struct, frozen=True):
    kind: BodyKind
    goal: str
    check_cmd: Optional[str] = None
    judge_backend_kind: str = "claude"
    judge_model_override: Optional[str] = None
    metric_spec: Optional[dict] = None


class LoopExit(msgspec.Struct, frozen=True):
    # Quality-gate / convergence first; HARD budgets last (always enforced).
    convergence: bool = True                  # Ouroboros verdict-convergence
    stagnation_no_progress_for: int = 0       # 0 = off
    max_iterations: int = 20
    max_wall_seconds: int = 1800
    max_cost_usd: float = 0.0                  # 0 = off
    max_tokens: int = 0                        # 0 = off (tokens_in+out accumulated)


class LoopState(msgspec.Struct, frozen=True):
    context_policy: ContextPolicy = "carry"
    checkpoint: bool = True


class LoopSpec(msgspec.Struct, frozen=True):
    body: LoopBody
    exit: LoopExit
    state: LoopState
    meta_execution_type: str = "goal_loop"

    @staticmethod
    def from_legacy_config(config: dict, *, execution_type: str = "goal_loop") -> "LoopSpec":
        c = config or {}
        if execution_type == "ralph":
            goal = (c.get("task_description") or c.get("goal") or "").strip()
            body = LoopBody(kind="agent_task", goal=goal, check_cmd=c.get("check_cmd"))
            exit_ = LoopExit(
                convergence=False,
                stagnation_no_progress_for=int(c.get("no_progress_threshold") or 3),
                max_iterations=int(c.get("max_iterations") or 50),
                max_wall_seconds=int(c.get("max_wall_seconds") or 1800),
                max_cost_usd=_as_float(c.get("max_cost_usd")),
                max_tokens=int(c.get("max_tokens") or 0),
            )
            state = LoopState(context_policy=c.get("context_policy") or "reset")
            return LoopSpec(body=body, exit=exit_, state=state, meta_execution_type="ralph")

        # goal_loop (default)
        body = LoopBody(
            kind="eval_refine",
            goal=(c.get("goal") or "").strip(),
            check_cmd=c.get("check_cmd"),
            judge_backend_kind=c.get("judge_backend_kind", "claude"),
            judge_model_override=c.get("judge_model_override"),
            metric_spec=c.get("metric_spec"),
        )
        exit_ = LoopExit(
            convergence=bool(c.get("ouroboros", True)),
            stagnation_no_progress_for=int(c.get("stagnation_no_progress_for") or 0),
            max_iterations=int(c.get("max_iterations") or 20),
            max_wall_seconds=int(c.get("max_wall_seconds") or 1800),
            max_cost_usd=_as_float(c.get("max_cost_usd")),
            max_tokens=int(c.get("max_tokens") or 0),
        )
        state = LoopState(context_policy=c.get("context_policy") or "carry")
        return LoopSpec(body=body, exit=exit_, state=state, meta_execution_type="goal_loop")


def _as_float(v) -> float:
    try:
        return float(v or 0.0)
    except (TypeError, ValueError):
        return 0.0
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && uv run pytest tests/test_loop_spec.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/loop_spec.py backend/tests/test_loop_spec.py
git commit -m "feat(loops): LoopSpec typed schema + from_legacy_config adapter"
```

---

## Task 2: Migration 169 — `body_kind` + `tokens_total` on `goal_loop_iterations`

**Files:**
- Modify: `backend/app/db/migrations/v07_features.py` (add `_migrate_169_loop_iteration_cols`; register after `(168, ...)`)
- Modify: `backend/app/db/goal_loop.py` (`record_iteration_complete` + `list_iterations` carry the new cols)
- Test: `backend/tests/test_migration_169_loop_cols.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_migration_169_loop_cols.py
def test_goal_loop_iterations_has_body_kind_and_tokens_total(isolated_db):
    from app.db.connection import get_connection
    with get_connection() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(goal_loop_iterations)")}
    assert "body_kind" in cols
    assert "tokens_total" in cols


def test_record_iteration_complete_persists_body_kind(isolated_db):
    from app.db.goal_loop import record_iteration_start, record_iteration_complete, list_iterations
    record_iteration_start("sess-x", 1)
    record_iteration_complete(
        "sess-x", 1, verdict="not_met", judge_source="cmd", judge_reason="r",
        judge_stdout="", tokens_in=10, tokens_out=20, cost_usd=0.01,
        body_kind="agent_task",
    )
    rows = list_iterations("sess-x")
    assert rows[0]["body_kind"] == "agent_task"
    assert rows[0]["tokens_total"] == 30
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_migration_169_loop_cols.py -q`
Expected: FAIL (`body_kind` not in cols / unexpected kwarg).

- [ ] **Step 3: Implement migration + db helper changes**

In `v07_features.py`, add near the other migration defs:

```python
def _migrate_169_loop_iteration_cols(conn) -> None:
    """v0.6.0 unified loops: tag each goal_loop_iterations row with the loop
    body kind (so Ralph's agent_task iterations share the table) and store a
    convenience tokens_total for the token-budget circuit breaker."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(goal_loop_iterations)")}
    if "body_kind" not in cols:
        conn.execute(
            "ALTER TABLE goal_loop_iterations ADD COLUMN body_kind TEXT DEFAULT 'eval_refine'"
        )
    if "tokens_total" not in cols:
        conn.execute("ALTER TABLE goal_loop_iterations ADD COLUMN tokens_total INTEGER")
```

Register it (after the `(168, "grd_genome_suggestions", ...)` entry):

```python
    # v0.6.0: unified-loops iteration tagging + token-total column.
    (169, "loop_iteration_cols", _migrate_169_loop_iteration_cols),
```

In `backend/app/db/goal_loop.py`, extend `record_iteration_complete` to accept `body_kind: str = "eval_refine"` and write `body_kind` + `tokens_total = (tokens_in or 0) + (tokens_out or 0)`; add both columns to the `SELECT`/`_row_to_dict` in `list_iterations` and `recent_iteration_verdicts` (the latter unchanged in shape). Exact edit: add the two columns to the `INSERT ... ON CONFLICT ... UPDATE` statement and the dict mapping.

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && uv run pytest tests/test_migration_169_loop_cols.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/migrations/v07_features.py backend/app/db/goal_loop.py backend/tests/test_migration_169_loop_cols.py
git commit -m "feat(loops): migration 169 — body_kind + tokens_total on loop iterations"
```

---

## Task 3: Runner consumes `LoopSpec` (compat wrapper, ladder from spec)

**Files:**
- Modify: `backend/app/services/goal_loop_runner.py` (`_RunnerState` gains `spec` + `total_tokens`; `_run` reads `state.spec.exit.*` for max_iterations / wall / cost / convergence instead of bare config keys)
- Test: `backend/tests/test_goal_loop_runner_loopspec.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_goal_loop_runner_loopspec.py
from app.services import goal_loop_runner as glr
from app.models.loop_spec import LoopSpec


def test_runner_state_exposes_parsed_spec():
    spec = LoopSpec.from_legacy_config({"goal": "g", "max_iterations": 7}, execution_type="goal_loop")
    state = glr._RunnerState(session_id="s", config={"goal": "g", "max_iterations": 7},
                             started_at=0.0, spec=spec)
    assert state.spec.exit.max_iterations == 7
    assert state.total_tokens == 0


def test_start_runner_parses_legacy_dict_into_spec(monkeypatch):
    captured = {}
    monkeypatch.setattr(glr.threading, "Thread",
                        lambda **kw: type("T", (), {"start": lambda self: captured.update(kw=kw)})())
    glr.start_runner("sess-spec", {"goal": "g", "max_iterations": 3}, cwd="/tmp")
    state = glr._runners["sess-spec"]
    assert state.spec.exit.max_iterations == 3
    glr._runners.pop("sess-spec", None)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_goal_loop_runner_loopspec.py -q`
Expected: FAIL (`_RunnerState` has no `spec`).

- [ ] **Step 3: Implement**

In `goal_loop_runner.py`: add to the `_RunnerState` dataclass (line ~230):

```python
    spec: "LoopSpec" = None  # parsed once at start; ladder reads from here
    total_tokens: int = 0
```

In `start_runner` (line 245), parse the spec when constructing state:

```python
from app.models.loop_spec import LoopSpec
...
        execution_type = (config.get("_execution_type") or "goal_loop")
        state = _RunnerState(
            session_id=session_id,
            config=config,
            started_at=time.time(),
            spec=LoopSpec.from_legacy_config(config, execution_type=execution_type),
        )
```

In `_run`, replace the bare reads (`max_iterations`, `max_wall_seconds`, `max_cost_usd`, `ouroboros`) with `state.spec.exit.max_iterations` etc. (`ouroboros` → `state.spec.exit.convergence`). Keep all existing ladder logic/order identical — only the source of the numbers changes. Update `get_runner_state` to read `state.spec.exit.max_iterations` / `max_wall_seconds`.

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && uv run pytest tests/test_goal_loop_runner_loopspec.py tests/test_goal_loop_runner.py -q`
Expected: PASS (new tests + existing goal-loop suite unaffected).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/goal_loop_runner.py backend/tests/test_goal_loop_runner_loopspec.py
git commit -m "feat(loops): goal_loop_runner consumes LoopSpec (back-compat dict adapter)"
```

---

## Task 4: Token-budget circuit breaker (`max_tokens`)

**Files:**
- Modify: `backend/app/services/goal_loop_runner.py` (accumulate `state.total_tokens`; ladder check after the cost-cap, emit `reason="token_cap"`)
- Test: `backend/tests/test_goal_loop_token_cap.py`

- [ ] **Step 1: Write the failing test** (drive `_check_token_cap` as an extracted pure helper for unit-testability)

```python
# backend/tests/test_goal_loop_token_cap.py
from app.services.goal_loop_runner import _token_cap_exceeded

def test_token_cap_off_when_zero():
    assert _token_cap_exceeded(total=10_000, max_tokens=0) is False

def test_token_cap_triggers_at_or_above_limit():
    assert _token_cap_exceeded(total=500_000, max_tokens=500_000) is True
    assert _token_cap_exceeded(total=499_999, max_tokens=500_000) is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_goal_loop_token_cap.py -q`
Expected: FAIL (`_token_cap_exceeded` undefined).

- [ ] **Step 3: Implement**

Add the helper + ladder check in `goal_loop_runner.py`:

```python
def _token_cap_exceeded(total: int, max_tokens: int) -> bool:
    return max_tokens > 0 and total >= max_tokens
```

In `_run`, right after the cost-cap block (line ~487), accumulate and check:

```python
            state.total_tokens += int((verdict.tokens_in or 0) + (verdict.tokens_out or 0))
            if _token_cap_exceeded(state.total_tokens, state.spec.exit.max_tokens):
                _broadcast_end(
                    session_id,
                    reason="token_cap",
                    detail=f"tokens {state.total_tokens} reached cap {state.spec.exit.max_tokens}",
                )
                ProjectSessionManager.stop_session(session_id)
                break
```

Pass `body_kind=state.spec.body.kind` into `record_iteration_complete` so the new column is populated.

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && uv run pytest tests/test_goal_loop_token_cap.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/goal_loop_runner.py backend/tests/test_goal_loop_token_cap.py
git commit -m "feat(loops): token-budget circuit breaker (max_tokens, reason=token_cap)"
```

---

## Task 5: Shared no-progress signal + generic stagnation exit

**Files:**
- Create: `backend/app/services/loop_progress.py` (git-commit-hash check, extracted from `RalphMonitorService`)
- Modify: `backend/app/services/goal_loop_runner.py` (stagnation exit when `stagnation_no_progress_for > 0`)
- Test: `backend/tests/test_loop_progress.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_loop_progress.py
from app.services.loop_progress import head_commit, made_progress

def test_made_progress_true_on_new_commit():
    assert made_progress(prev="abc123", current="def456") is True

def test_made_progress_false_when_unchanged():
    assert made_progress(prev="abc123", current="abc123") is False

def test_head_commit_returns_none_outside_repo(tmp_path):
    assert head_commit(str(tmp_path)) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_loop_progress.py -q`
Expected: FAIL (`app.services.loop_progress` missing).

- [ ] **Step 3: Implement**

```python
# backend/app/services/loop_progress.py
"""Shared no-progress signals for the unified loop executor.

agent_task loops (Ralph) detect progress via new git commits; the helper is
extracted from the retired RalphMonitorService so the executor — not a side
monitor — decides stagnation.
"""

from __future__ import annotations

import subprocess
from typing import Optional


def head_commit(cwd: str) -> Optional[str]:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True, timeout=10
        )
        return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def made_progress(prev: Optional[str], current: Optional[str]) -> bool:
    """True when the HEAD commit advanced (a new commit landed this iteration)."""
    return bool(current) and current != prev
```

In `goal_loop_runner.py`, track `state.no_progress_streak` and `state.last_commit` on `_RunnerState`; after recording each iteration, for `agent_task` bodies compute progress via `loop_progress`, for `eval_refine` reuse the existing `not_met_streak`. Add the ladder check (after convergence):

```python
            threshold = state.spec.exit.stagnation_no_progress_for
            if threshold > 0:
                if state.spec.body.kind == "agent_task":
                    cur = loop_progress.head_commit(cwd or ".")
                    if loop_progress.made_progress(state.last_commit, cur):
                        state.no_progress_streak = 0
                    else:
                        state.no_progress_streak += 1
                    state.last_commit = cur
                    streak = state.no_progress_streak
                else:
                    streak = state.not_met_streak
                if streak >= threshold:
                    _broadcast_end(
                        session_id, reason="stagnation",
                        detail=f"no progress for {threshold} iterations",
                    )
                    ProjectSessionManager.stop_session(session_id)
                    break
```

Add `no_progress_streak: int = 0` and `last_commit: Optional[str] = None` to `_RunnerState`.

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && uv run pytest tests/test_loop_progress.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/loop_progress.py backend/app/services/goal_loop_runner.py backend/tests/test_loop_progress.py
git commit -m "feat(loops): generic stagnation exit + shared no-progress signal"
```

---

## Task 6: `context_policy=reset` (fresh session per iteration)

**Files:**
- Modify: `backend/app/services/goal_loop_runner.py` (when `state.spec.state.context_policy == "reset"`, spawn a fresh session per continue instead of `_send_continue` into the same process; reuse the `_spawn_resumed_session` recipe at `:762`)
- Test: `backend/tests/test_goal_loop_context_policy.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_goal_loop_context_policy.py
from app.services import goal_loop_runner as glr

def test_carry_uses_send_continue(monkeypatch):
    calls = {"continue": 0, "reset": 0}
    monkeypatch.setattr(glr, "_send_continue", lambda *a, **k: calls.__setitem__("continue", calls["continue"] + 1))
    monkeypatch.setattr(glr, "_advance_iteration", lambda *a, **k: calls.__setitem__("reset", calls["reset"] + 1), raising=False)
    glr._next_iteration(policy="carry", session_id="s", cwd="/tmp", goal="g")
    assert calls["continue"] == 1 and calls["reset"] == 0

def test_reset_spawns_fresh_session(monkeypatch):
    calls = {"continue": 0, "reset": 0}
    monkeypatch.setattr(glr, "_send_continue", lambda *a, **k: calls.__setitem__("continue", calls["continue"] + 1))
    monkeypatch.setattr(glr, "_advance_iteration", lambda *a, **k: calls.__setitem__("reset", calls["reset"] + 1))
    glr._next_iteration(policy="reset", session_id="s", cwd="/tmp", goal="g")
    assert calls["reset"] == 1 and calls["continue"] == 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_goal_loop_context_policy.py -q`
Expected: FAIL (`_next_iteration` undefined).

- [ ] **Step 3: Implement**

Add a dispatcher that the loop calls to advance an iteration, and a reset-spawn that reuses the existing fresh-session recipe (factor the body of `_spawn_resumed_session` into `_advance_iteration(session_id, cwd, goal)` that spawns a fresh stream-json session seeded with `_build_resume_context` + the goal, accumulating budgets/tracking on the SAME `_RunnerState`):

```python
def _next_iteration(*, policy: str, session_id: str, cwd, goal: str, **kw) -> None:
    if policy == "reset":
        _advance_iteration(session_id=session_id, cwd=cwd, goal=goal, **kw)
    else:
        _send_continue(session_id, goal=goal, **kw)
```

In `_run`, replace the direct `_send_continue(...)` call at the end of the iteration body with `_next_iteration(policy=state.spec.state.context_policy, ...)`. Keep `carry` behavior byte-identical.

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && uv run pytest tests/test_goal_loop_context_policy.py tests/test_goal_loop_runner.py -q`
Expected: PASS (new + existing goal-loop suite green).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/goal_loop_runner.py backend/tests/test_goal_loop_context_policy.py
git commit -m "feat(loops): context_policy=reset (fresh session per iteration)"
```

---

## Task 7: Deep-unify Ralph onto the executor

**Files:**
- Modify: `backend/app/services/execution_type_handler.py` (`RalphSessionHandler.start` builds a `LoopSpec` legacy dict, creates a stream-json goal_loop-style session, calls `start_runner` with `_execution_type="ralph"`; retire the `/ralph-loop` skill prompt + `RalphMonitorService.start_monitoring`)
- Modify: `backend/app/services/ralph_monitor_service.py` (delete or shrink to a thin shim; logic now lives in `loop_progress`)
- Test: `backend/tests/test_ralph_unified.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_ralph_unified.py
from app.services.execution_type_handler import RalphSessionHandler
from app.models.loop_spec import LoopSpec

def test_ralph_start_config_becomes_agent_task_reset_loopspec(monkeypatch, isolated_db):
    seen = {}
    monkeypatch.setattr(RalphSessionHandler, "_check_ralph_plugin", staticmethod(lambda: None))
    import app.services.execution_type_handler as eth
    monkeypatch.setattr(eth.ProjectSessionManager, "create_session", lambda **kw: seen.update(create=kw) or "sess-r")
    monkeypatch.setattr(eth.ProjectSessionManager, "get_session_info", lambda sid: {"pid": 1, "status": "active"})
    started = {}
    monkeypatch.setattr(eth, "start_runner", lambda sid, cfg, cwd: started.update(sid=sid, cfg=cfg), raising=False)

    RalphSessionHandler().start({
        "project_id": "p", "cwd": "/tmp",
        "ralph_config": {"task_description": "do it", "max_iterations": 40, "no_progress_threshold": 3},
    })
    spec = LoopSpec.from_legacy_config(started["cfg"], execution_type=started["cfg"]["_execution_type"])
    assert spec.body.kind == "agent_task"
    assert spec.state.context_policy == "reset"
    assert spec.exit.max_iterations == 40
    assert seen["create"]["execution_type"] == "ralph"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_ralph_unified.py -q`
Expected: FAIL (handler still injects `/ralph-loop`, never calls `start_runner`).

- [ ] **Step 3: Implement**

Rewrite `RalphSessionHandler.start` (`:183`) to: keep the plugin precheck; build `cfg = {**ralph_config, "_execution_type": "ralph"}`; create a stream-json session (`execution_type="ralph"`, no PTY, mirroring `GoalLoopSessionHandler.start`'s create recipe at `:472`) seeded with the goal prompt; `set_goal_loop_config(session_id, cfg)`; `start_runner(session_id, cfg, cwd=...)`. Remove the `/ralph-loop` prompt construction and the `RalphMonitorService.start_monitoring` call. `monitor`/`stop`/`get_output` delegate to the goal-loop/ProjectSessionManager paths (Ralph now resumable + tracked). Reduce `ralph_monitor_service.py` to a deprecation shim (or delete + drop its imports).

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && uv run pytest tests/test_ralph_unified.py tests/test_goal_loop_runner.py -q`
Expected: PASS. Also run any existing ralph tests: `uv run pytest -q -k ralph`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/execution_type_handler.py backend/app/services/ralph_monitor_service.py backend/tests/test_ralph_unified.py
git commit -m "feat(loops): deep-unify Ralph onto the goal-loop executor (LoopSpec, resumable, budgeted)"
```

---

## Task 8: Frontend — surface the new loop config fields

**Files:**
- Modify: `frontend/src/services/api/grd.ts` (add `max_tokens?`, `context_policy?`, `stagnation_no_progress_for?` to the goal-loop/ralph config types)
- Modify: `frontend/src/locales/{en,ko,ja,zh}.json` (`loopConfig.*` keys: tokenBudget, contextPolicy, carry, reset, stagnation)
- Test: `frontend/src/services/api/__tests__/grd.loopconfig.test.ts`

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/services/api/__tests__/grd.loopconfig.test.ts
import { describe, it, expectTypeOf } from 'vitest';
import type { GoalLoopConfig } from '../grd';

describe('GoalLoopConfig has unified-loop fields', () => {
  it('accepts max_tokens / context_policy / stagnation', () => {
    const c: GoalLoopConfig = {
      goal: 'g', max_iterations: 10, max_tokens: 500000,
      context_policy: 'reset', stagnation_no_progress_for: 3,
    } as GoalLoopConfig;
    expectTypeOf(c.context_policy).toEqualTypeOf<'carry' | 'reset' | undefined>();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run src/services/api/__tests__/grd.loopconfig.test.ts`
Expected: FAIL (type error — fields absent).

- [ ] **Step 3: Implement**

In `grd.ts`, extend the goal-loop config interface:

```typescript
export interface GoalLoopConfig {
  goal: string;
  check_cmd?: string;
  max_iterations?: number;
  max_wall_seconds?: number;
  max_cost_usd?: number;
  ouroboros?: boolean;
  metric_spec?: Record<string, unknown> | null;
  // v0.6.0 unified loops
  max_tokens?: number;
  context_policy?: 'carry' | 'reset';
  stagnation_no_progress_for?: number;
}
```

Add `loopConfig` i18n keys to all four locales (key-identical): `tokenBudget`, `contextPolicy`, `contextCarry`, `contextReset`, `stagnation`.

- [ ] **Step 4: Run to verify it passes**

Run: `cd frontend && npx vitest run src/services/api/__tests__/grd.loopconfig.test.ts && npm run build`
Expected: PASS + typecheck clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/services/api/grd.ts frontend/src/services/api/__tests__/grd.loopconfig.test.ts frontend/src/locales/
git commit -m "feat(loops): surface max_tokens/context_policy/stagnation in loop config types + i18n"
```

---

## Task 9: Full verification

- [ ] **Step 1: Backend targeted suite**

Run: `cd backend && uv run pytest -q tests/test_loop_spec.py tests/test_migration_169_loop_cols.py tests/test_goal_loop_runner_loopspec.py tests/test_goal_loop_token_cap.py tests/test_loop_progress.py tests/test_goal_loop_context_policy.py tests/test_ralph_unified.py tests/test_goal_loop_runner.py tests/test_migrations_split.py`
Expected: all PASS.

- [ ] **Step 2: Frontend build + suite**

Run: `cd frontend && npm run build && npm run test:run`
Expected: build clean; suite at the 7-failure baseline, no new failures.

- [ ] **Step 3: Commit any test-fixup deltas, then finish the branch** (superpowers:finishing-a-development-branch).

---

## Self-review

**Spec coverage:** §2a LoopSpec → T1. §2b runner-consumes-spec → T3. §2c token budget → T4, stagnation → T5. §2d Ralph deep-unify → T7, context_policy=reset → T6. §2e migration 169 → T2. Frontend surfacing → T8. Verification → T9. ✅ all spec sections mapped.

**Placeholder scan:** every code step has literal code; commands have expected output. The one soft spot is T6/T7 (`_advance_iteration` factored from `_spawn_resumed_session`, and the Ralph create-recipe mirrored from `GoalLoopSessionHandler.start`) — both reference concrete existing functions (`goal_loop_runner.py:762`, `execution_type_handler.py:472`) the implementer copies from; flagged as the two riskiest tasks, build test-first.

**Type consistency:** `LoopSpec.body.kind` ∈ {agent_task, eval_refine}; `state.context_policy` ∈ {carry, reset}; `exit.stagnation_no_progress_for` / `max_tokens` used identically across T1/T3/T4/T5/T8; `_execution_type` config key threads T3↔T7; `record_iteration_complete(..., body_kind=)` consistent T2↔T4. ✅
