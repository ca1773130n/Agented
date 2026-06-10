# Harness-1 Phase 2 — Evidence Ledger + Verification Records Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist typed `tool_use` events from in-process super-agent runs into a queryable evidence ledger, and add durable verification records with a post-hoc gate on PR creation.

**Architecture:** Two independent units on two substrates. **P3** = `harness_evidence` table keyed by `session_id`, written from `streaming_helper.run_streaming_response`'s `ToolUseEvent` dispatch. **P5** = `verification_records` table keyed by `execution_id` (next to Phase 1's `harness_runs`), a `VerificationService` write API, a Litestar read/write router, and an advisory gate at the `auto_resolve_and_pr` call site. Both follow the established raw-SQLite `get_connection()` + `schema/_*.py` + numbered-migration patterns.

**Tech Stack:** Python 3.10+, raw SQLite (`app/db/connection.py:get_connection`), Litestar, pytest (`isolated_db` autouse fixture runs `init_db()` + `seed_predefined_triggers()`), ruff (line-length 100).

**Conventions to follow:**
- Mirror `app/db/schema/_harness_state.py` (DDL) and `app/db/harness_state.py` (repo) from Phase 1.
- Migrations: a `_migrate_NNN_<name>(conn)` fn in `app/db/migrations/v07_features.py` that imports + calls the schema fn, plus a `(NNN, "<name>", _migrate_NNN_<name>)` tuple appended to `V07_MIGRATIONS` (current max is **148**; Phase 2 uses **149** and **150**).
- Register each `create_*_tables` in `app/db/schema/__init__.py:create_fresh_schema` in FK-dependency order.
- Best-effort writes on the streaming hot path: wrap in `try/except`, log at `debug`, never raise.
- Targeted test runs only (`uv run pytest tests/<file>.py`) — the full serial suite is known to hang.

---

## Task 1: P3 — `harness_evidence` schema + migration 149

**Files:**
- Create: `backend/app/db/schema/_harness_evidence.py`
- Modify: `backend/app/db/schema/__init__.py` (import + register in `create_fresh_schema`)
- Modify: `backend/app/db/migrations/v07_features.py` (add `_migrate_149_harness_evidence` + registry tuple)
- Test: `backend/tests/test_harness_evidence_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_harness_evidence_schema.py
"""Schema + migration for the P3 evidence ledger (Harness-1 Phase 2)."""

from app.db.connection import get_connection


def test_harness_evidence_table_created_by_fresh_schema():
    with get_connection() as conn:
        tables = {
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    assert "harness_evidence" in tables


def test_create_harness_evidence_tables_idempotent():
    from app.db.schema._harness_evidence import create_harness_evidence_tables

    with get_connection() as conn:
        create_harness_evidence_tables(conn)
        create_harness_evidence_tables(conn)  # must not raise
        conn.commit()


def test_migration_149_registered():
    from app.db.migrations import VERSIONED_MIGRATIONS

    versions = {v for (v, _n, _f) in VERSIONED_MIGRATIONS}
    names = {n for (_v, n, _f) in VERSIONED_MIGRATIONS}
    assert 149 in versions
    assert "harness_evidence" in names


def test_migration_149_creates_table_on_existing_db():
    import sqlite3

    from app.db.migrations.v07_features import _migrate_149_harness_evidence

    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("CREATE TABLE super_agent_sessions (id TEXT PRIMARY KEY, super_agent_id TEXT)")
    _migrate_149_harness_evidence(conn)
    _migrate_149_harness_evidence(conn)  # idempotent
    tabs = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "harness_evidence" in tabs
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_harness_evidence_schema.py -q`
Expected: FAIL — `ImportError: cannot import name '_migrate_149_harness_evidence'` / `harness_evidence` not in tables.

- [ ] **Step 3: Create the schema module**

```python
# backend/app/db/schema/_harness_evidence.py
"""Typed tool_use evidence ledger (Harness-1 Phase 2, P3).

One row per ToolUseEvent emitted by an in-process super-agent run, keyed by
``session_id`` (FK to ``super_agent_sessions(id)``), so the run's tool calls
are queryable in order without grepping the transcript. ``seq`` is a
per-session monotonic ordinal.

Reference: docs/superpowers/specs/2026-06-10-harness-phase2-evidence-verification-design.md
"""

from __future__ import annotations


def create_harness_evidence_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS harness_evidence (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      TEXT    NOT NULL,
            super_agent_id  TEXT,
            seq             INTEGER NOT NULL,
            tool_name       TEXT    NOT NULL,
            tool_input_json TEXT    NOT NULL DEFAULT '{}',
            tool_use_id     TEXT,
            created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
            UNIQUE (session_id, seq),
            FOREIGN KEY (session_id)
                REFERENCES super_agent_sessions(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_harness_evidence_session "
        "ON harness_evidence(session_id, seq)"
    )
```

