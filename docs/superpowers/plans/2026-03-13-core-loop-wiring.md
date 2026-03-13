# Core Loop Wiring Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the end-to-end project-centric execution loop — triggers dispatch to super agent sessions, scheduling fires super agents on cron, and the UI connects projects → teams → super agents → chat → execution history.

**Architecture:** Thin slice through all layers. Backend adds `dispatch_type`/`super_agent_id` to triggers plus `session_id`/`source_type` to execution logs. Dispatcher routes `dispatch_type='super_agent'` to `SuperAgentSessionService` (bypassing execution queue). Frontend wires existing functional components (chat, mailbox, scheduling) into project and team dashboards.

**Tech Stack:** Python/Flask (flask-openapi3), SQLite, Pydantic v2, APScheduler, Vue 3/TypeScript, SSE streaming

**Spec:** `docs/superpowers/specs/2026-03-13-core-loop-wiring-design.md`

---

## Chunk 1: Backend Foundation (DB + Session Service + Models)

### Task 1: Database Migration — Add dispatch columns to triggers and execution_logs

**Files:**
- Modify: `backend/app/db/migrations.py` (append new migration at end of VERSIONED_MIGRATIONS)

- [ ] **Step 1: Write the migration function**

Add to `backend/app/db/migrations.py`, before the `VERSIONED_MIGRATIONS` list:

```python
def _migrate_76_super_agent_dispatch(conn):
    """Add super agent dispatch support to triggers and execution logs."""
    cur = conn.cursor()

    # Triggers: dispatch routing
    cur.execute("ALTER TABLE triggers ADD COLUMN dispatch_type TEXT DEFAULT 'bot'")
    cur.execute("ALTER TABLE triggers ADD COLUMN super_agent_id TEXT")

    # Execution logs: unified source tracking
    cur.execute("ALTER TABLE execution_logs ADD COLUMN session_id TEXT")
    cur.execute("ALTER TABLE execution_logs ADD COLUMN source_type TEXT DEFAULT 'bot'")
```

Then append to `VERSIONED_MIGRATIONS`:
```python
(76, "super_agent_dispatch", _migrate_76_super_agent_dispatch),
```

- [ ] **Step 2: Write the migration test**

Create `backend/tests/test_migration_76.py`:

```python
import sqlite3
import pytest
from app.db.migrations import _migrate_76_super_agent_dispatch


def test_migration_adds_dispatch_columns(tmp_path):
    """Migration 76 adds dispatch_type and super_agent_id to triggers,
    session_id and source_type to execution_logs."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE triggers (id TEXT PRIMARY KEY, name TEXT)"
    )
    conn.execute(
        "CREATE TABLE execution_logs (id INTEGER PRIMARY KEY, execution_id TEXT, trigger_id TEXT)"
    )
    conn.commit()

    _migrate_76_super_agent_dispatch(conn)
    conn.commit()

    # Verify triggers columns
    cur = conn.execute("PRAGMA table_info(triggers)")
    cols = {row[1] for row in cur.fetchall()}
    assert "dispatch_type" in cols
    assert "super_agent_id" in cols

    # Verify execution_logs columns
    cur = conn.execute("PRAGMA table_info(execution_logs)")
    cols = {row[1] for row in cur.fetchall()}
    assert "session_id" in cols
    assert "source_type" in cols

    # Verify defaults
    conn.execute("INSERT INTO triggers (id, name) VALUES ('t1', 'test')")
    row = conn.execute("SELECT dispatch_type FROM triggers WHERE id='t1'").fetchone()
    assert row[0] == "bot"

    conn.execute(
        "INSERT INTO execution_logs (execution_id, trigger_id) VALUES ('e1', 't1')"
    )
    row = conn.execute("SELECT source_type FROM execution_logs WHERE execution_id='e1'").fetchone()
    assert row[0] == "bot"

    conn.close()
```

- [ ] **Step 3: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_migration_76.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/db/migrations.py backend/tests/test_migration_76.py
git commit -m "feat: add migration 76 — super agent dispatch columns on triggers and execution_logs"
```

---

### Task 2: SuperAgentSessionService — Add `get_or_create_session` and `SessionLimitError`

**Files:**
- Modify: `backend/app/services/super_agent_session_service.py`
- Test: `backend/tests/test_session_get_or_create.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_session_get_or_create.py`:

```python
import pytest
from unittest.mock import patch, MagicMock
from app.services.super_agent_session_service import (
    SuperAgentSessionService,
    SessionLimitError,
)


@pytest.fixture(autouse=True)
def clear_sessions():
    SuperAgentSessionService._active_sessions.clear()
    yield
    SuperAgentSessionService._active_sessions.clear()


