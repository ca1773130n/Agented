"""Session fork onto a separate independent run (Phase 25, 25-03).

fork_to_run composes create_branch (immutable parent snapshot) + a fresh seeded
create_session. The parent conversation's messages JSON must be byte-identical
before/after; the child run gets a NEW psess id and diverges without leaking to
the parent.
"""

import json

import pytest
from litestar.exceptions import PermissionDeniedException

from app.db.agents import (
    create_agent_conversation,
    get_agent_conversation,
    update_agent_conversation,
)
from app.db.connection import get_connection
from app.services.conversation_branch_service import ConversationBranchService
from app_litestar.auth import Caller
from app_litestar.routes.conversation_branches import fork_session


def _seed_conversation(n=3, user_id=None):
    conv_id = create_agent_conversation(user_id=user_id)
    messages = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"message-{i}"} for i in range(n)
    ]
    update_agent_conversation(conv_id, messages=json.dumps(messages))
    return conv_id


def _seed_project(project_id="proj-fork", owner=None):
    with get_connection() as conn:
        if owner is None:
            conn.execute("INSERT INTO projects (id, name) VALUES (?, ?)", (project_id, "F"))
        else:
            conn.execute(
                "INSERT INTO projects (id, name, user_id) VALUES (?, ?, ?)",
                (project_id, "F", owner),
            )
        conn.commit()
    return project_id


def _caller(user_id, role="member"):
    return Caller(api_key="k", role=role, user_id=user_id, auth_method="api_key")


def test_fork_to_run_returns_branch_and_session(isolated_db, monkeypatch):
    conv_id = _seed_conversation(3)
    parent_before = get_agent_conversation(conv_id)["messages"]

    calls = {}

    def _fake_create_session(**kwargs):
        calls.update(kwargs)
        return "psess-forked1"

    monkeypatch.setattr(
        "app.services.project_session_manager.ProjectSessionManager.create_session",
        staticmethod(_fake_create_session),
    )

    result = ConversationBranchService.fork_to_run(
        conv_id, fork_message_index=2, project_id="proj-x", cwd="/tmp/x"
    )

    # A new branch id AND a new run id are returned.
    assert result["branch_id"]
    assert result["session_id"] == "psess-forked1"

    # create_session was called for the right project with a seed referencing the
    # forked messages (resume-style).
    assert calls["project_id"] == "proj-x"
    seed_blob = " ".join(str(x) for x in calls["cmd"])
    assert "message-0" in seed_blob and "message-2" in seed_blob
    # A brand-new independent run — pipe transport, not a cloned process.
    assert calls["use_pty"] is False

    # Parent conversation messages JSON is byte-identical (immutable).
    parent_after = get_agent_conversation(conv_id)["messages"]
    assert parent_after == parent_before


def test_child_divergence_does_not_leak_to_parent(isolated_db, monkeypatch):
    conv_id = _seed_conversation(2)
    parent_before = get_agent_conversation(conv_id)["messages"]

    monkeypatch.setattr(
        "app.services.project_session_manager.ProjectSessionManager.create_session",
        staticmethod(lambda **kwargs: "psess-forked2"),
    )

    result = ConversationBranchService.fork_to_run(
        conv_id, fork_message_index=1, project_id="proj-y", cwd="/tmp/y"
    )
    branch_id = result["branch_id"]

    # Diverge the CHILD branch — append a message to the fork.
    ConversationBranchService.add_message(branch_id, "user", "child-only divergence")

    # Parent conversation is untouched by the child's divergence.
    parent_after = get_agent_conversation(conv_id)["messages"]
    assert parent_after == parent_before
    assert "child-only divergence" not in parent_after


# ---------------------------------------------------------------------------
# #3 — fork route enforces ownership of the source conversation/project
# ---------------------------------------------------------------------------


def _fork_body(conv_id, idx=1):
    return {"conversation_id": conv_id, "fork_message_index": idx}


def _make_owner(email="owner@example.com"):
    # projects.user_id + agent_conversations.user_id FK to users(id), so the
    # owner must be a real user row.
    from app.db.users import create_user

    return create_user(email)


class TestForkOwnershipGate:
    def test_owner_forks_ok(self, isolated_db, monkeypatch):
        owner = _make_owner()
        proj = _seed_project(owner=owner)
        conv_id = _seed_conversation(3, user_id=owner)
        monkeypatch.setattr(
            "app.services.project_session_manager.ProjectSessionManager.create_session",
            staticmethod(lambda **kwargs: "psess-forked-owned"),
        )
        result = fork_session.fn(proj, "sid", _fork_body(conv_id, 2), _caller(owner))
        assert result["session_id"] == "psess-forked-owned"
        assert result["branch_id"]

    def test_non_owner_fork_forbidden(self, isolated_db):
        owner = _make_owner()
        proj = _seed_project(owner=owner)
        conv_id = _seed_conversation(3, user_id=owner)
        with pytest.raises(PermissionDeniedException):
            fork_session.fn(proj, "sid", _fork_body(conv_id), _caller("intruder"))

    def test_unowned_conversation_forbidden_for_non_admin(self, isolated_db):
        # Fail CLOSED: an unattributed (NULL user_id) conversation cannot be
        # forked by an arbitrary authenticated caller.
        proj = _seed_project(owner=None)
        conv_id = _seed_conversation(3, user_id=None)
        with pytest.raises(PermissionDeniedException):
            fork_session.fn(proj, "sid", _fork_body(conv_id), _caller("anyone"))

    def test_admin_can_fork_any(self, isolated_db, monkeypatch):
        owner = _make_owner()
        proj = _seed_project(owner=owner)
        conv_id = _seed_conversation(3, user_id=owner)
        monkeypatch.setattr(
            "app.services.project_session_manager.ProjectSessionManager.create_session",
            staticmethod(lambda **kwargs: "psess-forked-admin"),
        )
        result = fork_session.fn(proj, "sid", _fork_body(conv_id, 2), _caller("root", role="admin"))
        assert result["session_id"] == "psess-forked-admin"
