"""Phase 17-06: gated session-completion auto-import provenance (P9).

Covers the SECURITY house rule: only Agented-driven sessions auto-bind their
session-scaffolded `.claude/` primitives; foreign/unknown session kinds import
NOTHING (fail-closed). Provenance (sha256 + source session id) is recorded, and
a second identical call is a no-op.
"""

from __future__ import annotations

import hashlib

import pytest

from app.db import create_project, get_origin
from app.db.subagents import get_subagent_by_name, list_subagents
from app.services.forge_session_import import on_session_complete_import

_SUBAGENT_BODY = """---
name: foo-reviewer
description: A focused code-review delegate.
---

# Foo Reviewer

You review diffs for correctness and security.
"""


@pytest.fixture
def project_with_claude(isolated_db, tmp_path):
    """Project whose local_path is a real dir holding a session-scaffolded
    `.claude/agents/foo-reviewer.md` plus an operator/foreign file."""
    del isolated_db
    project_id = create_project(name="import-test", description="fixture", local_path=str(tmp_path))
    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "foo-reviewer.md").write_text(_SUBAGENT_BODY)
    # An operator/foreign file in an unrelated .claude subdir — must NOT import.
    other = tmp_path / ".claude" / "settings.json"
    other.write_text('{"operator": true}')
    return project_id, tmp_path


def test_agented_session_imports_subagent(project_with_claude):
    project_id, root = project_with_claude

    # Capture the source hash BEFORE the handler runs — materialization
    # rewrites the file in place (with manifest markers), so reading it back
    # afterwards would not reflect the imported bytes.
    raw = (root / ".claude" / "agents" / "foo-reviewer.md").read_bytes()
    expected_hash = hashlib.sha256(raw).hexdigest()

    on_session_complete_import(
        session_kind="project_session",
        session_id="sess-abc123",
        project_id=project_id,
        status="completed",
        output=None,
    )

    # The subagent was created + is project-scoped.
    sub = get_subagent_by_name("foo-reviewer")
    assert sub is not None
    assert sub["project_id"] == project_id

    # Provenance: sha256 of the source bytes + the source session id.
    origin = get_origin("foo-reviewer", "subagent")
    assert origin is not None
    assert origin["origin_hash"] == expected_hash
    assert origin["source_session_id"] == "sess-abc123"

    # Only one subagent imported (the operator settings.json was ignored).
    assert len(list_subagents(project_id)) == 1


def test_foreign_session_does_not_import(project_with_claude):
    project_id, _root = project_with_claude

    # A foreign kind (external clone-import) — gate must fail closed.
    on_session_complete_import(
        session_kind="external_clone_import",
        session_id="sess-foreign",
        project_id=project_id,
        status="completed",
        output=None,
    )

    assert get_subagent_by_name("foo-reviewer") is None
    assert get_origin("foo-reviewer", "subagent") is None
    assert list_subagents(project_id) == []


def test_unknown_kind_fails_closed(project_with_claude):
    project_id, _root = project_with_claude

    on_session_complete_import(
        session_kind="something_unrecognized",
        session_id="sess-x",
        project_id=project_id,
        status="completed",
        output=None,
    )
    assert get_subagent_by_name("foo-reviewer") is None


def test_import_idempotent(project_with_claude):
    project_id, _root = project_with_claude

    on_session_complete_import(
        session_kind="goal_loop",
        session_id="sess-1",
        project_id=project_id,
        status="completed",
        output=None,
    )
    first_count = len(list_subagents(project_id))
    first_origin = get_origin("foo-reviewer", "subagent")
    assert first_count == 1
    assert first_origin is not None

    # Second identical call — unchanged file (same hash) → no new import.
    on_session_complete_import(
        session_kind="goal_loop",
        session_id="sess-2",
        project_id=project_id,
        status="completed",
        output=None,
    )
    assert len(list_subagents(project_id)) == 1
    # Origin row unchanged (still the first hash; session id not refreshed
    # because the file was skipped as unchanged).
    second_origin = get_origin("foo-reviewer", "subagent")
    assert second_origin["origin_hash"] == first_origin["origin_hash"]
    assert second_origin["source_session_id"] == "sess-1"


def test_failed_session_does_not_import(project_with_claude):
    """Only successful sessions auto-bind — a failed session may leave
    half-written scaffolds behind (same gate as the tesserae exporter)."""
    project_id, _root = project_with_claude

    on_session_complete_import(
        session_kind="goal_loop",
        session_id="sess-fail",
        project_id=project_id,
        status="failed",
        output=None,
    )
    assert get_subagent_by_name("foo-reviewer") is None
    assert list_subagents(project_id) == []


def test_changed_file_reimported_in_place(isolated_db, tmp_path):
    """A changed source file (stem != frontmatter name, so the scaffolded file
    stays outside the manifest) is re-imported by UPDATING the existing row —
    not a duplicate create that would trip the global UNIQUE name constraint —
    and its origin row is refreshed. Regression: the old code warn-skipped the
    IntegrityError forever, so changed files never re-imported."""
    del isolated_db
    project_id = create_project(
        name="reimport-test", description="fixture", local_path=str(tmp_path)
    )
    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    src = agents / "scaffolded-reviewer.md"
    src.write_text("---\nname: foo-reviewer\n---\n\nv1 body\n")

    on_session_complete_import(
        session_kind="project_session",
        session_id="sess-1",
        project_id=project_id,
        status="completed",
        output=None,
    )
    v1 = get_subagent_by_name("foo-reviewer")
    assert v1 is not None and "v1 body" in v1["content"]
    origin_1 = get_origin("foo-reviewer", "subagent")

    src.write_text("---\nname: foo-reviewer\n---\n\nv2 body\n")
    on_session_complete_import(
        session_kind="project_session",
        session_id="sess-2",
        project_id=project_id,
        status="completed",
        output=None,
    )

    v2 = get_subagent_by_name("foo-reviewer")
    assert v2["id"] == v1["id"], "re-import must update in place, not recreate"
    assert "v2 body" in v2["content"]
    assert len(list_subagents(project_id)) == 1
    origin_2 = get_origin("foo-reviewer", "subagent")
    assert origin_2["origin_hash"] != origin_1["origin_hash"]
    assert origin_2["source_session_id"] == "sess-2"


def test_foreign_project_name_not_hijacked(isolated_db, tmp_path):
    """A scaffolded file whose subagent name is owned by ANOTHER project must
    never update that row — cross-project hijack fails closed."""
    from app.db.subagents import create_subagent

    del isolated_db
    other_project = create_project(name="other-proj", description="fixture")
    create_subagent(name="foo-reviewer", content="other body", project_id=other_project)

    project_id = create_project(name="victim-test", description="fixture", local_path=str(tmp_path))
    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "foo-reviewer.md").write_text(_SUBAGENT_BODY)

    on_session_complete_import(
        session_kind="goal_loop",
        session_id="sess-h",
        project_id=project_id,
        status="completed",
        output=None,
    )

    row = get_subagent_by_name("foo-reviewer")
    assert row["content"] == "other body"
    assert row["project_id"] == other_project
    assert get_origin("foo-reviewer", "subagent") is None
    assert list_subagents(project_id) == []