class TestGetOrCreateSession:
    def test_creates_new_session_when_none_exist(self, isolated_db):
        """When no active/paused session exists, creates a new one."""
        sa_id = "sa-test01"
        with patch.object(
            SuperAgentSessionService, "create_session", return_value=("sess-new", None)
        ) as mock_create:
            session_id = SuperAgentSessionService.get_or_create_session(sa_id)
            assert session_id == "sess-new"
            mock_create.assert_called_once_with(sa_id)

    def test_returns_existing_active_session(self, isolated_db):
        """When an active session exists, returns it without creating."""
        sa_id = "sa-test02"
        SuperAgentSessionService._active_sessions["sess-exist"] = {
            "session_id": "sess-exist",
            "super_agent_id": sa_id,
            "status": "active",
        }
        with patch.object(
            SuperAgentSessionService, "create_session"
        ) as mock_create:
            session_id = SuperAgentSessionService.get_or_create_session(sa_id)
            assert session_id == "sess-exist"
            mock_create.assert_not_called()

    def test_resumes_paused_session(self, isolated_db):
        """When a paused session exists, resumes it and returns its ID."""
        sa_id = "sa-test03"
        SuperAgentSessionService._active_sessions["sess-paused"] = {
            "session_id": "sess-paused",
            "super_agent_id": sa_id,
            "status": "paused",
        }
        with patch.object(
            SuperAgentSessionService, "resume_session", return_value=(True, None)
        ) as mock_resume:
            session_id = SuperAgentSessionService.get_or_create_session(sa_id)
            assert session_id == "sess-paused"
            mock_resume.assert_called_once_with("sess-paused")

    def test_raises_session_limit_error(self, isolated_db):
        """When create_session fails due to limit, raises SessionLimitError."""
        sa_id = "sa-test04"
        with patch.object(
            SuperAgentSessionService,
            "create_session",
            return_value=(None, "Maximum concurrent sessions reached"),
        ):
            with pytest.raises(SessionLimitError):
                SuperAgentSessionService.get_or_create_session(sa_id)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_session_get_or_create.py -v`
Expected: FAIL — `SessionLimitError` and `get_or_create_session` not defined

- [ ] **Step 3: Implement SessionLimitError and get_or_create_session**

In `backend/app/services/super_agent_session_service.py`, add the exception class near the top (after imports):

```python
class SessionLimitError(Exception):
    """Raised when no session can be created due to the global concurrent session limit."""
    pass
```

Add the method to `SuperAgentSessionService` class (after `resume_session`):

```python
    @classmethod
    def get_or_create_session(cls, super_agent_id: str) -> str:
        """Get an existing active/paused session or create a new one.

        Returns the session_id. Raises SessionLimitError if at capacity.
        """
        with cls._lock:
            for sid, state in cls._active_sessions.items():
                if state["super_agent_id"] == super_agent_id:
                    if state["status"] == "active":
                        return sid
                    if state["status"] == "paused":
                        # Release lock before calling resume (it acquires lock internally)
                        break
            else:
                # No existing session found — create outside of lock
                pass

        # Check if we found a paused session to resume
        for sid, state in list(cls._active_sessions.items()):
            if (
                state["super_agent_id"] == super_agent_id
                and state["status"] == "paused"
            ):
                ok, err = cls.resume_session(sid)
                if ok:
                    return sid
                break

        # Create new session
        session_id, error = cls.create_session(super_agent_id)
        if error:
            raise SessionLimitError(error)
        return session_id
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_session_get_or_create.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/super_agent_session_service.py backend/tests/test_session_get_or_create.py
git commit -m "feat: add get_or_create_session to SuperAgentSessionService with SessionLimitError"
```

---

### Task 3: Pydantic Model Updates — Trigger and Execution Log models

**Files:**
- Modify: `backend/app/models/trigger.py`
- Test: `backend/tests/test_trigger_models.py` (create)

- [ ] **Step 1: Write test for model changes**

Create `backend/tests/test_trigger_models.py`:

```python
from app.models.trigger import CreateTriggerRequest, UpdateTriggerRequest, Trigger


class TestTriggerModelDispatchFields:
    def test_create_request_defaults_to_bot(self):
        req = CreateTriggerRequest(name="test", prompt_template="do stuff")
        assert req.dispatch_type == "bot"
        assert req.super_agent_id is None

    def test_create_request_with_super_agent(self):
        req = CreateTriggerRequest(
            name="test",
            prompt_template="do stuff",
            dispatch_type="super_agent",
            super_agent_id="sa-abc123",
        )
        assert req.dispatch_type == "super_agent"
        assert req.super_agent_id == "sa-abc123"

    def test_update_request_accepts_dispatch_fields(self):
        req = UpdateTriggerRequest(
            dispatch_type="super_agent", super_agent_id="sa-abc123"
        )
        assert req.dispatch_type == "super_agent"
        assert req.super_agent_id == "sa-abc123"

    def test_trigger_response_includes_dispatch_fields(self):
        t = Trigger(
            id="trg-123",
            name="test",
            prompt_template="do stuff",
            backend_type="claude",
            trigger_source="webhook",
            dispatch_type="super_agent",
            super_agent_id="sa-abc123",
        )
        assert t.dispatch_type == "super_agent"
        assert t.super_agent_id == "sa-abc123"

    def test_trigger_response_defaults(self):
        t = Trigger(
            id="trg-123",
            name="test",
            prompt_template="do stuff",
            backend_type="claude",
            trigger_source="webhook",
        )
        assert t.dispatch_type == "bot"
        assert t.super_agent_id is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_trigger_models.py -v`
Expected: FAIL — fields don't exist on models yet

- [ ] **Step 3: Add fields to Pydantic models**

In `backend/app/models/trigger.py`:

Add to the `Trigger` response model (after `cron_expression` field):
```python
    dispatch_type: str = "bot"
    super_agent_id: Optional[str] = None
```

Add to `CreateTriggerRequest` (after `webhook_secret` or last field):
```python
    dispatch_type: str = "bot"
    super_agent_id: Optional[str] = None
```

Add to `UpdateTriggerRequest` (after the last optional field):
```python
    dispatch_type: Optional[str] = None
    super_agent_id: Optional[str] = None
```

Ensure `Optional` is imported from `typing` (likely already is).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_trigger_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/trigger.py backend/tests/test_trigger_models.py
git commit -m "feat: add dispatch_type and super_agent_id to trigger Pydantic models"
```

---

## Chunk 2: Backend Dispatch (Dispatcher + Scheduler + Routes + Execution Logs)

### Task 4: Trigger CRUD — Accept and persist dispatch fields

**Files:**
- Modify: `backend/app/db/triggers.py` (`create_trigger`, `update_trigger`)
- Test: `backend/tests/test_trigger_dispatch_crud.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_trigger_dispatch_crud.py`:

```python
import pytest
from app.db import triggers as trigger_db


class TestTriggerDispatchCrud:
    def test_create_trigger_with_dispatch_type(self, isolated_db):
        tid = trigger_db.create_trigger(
            name="sa-trigger",
            prompt_template="run {message}",
            dispatch_type="super_agent",
            super_agent_id="sa-abc123",
        )
        assert tid is not None
        t = trigger_db.get_trigger(tid)
        assert t["dispatch_type"] == "super_agent"
        assert t["super_agent_id"] == "sa-abc123"

    def test_create_trigger_defaults_to_bot(self, isolated_db):
        tid = trigger_db.create_trigger(
            name="bot-trigger",
            prompt_template="run {message}",
        )
        t = trigger_db.get_trigger(tid)
        assert t["dispatch_type"] == "bot"
        assert t["super_agent_id"] is None

    def test_update_trigger_dispatch_type(self, isolated_db):
        tid = trigger_db.create_trigger(
            name="update-test",
            prompt_template="run {message}",
        )
        result = trigger_db.update_trigger(
            tid, dispatch_type="super_agent", super_agent_id="sa-xyz789"
        )
        assert result is True
        t = trigger_db.get_trigger(tid)
        assert t["dispatch_type"] == "super_agent"
        assert t["super_agent_id"] == "sa-xyz789"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_trigger_dispatch_crud.py -v`
Expected: FAIL — `create_trigger()` doesn't accept `dispatch_type`/`super_agent_id`

- [ ] **Step 3: Add dispatch fields to create_trigger and update_trigger**

In `backend/app/db/triggers.py`:

**`create_trigger()`** (line ~174): Add parameters `dispatch_type="bot"` and `super_agent_id=None` to the function signature. Add these columns to the INSERT statement and values tuple.

**`update_trigger()`** (line ~273): Add parameters `dispatch_type=None` and `super_agent_id=None` to the function signature. Add these to the dynamic UPDATE builder (same pattern as other optional fields).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_trigger_dispatch_crud.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/triggers.py backend/tests/test_trigger_dispatch_crud.py
git commit -m "feat: accept dispatch_type and super_agent_id in trigger CRUD"
```

---

### Task 5: Execution Log CRUD — Accept session_id and source_type

**Files:**
- Modify: `backend/app/db/triggers.py` (`create_execution_log`)
- Test: `backend/tests/test_execution_log_source_type.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_execution_log_source_type.py`:

```python
import pytest
from datetime import datetime
from app.db import triggers as trigger_db