`UNIQUE (session_id, seq)` is a correctness backstop: `seq` is assigned atomically inside the INSERT (Task 2), and this constraint guarantees no two rows in a session can ever share an ordinal even under concurrent writers.

- [ ] **Step 4: Register in `create_fresh_schema`**

In `backend/app/db/schema/__init__.py`, add the import next to the other harness imports:

```python
from ._harness_evidence import create_harness_evidence_tables
```

And call it in `create_fresh_schema` AFTER `create_super_agent_tables(conn)` (the FK target), e.g. immediately after that line:

```python
    create_super_agent_tables(conn)
    create_harness_evidence_tables(conn)
```

- [ ] **Step 5: Add migration 149**

In `backend/app/db/migrations/v07_features.py`, add the function just before the `V07_MIGRATIONS` list:

```python
def _migrate_149_harness_evidence(conn):
    """Harness-1 Phase 2 (P3): typed tool_use evidence ledger keyed by
    session_id. Added to create_fresh_schema; idempotent on existing DBs."""
    from app.db.schema._harness_evidence import create_harness_evidence_tables

    create_harness_evidence_tables(conn)
```

And append to `V07_MIGRATIONS` (after the `148, "harness_state"` tuple):

```python
    # Harness-1 Phase 2: typed tool_use evidence ledger (chat substrate).
    (149, "harness_evidence", _migrate_149_harness_evidence),
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_harness_evidence_schema.py -q`
Expected: PASS (4 passed).

- [ ] **Step 7: Commit**

```bash
git add backend/app/db/schema/_harness_evidence.py backend/app/db/schema/__init__.py backend/app/db/migrations/v07_features.py backend/tests/test_harness_evidence_schema.py
git commit -m "feat(harness): harness_evidence schema + migration 149 (Phase 2 P3)"
```

---

## Task 2: P3 — `harness_evidence` repository module

**Files:**
- Create: `backend/app/db/harness_evidence.py`
- Test: `backend/tests/test_harness_evidence_repo.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_harness_evidence_repo.py
"""Repository for the P3 evidence ledger."""

from app.db import harness_evidence
from app.db.connection import get_connection


def _make_session(session_id: str = "sess-1", super_agent_id: str = "sa-1") -> None:
    # FKs are ON: super_agent_sessions.super_agent_id REFERENCES super_agents(id),
    # so the parent must exist first.
    with get_connection() as conn:
        conn.execute("INSERT INTO super_agents (id, name) VALUES (?, ?)", (super_agent_id, "Test SA"))
        conn.execute(
            "INSERT INTO super_agent_sessions (id, super_agent_id) VALUES (?, ?)",
            (session_id, super_agent_id),
        )
        conn.commit()


def test_record_tool_use_assigns_monotonic_seq():
    _make_session()
    s1 = harness_evidence.record_tool_use(
        "sess-1", super_agent_id="sa-1", tool_name="grep", tool_input={"q": "x"}, tool_use_id="t1"
    )
    s2 = harness_evidence.record_tool_use(
        "sess-1", super_agent_id="sa-1", tool_name="read", tool_input={"path": "a"}
    )
    assert s1 == 1
    assert s2 == 2


def test_list_evidence_ordered_with_deserialized_input():
    _make_session()
    harness_evidence.record_tool_use("sess-1", super_agent_id="sa-1", tool_name="grep", tool_input={"q": "x"})
    harness_evidence.record_tool_use("sess-1", super_agent_id="sa-1", tool_name="read", tool_input={"path": "a"})
    rows = harness_evidence.list_evidence("sess-1")
    assert [r["seq"] for r in rows] == [1, 2]
    assert rows[0]["tool_name"] == "grep"
    assert rows[0]["tool_input"] == {"q": "x"}


def test_count_evidence():
    _make_session()
    assert harness_evidence.count_evidence("sess-1") == 0
    harness_evidence.record_tool_use("sess-1", super_agent_id="sa-1", tool_name="grep", tool_input={})
    assert harness_evidence.count_evidence("sess-1") == 1


def test_list_evidence_empty_for_unknown_session():
    assert harness_evidence.list_evidence("nope") == []


def test_fk_cascade_delete_removes_evidence():
    _make_session()
    harness_evidence.record_tool_use("sess-1", super_agent_id="sa-1", tool_name="grep", tool_input={})
    with get_connection() as conn:
        conn.execute("DELETE FROM super_agent_sessions WHERE id = ?", ("sess-1",))
        conn.commit()
    assert harness_evidence.list_evidence("sess-1") == []


def test_unique_session_seq_constraint_rejects_duplicate():
    """The UNIQUE(session_id, seq) backstop forbids two rows sharing an ordinal."""
    import sqlite3

    import pytest

    _make_session()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO harness_evidence (session_id, seq, tool_name) VALUES ('sess-1', 1, 'a')"
        )
        conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO harness_evidence (session_id, seq, tool_name) VALUES ('sess-1', 1, 'b')"
            )
            conn.commit()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_harness_evidence_repo.py -q`
