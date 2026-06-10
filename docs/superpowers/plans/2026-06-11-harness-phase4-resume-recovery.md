# Harness-1 Phase 4 — Restart Recovery + Claude Resume + Goal-Loop Re-Entry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Interrupted trigger executions become recoverable (manual `POST /redispatch` + per-trigger opt-in auto-recovery at startup), claude re-dispatches resume with `--resume <session_id>` when a handle exists, and dead goal-loop sessions re-enter from persisted iteration knowledge.

**Architecture:** Unit A: a `redispatch_execution` service entry that re-runs an `interrupted`/`failed` execution through the existing `run_trigger` path with the **stored** prompt (`prompt_override` — no re-render), provenance via `execution_logs.redispatched_from` (migration 152) and a no-fan-out guard. Unit B: capture claude's `session_id` (already parsed by `extract_token_usage`) onto `execution_logs` post-run; `CommandBuilder` gains `resume_session_id` (claude-only `--resume`). Unit C: `resume_goal_loop` reads `get_goal_loop_config` + `goal_loop_iterations`/dead-ends and respawns through the existing `start_runner` path with a re-entry context block; `failed` goal-loop sessions are eligible (no status-CHECK rebuild). One frontend touch: a Re-dispatch button in ExecutionHistory.

**Tech Stack:** Python/raw SQLite/Litestar/pytest; Vue 3 + Vitest (one button); ruff 100.

**Conventions:**
- Migration **152** (current max 151), PRAGMA-guarded ALTERs (pattern `_migrate_151`), registered in `V07_MIGRATIONS` AND every touched fresh-DDL module; fresh-DDL tests call `create_fresh_schema` directly (Phase-3 lesson).
- Targeted pytest only; frontend tests colocated `__tests__/`; i18n keys in all four catalogs.
- Verified grounding (do not re-derive): `run_trigger(cls, trigger: dict, message_text, event=None, trigger_type="webhook", env_overrides=None, account_id=None, working_directory=None, execution_id=None)` renders the prompt at ~`execution_service.py:376` via `PromptRenderer`; post-run usage block at ~`:714-718`; `set/get_goal_loop_config` in `app/db/goal_loop.py`; goal-loop spawn recipe at `execution_type_handler.py:478-495` (`create` → `set_goal_loop_config` → `start_runner(session_id, goal_config, cwd)`); goal-loop session routes live in `app_litestar/routes/grd_routes.py` (`/{project_id}/sessions/{session_id}/...`); `project_sessions` CHECK is `('active','paused','completed','failed')`.

---

## Task 1: Migration 152 — provenance columns + auto_redispatch flag

**Files:**
- Modify: `backend/app/db/schema/_core.py` (execution_logs DDL: + `redispatched_from`; triggers DDL: + `auto_redispatch`)
- Modify: `backend/app/db/schema/_orgs.py` (project_sessions DDL: + `resumed_from`)
- Modify: `backend/app/db/migrations/v07_features.py` (`_migrate_152_resume_recovery` + tuple)
- Modify: `backend/app/db/execution_logs.py` (three small helpers)
- Test: `backend/tests/test_migration_152_resume_recovery.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_migration_152_resume_recovery.py
"""Migration 152: redispatch/resume provenance + auto_redispatch flag (Phase 4)."""

from app.db.connection import get_connection


def _make_execution(execution_id: str = "exec-1") -> None:
    from app.db.execution_logs import create_execution_log

    create_execution_log(
        execution_id=execution_id,
        trigger_id="bot-pr-review",
        trigger_type="manual",
        started_at="2026-06-11T00:00:00",
        prompt="p",
        backend_type="claude",
        command="echo hi",
    )


def test_migration_152_registered():
    from app.db.migrations import VERSIONED_MIGRATIONS

    versions = {v for (v, _n, _f) in VERSIONED_MIGRATIONS}
    names = {n for (_v, n, _f) in VERSIONED_MIGRATIONS}
    assert 152 in versions
    assert "resume_recovery" in names


def test_fresh_schema_has_all_three_columns():
    """create_fresh_schema directly — the fixture DB also runs migrations and
    would mask a missing fresh-DDL edit (Phase-3 lesson)."""
    import sqlite3

    from app.db.schema import create_fresh_schema

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_fresh_schema(conn)
    el = {r["name"] for r in conn.execute("PRAGMA table_info(execution_logs)")}
    tr = {r["name"] for r in conn.execute("PRAGMA table_info(triggers)")}
    ps = {r["name"] for r in conn.execute("PRAGMA table_info(project_sessions)")}
    assert "redispatched_from" in el
    assert "auto_redispatch" in tr
    assert "resumed_from" in ps


def test_migration_152_alter_is_idempotent():
    import sqlite3

    from app.db.migrations.v07_features import _migrate_152_resume_recovery

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE execution_logs (id INTEGER PRIMARY KEY, execution_id TEXT UNIQUE)")
    conn.execute("CREATE TABLE triggers (id TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE project_sessions (id TEXT PRIMARY KEY)")
    _migrate_152_resume_recovery(conn)
    _migrate_152_resume_recovery(conn)  # must not raise
    assert "redispatched_from" in {
        r["name"] for r in conn.execute("PRAGMA table_info(execution_logs)")
    }
    assert "auto_redispatch" in {r["name"] for r in conn.execute("PRAGMA table_info(triggers)")}
    assert "resumed_from" in {
        r["name"] for r in conn.execute("PRAGMA table_info(project_sessions)")
    }


def test_redispatch_provenance_helpers():
    from app.db.execution_logs import (
        get_redispatch_child,
        set_execution_session_id,
        set_redispatched_from,
    )

    _make_execution("exec-orig")
    _make_execution("exec-new")
    assert get_redispatch_child("exec-orig") is None

    set_redispatched_from("exec-new", "exec-orig")
    child = get_redispatch_child("exec-orig")
    assert child is not None and child["execution_id"] == "exec-new"

    set_execution_session_id("exec-orig", "sess-abc123")
    with get_connection() as conn:
        row = conn.execute(
            "SELECT session_id FROM execution_logs WHERE execution_id = ?", ("exec-orig",)
        ).fetchone()
    assert row["session_id"] == "sess-abc123"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_migration_152_resume_recovery.py -q`