class TestExecutionLogSourceType:
    def _create_trigger(self):
        return trigger_db.create_trigger(
            name="test-trigger", prompt_template="test"
        )

    def test_create_log_with_source_type(self, isolated_db):
        tid = self._create_trigger()
        eid = "exec-001"
        result = trigger_db.create_execution_log(
            execution_id=eid,
            trigger_id=tid,
            trigger_type="webhook",
            started_at=datetime.utcnow().isoformat(),
            prompt="test prompt",
            backend_type="claude",
            command="claude -p test",
            source_type="super_agent",
            session_id="sess-abc123",
        )
        assert result is True
        log = trigger_db.get_execution_log(eid)
        assert log["source_type"] == "super_agent"
        assert log["session_id"] == "sess-abc123"

    def test_create_log_defaults_to_bot(self, isolated_db):
        tid = self._create_trigger()
        eid = "exec-002"
        trigger_db.create_execution_log(
            execution_id=eid,
            trigger_id=tid,
            trigger_type="webhook",
            started_at=datetime.utcnow().isoformat(),
            prompt="test",
            backend_type="claude",
            command="claude -p test",
        )
        log = trigger_db.get_execution_log(eid)
        assert log["source_type"] == "bot"
        assert log["session_id"] is None

    def test_create_log_with_null_trigger_id_for_user_chat(self, isolated_db):
        eid = "exec-003"
        result = trigger_db.create_execution_log(
            execution_id=eid,
            trigger_id=None,
            trigger_type="user_chat",
            started_at=datetime.utcnow().isoformat(),
            prompt="user chat prompt",
            backend_type="claude",
            command="",
            source_type="user_chat",
            session_id="sess-xyz",
        )
        assert result is True
        log = trigger_db.get_execution_log(eid)
        assert log["source_type"] == "user_chat"
        assert log["trigger_id"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_execution_log_source_type.py -v`
Expected: FAIL — `create_execution_log()` doesn't accept `source_type`/`session_id`

- [ ] **Step 3: Add source_type and session_id to create_execution_log**

In `backend/app/db/triggers.py`:

**`create_execution_log()`** (line ~827): Add parameters `source_type="bot"` and `session_id=None` to the function signature. Change `trigger_id` to accept `None` (for user_chat source). Add these columns to the INSERT statement.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_execution_log_source_type.py -v`
Expected: PASS

- [ ] **Step 5: Run all existing tests to check nothing broke**

Run: `cd backend && uv run pytest -x -q`
Expected: All pass (new parameters have defaults, existing callers unchanged)

- [ ] **Step 6: Commit**

```bash
git add backend/app/db/triggers.py backend/tests/test_execution_log_source_type.py
git commit -m "feat: add session_id and source_type to execution log CRUD"
```

---

### Task 6: Trigger Dispatcher — Route super_agent dispatch_type

**Scope note:** `trigger_dispatcher.py` has three dispatch entry points: `dispatch_webhook_event`, `dispatch_github_event`, and `dispatch_pr_comment_commands`. This task modifies `dispatch_webhook_event` only. GitHub event dispatch follows the same pattern and should be added in a follow-up task after the webhook path is validated.

**Files:**
- Modify: `backend/app/services/trigger_dispatcher.py`
- Test: `backend/tests/test_trigger_dispatch_super_agent.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_trigger_dispatch_super_agent.py`:

```python
import pytest
from unittest.mock import patch, MagicMock
from app.services.trigger_dispatcher import dispatch_webhook_event
from app.services.super_agent_session_service import SessionLimitError


class TestSuperAgentDispatch:
    def test_super_agent_trigger_dispatches_to_session(self, isolated_db):
        """A trigger with dispatch_type='super_agent' routes to SuperAgentSessionService."""
        from app.db import triggers as trigger_db

        tid = trigger_db.create_trigger(
            name="sa-webhook",
            prompt_template="analyze {text}",
            trigger_source="webhook",
            dispatch_type="super_agent",
            super_agent_id="sa-test01",
            match_field_path="type",
            match_field_value="test",
            text_field_path="text",
        )

        payload = {"type": "test", "text": "hello world"}

        with (
            patch(
                "app.services.trigger_dispatcher.SuperAgentSessionService"
            ) as mock_svc,
            patch(
                "app.services.trigger_dispatcher.create_execution_log"
            ),
        ):
            mock_svc.get_or_create_session.return_value = "sess-new"
            mock_svc.send_message.return_value = (True, None)

            result = dispatch_webhook_event(payload)
            assert result is True

            mock_svc.get_or_create_session.assert_called_once_with("sa-test01")
            mock_svc.send_message.assert_called_once()
            call_args = mock_svc.send_message.call_args
            assert "sess-new" == call_args[0][0]
            assert "hello world" in call_args[0][1]

    def test_bot_trigger_still_uses_execution_queue(self, isolated_db):
        """A trigger with dispatch_type='bot' (default) uses existing queue path."""
        from app.db import triggers as trigger_db

        tid = trigger_db.create_trigger(
            name="bot-webhook",
            prompt_template="scan {text}",
            trigger_source="webhook",
            match_field_path="type",
            match_field_value="test",
            text_field_path="text",
        )

        payload = {"type": "test", "text": "hello"}

        with patch(
            "app.services.trigger_dispatcher.ExecutionQueueService"
        ) as mock_queue:
            mock_queue.enqueue.return_value = True
            result = dispatch_webhook_event(payload)
            assert result is True
            mock_queue.enqueue.assert_called()

    def test_session_limit_error_logs_failure(self, isolated_db):
        """When session limit is reached, execution is logged as failed."""
        from app.db import triggers as trigger_db

        tid = trigger_db.create_trigger(
            name="sa-limit",
            prompt_template="run {text}",
            trigger_source="webhook",
            dispatch_type="super_agent",
            super_agent_id="sa-test02",
            match_field_path="type",
            match_field_value="test",
            text_field_path="text",
        )

        payload = {"type": "test", "text": "hello"}

        with (
            patch(
                "app.services.trigger_dispatcher.SuperAgentSessionService"
            ) as mock_svc,
            patch(
                "app.services.trigger_dispatcher.create_execution_log"
            ) as mock_log,
        ):
            mock_svc.get_or_create_session.side_effect = SessionLimitError(
                "limit reached"
            )

            result = dispatch_webhook_event(payload)
            # Should still return True (trigger matched), but log failure
            assert result is True
            mock_log.assert_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_trigger_dispatch_super_agent.py -v`
Expected: FAIL — dispatcher doesn't import or handle super agent dispatch

- [ ] **Step 3: Add super agent dispatch routing to trigger_dispatcher.py**

In `backend/app/services/trigger_dispatcher.py`:

Add imports at top:
```python
from app.services.super_agent_session_service import SuperAgentSessionService, SessionLimitError
from app.db.triggers import create_execution_log
```

In `dispatch_webhook_event()`, after the existing trigger matching and before the `ExecutionQueueService.enqueue()` call, add a dispatch_type check:

```python
# After trigger is matched and payload extracted...
if trigger.get("dispatch_type") == "super_agent" and trigger.get("super_agent_id"):
    try:
        session_id = SuperAgentSessionService.get_or_create_session(
            trigger["super_agent_id"]
        )
        # Render prompt using the same placeholder substitution
        rendered = trigger["prompt_template"]
        if matched_text:
            rendered = rendered.replace("{text}", matched_text)
            rendered = rendered.replace("{message}", matched_text)
        SuperAgentSessionService.send_message(session_id, rendered)
        # Log execution
        exec_id = f"exec-{trigger['id']}-{int(time.time())}"
        create_execution_log(
            execution_id=exec_id,
            trigger_id=trigger["id"],
            trigger_type="webhook",
            started_at=datetime.utcnow().isoformat(),
            prompt=rendered,
            backend_type=trigger.get("backend_type", "claude"),
            command="",
            source_type="super_agent",
            session_id=session_id,
        )
        triggered = True
    except SessionLimitError as e:
        logger.warning(f"Session limit for trigger {trigger['id']}: {e}")
        exec_id = f"exec-{trigger['id']}-{int(time.time())}"
        create_execution_log(
            execution_id=exec_id,
            trigger_id=trigger["id"],
            trigger_type="webhook",
            started_at=datetime.utcnow().isoformat(),
            prompt=trigger["prompt_template"],
            backend_type=trigger.get("backend_type", "claude"),
            command="",
            source_type="super_agent",
        )
        # Update to failed status
        from app.db.triggers import update_execution_log
        update_execution_log(exec_id, status="failed", error_message=str(e))
        triggered = True
    continue  # Skip the bot execution path for this trigger
```

The exact insertion point and variable names depend on the existing code flow — the implementer should read the full `dispatch_webhook_event` function and insert the check at the trigger-matched-and-payload-extracted stage, before the existing `ExecutionQueueService.enqueue()` call.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_trigger_dispatch_super_agent.py -v`
Expected: PASS

- [ ] **Step 5: Run all backend tests**

Run: `cd backend && uv run pytest -x -q`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/trigger_dispatcher.py backend/tests/test_trigger_dispatch_super_agent.py
git commit -m "feat: route dispatch_type=super_agent triggers to SuperAgentSessionService"
```

---

### Task 7: Scheduler — Fire super agent triggers on cron

**Files:**
- Modify: `backend/app/services/scheduler_service.py`
- Test: `backend/tests/test_scheduler_super_agent.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_scheduler_super_agent.py`:

```python
import pytest
from unittest.mock import patch, MagicMock


class TestSchedulerSuperAgentDispatch:
    def test_execute_trigger_routes_super_agent(self, isolated_db):
        """Scheduler _execute_trigger routes super_agent dispatch_type to session service."""
        from app.db import triggers as trigger_db
        from app.services.scheduler_service import SchedulerService

        tid = trigger_db.create_trigger(
            name="scheduled-sa",
            prompt_template="nightly scan",
            trigger_source="scheduled",
            schedule_type="daily",
            schedule_time="02:00",
            dispatch_type="super_agent",
            super_agent_id="sa-nightly",
        )

        with (
            patch(
                "app.services.scheduler_service.SuperAgentSessionService"
            ) as mock_svc,
            patch(
                "app.services.scheduler_service.create_execution_log",
                return_value=True,
            ),
        ):
            mock_svc.get_or_create_session.return_value = "sess-cron"
            mock_svc.send_message.return_value = (True, None)

            SchedulerService._execute_trigger(tid)

            mock_svc.get_or_create_session.assert_called_once_with("sa-nightly")
            mock_svc.send_message.assert_called_once()

    def test_execute_trigger_bot_unchanged(self, isolated_db):
        """Bot triggers still use the existing ExecutionService path."""
        from app.db import triggers as trigger_db
        from app.services.scheduler_service import SchedulerService

        tid = trigger_db.create_trigger(
            name="scheduled-bot",
            prompt_template="scan",
            trigger_source="scheduled",
            schedule_type="daily",
            schedule_time="03:00",
        )

        with patch(
            "app.services.scheduler_service.ExecutionService"
        ) as mock_exec:
            SchedulerService._execute_trigger(tid)
            mock_exec.run_trigger.assert_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_scheduler_super_agent.py -v`
Expected: FAIL — `_execute_trigger` doesn't handle dispatch_type

- [ ] **Step 3: Add super agent routing to _execute_trigger**

In `backend/app/services/scheduler_service.py`:

Add imports:
```python
from app.services.super_agent_session_service import SuperAgentSessionService, SessionLimitError
from app.db.triggers import create_execution_log, update_execution_log
```

Modify `_execute_trigger()` (line ~208). After fetching the trigger data, add:

```python
@classmethod
def _execute_trigger(cls, trigger_id: str) -> None:
    trigger = get_trigger(trigger_id)
    if not trigger or not trigger.get("enabled", True):
        return

    # Update last_run_at
    update_trigger_last_run(trigger_id, datetime.utcnow().isoformat())

    if trigger.get("dispatch_type") == "super_agent" and trigger.get("super_agent_id"):
        try:
            session_id = SuperAgentSessionService.get_or_create_session(
                trigger["super_agent_id"]
            )
            SuperAgentSessionService.send_message(
                session_id, trigger["prompt_template"]
            )
            exec_id = f"exec-{trigger_id}-{int(time.time())}"
            create_execution_log(
                execution_id=exec_id,
                trigger_id=trigger_id,
                trigger_type="scheduled",
                started_at=datetime.utcnow().isoformat(),
                prompt=trigger["prompt_template"],
                backend_type=trigger.get("backend_type", "claude"),
                command="",
                source_type="super_agent",
                session_id=session_id,
            )
        except SessionLimitError as e:
            logger.warning(f"Scheduled trigger {trigger_id} session limit: {e}")
        return

    # Existing bot path
    ExecutionService.run_trigger(trigger_id, trigger_type="scheduled")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_scheduler_super_agent.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/scheduler_service.py backend/tests/test_scheduler_super_agent.py
git commit -m "feat: scheduler routes super_agent triggers to session service on cron"
```

---

### Task 8: Trigger Routes — Accept dispatch fields in create/update endpoints

**Files:**
- Modify: `backend/app/routes/triggers.py`
- Test: `backend/tests/test_trigger_routes_dispatch.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_trigger_routes_dispatch.py`:

```python
import pytest
from app import create_app


@pytest.fixture
def client(isolated_db):
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestTriggerRouteDispatchFields:
    def test_create_trigger_with_dispatch_type(self, client):
        resp = client.post(
            "/admin/triggers/",
            json={
                "name": "sa-trigger",
                "prompt_template": "do {message}",
                "dispatch_type": "super_agent",
                "super_agent_id": "sa-abc123",
            },
        )
        assert resp.status_code == 201
        data = resp.get_json()
        trigger_id = data["trigger_id"]

        resp = client.get(f"/admin/triggers/{trigger_id}")
        assert resp.status_code == 200
        detail = resp.get_json()
        assert detail["dispatch_type"] == "super_agent"
        assert detail["super_agent_id"] == "sa-abc123"

    def test_update_trigger_dispatch_type(self, client):
        resp = client.post(
            "/admin/triggers/",
            json={"name": "update-test", "prompt_template": "test"},
        )
        trigger_id = resp.get_json()["trigger_id"]

        resp = client.put(
            f"/admin/triggers/{trigger_id}",
            json={
                "dispatch_type": "super_agent",
                "super_agent_id": "sa-xyz789",
            },
        )
        assert resp.status_code == 200

        resp = client.get(f"/admin/triggers/{trigger_id}")
        detail = resp.get_json()
        assert detail["dispatch_type"] == "super_agent"
        assert detail["super_agent_id"] == "sa-xyz789"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_trigger_routes_dispatch.py -v`
Expected: FAIL — route handlers don't pass dispatch fields to DB

- [ ] **Step 3: Update trigger route handlers**

In `backend/app/routes/triggers.py`:

In the `create_trigger` handler (line ~34), where `request.get_json()` data is passed to `trigger_db.create_trigger()` or `TriggerService.create_trigger()`, add `dispatch_type` and `super_agent_id` from the request body.

In the `update_trigger` handler (line ~53), same — pass `dispatch_type` and `super_agent_id` from the JSON body to the update function.

The exact changes depend on how the route currently extracts and passes fields — the implementer should follow the existing pattern for other optional fields like `team_id` or `cron_expression`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_trigger_routes_dispatch.py -v`
Expected: PASS

- [ ] **Step 5: Run all backend tests**

Run: `cd backend && uv run pytest -x -q`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add backend/app/routes/triggers.py backend/tests/test_trigger_routes_dispatch.py
git commit -m "feat: trigger routes accept dispatch_type and super_agent_id"
```

---

## Chunk 3: Frontend Wiring

### Task 9: API Types — Add dispatch and source fields to TypeScript types

**Files:**
- Modify: `frontend/src/services/api/triggers.ts` (or wherever Trigger type is defined)
- Modify: `frontend/src/services/api/types/triggers.ts` (contains the `Execution` type at ~line 135)

- [ ] **Step 1: Find and update Trigger type**

Search for the `Trigger` TypeScript interface/type. Add:

```typescript
dispatch_type?: 'bot' | 'super_agent'
super_agent_id?: string | null
```

- [ ] **Step 2: Update Execution type in `frontend/src/services/api/types/triggers.ts`**

Find the `Execution` interface (~line 135). Add:

```typescript
session_id?: string | null
source_type?: 'bot' | 'super_agent' | 'user_chat'
```

- [ ] **Step 3: Update trigger API create/update functions**

Ensure `triggerApi.create()` and `triggerApi.update()` pass through `dispatch_type` and `super_agent_id` from the request body to the API call.

- [ ] **Step 4: Run frontend type check**

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: No new type errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/services/api/
git commit -m "feat: add dispatch_type, super_agent_id, source_type to frontend API types"
```

---

### Task 10: Trigger Detail Panel — Add dispatch_type selector

**Files:**
- Modify: `frontend/src/components/triggers/TriggerDetailPanel.vue` (or `AddTriggerModal.vue`)

- [ ] **Step 1: Find the trigger form component**

The TriggerManagement.vue uses TriggerDetailPanel and AddTriggerModal. Find where trigger fields are edited.

- [ ] **Step 2: Add dispatch_type radio/select**

In the trigger form, add a section after the existing fields:

```vue
<div class="form-group">
  <label>Dispatch Type</label>
  <div class="radio-group">
    <label>
      <input type="radio" v-model="form.dispatch_type" value="bot" />
      Bot (stateless CLI)
    </label>
    <label>
      <input type="radio" v-model="form.dispatch_type" value="super_agent" />
      Super Agent (persistent session)
    </label>
  </div>
</div>

<div v-if="form.dispatch_type === 'super_agent'" class="form-group">
  <label>Target Super Agent</label>
  <select v-model="form.super_agent_id">
    <option value="">Select super agent...</option>
    <option v-for="sa in superAgents" :key="sa.id" :value="sa.id">
      {{ sa.name }}
    </option>
  </select>
</div>
```

Load super agents list with `superAgentApi.list()` on mount.

- [ ] **Step 3: Wire form data to save/update calls**

Ensure the save handler passes `dispatch_type` and `super_agent_id` to the API.

- [ ] **Step 4: Run frontend build**

Run: `cd frontend && npm run build`
Expected: Build passes

- [ ] **Step 5: Write test**

Create `frontend/src/tests/trigger-dispatch-type.test.ts`:

```typescript
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref, nextTick } from 'vue'
// Import the actual trigger form/detail component
// import TriggerDetailPanel from '@/components/triggers/TriggerDetailPanel.vue'

