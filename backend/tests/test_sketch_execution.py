"""Delegation / mention cwd + backend-derivation tests (19-03).

Phase 19-03 fixes three cwd=None / backend='claude' bugs:

* ``execute_delegate`` must resolve the project workspace
  (``ProjectWorkspaceService.resolve_working_directory``) and pass it as
  the stream cwd instead of None.
* ``_scan_mentions_and_notify`` must do the same for auto-launched
  sessions.
* ``grd_routes.project_chat`` must pass the resolved cwd and derive the
  backend from the SuperAgent's ``backend_type`` (never the literal
  ``"claude"``).

When ``resolve_working_directory`` raises ``ValueError`` the sites
degrade to cwd=None rather than crashing the turn.

These tests monkeypatch the workspace resolver and the streaming
launcher to spies so we can assert the forwarded cwd/backend without
spawning a real subprocess or cloning a repo.
"""

from __future__ import annotations

from typing import Any

import pytest

import app.services.sketch_execution_service as ses


@pytest.fixture
def capture_stream(monkeypatch):
    """Replace ``run_streaming_response`` with a spy that records kwargs."""
    calls: list[dict[str, Any]] = []

    def _spy(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(ses, "run_streaming_response", _spy)
    return calls


@pytest.fixture
def _stub_session(monkeypatch):
    """Stub the session service so no real session machinery runs."""
    monkeypatch.setattr(
        ses.SuperAgentSessionService,
        "get_or_create_session",
        staticmethod(lambda *a, **k: "sess-1"),
    )
    monkeypatch.setattr(
        ses.SuperAgentSessionService,
        "send_message",
        staticmethod(lambda *a, **k: None),
    )


# --------------------------------------------------------------------------
# execute_delegate
# --------------------------------------------------------------------------


def test_execute_delegate_passes_resolved_cwd(monkeypatch, capture_stream, _stub_session):
    monkeypatch.setattr(ses, "get_sketch", lambda _sid: {"project_id": "proj-x"})
    monkeypatch.setattr(ses, "get_super_agent", lambda _id: {"backend_type": "claude"})
    monkeypatch.setattr(
        ses.ProjectWorkspaceService,
        "resolve_working_directory",
        staticmethod(lambda _pid: "/clones/proj-x"),
    )
    # No-op the post-launch bookkeeping the delegate would touch.
    monkeypatch.setattr(ses, "_mark_delegation_status", lambda *a, **k: None)
    monkeypatch.setattr(ses, "_check_all_delegations_complete", lambda *a, **k: None)

    ses.execute_delegate(
        sketch_id="sk-1",
        super_agent_id="sa-1",
        task_content="do the thing",
        leader_agent_id="leader-1",
    )

    assert len(capture_stream) == 1
    assert capture_stream[0]["cwd"] == "/clones/proj-x"


def test_execute_delegate_degrades_on_value_error(monkeypatch, capture_stream, _stub_session):
    """ValueError from the resolver must not bubble; cwd falls back to None."""
    monkeypatch.setattr(ses, "get_sketch", lambda _sid: {"project_id": "proj-x"})
    monkeypatch.setattr(ses, "get_super_agent", lambda _id: {"backend_type": "codex"})

    def _boom(_pid):
        raise ValueError("workspace_root not configured")

    monkeypatch.setattr(
        ses.ProjectWorkspaceService,
        "resolve_working_directory",
        staticmethod(_boom),
    )
    monkeypatch.setattr(ses, "_mark_delegation_status", lambda *a, **k: None)
    monkeypatch.setattr(ses, "_check_all_delegations_complete", lambda *a, **k: None)

    # Should not raise.
    ses.execute_delegate(
        sketch_id="sk-1",
        super_agent_id="sa-1",
        task_content="do the thing",
        leader_agent_id="leader-1",
    )

    assert len(capture_stream) == 1
    assert capture_stream[0]["cwd"] is None


# --------------------------------------------------------------------------
# _scan_mentions_and_notify
# --------------------------------------------------------------------------


def test_scan_mentions_passes_resolved_cwd(monkeypatch, capture_stream):
    """The auto-launch path forwards the resolved project cwd."""
    monkeypatch.setattr(ses, "get_sketch", lambda _sid: {"project_id": "proj-x", "title": "T"})
    monkeypatch.setattr(
        ses.ProjectWorkspaceService,
        "resolve_working_directory",
        staticmethod(lambda _pid: "/clones/proj-x"),
    )
    # Two agents: the author (skipped) and one mentionable target.
    monkeypatch.setattr(
        ses,
        "get_all_super_agents",
        lambda: [
            {"id": "from-1", "name": "Leader"},
            {"id": "to-1", "name": "Seraph", "backend_type": "claude"},
        ],
        raising=False,
    )
    # The function imports get_all_super_agents lazily; patch the source too.
    import app.db.super_agents as sa_mod

    monkeypatch.setattr(
        sa_mod,
        "get_all_super_agents",
        lambda: [
            {"id": "from-1", "name": "Leader"},
            {"id": "to-1", "name": "Seraph", "backend_type": "claude"},
        ],
    )
    monkeypatch.setattr(
        ses.SuperAgentSessionService,
        "get_or_create_session",
        staticmethod(lambda *a, **k: "sess-2"),
    )
    monkeypatch.setattr(
        ses.SuperAgentSessionService,
        "send_message",
        staticmethod(lambda *a, **k: None),
    )
    monkeypatch.setattr(
        ses.AgentMessageBusService,
        "send_message",
        staticmethod(lambda *a, **k: None),
    )

    ses._scan_mentions_and_notify(
        "sk-1", "from-1", "- **Seraph**: deep dive into the memory subsystem"
    )

    assert len(capture_stream) == 1
    assert capture_stream[0]["cwd"] == "/clones/proj-x"


# --------------------------------------------------------------------------
# project_chat (grd_routes) backend derivation + cwd
# --------------------------------------------------------------------------


def test_project_chat_derives_backend_and_cwd(monkeypatch):
    """project_chat must forward the SA's backend_type (not 'claude') and a
    resolved cwd to the stream launcher."""
    from app_litestar.routes import grd_routes as gr

    fn = gr.project_chat.fn if hasattr(gr.project_chat, "fn") else gr.project_chat

    captured: dict[str, Any] = {}

    # Project + manager resolution stubs.
    monkeypatch.setattr(gr, "_ensure_project", lambda pid: {"id": pid})
    monkeypatch.setattr(gr, "_resolve_manager_agent", lambda project: "sa-mgr")
    monkeypatch.setattr(
        gr, "get_super_agent", lambda _id: {"id": "sa-mgr", "backend_type": "codex"}
    )
    monkeypatch.setattr(
        gr.ProjectWorkspaceService,
        "resolve_working_directory",
        staticmethod(lambda _pid: "/clones/proj-x"),
    )

    # Session + chat-state stubs (imported lazily inside the handler).
    from app.services.chat_state_service import ChatStateService
    from app.services.super_agent_session_service import SuperAgentSessionService

    monkeypatch.setattr(
        SuperAgentSessionService, "create_session", staticmethod(lambda *a, **k: ("sess-9", None))
    )
    monkeypatch.setattr(
        SuperAgentSessionService, "send_message", staticmethod(lambda *a, **k: (True, None))
    )
    monkeypatch.setattr(
        SuperAgentSessionService,
        "assemble_system_prompt",
        staticmethod(lambda *a, **k: "SYS"),
    )
    monkeypatch.setattr(
        SuperAgentSessionService,
        "get_session_state",
        staticmethod(lambda *a, **k: {"conversation_log": []}),
    )
    monkeypatch.setattr(
        SuperAgentSessionService, "add_assistant_message", staticmethod(lambda *a, **k: None)
    )
    monkeypatch.setattr(ChatStateService, "init_session", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(ChatStateService, "push_delta", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(ChatStateService, "push_status", staticmethod(lambda *a, **k: None))

    import app.services.project_chat_service as pcs

    monkeypatch.setattr(pcs, "build_project_context", lambda *a, **k: "CTX")
    monkeypatch.setattr(pcs, "execute_plan_actions", lambda *a, **k: [])

    # Routing: force the non-CLI (token) branch so we inspect stream_llm_response.
    import app.services.cli_agent_runner_service as cli

    monkeypatch.setattr(cli, "should_route_via_cli_agent", lambda *a, **k: False)

    import app.services.conversation_streaming as cs

    def _spy_stream(messages, **kwargs):
        captured["backend"] = kwargs.get("backend")
        captured["cwd"] = kwargs.get("cwd")
        return iter([])

    monkeypatch.setattr(cs, "stream_llm_response", _spy_stream)

    # Run the background work synchronously instead of spawning a thread.
    import app_litestar.routes.grd_routes as grmod

    class _SyncThread:
        def __init__(self, target=None, daemon=None, **kw):
            self._target = target

        def start(self):
            self._target()

    monkeypatch.setattr(grmod.threading, "Thread", _SyncThread)

    result = fn(project_id="proj-x", data={"content": "hello"})

    assert result["status"] == "streaming"
    assert captured["backend"] == "codex"
    assert captured["backend"] != "claude"
    assert captured["cwd"] == "/clones/proj-x"