Expected: FAIL — `ImportError: cannot import name 'harness_evidence' from 'app.db'`.

- [ ] **Step 3: Write the repository module**

```python
# backend/app/db/harness_evidence.py
"""Repository for the typed tool_use evidence ledger (Harness-1 Phase 2, P3).

See ``app.db.schema._harness_evidence`` for the DDL. ``record_tool_use`` is
the core primitive: it assigns the next per-session ``seq`` and inserts one
row in a single transaction, returning the assigned ``seq``.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from .connection import get_connection


def record_tool_use(
    session_id: str,
    *,
    super_agent_id: Optional[str],
    tool_name: str,
    tool_input: Any,
    tool_use_id: Optional[str] = None,
) -> int:
    """Append one tool_use row with the next per-session ``seq``. Returns seq.

    The ordinal is computed inside the INSERT (a correlated subquery), so it is
    evaluated while SQLite holds the write lock — assignment is atomic and
    cannot race across connections. ``UNIQUE(session_id, seq)`` is the backstop.
    """
    payload = json.dumps(tool_input, default=str)
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO harness_evidence "
            "(session_id, super_agent_id, seq, tool_name, tool_input_json, tool_use_id) "
            "VALUES (?, ?, "
            "  (SELECT COALESCE(MAX(seq), 0) + 1 FROM harness_evidence WHERE session_id = ?), "
            "  ?, ?, ?)",
            (session_id, super_agent_id, session_id, tool_name, payload, tool_use_id),
        )
        seq = conn.execute(
            "SELECT seq FROM harness_evidence WHERE id = ?", (cur.lastrowid,)
        ).fetchone()[0]
        conn.commit()
    return int(seq)


def list_evidence(session_id: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM harness_evidence WHERE session_id = ? ORDER BY seq ASC",
            (session_id,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def count_evidence(session_id: str) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM harness_evidence WHERE session_id = ?", (session_id,)
        ).fetchone()
    return int(row[0])


def _row_to_dict(row) -> dict:
    d = dict(row)
    try:
        d["tool_input"] = json.loads(d.pop("tool_input_json") or "{}")
    except (TypeError, ValueError):
        d["tool_input"] = {}
    return d
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_harness_evidence_repo.py -q`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/harness_evidence.py backend/tests/test_harness_evidence_repo.py
git commit -m "feat(harness): harness_evidence repository (Phase 2 P3)"
```

---

## Task 3: P3 — Tap `ToolUseEvent` into the evidence ledger

**Files:**
- Modify: `backend/app/services/streaming_helper.py` (two `isinstance(chunk, ToolUseEvent)` sites: ≈ lines 177-178 and 275-276)
- Test: `backend/tests/test_evidence_ledger_tap.py`

Both tap sites have `_session_id` and `_super_agent_id` in local scope (set near the top of `run_streaming_response`).

- [ ] **Step 1: Write the failing test**

The tap logic is small; test it via a module-level helper `_record_tool_use_evidence` that we will add and call from both sites (keeps the test independent of launching a real stream thread).

```python
# backend/tests/test_evidence_ledger_tap.py
"""The P3 tap records ToolUseEvents and never breaks streaming."""

from unittest.mock import patch

from app.db import harness_evidence
from app.db.connection import get_connection
from app.services.conversation_streaming import ToolUseEvent
from app.services.streaming_helper import _record_tool_use_evidence


def _make_session(session_id="sess-1", super_agent_id="sa-1"):
    with get_connection() as conn:
        conn.execute("INSERT INTO super_agents (id, name) VALUES (?, ?)", (super_agent_id, "Test SA"))
        conn.execute(
            "INSERT INTO super_agent_sessions (id, super_agent_id) VALUES (?, ?)",
            (session_id, super_agent_id),
        )
        conn.commit()


def test_tap_records_tool_use_event():
    _make_session()
    evt = ToolUseEvent(name="grep", input={"q": "x"}, id="t1")
    _record_tool_use_evidence("sess-1", "sa-1", evt)
    rows = harness_evidence.list_evidence("sess-1")
    assert len(rows) == 1
    assert rows[0]["tool_name"] == "grep"
    assert rows[0]["tool_input"] == {"q": "x"}
    assert rows[0]["tool_use_id"] == "t1"