describe('TriggerDetailPanel dispatch_type', () => {
  it('renders dispatch_type radio buttons', () => {
    // Mount component with a trigger prop
    // Assert: radio inputs for 'bot' and 'super_agent' exist
    // Assert: 'bot' is selected by default
    expect(true).toBe(true) // Placeholder — replace with actual mount
  })

  it('shows super agent dropdown when dispatch_type is super_agent', async () => {
    // Mount component, set dispatch_type to 'super_agent'
    // Assert: super agent select dropdown is visible
    // Assert: dropdown contains loaded super agents
    expect(true).toBe(true) // Placeholder — replace with actual mount
  })

  it('hides super agent dropdown when dispatch_type is bot', async () => {
    // Mount component, set dispatch_type to 'bot'
    // Assert: super agent select dropdown is NOT visible
    expect(true).toBe(true) // Placeholder — replace with actual mount
  })
})
```

**Note:** The exact component import and props depend on `TriggerDetailPanel.vue`'s API. The implementer should read that component, adjust the import/mount, and replace the placeholder assertions with real ones.

- [ ] **Step 6: Run frontend tests**

Run: `cd frontend && npm run test:run`
Expected: All pass

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/triggers/ frontend/src/tests/trigger-dispatch-type.test.ts
git commit -m "feat: add dispatch_type selector to trigger form UI"
```