Expected: FAIL — migration fn + helpers missing.

- [ ] **Step 3: Fresh DDL edits**

In `backend/app/db/schema/_core.py`:
- `execution_logs` CREATE TABLE: add `redispatched_from TEXT,` after `session_id TEXT,`.
- `triggers` CREATE TABLE: add `auto_redispatch INTEGER DEFAULT 0,` after `auto_resolve INTEGER DEFAULT 0,`.

In `backend/app/db/schema/_orgs.py`, `project_sessions` CREATE TABLE: add `resumed_from TEXT,` after the `super_agent_id`-area columns (any position before the constraints).

- [ ] **Step 4: Migration 152**

In `backend/app/db/migrations/v07_features.py`, before `V07_MIGRATIONS`:

```python
def _migrate_152_resume_recovery(conn):
    """Harness-1 Phase 4: redispatch/resume provenance + per-trigger
    auto-recovery flag. PRAGMA-guarded ALTERs — idempotent."""
    el = {r["name"] for r in conn.execute("PRAGMA table_info(execution_logs)")}
    if "redispatched_from" not in el:
        conn.execute("ALTER TABLE execution_logs ADD COLUMN redispatched_from TEXT")
    tr = {r["name"] for r in conn.execute("PRAGMA table_info(triggers)")}
    if "auto_redispatch" not in tr:
        conn.execute("ALTER TABLE triggers ADD COLUMN auto_redispatch INTEGER DEFAULT 0")
    ps = {r["name"] for r in conn.execute("PRAGMA table_info(project_sessions)")}
    if "resumed_from" not in ps:
        conn.execute("ALTER TABLE project_sessions ADD COLUMN resumed_from TEXT")
```

Registry tuple (after 151):

```python
    # Harness-1 Phase 4: restart recovery + resume provenance.
    (152, "resume_recovery", _migrate_152_resume_recovery),
```

- [ ] **Step 5: The three helpers**

Append to `backend/app/db/execution_logs.py`:

```python
def set_redispatched_from(execution_id: str, origin_execution_id: str) -> bool:
    """Provenance link: this execution is a re-dispatch of origin (Phase 4)."""
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE execution_logs SET redispatched_from = ? WHERE execution_id = ?",
            (origin_execution_id, execution_id),
        )
        conn.commit()
        return cur.rowcount > 0


def get_redispatch_child(origin_execution_id: str) -> Optional[dict]:
    """The execution that re-dispatched origin, if any (no-fan-out guard)."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM execution_logs WHERE redispatched_from = ? LIMIT 1",
            (origin_execution_id,),
        ).fetchone()
    return dict(row) if row else None


def set_execution_session_id(execution_id: str, session_id: str) -> bool:
    """Persist the harness-reported session id (claude resume handle, Phase 4)."""
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE execution_logs SET session_id = ? WHERE execution_id = ?",
            (session_id, execution_id),
        )
        conn.commit()
        return cur.rowcount > 0
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_migration_152_resume_recovery.py -q`
Expected: PASS (4 passed).

- [ ] **Step 7: Commit**

```bash
git add backend/app/db/schema/_core.py backend/app/db/schema/_orgs.py backend/app/db/migrations/v07_features.py backend/app/db/execution_logs.py backend/tests/test_migration_152_resume_recovery.py
git commit -m "feat(harness): migration 152 — redispatch/resume provenance + auto_redispatch (Phase 4)"
```

---

## Task 2: Unit B — capture claude session_id + `resume_session_id` in CommandBuilder

**Files:**
- Modify: `backend/app/services/execution_service.py` (post-run usage block ~:714-718)
- Modify: `backend/app/services/command_builder.py` (claude branch) and the `ExecutionService.build_command` facade (~:280, add the passthrough param)
- Test: `backend/tests/test_claude_resume_command.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_claude_resume_command.py
"""Claude resume handle: capture + --resume command flag (Phase 4, Unit B)."""

from app.services.execution_service import ExecutionService


def test_build_command_claude_with_resume_session_id():
    cmd = ExecutionService.build_command("claude", "continue the task", resume_session_id="sess-1")
    assert "--resume" in cmd
    assert cmd[cmd.index("--resume") + 1] == "sess-1"


def test_build_command_claude_without_resume_unchanged():
    cmd = ExecutionService.build_command("claude", "do the task")
    assert "--resume" not in cmd


def test_build_command_codex_ignores_resume():
    cmd = ExecutionService.build_command("codex", "do the task", resume_session_id="sess-1")
    assert "--resume" not in cmd


def test_build_command_gemini_ignores_resume():
    cmd = ExecutionService.build_command("gemini", "do the task", resume_session_id="sess-1")
    assert "--resume" not in cmd


def test_post_run_usage_capture_writes_session_id():
    """The usage-recording path persists claude's session_id onto execution_logs."""
    from unittest.mock import patch

    from app.db.execution_logs import create_execution_log, get_execution_log
    from app.services.execution_service import _capture_session_id

    create_execution_log(
        execution_id="exec-1",
        trigger_id="bot-pr-review",
        trigger_type="manual",
        started_at="2026-06-11T00:00:00",
        prompt="p",
        backend_type="claude",
        command="echo hi",
    )
    _capture_session_id("exec-1", {"input_tokens": 1, "session_id": "sess-xyz"})
    assert get_execution_log("exec-1")["session_id"] == "sess-xyz"
    # None / absent session_id is a no-op, never an error.
    _capture_session_id("exec-1", {"input_tokens": 1})
    _capture_session_id("exec-1", None)
    assert get_execution_log("exec-1")["session_id"] == "sess-xyz"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_claude_resume_command.py -q`
Expected: FAIL — unexpected keyword `resume_session_id`; `_capture_session_id` missing.

- [ ] **Step 3: CommandBuilder + facade**

In `backend/app/services/command_builder.py`: add `resume_session_id: Optional[str] = None` as the last parameter of `CommandBuilder.build(...)` (check the exact signature first — it currently takes `backend, prompt, allowed_paths, model, codex_settings, allowed_tools`). **The module imports only `logging` today — add `from typing import Optional`.** In the **claude branch only**, after the base `cmd` list is built:

```python
        if resume_session_id:
            cmd.extend(["--resume", resume_session_id])
```