def test_tap_swallows_errors_and_never_raises():
    evt = ToolUseEvent(name="grep", input={"q": "x"}, id="t1")
    with patch(
        "app.services.streaming_helper.harness_evidence.record_tool_use",
        side_effect=RuntimeError("db down"),
    ):
        # Must not raise — streaming must never be disrupted by a ledger write.
        _record_tool_use_evidence("sess-1", "sa-1", evt)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_evidence_ledger_tap.py -q`
Expected: FAIL — `ImportError: cannot import name '_record_tool_use_evidence'`.

- [ ] **Step 3: Add the helper + import, and call it at both tap sites**

In `backend/app/services/streaming_helper.py`, add the import near the top (with the other `..db` imports):

```python
from ..db import harness_evidence
```

Add the module-level helper (place it above `run_streaming_response`):

```python
def _record_tool_use_evidence(session_id: str, super_agent_id, event) -> None:
    """Best-effort: persist a ToolUseEvent to the evidence ledger (Phase 2 P3).
    Never raises — a ledger write must not disrupt streaming."""
    try:
        harness_evidence.record_tool_use(
            session_id,
            super_agent_id=super_agent_id,
            tool_name=event.name,
            tool_input=event.input,
            tool_use_id=event.id,
        )
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("evidence ledger write failed for %s: %s", session_id, e)
```

At BOTH dispatch sites (≈ line 178 and ≈ line 276), immediately after the existing `ChatStateService.push_delta(_session_id, "tool_use", chunk.to_dict())`, add:

```python
                        _record_tool_use_evidence(_session_id, _super_agent_id, chunk)
```

So each site becomes:

```python
                    if isinstance(chunk, ToolUseEvent):
                        ChatStateService.push_delta(_session_id, "tool_use", chunk.to_dict())
                        _record_tool_use_evidence(_session_id, _super_agent_id, chunk)
                        continue
```

(Both sites — `streaming_helper.py:177-179` and `:275-277` — already `continue` after the `push_delta`. Insert the one new `_record_tool_use_evidence(...)` line between the existing `push_delta` and `continue` at each site; do not change any other control flow.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_evidence_ledger_tap.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Run streaming regression check**

Run: `cd backend && uv run pytest tests/test_litestar_streams.py tests/test_rate_limit_service.py -q`
Expected: PASS (no regressions in the streaming path).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/streaming_helper.py backend/tests/test_evidence_ledger_tap.py
git commit -m "feat(harness): tap ToolUseEvent into evidence ledger (Phase 2 P3)"
```

---

## Task 4: P5 — `verification_records` schema + migration 150

**Files:**
- Create: `backend/app/db/schema/_verification_records.py`
- Modify: `backend/app/db/schema/__init__.py`
- Modify: `backend/app/db/migrations/v07_features.py`
- Test: `backend/tests/test_verification_records_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_verification_records_schema.py
"""Schema + migration for the P5 verification records (Harness-1 Phase 2)."""

from app.db.connection import get_connection


def test_verification_records_table_created_by_fresh_schema():
    with get_connection() as conn:
        tables = {
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    assert "verification_records" in tables


def test_create_verification_records_tables_idempotent():
    from app.db.schema._verification_records import create_verification_records_tables

    with get_connection() as conn:
        create_verification_records_tables(conn)
        create_verification_records_tables(conn)
        conn.commit()


def test_migration_150_registered():
    from app.db.migrations import VERSIONED_MIGRATIONS

    versions = {v for (v, _n, _f) in VERSIONED_MIGRATIONS}
    names = {n for (_v, n, _f) in VERSIONED_MIGRATIONS}
    assert 150 in versions
    assert "verification_records" in names


def test_status_check_constraint_rejects_bad_value():
    import sqlite3

    from app.db.migrations.v07_features import _migrate_150_verification_records

    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("CREATE TABLE execution_logs (id INTEGER PRIMARY KEY, execution_id TEXT UNIQUE)")
    conn.execute("INSERT INTO execution_logs(execution_id) VALUES ('e1')")
    _migrate_150_verification_records(conn)
    try:
        conn.execute(
            "INSERT INTO verification_records (execution_id, claim, status) VALUES ('e1','c','bogus')"
        )
        raise AssertionError("CHECK constraint should have rejected 'bogus'")
    except sqlite3.IntegrityError:
        pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_verification_records_schema.py -q`
Expected: FAIL — module/migration not found.

- [ ] **Step 3: Create the schema module**

```python
# backend/app/db/schema/_verification_records.py
"""Durable verification records (Harness-1 Phase 2, P5).

One row per claim checked against an execution, keyed by
``execution_logs(execution_id)``. Sits next to Phase 1's ``harness_runs``.
Read/written via app.db.verification_records and VerificationService; consulted
by the post-hoc PR gate in ExecutionService.
"""

from __future__ import annotations


def create_verification_records_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS verification_records (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            execution_id  TEXT    NOT NULL,
            claim         TEXT    NOT NULL,
            status        TEXT    NOT NULL DEFAULT 'pending'
                          CHECK (status IN ('pending', 'passed', 'failed')),
            evidence_ref  TEXT,
            checked_at    TEXT,
            created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (execution_id)
                REFERENCES execution_logs(execution_id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_verification_records_exec "
        "ON verification_records(execution_id)"
    )
```