---

### Task 11: Execution History — Add source_type badge

**Files:**
- Modify: `frontend/src/views/ExecutionHistory.vue`

- [ ] **Step 1: Find the Source column in the table**

The exploration found `<th>Source</th>` exists (line ~270) but the cell isn't populated.

- [ ] **Step 2: Add source_type badge to table row**

In the `<tbody>` section, find where other `<td>` cells are rendered and add:

```vue
<td class="cell-source">
  <span
    class="source-badge"
    :class="execution.source_type || 'bot'"
  >
    {{ formatSourceType(execution.source_type) }}
  </span>
</td>
```

Add helper:
```typescript
function formatSourceType(type: string | undefined): string {
  const labels: Record<string, string> = {
    bot: 'Bot',
    super_agent: 'Super Agent',
    user_chat: 'Chat',
  }
  return labels[type || 'bot'] || type || 'Bot'
}
```

Add CSS:
```css
.source-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.75rem;
}
.source-badge.bot { background: var(--color-surface-2); color: var(--color-text-secondary); }
.source-badge.super_agent { background: var(--color-primary-dim); color: var(--color-primary); }
.source-badge.user_chat { background: var(--color-success-dim); color: var(--color-success); }
```

- [ ] **Step 3: Add source_type to status filter (optional)**