In `backend/app/services/execution_service.py`, extend the `build_command` facade (~:280) with `resume_session_id: str = None` and pass it through to `CommandBuilder.build(...)` as the last argument.

- [ ] **Step 4: `_capture_session_id` + wire into the usage block**

In `backend/app/services/execution_service.py`, add a module-level helper (near `_verification_pr_gate`):

```python
def _capture_session_id(execution_id: str, usage_data) -> None:
    """Persist the harness-reported session id as a resume handle (Phase 4,
    Unit B). Claude's terminal result JSON carries it; crashed/SIGKILLed runs
    never print that JSON, so they have no handle — documented limitation.
    Best-effort: never raises."""
    try:
        session_id = (usage_data or {}).get("session_id")
        if session_id:
            from ..db.execution_logs import set_execution_session_id

            set_execution_session_id(execution_id, session_id)
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("session_id capture failed for %s: %s", execution_id, e)
```

**Wiring — capture must run for ALL terminal outcomes, not only success.** The
current usage extraction lives under `elif exit_code == 0` (~:688/:711-718),
but true resume mainly benefits *failed*-but-cleanly-exited claude runs, so
hoist the capture ABOVE the status branch: after the output pipes have been
joined / the process has exited (where `stdout_log` is obtainable via
`ExecutionLogService.get_stdout_log(execution_id)`) and BEFORE the
success/cancelled/failed branching, add:

```python
            # Capture the harness session id for ANY terminal outcome (Phase 4):
            # failed-but-cleanly-exited claude runs are the main resume audience.
            _capture_session_id(
                execution_id,
                BudgetService.extract_token_usage(
                    ExecutionLogService.get_stdout_log(execution_id), backend
                ),
            )
```

(Inspect the exact local names — `backend` vs `backend_type` — at that point in
`run_trigger`. Keep the existing `record_usage` call inside the `exit_code == 0`
branch unchanged; double extraction is acceptable, correctness first.)

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_claude_resume_command.py tests/test_execution_service.py -q`
Expected: PASS (5 new + existing regression green).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/command_builder.py backend/app/services/execution_service.py backend/tests/test_claude_resume_command.py
git commit -m "feat(harness): capture claude session_id + --resume command support (Phase 4 Unit B)"
```

---

## Task 3: Unit A — `redispatch_execution` service + `prompt_override` in run_trigger

**Files:**
- Modify: `backend/app/services/execution_service.py` (`run_trigger` params; new `redispatch_execution` classmethod)
- Test: `backend/tests/test_redispatch_service.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_redispatch_service.py
"""Manual re-dispatch of interrupted/failed executions (Phase 4, Unit A)."""

from unittest.mock import patch

from app.db.execution_logs import (
    create_execution_log,
    get_redispatch_child,
    set_execution_session_id,
    update_execution_log,
)
from app.services.execution_service import ExecutionService


def _make_execution(execution_id="exec-1", status="interrupted", backend="claude"):
    create_execution_log(
        execution_id=execution_id,
        trigger_id="bot-pr-review",
        trigger_type="manual",
        started_at="2026-06-11T00:00:00",
        prompt="ORIGINAL STORED PROMPT",
        backend_type=backend,
        command="echo hi",
    )
    update_execution_log(execution_id, status=status, finished_at="2026-06-11T00:01:00")


def test_redispatch_interrupted_uses_stored_prompt():
    _make_execution()
    with patch.object(ExecutionService, "run_trigger", return_value="exec-new") as rt:
        result = ExecutionService.redispatch_execution("exec-1")
    assert result["execution_id"] == "exec-new"
    kwargs = rt.call_args.kwargs
    assert kwargs["prompt_override"] == "ORIGINAL STORED PROMPT"
    assert kwargs["redispatched_from"] == "exec-1"
    assert kwargs.get("resume_session_id") is None  # interrupted run has no handle


def test_redispatch_failed_claude_with_session_resumes():
    _make_execution(status="failed")
    set_execution_session_id("exec-1", "sess-abc")
    with patch.object(ExecutionService, "run_trigger", return_value="exec-new") as rt:
        ExecutionService.redispatch_execution("exec-1")
    kwargs = rt.call_args.kwargs
    assert kwargs["resume_session_id"] == "sess-abc"
    # Continuation prompt replaces the raw stored prompt when resuming.
    assert "Continue" in kwargs["prompt_override"]
    assert "ORIGINAL STORED PROMPT" in kwargs["prompt_override"]


def test_redispatch_codex_never_resumes():
    _make_execution(status="failed", backend="codex")
    set_execution_session_id("exec-1", "sess-abc")  # even with a stored id
    with patch.object(ExecutionService, "run_trigger", return_value="exec-new") as rt:
        ExecutionService.redispatch_execution("exec-1")
    assert rt.call_args.kwargs.get("resume_session_id") is None


def test_redispatch_rejects_running_and_success():
    _make_execution("exec-r", status="running")
    _make_execution("exec-s", status="success")
    for eid in ("exec-r", "exec-s"):
        result = ExecutionService.redispatch_execution(eid)
        assert result.get("error") == "not_eligible"


def test_redispatch_rejects_unknown():
    assert ExecutionService.redispatch_execution("nope").get("error") == "not_found"


def test_redispatch_prefers_trigger_config_snapshot():
    """Deterministic replay: the trigger dict passed to run_trigger comes from
    the stored snapshot, not the (possibly since-edited) DB trigger."""
    import json

    create_execution_log(
        execution_id="exec-snap",
        trigger_id="bot-pr-review",
        trigger_type="manual",
        started_at="2026-06-11T00:00:00",
        prompt="stored prompt",
        backend_type="claude",
        command="echo hi",
        trigger_config_snapshot=json.dumps(
            {"id": "bot-pr-review", "name": "AS-IT-WAS", "prompt_template": "old tpl"}
        ),
    )
    update_execution_log("exec-snap", status="interrupted", finished_at="2026-06-11T00:01:00")
    with patch.object(ExecutionService, "run_trigger", return_value="exec-new") as rt:
        ExecutionService.redispatch_execution("exec-snap")
    assert rt.call_args.args[0]["name"] == "AS-IT-WAS"  # snapshot, not current DB row


def test_redispatch_no_fan_out():
    _make_execution()
    with patch.object(ExecutionService, "run_trigger", return_value="exec-new"):
        first = ExecutionService.redispatch_execution("exec-1")
    assert "execution_id" in first
    # run_trigger was mocked, so set provenance the way the real path does:
    from app.db.execution_logs import set_redispatched_from

    create_execution_log(
        execution_id="exec-new",
        trigger_id="bot-pr-review",
        trigger_type="manual",
        started_at="2026-06-11T00:02:00",
        prompt="p",
        backend_type="claude",
        command="echo hi",
    )
    set_redispatched_from("exec-new", "exec-1")
    second = ExecutionService.redispatch_execution("exec-1")
    assert second.get("error") == "already_redispatched"
    assert get_redispatch_child("exec-1")["execution_id"] == "exec-new"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_redispatch_service.py -q`