- [ ] **Step 4: Register in `create_fresh_schema`**

In `backend/app/db/schema/__init__.py`, add the import:

```python
from ._verification_records import create_verification_records_tables
```

And call it AFTER `create_core_tables(conn)` (the `execution_logs` FK target):

```python
    create_core_tables(conn)
    create_verification_records_tables(conn)
```

- [ ] **Step 5: Add migration 150**

In `backend/app/db/migrations/v07_features.py`, add the function before `V07_MIGRATIONS`:

```python
def _migrate_150_verification_records(conn):
    """Harness-1 Phase 2 (P5): durable verification records keyed by
    execution_id. Added to create_fresh_schema; idempotent on existing DBs."""
    from app.db.schema._verification_records import create_verification_records_tables

    create_verification_records_tables(conn)
```

And append to `V07_MIGRATIONS`:

```python
    # Harness-1 Phase 2: durable verification records (execution substrate).
    (150, "verification_records", _migrate_150_verification_records),
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_verification_records_schema.py -q`
Expected: PASS (4 passed).

- [ ] **Step 7: Commit**

```bash
git add backend/app/db/schema/_verification_records.py backend/app/db/schema/__init__.py backend/app/db/migrations/v07_features.py backend/tests/test_verification_records_schema.py
git commit -m "feat(harness): verification_records schema + migration 150 (Phase 2 P5)"
```

---

## Task 5: P5 — `verification_records` repository module

**Files:**
- Create: `backend/app/db/verification_records.py`
- Test: `backend/tests/test_verification_records_repo.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_verification_records_repo.py
"""Repository for P5 verification records."""

from app.db import verification_records as vr
from app.db.connection import get_connection


def _make_execution(execution_id: str = "exec-1") -> None:
    from app.db.execution_logs import create_execution_log

    create_execution_log(
        execution_id=execution_id,
        trigger_id="bot-pr-review",
        trigger_type="manual",
        started_at="2026-06-10T00:00:00",
        prompt="p",
        backend_type="claude",
        command="echo hi",
    )


def test_record_verification_pending_has_no_checked_at():
    _make_execution()
    rid = vr.record_verification("exec-1", "tests pass")
    assert rid > 0
    rows = vr.list_verifications("exec-1")
    assert rows[0]["status"] == "pending"
    assert rows[0]["checked_at"] is None


def test_record_verification_terminal_sets_checked_at():
    _make_execution()
    vr.record_verification("exec-1", "no secrets", status="passed", evidence_ref="scan.json")
    row = vr.list_verifications("exec-1")[0]
    assert row["status"] == "passed"
    assert row["evidence_ref"] == "scan.json"
    assert row["checked_at"] is not None


def test_has_failed_only_true_when_a_failed_record_exists():
    _make_execution()
    assert vr.has_failed("exec-1") is False
    vr.record_verification("exec-1", "lint clean", status="passed")
    assert vr.has_failed("exec-1") is False
    vr.record_verification("exec-1", "no high-sev CVEs", status="failed")
    assert vr.has_failed("exec-1") is True


def test_list_empty_for_unknown_execution():
    assert vr.list_verifications("nope") == []


def test_fk_cascade_delete_removes_records():
    _make_execution()
    vr.record_verification("exec-1", "x", status="failed")
    with get_connection() as conn:
        conn.execute("DELETE FROM execution_logs WHERE execution_id = ?", ("exec-1",))
        conn.commit()
    assert vr.list_verifications("exec-1") == []
    assert vr.has_failed("exec-1") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_verification_records_repo.py -q`
Expected: FAIL — `ImportError: cannot import name 'verification_records'`.

- [ ] **Step 3: Write the repository module**

```python
# backend/app/db/verification_records.py
"""Repository for durable verification records (Harness-1 Phase 2, P5)."""

from __future__ import annotations

from typing import Optional

from .connection import get_connection


def record_verification(
    execution_id: str,
    claim: str,
    status: str = "pending",
    evidence_ref: Optional[str] = None,
) -> int:
    """Insert a verification record. Sets ``checked_at`` when terminal
    (status != 'pending'). Returns the new row id."""
    checked_at_expr = "datetime('now')" if status != "pending" else "NULL"
    with get_connection() as conn:
        cur = conn.execute(
            f"INSERT INTO verification_records "
            f"(execution_id, claim, status, evidence_ref, checked_at) "
            f"VALUES (?, ?, ?, ?, {checked_at_expr})",
            (execution_id, claim, status, evidence_ref),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_verifications(execution_id: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM verification_records WHERE execution_id = ? ORDER BY id ASC",
            (execution_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def has_failed(execution_id: str) -> bool:
    """True iff at least one record for this execution is 'failed'. The
    post-hoc gate predicate."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM verification_records "
            "WHERE execution_id = ? AND status = 'failed' LIMIT 1",
            (execution_id,),
        ).fetchone()
    return row is not None
```