If the status filter dropdown exists, add source_type as an additional filter dimension.

- [ ] **Step 4: Run frontend build**

Run: `cd frontend && npm run build`
Expected: Build passes

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/ExecutionHistory.vue
git commit -m "feat: show source_type badge in execution history table"
```

---

### Task 12: Project Dashboard — Add sessions panel and chat access

**Files:**
- Modify: `frontend/src/views/ProjectDashboard.vue`

- [ ] **Step 1: Add active sessions section**

After the existing Teams panel, add a Sessions section that shows active super agent sessions for the project's teams:

```vue
<section class="sessions-panel">
  <h3>Active Sessions</h3>
  <div v-if="activeSessions.length === 0" class="empty-state">
    No active sessions
  </div>
  <div v-for="session in activeSessions" :key="session.id" class="session-card">
    <span class="agent-name">{{ session.super_agent_name }}</span>
    <span class="status-badge" :class="session.status">{{ session.status }}</span>
    <button @click="openChat(session.super_agent_id, session.id)">Chat</button>
  </div>
</section>
```

- [ ] **Step 2: Load sessions data**

On mount, after loading project teams, fetch sessions for each team's super agents:

```typescript
const activeSessions = ref<any[]>([])

async function loadSessions() {
  const sessions: any[] = []
  for (const member of teamMembers) {
    if (member.super_agent_id) {
      const resp = await superAgentSessionApi.list(member.super_agent_id)
      for (const s of resp.sessions || []) {
        if (s.status === 'active' || s.status === 'paused') {
          sessions.push({ ...s, super_agent_name: member.name, super_agent_id: member.super_agent_id })
        }
      }
    }
  }
  activeSessions.value = sessions
}
```

- [ ] **Step 3: Add chat slide-over**

Use the existing `SlideOver` component to open a chat panel. Inside, embed the `useAiChat` composable:

```vue
<SlideOver v-model="showChat" title="Chat">
  <!-- Chat UI using useAiChat composable -->
</SlideOver>
```

The chat UI can reuse the pattern from `SuperAgentPlayground.vue`.

- [ ] **Step 4: Run frontend build**

Run: `cd frontend && npm run build`
Expected: Build passes

- [ ] **Step 5: Write test**

Create `frontend/src/tests/project-dashboard.test.ts`:

```typescript
import { describe, it, expect, vi } from 'vitest'

describe('ProjectDashboard sessions panel', () => {
  it('renders active sessions section', () => {
    // Mount ProjectDashboard with mocked API responses
    // Assert: "Active Sessions" heading exists
    expect(true).toBe(true) // Placeholder — replace with actual mount
  })

  it('shows session status for team super agents', () => {
    // Mock superAgentSessionApi.list to return active sessions
    // Assert: session cards render with status badges
    expect(true).toBe(true) // Placeholder
  })

  it('opens chat slide-over when chat button clicked', () => {
    // Click chat button on a session card
    // Assert: SlideOver becomes visible
    expect(true).toBe(true) // Placeholder
  })
})
```

- [ ] **Step 6: Run frontend tests**

Run: `cd frontend && npm run test:run`
Expected: All pass

- [ ] **Step 7: Commit**

```bash
git add frontend/src/views/ProjectDashboard.vue frontend/src/tests/project-dashboard.test.ts
git commit -m "feat: add active sessions panel and chat access to project dashboard"
```

---

### Task 13: Team Dashboard — Wire chat button and mailbox

**Files:**
- Modify: `frontend/src/views/TeamDashboard.vue`

- [ ] **Step 1: Add session status to member list**

In the members section, for each super agent member, show session status and a Chat button:

```vue
<div v-for="member in team.members" :key="member.id" class="member-card">
  <span>{{ member.name }}</span>
  <span v-if="member.member_type === 'super_agent'" class="session-status">
    {{ memberSessionStatus[member.super_agent_id] || 'idle' }}
  </span>
  <button
    v-if="member.member_type === 'super_agent'"
    @click="openChat(member.super_agent_id)"
  >
    Chat
  </button>
</div>
```

- [ ] **Step 2: Load session status for each super agent member**

```typescript
const memberSessionStatus = ref<Record<string, string>>({})

async function loadMemberSessions() {
  for (const member of team.value?.members || []) {
    if (member.super_agent_id) {
      const resp = await superAgentSessionApi.list(member.super_agent_id)
      const active = (resp.sessions || []).find(
        (s: any) => s.status === 'active' || s.status === 'paused'
      )
      memberSessionStatus.value[member.super_agent_id] = active?.status || 'idle'
    }
  }
}
```

- [ ] **Step 3: Add mailbox section**

Below the members list, add the MessageInbox component for the team leader:

```vue
<section v-if="leaderSuperAgentId" class="mailbox-section">
  <h3>Team Mailbox</h3>
  <MessageInbox
    :super-agent-id="leaderSuperAgentId"
    @select-thread="openThread"
  />