Expected: FAIL — `redispatch_execution` missing.

- [ ] **Step 3: `run_trigger` params**

Extend `run_trigger`'s signature with three keyword params (after `execution_id`):

```python
        prompt_override: str = None,
        resume_session_id: str = None,
        redispatched_from: str = None,
```

Inside `run_trigger`:
1. Where the prompt renders (~:376 `prompt = PromptRenderer.render(...)`), guard it:

```python
            if prompt_override is not None:
                prompt = prompt_override
            else:
                prompt = PromptRenderer.render(trigger, trigger_id, message_text, paths_str, event)
```

(Keep the existing post-render augmentations — PR-diff context etc. — applying only on the render path; the override path uses the stored prompt verbatim. Inspect the surrounding lines and place the guard so the override skips those augmentations.)

2. Where the command builds, pass `resume_session_id=resume_session_id` through `build_command` (find the `build_command(` call site inside `run_trigger`).
3. After the execution record exists (the `ExecutionLogService.start_execution(... execution_id ...)` call), add:

```python
            if redispatched_from:
                from ..db.execution_logs import set_redispatched_from

                set_redispatched_from(execution_id_local, redispatched_from)
```

(using whatever local name holds the new execution id at that point — inspect; it is the `execution_id` returned by/passed to `start_execution`).

- [ ] **Step 4: `redispatch_execution`**

Add to `ExecutionService` (near `restore_pending_retries`):

```python
    @classmethod
    def redispatch_execution(cls, execution_id: str) -> dict:
        """Re-run an interrupted/failed execution as a NEW execution using the
        stored prompt (deterministic — no re-render). Claude runs that carry a
        session_id resume with --resume + a continuation prompt; everything
        else re-runs fresh (Phase 4, Units A+B). Returns {"execution_id": ...}
        or {"error": "not_found" | "not_eligible" | "already_redispatched" |
        "trigger_missing"}."""
        from ..db.execution_logs import get_execution_log, get_redispatch_child
        from ..db.triggers import get_trigger

        original = get_execution_log(execution_id)
        if not original:
            return {"error": "not_found"}
        if original.get("status") not in ("interrupted", "failed"):
            return {"error": "not_eligible"}
        if get_redispatch_child(execution_id):
            return {"error": "already_redispatched"}

        # Deterministic replay: prefer the trigger as it was AT RUN TIME (the
        # stored trigger_config_snapshot); fall back to the current DB trigger
        # for legacy rows without a snapshot. Paths/cwd still resolve at
        # re-dispatch time — documented semantics (spec Unit A).
        trigger = None
        snapshot = original.get("trigger_config_snapshot")
        if snapshot:
            try:
                import json as _json

                parsed = _json.loads(snapshot)
                if isinstance(parsed, dict) and parsed.get("id"):
                    trigger = parsed
            except (TypeError, ValueError):
                pass
        if trigger is None and original.get("trigger_id"):
            trigger = get_trigger(original["trigger_id"])
        if not trigger:
            return {"error": "trigger_missing"}

        stored_prompt = original.get("prompt") or ""
        resume_session_id = None
        prompt_override = stored_prompt
        if original.get("backend_type") == "claude" and original.get("session_id"):
            resume_session_id = original["session_id"]
            prompt_override = (
                "You were interrupted while working on the task below. "
                "Continue from where you left off.\n\n" + stored_prompt
            )

        AuditLogService.log(
            action="execution.redispatched",
            entity_type="trigger",
            entity_id=original.get("trigger_id") or "",
            outcome="dispatched",
            details={"origin_execution_id": execution_id, "resumed": bool(resume_session_id)},
        )
        new_id = cls.run_trigger(
            trigger,
            message_text="",
            trigger_type=original.get("trigger_type") or "manual",
            prompt_override=prompt_override,
            resume_session_id=resume_session_id,
            redispatched_from=execution_id,
        )
        if not new_id:
            return {"error": "dispatch_failed"}
        return {"execution_id": new_id}
```