Note: `status` is validated by the table's CHECK constraint, and `checked_at_expr` only ever interpolates one of two fixed literals (never user input) — safe.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_verification_records_repo.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/verification_records.py backend/tests/test_verification_records_repo.py
git commit -m "feat(harness): verification_records repository (Phase 2 P5)"
```

---

## Task 6: P5 — `VerificationService` write facade

**Files:**
- Create: `backend/app/services/verification_service.py`
- Test: `backend/tests/test_verification_service.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_verification_service.py
"""VerificationService write facade (Harness-1 Phase 2, P5)."""

from app.db import verification_records as vr
from app.services.verification_service import VerificationService


def _make_execution(execution_id: str = "exec-1") -> None:
    from app.db.execution_logs import create_execution_log

    create_execution_log(
        execution_id=execution_id,
        trigger_id="bot-pr-review",
        trigger_type="manual",
        started_at="2026-06-10T00:00:00",
        prompt="p",
        backend_type="claude",
        command="echo hi",
    )


def test_record_writes_a_verification_row():
    _make_execution()
    rid = VerificationService.record("exec-1", "no secrets", status="passed", evidence_ref="scan.json")
    assert rid > 0
    rows = vr.list_verifications("exec-1")
    assert rows[0]["claim"] == "no secrets"
    assert rows[0]["status"] == "passed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_verification_service.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the service**

```python
# backend/app/services/verification_service.py
"""Write facade for verification records (Harness-1 Phase 2, P5).

The deliverable is the write API. Auto-wiring a specific bot
(bot-security / bot-pr-review) to populate records is a later integration.
"""

from __future__ import annotations

from typing import Optional

from ..db import verification_records


class VerificationService:
    @staticmethod
    def record(
        execution_id: str,
        claim: str,
        status: str = "pending",
        evidence_ref: Optional[str] = None,
    ) -> int:
        """Record a verification claim against an execution. Returns row id."""
        return verification_records.record_verification(
            execution_id, claim, status=status, evidence_ref=evidence_ref
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_verification_service.py -q`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/verification_service.py backend/tests/test_verification_service.py
git commit -m "feat(harness): VerificationService write facade (Phase 2 P5)"
```

---

## Task 7: P5 — Advisory PR gate at the `auto_resolve_and_pr` call site

**Files:**
- Modify: `backend/app/services/execution_service.py` (≈ line 672, the `auto_resolve_and_pr(trigger, github_repo_map, scan_output)` call)
- Test: `backend/tests/test_verification_gate.py`

Two pieces: a module-level predicate `_verification_pr_gate(execution_id) -> bool`, and a thin `ExecutionService._maybe_auto_resolve_and_pr(...)` classmethod that the call site at `:672` delegates to. The classmethod is what makes the *wiring* testable: a unit test asserts the side-effect is skipped/run based on records, without driving the full `run_trigger` subprocess flow. (Driving `run_trigger` end-to-end to reach line 672 needs heavy subprocess/github mocking; extracting the gate into a one-line classmethod is the cleaner, deterministic way to prove the call site is actually guarded.)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_verification_gate.py
"""The P5 advisory gate blocks the PR side-effect only on a failed claim."""

from app.db import verification_records as vr
from app.services.execution_service import _verification_pr_gate


def _make_execution(execution_id: str = "exec-1") -> None:
    from app.db.execution_logs import create_execution_log

    create_execution_log(
        execution_id=execution_id,
        trigger_id="bot-pr-review",
        trigger_type="manual",
        started_at="2026-06-10T00:00:00",
        prompt="p",
        backend_type="claude",
        command="echo hi",
    )


def test_gate_allows_when_no_records():
    _make_execution()
    assert _verification_pr_gate("exec-1") is True


def test_gate_allows_when_only_passed():
    _make_execution()
    vr.record_verification("exec-1", "lint", status="passed")
    assert _verification_pr_gate("exec-1") is True


def test_gate_blocks_when_a_claim_failed():
    _make_execution()
    vr.record_verification("exec-1", "no high-sev CVEs", status="failed")
    assert _verification_pr_gate("exec-1") is False


def test_call_site_runs_side_effect_when_gate_allows():
    """_maybe_auto_resolve_and_pr (used by run_trigger at :672) invokes the
    side-effect when no claim failed."""
    from unittest.mock import patch

    from app.services.execution_service import ExecutionService

    _make_execution()
    with patch("app.services.execution_service.auto_resolve_and_pr") as m:
        ExecutionService._maybe_auto_resolve_and_pr("exec-1", {"id": "t"}, {"r": "x"}, "out")
    m.assert_called_once_with({"id": "t"}, {"r": "x"}, "out")


def test_call_site_skips_side_effect_when_a_claim_failed():
    """The wiring is real: a failed verification record skips the PR side-effect."""
    from unittest.mock import patch

    from app.services.execution_service import ExecutionService

    _make_execution()
    vr.record_verification("exec-1", "no high-sev CVEs", status="failed")
    with patch("app.services.execution_service.auto_resolve_and_pr") as m:
        ExecutionService._maybe_auto_resolve_and_pr("exec-1", {"id": "t"}, {"r": "x"}, "out")
    m.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_verification_gate.py -q`
