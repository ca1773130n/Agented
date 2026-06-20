"""Sketch → SA session project_id propagation (v0.7.40).

Before v0.7.40, ``execute_sketch`` reused
``SuperAgentSessionService.get_or_create_session(sa_id)`` without
passing the sketch's ``project_id``. The resulting
``super_agent_sessions`` row had ``project_id = NULL``, so the
project's Sessions tab never surfaced the work — and the user reported
that /sketch work "disappears" from the project page.

These tests pin three things:

* New ``get_or_create_session(project_id=...)`` keyword stamps the
  project on a freshly-created session.
* When an existing session for the same SA already exists but has
  no ``project_id``, it gets backfilled in-place.
* When a session already has a ``project_id``, a different
  ``project_id`` does NOT overwrite it (one session, one project).
"""

from __future__ import annotations

from typing import Any

import pytest

from app.db.super_agents import (
    create_super_agent,
    get_sessions_for_project,
)
from app.services.super_agent_session_service import SuperAgentSessionService


@pytest.fixture(autouse=True)
def _reset_session_service_state():
    """``SuperAgentSessionService`` keeps an in-memory dict of active
    sessions on the class. Between tests in this module that state
    needs to be wiped or sessions from one test leak into the next and
    break the "create fresh session" path. The ``isolated_db`` fixture
    only resets the SQLite file."""
    SuperAgentSessionService._active_sessions.clear()
    yield
    SuperAgentSessionService._active_sessions.clear()


def _seed_project(project_id: str, name: str = "test") -> None:
    """Insert a project row so ``super_agent_sessions.project_id`` FK
    constraints are satisfied. The session schema has
    ``project_id TEXT REFERENCES projects(id) ON DELETE SET NULL`` —
    inserting a session with a non-existent ``project_id`` would
    silently return None (IntegrityError swallowed) and look like
    "create_session failed" in the test output."""
    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, created_at, updated_at) "
            "VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (project_id, name),
        )
        conn.commit()


def _set_session_project_id(session_id: str, value: str | None) -> None:
    """Test helper — directly stamp a value on the DB row."""
    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute(
            "UPDATE super_agent_sessions SET project_id = ? WHERE id = ?",
            (value, session_id),
        )
        conn.commit()


def _get_session_project_id(session_id: str) -> Any:
    from app.db.connection import get_connection

    with get_connection() as conn:
        row = conn.execute(
            "SELECT project_id FROM super_agent_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
    return row["project_id"] if row else None


def test_new_session_stamps_project_id(isolated_db):
    _seed_project("proj-xyz")
    sa_id = create_super_agent(name="planner")
    sess = SuperAgentSessionService.get_or_create_session(sa_id, project_id="proj-xyz")
    assert _get_session_project_id(sess) == "proj-xyz"
    matches = get_sessions_for_project("proj-xyz")
    assert any(s["id"] == sess for s in matches)


def test_orphan_session_gets_project_id_backfilled(isolated_db):
    """Existing active session for the SA without a project_id is
    updated when the next call passes one. Pre-v0.7.40, that update
    silently never happened and the session stayed invisible to the
    project Sessions tab forever."""
    _seed_project("proj-xyz")
    sa_id = create_super_agent(name="planner")
    sess = SuperAgentSessionService.get_or_create_session(sa_id)
    assert _get_session_project_id(sess) is None  # baseline

    # Same SA, same call shape, but now we have a project context:
    sess2 = SuperAgentSessionService.get_or_create_session(sa_id, project_id="proj-xyz")
    assert sess2 == sess  # session reused, not recreated
    assert _get_session_project_id(sess) == "proj-xyz"
    assert any(s["id"] == sess for s in get_sessions_for_project("proj-xyz"))


def test_existing_project_id_is_not_overwritten(isolated_db):
    """A session that already belongs to project A doesn't get
    silently moved to project B on the next call."""
    _seed_project("proj-A")
    _seed_project("proj-B")
    sa_id = create_super_agent(name="planner")
    sess = SuperAgentSessionService.get_or_create_session(sa_id, project_id="proj-A")
    sess2 = SuperAgentSessionService.get_or_create_session(sa_id, project_id="proj-B")
    assert sess2 == sess
    assert _get_session_project_id(sess) == "proj-A"


def test_session_without_project_arg_still_works(isolated_db):
    """Back-compat: callers that don't pass ``project_id`` still get a
    valid session (just without a project association). Mirrors the
    pre-v0.7.40 call shape that every non-sketch site uses."""
    sa_id = create_super_agent(name="planner")
    sess = SuperAgentSessionService.get_or_create_session(sa_id)
    assert _get_session_project_id(sess) is None


def test_migration_118_backfills_historical_orphan_sessions(isolated_db):
    """Migration 118 walks ``sketches`` and stamps each sketch's
    ``project_id`` onto the SA session referenced in its
    ``routing_json``. Pin that pass so a future schema rename doesn't
    silently break the backfill.
    """
    import json as _json

    _seed_project("proj-fix")
    sa_id = create_super_agent(name="planner")
    sess = SuperAgentSessionService.get_or_create_session(sa_id)
    assert _get_session_project_id(sess) is None

    # Insert a sketch that historically routed to this orphan session.
    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO sketches (id, title, content, status, project_id, routing_json) "
            "VALUES ('sk-orphan', 't', '', 'completed', 'proj-fix', ?)",
            (
                _json.dumps(
                    {
                        "target_type": "super_agent",
                        "target_id": sa_id,
                        "session_id": sess,
                        "super_agent_id": sa_id,
                    }
                ),
            ),
        )
        conn.commit()

    # Re-run the migration body — idempotent.
    from app.db.migrations.v07_features import (
        _migrate_118_backfill_sketch_session_project_id,
    )

    with get_connection() as conn:
        # SQLite Row factory is enabled by the connection helper, so the
        # migration's ``row["project_id"]`` access works as-is.
        _migrate_118_backfill_sketch_session_project_id(conn)
        conn.commit()

    assert _get_session_project_id(sess) == "proj-fix"

    # Running it again is a no-op (idempotent).
    with get_connection() as conn:
        _migrate_118_backfill_sketch_session_project_id(conn)
        conn.commit()
    assert _get_session_project_id(sess) == "proj-fix"