(Confirm `get_trigger` import path — it's exported from `app.db.triggers`/`app.db`. Confirm `AuditLogService` is already imported in the module — it is, the budget paths use it.)

- [ ] **Step 5: Run tests**

Run: `cd backend && uv run pytest tests/test_redispatch_service.py tests/test_execution_service.py -q`
Expected: PASS (6 new + regression green).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/execution_service.py backend/tests/test_redispatch_service.py
git commit -m "feat(harness): redispatch_execution + prompt_override/resume in run_trigger (Phase 4 Unit A)"
```

---

## Task 4: Unit A — route + startup auto-recovery

**Files:**
- Modify: `backend/app_litestar/routes/executions.py` (POST redispatch handler + register)
- Modify: `backend/app_litestar/lifecycle.py` (startup step beside `restore_pending_retries`, ~:361)
- Modify: `backend/app/services/execution_service.py` (small `auto_redispatch_interrupted` classmethod)
- Test: `backend/tests/test_redispatch_route_and_startup.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_redispatch_route_and_startup.py
"""Redispatch route + startup auto-recovery (Phase 4, Unit A)."""

from unittest.mock import patch

from litestar.testing import create_test_client

from app.db.execution_logs import create_execution_log, update_execution_log
from app.services.execution_service import ExecutionService
from app_litestar.auth import provide_caller
from app_litestar.routes.executions import executions_router


def _client():
    return create_test_client(
        route_handlers=[executions_router],
        dependencies={"caller": provide_caller},
    )


def _make_execution(execution_id="exec-1", trigger_id="bot-pr-review", status="interrupted"):
    create_execution_log(
        execution_id=execution_id,
        trigger_id=trigger_id,
        trigger_type="manual",
        started_at="2026-06-11T00:00:00",
        prompt="stored prompt",
        backend_type="claude",
        command="echo hi",
    )
    update_execution_log(execution_id, status=status, finished_at="2026-06-11T00:01:00")


def test_route_redispatches():
    _make_execution()
    with patch.object(
        ExecutionService, "redispatch_execution", return_value={"execution_id": "exec-new"}
    ) as svc:
        with _client() as client:
            resp = client.post("/admin/executions/exec-1/redispatch")
    assert resp.status_code in (200, 201)
    assert resp.json()["execution_id"] == "exec-new"
    svc.assert_called_once_with("exec-1")


def test_route_maps_errors_to_4xx():
    with patch.object(
        ExecutionService, "redispatch_execution", return_value={"error": "not_found"}
    ):
        with _client() as client:
            assert client.post("/admin/executions/nope/redispatch").status_code == 404
    with patch.object(
        ExecutionService, "redispatch_execution", return_value={"error": "already_redispatched"}
    ):
        with _client() as client:
            assert client.post("/admin/executions/x/redispatch").status_code == 409
    with patch.object(
        ExecutionService, "redispatch_execution", return_value={"error": "not_eligible"}
    ):
        with _client() as client:
            assert client.post("/admin/executions/x/redispatch").status_code == 409


def test_auto_redispatch_only_opted_in_triggers():
    """Startup recovery touches only interrupted executions whose trigger has
    auto_redispatch=1, and skips rows that already have a redispatch child."""
    from app.db.connection import get_connection

    _make_execution("exec-a", status="interrupted")  # trigger NOT opted in
    _make_execution("exec-b", status="interrupted")
    with get_connection() as conn:  # opt the trigger in for exec-b only via a 2nd trigger
        conn.execute(
            "INSERT INTO triggers (id, name, prompt_template, auto_redispatch) "
            "VALUES ('trig-auto', 'T', 'tpl', 1)"
        )
        conn.execute(
            "UPDATE execution_logs SET trigger_id = 'trig-auto' WHERE execution_id = 'exec-b'"
        )
        conn.commit()

    with patch.object(
        ExecutionService, "redispatch_execution", return_value={"execution_id": "exec-new"}
    ) as svc:
        count = ExecutionService.auto_redispatch_interrupted()
    assert count == 1
    svc.assert_called_once_with("exec-b")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_redispatch_route_and_startup.py -q`
Expected: FAIL — route 404s (handler missing), `auto_redispatch_interrupted` missing.

- [ ] **Step 3: Route handler**

In `backend/app_litestar/routes/executions.py` — find the existing cancel handler (`grep -n '"/executions/{execution_id:str}/cancel"' app_litestar/routes/executions.py`) and mirror its style:

```python
@post("/executions/{execution_id:str}/redispatch", sync_to_thread=True)
def redispatch_execution(execution_id: str) -> dict[str, Any]:
    """Re-run an interrupted/failed execution (Phase 4). 404 unknown, 409 not
    eligible / already re-dispatched."""
    from app.services.execution_service import ExecutionService

    result = ExecutionService.redispatch_execution(execution_id)
    if result.get("error") == "not_found":
        raise NotFoundException(detail=f"Execution {execution_id} not found")
    if "error" in result:
        raise HTTPException(status_code=409, detail=result["error"])
    return result
```

(`executions.py` already imports `HTTPException` (~:24) and uses it for 409s — mirror that, NOT `ClientException`.) Register in the `executions_router` handler list.

- [ ] **Step 4: Make `auto_redispatch` settable through the normal trigger-update path**

The flag is useless if nothing can set it. Trace how an existing boolean trigger
field (`auto_resolve`) flows through `update_trigger` (`app/db/triggers.py` ~:277
— check the allowed-fields handling), the trigger service payload
(`app/services/trigger_service.py` ~:82), and the trigger update route's accepted
body fields. Add `auto_redispatch` at each layer, mirroring `auto_resolve`
exactly (int 0/1 coercion included). Append to the route/service test below —
add to `tests/test_redispatch_route_and_startup.py`:

```python
def test_trigger_update_accepts_auto_redispatch():
    from app.db.connection import get_connection
    from app.db.triggers import get_trigger, update_trigger

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO triggers (id, name, prompt_template) VALUES ('trig-u', 'T', 'tpl')"
        )
        conn.commit()
    assert update_trigger("trig-u", {"auto_redispatch": 1}) is not False
    assert get_trigger("trig-u")["auto_redispatch"] == 1
```

(Adapt the `update_trigger` call shape to its real signature — it may take
kwargs or a dict; mirror how `auto_resolve` is updated in existing tests.)

- [ ] **Step 5: `auto_redispatch_interrupted` + lifecycle wiring**

Add to `ExecutionService`:

```python
    @classmethod
    def auto_redispatch_interrupted(cls) -> int:
        """Startup recovery (Phase 4): one re-dispatch attempt for interrupted
        executions whose trigger opted in via auto_redispatch=1. Returns count."""
        from ..db.connection import get_connection

        with get_connection() as conn:
            rows = conn.execute(
                """SELECT e.execution_id FROM execution_logs e
                   JOIN triggers t ON t.id = e.trigger_id
                   WHERE e.status = 'interrupted'
                     AND t.auto_redispatch = 1
                     AND NOT EXISTS (
                         SELECT 1 FROM execution_logs c
                         WHERE c.redispatched_from = e.execution_id
                     )"""
            ).fetchall()
        count = 0
        for row in rows:
            try:
                result = cls.redispatch_execution(row["execution_id"])
                if "execution_id" in result:
                    count += 1
            except Exception as e:  # pragma: no cover - defensive
                logger.warning("auto-redispatch failed for %s: %s", row["execution_id"], e)
        if count:
            logger.info("Auto-redispatched %d interrupted execution(s)", count)
        return count