Expected: FAIL — `ImportError: cannot import name '_verification_pr_gate'` (and `_maybe_auto_resolve_and_pr` missing).

- [ ] **Step 3: Add the gate helper and guard the call site**

In `backend/app/services/execution_service.py`, add the import near the other `..db` imports:

```python
from ..db import verification_records
```

Add the module-level helper (near the top of the module, after imports):

```python
def _verification_pr_gate(execution_id: str) -> bool:
    """Advisory post-hoc gate (Harness-1 Phase 2, P5): allow the downstream
    PR side-effect unless a verification claim is marked 'failed'. Returns
    True to proceed, False to skip. Best-effort: any error allows (fail-open),
    since this must never block a healthy run on a gate-infra hiccup."""
    try:
        if verification_records.has_failed(execution_id):
            logger.warning(
                "Skipping auto-PR for %s: a verification claim failed", execution_id
            )
            return False
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("verification gate check failed for %s: %s", execution_id, e)
    return True
```

Add the gated wrapper as a classmethod on `ExecutionService` (place it near the other private helpers in the class):

```python
    @classmethod
    def _maybe_auto_resolve_and_pr(cls, execution_id, trigger, github_repo_map, scan_output):
        """Run the auto-resolve+PR side-effect unless a verification claim
        failed (Harness-1 Phase 2, P5). The gate is advisory: with no records
        it always proceeds."""
        if _verification_pr_gate(execution_id):
            auto_resolve_and_pr(trigger, github_repo_map, scan_output)
```

At the call site (≈ line 672), replace the bare call with the gated classmethod:

```python
                    scan_output = ExecutionLogService.get_stdout_log(execution_id)
                    cls._maybe_auto_resolve_and_pr(
                        execution_id, trigger, github_repo_map, scan_output
                    )
```

`run_trigger` is a `@classmethod`, so `cls` and `execution_id` are both in scope at line 672 (confirmed). If the enclosing method is not a classmethod in the version you see, call `ExecutionService._maybe_auto_resolve_and_pr(...)` explicitly.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_verification_gate.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Run execution_service regression check**

Run: `cd backend && uv run pytest tests/test_execution_service.py -q`
Expected: PASS (no regressions).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/execution_service.py backend/tests/test_verification_gate.py
git commit -m "feat(harness): advisory PR gate on failed verification (Phase 2 P5)"
```

---

## Task 8: P5 — Litestar verification router (read + write)

**Files:**
- Create: `backend/app_litestar/routes/verification.py`
- Modify: the Litestar app route registration (where other routers like `quality_ratings_router` are registered — search `quality_ratings_router` to find the import + `route_handlers`/`Router` aggregation site)
- Test: `backend/tests/test_litestar_verification_routes.py`

- [ ] **Step 1: Find the router registration site**

Run: `cd backend && grep -rn "quality_ratings_router" app_litestar/`
Expected: an import in the app/router aggregation module and its inclusion in `route_handlers`. Register `verification_router` the same way.

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/test_litestar_verification_routes.py
"""GET/POST verification records over the Litestar app (Phase 2 P5)."""

import os

os.environ.setdefault("AGENTED_LITESTAR_SKIP_STARTUP", "1")

from litestar.testing import TestClient

from app.db import verification_records as vr
from app_litestar.main import create_app


def _make_execution(execution_id: str = "exec-1") -> None:
    from app.db.execution_logs import create_execution_log

    create_execution_log(
        execution_id=execution_id,
        trigger_id="bot-pr-review",
        trigger_type="manual",
        started_at="2026-06-10T00:00:00",
        prompt="p",
        backend_type="claude",
        command="echo hi",
    )


def test_get_returns_records():
    _make_execution()
    vr.record_verification("exec-1", "no secrets", status="passed")
    with TestClient(app=create_app()) as client:
        resp = client.get("/api/executions/exec-1/verifications")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["claim"] == "no secrets"


def test_post_records_a_verification():
    _make_execution()
    with TestClient(app=create_app()) as client:
        resp = client.post(
            "/api/executions/exec-1/verifications",
            json={"claim": "lint clean", "status": "passed", "evidence_ref": "ci.log"},
        )
    assert resp.status_code in (200, 201)
    rows = vr.list_verifications("exec-1")
    assert rows[0]["claim"] == "lint clean"
```

