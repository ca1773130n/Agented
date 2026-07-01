"""Session fork onto a separate independent run (Phase 25, 25-03).

fork_to_run composes create_branch (immutable parent snapshot) + a fresh seeded
create_session. The parent conversation's messages JSON must be byte-identical
before/after; the child run gets a NEW psess id and diverges without leaking to
the parent.
"""

import json

from app.db.agents import (
    create_agent_conversation,
    get_agent_conversation,
    update_agent_conversation,
)
from app.services.conversation_branch_service import ConversationBranchService


def _seed_conversation(n=3):
    conv_id = create_agent_conversation()
    messages = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"message-{i}"} for i in range(n)
    ]
    update_agent_conversation(conv_id, messages=json.dumps(messages))
    return conv_id


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