```

In `backend/app_litestar/lifecycle.py`, immediately after the `restore_pending_retries()` try-block (~:361), add a sibling block:

```python
    try:
        from app.services.execution_service import ExecutionService

        ExecutionService.auto_redispatch_interrupted()
    except Exception as exc:
        logger.error("Auto-redispatch on startup failed: %s", exc, exc_info=True)
        _startup_warnings.append(f"auto_redispatch: {exc}")
```

- [ ] **Step 6: Run tests**

Run: `cd backend && uv run pytest tests/test_redispatch_route_and_startup.py tests/test_execution_state_route.py -q`
Expected: PASS (5 new + Phase-3 route regression green).

- [ ] **Step 7: Commit**

```bash
git add backend/app_litestar/routes/executions.py backend/app_litestar/lifecycle.py backend/app/services/execution_service.py backend/app/db/triggers.py backend/app/services/trigger_service.py backend/tests/test_redispatch_route_and_startup.py
git commit -m "feat(harness): redispatch route + opt-in startup auto-recovery (Phase 4 Unit A)"
```

---

## Task 5: Unit C — goal-loop re-entry service + route

**Files:**
- Modify: `backend/app/services/goal_loop_runner.py` (`resume_goal_loop` + `resume_context` consumed by the initial prompt)
- Modify: `backend/app_litestar/routes/grd_routes.py` (POST resume-loop handler, mirroring sibling session routes)
- Test: `backend/tests/test_goal_loop_reentry.py`

- [ ] **Step 1: Study the spawn recipe (read, don't guess)**

Read `backend/app/services/execution_type_handler.py:460-500` (how a goal-loop session is created: the `ProjectSessionManager.create_session(...)` call, `set_goal_loop_config`, `start_runner`) and `goal_loop_runner.py` `_initial_prompt` / `_send_initial` / `start_runner`. Also `app/db/goal_loop.py` (`get_goal_loop_config`) and how `goal_loop_iterations` + dead-ends are queried (`grep -rn "goal_loop_iterations" app/db/`). Pin: the exact `create_session` kwargs the goal-loop path uses, the dead-ends query helper, and how `project_sessions` rows expose `execution_type`/`status`/`project_id` (via `get_project_session` or similar in `app/db/grd.py`).

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/test_goal_loop_reentry.py
"""Goal-loop re-entry from persisted iteration knowledge (Phase 4, Unit C)."""

from unittest.mock import patch

from app.services import goal_loop_runner


def _make_failed_goal_session(session_id="gls-1", project_id="proj-1"):
    """Insert a minimal failed goal-loop project_sessions row + config +
    iteration history. Use the real DB helpers found in Step 1 (create the
    project row first if project_sessions FKs projects)."""
    from app.db.connection import get_connection
    from app.db.goal_loop import set_goal_loop_config

    with get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO projects (id, name) VALUES (?, ?)", (project_id, "P"))
        conn.execute(
            "INSERT INTO project_sessions (id, project_id, status, execution_type) "
            "VALUES (?, ?, 'failed', 'goal_loop')",
            (session_id, project_id),
        )
        conn.executemany(
            "INSERT INTO goal_loop_iterations (session_id, iteration, judge_source, verdict) "
            "VALUES (?, ?, ?, ?)",
            [
                (session_id, 1, "judge", "not_achieved"),
                (session_id, 2, "judge", "not_achieved"),
            ],
        )
        conn.commit()
    set_goal_loop_config(session_id, {"goal": "make tests pass", "max_iterations": 10})


def test_resume_goal_loop_spawns_fresh_session_with_context():
    _make_failed_goal_session()
    with patch.object(goal_loop_runner, "_spawn_resumed_session", return_value="gls-2") as spawn:
        result = goal_loop_runner.resume_goal_loop("gls-1")
    assert result["session_id"] == "gls-2"
    cfg = spawn.call_args.args[1]  # (origin_session_id, goal_config, ...)
    assert "resume_context" in cfg
    assert "iteration 2" in cfg["resume_context"]  # resumed AFTER iteration N
    assert cfg["goal"] == "make tests pass"


def test_resume_rejects_non_goal_or_active_sessions():
    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO projects (id, name) VALUES ('proj-1', 'P')")
        conn.execute(
            "INSERT INTO project_sessions (id, project_id, status, execution_type) "
            "VALUES ('s-active', 'proj-1', 'active', 'goal_loop'), "
            "       ('s-direct', 'proj-1', 'failed', 'direct'), "
            "       ('s-ralph', 'proj-1', 'failed', 'ralph_loop')",
        )
        conn.commit()
    assert goal_loop_runner.resume_goal_loop("s-active").get("error") == "not_eligible"
    assert goal_loop_runner.resume_goal_loop("s-direct").get("error") == "not_eligible"
    # ralph_loop excluded: no durable config/iterations to resume from.
    assert goal_loop_runner.resume_goal_loop("s-ralph").get("error") == "not_eligible"
    assert goal_loop_runner.resume_goal_loop("nope").get("error") == "not_found"


def test_resume_no_fan_out():
    _make_failed_goal_session("gls-3")
    from app.db.connection import get_connection

    with get_connection() as conn:  # an existing resumed child blocks a second resume
        conn.execute(
            "INSERT INTO project_sessions (id, project_id, status, execution_type, resumed_from) "
            "VALUES ('gls-3b', 'proj-1', 'active', 'goal_loop', 'gls-3')"
        )
        conn.commit()
    assert goal_loop_runner.resume_goal_loop("gls-3").get("error") == "already_resumed"


def test_resume_requires_config():
    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO projects (id, name) VALUES ('proj-1', 'P')")
        conn.execute(
            "INSERT INTO project_sessions (id, project_id, status, execution_type) "
            "VALUES ('gls-nocfg', 'proj-1', 'failed', 'goal_loop')"
        )
        conn.commit()
    assert goal_loop_runner.resume_goal_loop("gls-nocfg").get("error") == "config_missing"
```