Note: confirm the existing route-test convention in `tests/test_litestar_*` (some suites build the app via a shared fixture and may need an API key header). Match whatever `tests/test_litestar_streams.py` or `tests/test_litestar_harness_annotation_routes.py` does for client construction and auth; adjust the two requests above to include the same headers if those suites do.

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_litestar_verification_routes.py -q`
Expected: FAIL — 404 (route not registered) or import error.

- [ ] **Step 4: Write the router**

```python
# backend/app_litestar/routes/verification.py
"""Litestar routes for verification records (Harness-1 Phase 2, P5)."""

from __future__ import annotations

from typing import Any, Optional

import msgspec
from litestar import Router, get, post

from app.db import verification_records
from app.services.verification_service import VerificationService


class VerificationCreate(msgspec.Struct):
    claim: str
    status: str = "pending"
    evidence_ref: Optional[str] = None


@get("/api/executions/{execution_id:str}/verifications", sync_to_thread=True)
def list_verifications(execution_id: str) -> list[dict[str, Any]]:
    return verification_records.list_verifications(execution_id)


@post("/api/executions/{execution_id:str}/verifications", sync_to_thread=True)
def create_verification(execution_id: str, data: VerificationCreate) -> dict[str, Any]:
    rid = VerificationService.record(
        execution_id, data.claim, status=data.status, evidence_ref=data.evidence_ref
    )
    return {"id": rid, "execution_id": execution_id, "claim": data.claim, "status": data.status}


verification_router = Router(path="/", route_handlers=[list_verifications, create_verification])
```

Note: `Router(path="/")` matches the sibling pattern at `quality_ratings.py:60` (the handlers carry absolute paths). Match the decorator/auth style of the sibling routers found in Step 1; if they apply a guard/auth dependency, mirror it.

- [ ] **Step 5: Register the router**

In the same aggregation module found in Step 1, import and add `verification_router`:

```python
from .routes.verification import verification_router  # adjust import path to match siblings
# ... and include verification_router alongside quality_ratings_router in route_handlers
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_litestar_verification_routes.py -q`
Expected: PASS (2 passed).

- [ ] **Step 7: Commit**

```bash
git add backend/app_litestar/routes/verification.py backend/tests/test_litestar_verification_routes.py
# plus the modified router-registration module
git commit -m "feat(harness): Litestar verification records router (Phase 2 P5)"
```

---

## Task 9: Full Phase-2 verification sweep

- [ ] **Step 1: Run all Phase-2 tests together**

Run:
```bash
cd backend && uv run pytest \
  tests/test_harness_evidence_schema.py tests/test_harness_evidence_repo.py tests/test_evidence_ledger_tap.py \
  tests/test_verification_records_schema.py tests/test_verification_records_repo.py \
  tests/test_verification_service.py tests/test_verification_gate.py \
  tests/test_litestar_verification_routes.py -q
```
Expected: ALL PASS.

- [ ] **Step 2: Regression sweep on touched subsystems**

Run:
```bash
cd backend && uv run pytest \
  tests/test_execution_service.py tests/test_litestar_streams.py \
  tests/test_execution_log_checkpoint.py tests/test_harness_state_repo.py -q
```
Expected: ALL PASS (Phase 1 + streaming + execution untouched).

- [ ] **Step 3: Lint/format**

Run:
```bash
cd backend && uv run ruff format app/db/harness_evidence.py app/db/schema/_harness_evidence.py app/db/verification_records.py app/db/schema/_verification_records.py app/services/verification_service.py app/services/streaming_helper.py app/services/execution_service.py app_litestar/routes/verification.py
cd backend && uv run ruff check app/db/harness_evidence.py app/db/verification_records.py app/services/verification_service.py app_litestar/routes/verification.py
```
Expected: format clean, `All checks passed!`.

- [ ] **Step 4: Final commit (if format changed anything)**

```bash
git add -A backend/
git commit -m "chore(harness): ruff format Phase 2 evidence + verification"
```

---

## Self-Review notes (author)
- **Spec coverage:** P3 schema (T1), P3 repo (T2), P3 tap (T3); P5 schema (T4), P5 repo (T5), P5 write API (T6), P5 gate (T7), P5 router (T8); verification sweep (T9). All spec sections covered.
- **Type consistency:** `record_tool_use(...)->seq:int`, `list_evidence`/`count_evidence`, `record_verification(...)->id:int`, `has_failed(...)->bool`, `VerificationService.record(...)`, `_verification_pr_gate(...)->bool`, `_record_tool_use_evidence(session_id, super_agent_id, event)` — names consistent across tasks.
- **Known confirm-at-execution points (flagged in-task, not placeholders):** exact `_session_id`/`_super_agent_id` locals at the second tap site; the `execution_id` local name at `execution_service.py:672`; the sibling-router auth/registration convention in Task 8. Each task says exactly how to confirm.