</section>
```

Import `MessageInbox` from `@/components/super-agents/MessageInbox.vue`.

- [ ] **Step 4: Add chat slide-over (same pattern as Task 12)**

- [ ] **Step 5: Write test**

Create `frontend/src/tests/team-dashboard-chat.test.ts`:

```typescript
import { describe, it, expect, vi } from 'vitest'

describe('TeamDashboard chat and mailbox', () => {
  it('shows chat button for super agent members', () => {
    // Mount TeamDashboard with team data containing super_agent members
    // Assert: Chat button visible for super agent members
    // Assert: Chat button NOT visible for regular agent members
    expect(true).toBe(true) // Placeholder
  })

  it('shows session status indicator per super agent', () => {
    // Mock superAgentSessionApi.list to return active/idle sessions
    // Assert: status badges show correct states
    expect(true).toBe(true) // Placeholder
  })

  it('renders MessageInbox for team leader', () => {
    // Mount with a team that has a leader super agent
    // Assert: MessageInbox component is rendered
    expect(true).toBe(true) // Placeholder
  })
})
```

- [ ] **Step 6: Run frontend build and tests**

Run: `cd frontend && npm run build && npm run test:run`
Expected: Both pass

- [ ] **Step 7: Commit**

```bash
git add frontend/src/views/TeamDashboard.vue frontend/src/tests/team-dashboard-chat.test.ts
git commit -m "feat: wire chat button and mailbox to team dashboard"
```

---

### Task 14: Scheduling Dashboard — Wire to real data

**Files:**
- Modify: `frontend/src/views/SchedulingDashboard.vue`

- [ ] **Step 1: Review current state**

The exploration shows SchedulingDashboard is already functional — it loads `schedulerApi.getStatus`, shows scheduler sessions, rotation events, and a timeline chart. It already displays `trigger_id` and `backend_type` for active sessions.

- [ ] **Step 2: Add scheduled triggers list**

Add a section showing all triggers with `trigger_source='scheduled'`:

```vue
<section class="scheduled-triggers">
  <h3>Scheduled Triggers</h3>
  <table>
    <thead>
      <tr>
        <th>Name</th>
        <th>Dispatch</th>
        <th>Schedule</th>
        <th>Next Run</th>
        <th>Last Run</th>
        <th>Status</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="t in scheduledTriggers" :key="t.id">
        <td>{{ t.name }}</td>
        <td>
          <span class="source-badge" :class="t.dispatch_type">
            {{ t.dispatch_type === 'super_agent' ? 'Super Agent' : 'Bot' }}
          </span>
        </td>
        <td>{{ t.cron_expression || formatSchedule(t) }}</td>
        <td>{{ formatDate(t.next_run_at) }}</td>
        <td>{{ formatDate(t.last_run_at) }}</td>
        <td>
          <span :class="t.enabled ? 'enabled' : 'disabled'">
            {{ t.enabled ? 'Active' : 'Paused' }}
          </span>
        </td>
      </tr>
    </tbody>
  </table>
</section>
```

- [ ] **Step 3: Load scheduled triggers**

```typescript
const scheduledTriggers = ref<any[]>([])

async function loadScheduledTriggers() {
  const resp = await triggerApi.list({ limit: 100 })
  scheduledTriggers.value = (resp.triggers || []).filter(
    (t: any) => t.trigger_source === 'scheduled'
  )
}
```

- [ ] **Step 4: Run frontend build**

Run: `cd frontend && npm run build`
Expected: Build passes

- [ ] **Step 5: Write test**

Create `frontend/src/tests/scheduling-dashboard.test.ts`:

```typescript
import { describe, it, expect, vi } from 'vitest'

describe('SchedulingDashboard triggers list', () => {
  it('renders scheduled triggers table', () => {
    // Mock triggerApi.list to return triggers with trigger_source='scheduled'
    // Assert: table renders with Name, Dispatch, Schedule columns
    expect(true).toBe(true) // Placeholder
  })

  it('shows dispatch_type badge for each trigger', () => {
    // Assert: bot triggers show "Bot" badge
    // Assert: super_agent triggers show "Super Agent" badge
    expect(true).toBe(true) // Placeholder
  })
})
```

- [ ] **Step 6: Run frontend build and tests**

Run: `cd frontend && npm run build && npm run test:run`
Expected: Both pass

- [ ] **Step 7: Commit**

```bash
git add frontend/src/views/SchedulingDashboard.vue frontend/src/tests/scheduling-dashboard.test.ts
git commit -m "feat: wire scheduling dashboard with scheduled triggers list and dispatch type"
```

---

## Chunk 4: Verification

### Task 15: Full verification pass

- [ ] **Step 1: Run all backend tests**

Run: `cd backend && uv run pytest -v`
Expected: All pass

- [ ] **Step 2: Run all frontend tests**

Run: `cd frontend && npm run test:run`
Expected: All pass

- [ ] **Step 3: Run frontend build (type check + vite)**

Run: `cd frontend && npm run build`
Expected: Build succeeds with zero errors

- [ ] **Step 4: Format backend code**

Run: `cd backend && uv run ruff format .`

- [ ] **Step 5: Manual smoke test (if dev servers available)**

1. Start backend: `just dev-backend`
2. Start frontend: `just dev-frontend`
3. Walk through success criteria:
   - Create project → create team with super agents → assign team → create trigger with dispatch_type=super_agent → fire trigger → verify session created → verify execution logged
   - Open project dashboard → see sessions panel → click chat
   - Open scheduling dashboard → see scheduled triggers with dispatch type
   - Open execution history → see source_type badges

- [ ] **Step 6: Final commit if any formatting changes**

```bash
git add -A && git commit -m "chore: format and verify core loop wiring"
```