(Adapt the raw INSERTs in the helpers to the real `project_sessions`/`goal_loop_iterations` NOT-NULL columns found in Step 1 — add whatever minimal extra columns the schema requires; the assertions are the invariant.)

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_goal_loop_reentry.py -q`
Expected: FAIL — `resume_goal_loop` / `_spawn_resumed_session` missing.

- [ ] **Step 4: Implement `resume_goal_loop`**

In `backend/app/services/goal_loop_runner.py`:

```python
def _build_resume_context(session_id: str) -> str:
    """Re-entry context block from durable history: iteration count, verdicts,
    known dead ends. The fresh loop continues from accumulated knowledge —
    a dead PTY cannot be reattached or replayed (Phase 4, Unit C)."""
    from ..db.connection import get_connection

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT iteration, verdict, judge_reason FROM goal_loop_iterations "
            "WHERE session_id = ? ORDER BY iteration ASC",
            (session_id,),
        ).fetchall()
    last_iter = rows[-1]["iteration"] if rows else 0
    verdict_lines = [
        f"- iteration {r['iteration']}: {r['verdict'] or 'unknown'}"
        f"{(' — ' + r['judge_reason']) if r['judge_reason'] else ''}"
        for r in rows
    ]
    dead_ends = _dead_ends_context(session_id)  # existing helper in this module
    parts = [
        f"RESUMING after interruption at iteration {last_iter}.",
        "Prior iteration verdicts:" if verdict_lines else "",
        *verdict_lines,
        dead_ends or "",
    ]
    return "\n".join(p for p in parts if p)


def resume_goal_loop(session_id: str) -> dict:
    """Resume a dead goal-loop session by spawning a FRESH session seeded with
    the persisted goal config + accumulated knowledge. Eligible: execution_type
    goal_loop/ralph_loop, status 'failed', no prior resume child."""
    from ..db.connection import get_connection
    from ..db.goal_loop import get_goal_loop_config

    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM project_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if not row:
            return {"error": "not_found"}
        session = dict(row)
        child = conn.execute(
            "SELECT id FROM project_sessions WHERE resumed_from = ? LIMIT 1", (session_id,)
        ).fetchone()
    # goal_loop ONLY: ralph_loop persists no goal-loop config/iterations to
    # re-enter from (its ralph_config is start-only) — excluded this phase.
    if session.get("execution_type") != "goal_loop":
        return {"error": "not_eligible"}
    if session.get("status") != "failed":
        return {"error": "not_eligible"}
    if child:
        return {"error": "already_resumed"}

    config = get_goal_loop_config(session_id)
    if not config or not config.get("goal"):
        return {"error": "config_missing"}
    config["resume_context"] = _build_resume_context(session_id)

    new_session_id = _spawn_resumed_session(session_id, config, session)
    return {"session_id": new_session_id, "resumed_from": session_id}
```

`_spawn_resumed_session(origin_session_id, goal_config, origin_session) -> str`: mirror the spawn recipe pinned in Step 1 — `GoalLoopSessionHandler.start()`'s kwargs at `execution_type_handler.py:~468-495` are the template. **cwd derivation (the row does NOT store cwd):** use the origin row's `worktree_path` when set, else `ProjectWorkspaceService.resolve_working_directory(origin_session["project_id"])` (confirm that service/fn name via `grep -rn "resolve_working_directory" app/services/`). Then: `ProjectSessionManager.create_session(...)` with the mirrored kwargs, set `resumed_from` on the new row (direct UPDATE or the allowlisted helper), `set_goal_loop_config(new_id, goal_config)`, `start_runner(new_id, goal_config, cwd=derived_cwd)`, audit-log `session.loop_resumed`, return the new id. Keep it a module-level function so tests can patch it.

Finally, make the initial prompt consume the context — the threading is explicit, do all three points:
1. `_run()` (~`goal_loop_runner.py:347`) currently calls `_send_initial(session_id, goal, ouroboros=ouroboros, result_block=result_block)`; the config is on `_RunnerState` (~`:241`). Change the call to also pass `resume_context=(state.config or {}).get("resume_context")` (confirm the state attribute name holding the config — inspect `_RunnerState`).
2. `_send_initial(...)` gains `resume_context: Optional[str] = None` and forwards it to `_initial_prompt(...)`.
3. `_initial_prompt(...)` gains the same param and prepends when present:

```python
    if resume_context:
        prompt = f"{resume_context}\n\n{prompt}"
```

(`prompt` = whatever local holds the composed initial prompt just before return — inspect and place accordingly.)

- [ ] **Step 5: Route**

In `backend/app_litestar/routes/grd_routes.py`, mirror a sibling session POST (e.g. the `/{project_id}/sessions/{session_id}/answer-question` handler style):

```python
@post("/{project_id:str}/sessions/{session_id:str}/resume-loop", sync_to_thread=True)
def resume_goal_loop_route(project_id: str, session_id: str) -> dict[str, Any]:
    from app.services.goal_loop_runner import resume_goal_loop

    result = resume_goal_loop(session_id)
    if result.get("error") == "not_found":
        raise NotFoundException(detail=f"Session {session_id} not found")
    if "error" in result:
        raise HTTPException(status_code=409, detail=result["error"])
    return result
```

(Match the file's actual imports/exception conventions and register in its router list.) Add one route test to `tests/test_goal_loop_reentry.py` mirroring the file's sibling route tests if a grd-routes test exists; otherwise the service tests + a direct `create_test_client` check on the router suffice:

```python
def test_resume_loop_route_409_when_not_eligible():
    from litestar.testing import create_test_client

    from app_litestar.auth import provide_caller
    from app_litestar.routes.grd_routes import grd_router  # confirm symbol via grep

    with create_test_client(route_handlers=[grd_router], dependencies={"caller": provide_caller}) as client:
        resp = client.post("/api/projects/proj-1/sessions/nope/resume-loop")
    assert resp.status_code == 404
```

(Adjust the mount prefix to the router's real `path` — grep `Router(` in grd_routes.py.)

- [ ] **Step 6: Run tests**

Run: `cd backend && uv run pytest tests/test_goal_loop_reentry.py -q`
Expected: PASS (5 passed).

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/goal_loop_runner.py backend/app_litestar/routes/grd_routes.py backend/tests/test_goal_loop_reentry.py
git commit -m "feat(harness): goal-loop re-entry from persisted knowledge (Phase 4 Unit C / P8)"
```

---

## Task 6: Frontend — Re-dispatch button in ExecutionHistory

**Files:**
- Modify: `frontend/src/services/api/triggers.ts` (`executionApi.redispatch`)
- Modify: `frontend/src/views/ExecutionHistory.vue` (button on interrupted/failed rows or in the log modal actions)
- Modify: `frontend/src/locales/{en,ko,ja,zh}.json` (`executionHistory.redispatch*` keys)
- Test: extend the ExecutionHistory test if one exists (`ls frontend/src/views/__tests__/ 2>/dev/null; grep -rln "ExecutionHistory" frontend/src --include=*.test.ts`); otherwise create `frontend/src/views/__tests__/ExecutionHistory.redispatch.test.ts` is NOT required — instead add the api-level test below plus manual placement.

- [ ] **Step 1: Study conventions**

1. `grep -n "executionApi" frontend/src/services/api/triggers.ts` — mirror a sibling POST-style method (e.g. cancel, if present; otherwise mirror `getState`'s shape with the POST variant the `apiFetch` helper supports — check `services/api/client.ts` for how POSTs are made).
2. In `ExecutionHistory.vue`, find the row/modal action buttons (search `@click` handlers around the execution rows and the log modal header) and the `t('executionHistory....')` key usage; mirror one.

- [ ] **Step 2: api method + button + i18n**

`triggers.ts`:

```typescript
  redispatch: (executionId: string) =>
    apiFetch<{ execution_id: string }>(`/admin/executions/${executionId}/redispatch`, {
      method: 'POST',
    }),
```

(Adapt to the real `apiFetch` POST signature found in Step 1.)

`ExecutionHistory.vue`: a button visible when the row/selected execution status is `interrupted` or `failed`:

```vue
<button
  v-if="['interrupted', 'failed'].includes(execution.status)"
  class="btn-redispatch"
  :disabled="redispatchInFlight === execution.execution_id"
  @click.stop="redispatchExecution(execution)"
>
  {{ t('executionHistory.redispatch') }}
</button>
```

With the handler (mirror the view's existing async action style + refresh call):

```typescript
const redispatchInFlight = ref<string | null>(null);
async function redispatchExecution(execution: Execution) {
  redispatchInFlight.value = execution.execution_id;
  try {
    await executionApi.redispatch(execution.execution_id);
    await loadExecutions(); // the view's existing refresh fn — confirm name
  } catch (e) {
    // mirror the view's existing error display pattern
  } finally {
    redispatchInFlight.value = null;
  }
}
```

i18n (all four catalogs, in the existing `executionHistory` namespace): `"redispatch": "Re-dispatch"` (+ translated) and `"redispatchFailed": "Re-dispatch failed"` if the view's error pattern uses a message key.

**Also: the `auto_redispatch` toggle in `TriggerDetailPanel.vue`** (the opt-in's
UI half — the backend path landed in Task 4). Find how an existing boolean
trigger setting (e.g. `auto_resolve` or `enabled`) is rendered/bound/saved in
that panel and mirror it exactly for `auto_redispatch`: checkbox/switch bound to
local state, loaded from the trigger payload, included in the save payload, with
a label key in the panel's existing namespace (all four catalogs, e.g.
`"autoRedispatch": "Auto re-dispatch interrupted runs"` + translations). If the
trigger api types in `services/api/types/triggers.ts` model the trigger fields,
add `auto_redispatch?: number` there too.

- [ ] **Step 3: Tests + build**

Run: `cd frontend && npm run test:run` → suite at baseline (no new failures).
Run: `cd frontend && npx vue-tsc --noEmit` → exit 0.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/services/api/triggers.ts frontend/src/views/ExecutionHistory.vue frontend/src/locales/
git commit -m "feat(harness): re-dispatch button in ExecutionHistory (Phase 4)"
```

---

## Task 7: Full Phase-4 verification sweep

- [ ] **Step 1: Backend — all Phase-4 tests + regressions**

```bash
cd backend && uv run pytest \
  tests/test_migration_152_resume_recovery.py tests/test_claude_resume_command.py \
  tests/test_redispatch_service.py tests/test_redispatch_route_and_startup.py \
  tests/test_goal_loop_reentry.py \
  tests/test_execution_service.py tests/test_execution_state_route.py \
  tests/test_budget_monitor_per_run.py tests/test_harness_state_repo.py \
  tests/test_litestar_streams.py -q
```
Expected: ALL PASS.

- [ ] **Step 2: Lint**

```bash
cd backend && uv run ruff format app/db/execution_logs.py app/db/schema/_core.py app/db/schema/_orgs.py app/db/migrations/v07_features.py app/services/execution_service.py app/services/command_builder.py app/services/goal_loop_runner.py app_litestar/routes/executions.py app_litestar/routes/grd_routes.py app_litestar/lifecycle.py
cd backend && uv run ruff check app/db/execution_logs.py app/services/command_builder.py app/services/goal_loop_runner.py app_litestar/routes/executions.py
```
Expected: format clean; check passes (no NEW errors vs origin/main).

- [ ] **Step 3: Frontend**

```bash
cd frontend && npm run test:run
just build
```
Expected: suite at baseline; build green.

- [ ] **Step 4: Final commit if needed**

```bash
git add -A backend/ frontend/ && git commit -m "chore(harness): format/lint pass for Phase 4"
```

---

## Self-Review notes (author)
- **Spec coverage:** migration+helpers (T1), session_id capture + --resume (T2), redispatch service + run_trigger params (T3), route + startup auto-recovery (T4), goal-loop re-entry + route (T5), frontend button (T6), sweep (T7). The spec's failed-eligible Unit-C reframe (no CHECK rebuild) is implemented in T5.
- **Type consistency:** `redispatch_execution(execution_id) -> dict`; `run_trigger(..., prompt_override, resume_session_id, redispatched_from)`; `build_command(..., resume_session_id)`; `set_redispatched_from/get_redispatch_child/set_execution_session_id`; `resume_goal_loop(session_id) -> dict`; `_spawn_resumed_session(origin_session_id, goal_config, origin_session)`; `auto_redispatch_interrupted() -> int` — consistent across tasks.
- **Confirm-at-execution points (each task says how):** exact placement of the prompt-override guard vs post-render augmentations (T3 S3); cancel-handler 409 style (T4 S3); the goal-loop spawn kwargs + dead-ends helper + minimal NOT-NULL columns for test fixtures (T5 S1/S2); grd_router symbol + mount prefix (T5 S5); apiFetch POST signature + refresh-fn name (T6).
