"""Tests for chat_mode and psa- resolution in chat streaming.

Covers:
1. _resolve_session with psa- prefix — instance lookup, backend resolution, chat_mode, cwd
2. stream_llm_response work-mode routing (forces CLI subprocess with cwd)
3. assemble_system_prompt with instance_id — project context injection
4. List sessions endpoint with psa- prefix — queries by instance_id
5. run_streaming_response passes cwd, chat_mode, instance_id through
6. _stream_via_cli and _stream_via_opencode_cli accept cwd parameter
7. create_session and restore_active_sessions store instance_id in memory
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from app.db.project_sa_instances import create_project_sa_instance, get_project_sa_instance
from app.db.projects import create_project
from app.db.super_agents import (
    add_super_agent_session,
    create_super_agent,
    get_sessions_for_instance,
)
from app.services.super_agent_session_service import SuperAgentSessionService

_STREAM_MOCK = "app.services.conversation_streaming.stream_llm_response"


@pytest.fixture(autouse=True)
def _reset_sessions():
    SuperAgentSessionService._active_sessions.clear()
    yield
    SuperAgentSessionService._active_sessions.clear()


def _setup(isolated_db, chat_mode="management", worktree_path=None):
    """Create project, SA, and instance. Return (proj_id, sa_id, psa_id)."""
    proj_id = create_project(name="Chat Mode Project", description="Test project")
    sa_id = create_super_agent(name="Chat SA", backend_type="claude")
    psa_id = create_project_sa_instance(
        proj_id, sa_id, default_chat_mode=chat_mode, worktree_path=worktree_path
    )
    return proj_id, sa_id, psa_id


def _create_sa_and_session(client, backend_type="claude"):
    """Helper: create a super agent and session via API."""
    resp = client.post(
        "/admin/super-agents/",
        json={"name": "Test Agent", "description": "test", "backend_type": backend_type},
    )
    assert resp.status_code == 201
    sa_id = resp.get_json()["super_agent_id"]
    resp = client.post(f"/admin/super-agents/{sa_id}/sessions")
    assert resp.status_code == 201
    sess_id = resp.get_json()["session_id"]
    return sa_id, sess_id


# ===========================================================================
# _resolve_session with psa- prefix
# ===========================================================================


class TestResolvePsaPrefix:
    def test_resolve_psa_returns_instance_and_chat_mode(self, client, isolated_db):
        """_resolve_session with psa- prefix resolves instance and default chat_mode."""
        from app.routes.super_agent_chat import _resolve_session

        proj_id, sa_id, psa_id = _setup(isolated_db, chat_mode="work", worktree_path="/tmp/wt")

        # Create a session linked to this instance
        session_id, _ = SuperAgentSessionService.create_session(sa_id, instance_id=psa_id)

        result = _resolve_session({}, psa_id, session_id)

        assert "error_response" not in result
        assert result["instance"] is not None
        assert result["instance"]["id"] == psa_id
        assert result["chat_mode"] == "work"
        assert result["cwd"] == "/tmp/wt"
        assert result["effective_backend"] == "claude"

    def test_resolve_psa_management_mode_no_cwd(self, client, isolated_db):
        """_resolve_session with psa- prefix in management mode sets cwd=None."""
        from app.routes.super_agent_chat import _resolve_session

        proj_id, sa_id, psa_id = _setup(
            isolated_db, chat_mode="management", worktree_path="/tmp/wt"
        )
        session_id, _ = SuperAgentSessionService.create_session(sa_id, instance_id=psa_id)

        result = _resolve_session({}, psa_id, session_id)

        assert result["chat_mode"] == "management"
        assert result["cwd"] is None  # management mode does not set cwd

    def test_resolve_psa_explicit_chat_mode_overrides_default(self, client, isolated_db):
        """Explicit chat_mode in request data overrides instance default."""
        from app.routes.super_agent_chat import _resolve_session

        proj_id, sa_id, psa_id = _setup(
            isolated_db, chat_mode="management", worktree_path="/tmp/wt"
        )
        session_id, _ = SuperAgentSessionService.create_session(sa_id, instance_id=psa_id)

        result = _resolve_session({"chat_mode": "work"}, psa_id, session_id)

        assert result["chat_mode"] == "work"
        assert result["cwd"] == "/tmp/wt"

    def test_resolve_psa_nonexistent_instance_returns_error(self, client, isolated_db):
        """_resolve_session with nonexistent psa- ID returns error."""
        from app.routes.super_agent_chat import _resolve_session

        sa_id = create_super_agent(name="Orphan SA", backend_type="claude")
        session_id, _ = SuperAgentSessionService.create_session(sa_id)

        result = _resolve_session({}, "psa-nonexist", session_id)
        assert "error_response" in result

    def test_resolve_regular_sa_no_instance(self, client, isolated_db):
        """_resolve_session with regular SA ID sets instance=None."""
        from app.routes.super_agent_chat import _resolve_session

        sa_id = create_super_agent(name="Regular SA", backend_type="claude")
        session_id, _ = SuperAgentSessionService.create_session(sa_id)

        result = _resolve_session({}, sa_id, session_id)

        assert result["instance"] is None
        assert result["chat_mode"] is None
        assert result["cwd"] is None

    def test_resolve_psa_backend_from_template(self, client, isolated_db):
        """psa- resolution uses template SA's backend_type."""
        from app.routes.super_agent_chat import _resolve_session

        proj_id = create_project(name="Backend Test")
        sa_id = create_super_agent(name="OpenCode SA", backend_type="opencode")
        psa_id = create_project_sa_instance(proj_id, sa_id, worktree_path="/tmp/oc")
        session_id, _ = SuperAgentSessionService.create_session(sa_id, instance_id=psa_id)

        result = _resolve_session({}, psa_id, session_id)
        assert result["effective_backend"] == "opencode"


# ===========================================================================
# Chat endpoint with psa- prefix (full route test)
# ===========================================================================


class TestChatEndpointWithPsaPrefix:
    def test_chat_with_psa_passes_cwd_to_streaming(self, client, isolated_db):
        """POST chat with psa- ID passes cwd and chat_mode to streaming."""
        proj_id, sa_id, psa_id = _setup(isolated_db, chat_mode="work", worktree_path="/tmp/work")
        session_id, _ = SuperAgentSessionService.create_session(sa_id, instance_id=psa_id)

        # Init chat state
        from app.services.chat_state_service import ChatStateService

        ChatStateService.init_session(session_id)

        with patch(_STREAM_MOCK) as mock_stream:
            mock_stream.return_value = iter(["ok"])

            resp = client.post(
                f"/admin/super-agents/{psa_id}/sessions/{session_id}/chat",
                json={"content": "hello"},
            )
            assert resp.status_code == 200

            time.sleep(0.3)

            mock_stream.assert_called_once()
            call_kwargs = mock_stream.call_args.kwargs
            assert call_kwargs.get("cwd") == "/tmp/work"
            assert call_kwargs.get("chat_mode") == "work"


# ===========================================================================
# stream_llm_response work-mode routing
# ===========================================================================


class TestWorkModeRouting:
    def test_work_mode_routes_to_cli(self):
        """Work mode with cwd forces _stream_via_cli for claude backend."""
        with (
            patch("app.services.conversation_streaming._stream_via_cli") as mock_cli,
            patch("app.services.conversation_streaming._find_cliproxy", return_value=None),
        ):
            mock_cli.return_value = iter(["response"])

            from app.services.conversation_streaming import stream_llm_response

            chunks = list(
                stream_llm_response(
                    [{"role": "user", "content": "test"}],
                    backend="claude",
                    cwd="/tmp/worktree",
                    chat_mode="work",
                )
            )

            mock_cli.assert_called_once()
            _, kwargs = mock_cli.call_args
            assert kwargs.get("cwd") == "/tmp/worktree"

    def test_work_mode_routes_to_opencode_cli(self):
        """Work mode with opencode backend routes to _stream_via_opencode_cli."""
        with patch("app.services.conversation_streaming._stream_via_opencode_cli") as mock_oc:
            mock_oc.return_value = iter(["response"])

            from app.services.conversation_streaming import stream_llm_response

            chunks = list(
                stream_llm_response(
                    [{"role": "user", "content": "test"}],
                    backend="opencode",
                    cwd="/tmp/worktree",
                    chat_mode="work",
                )
            )

            mock_oc.assert_called_once()
            _, kwargs = mock_oc.call_args
            assert kwargs.get("cwd") == "/tmp/worktree"

    def test_management_mode_uses_normal_routing(self):
        """Management mode (or no chat_mode) uses the existing routing."""
        with (
            patch("app.services.conversation_streaming._find_cliproxy", return_value=None),
            patch("app.services.conversation_streaming._stream_via_cli") as mock_cli,
        ):
            mock_cli.return_value = iter(["response"])

            from app.services.conversation_streaming import stream_llm_response

            # chat_mode=management, even with cwd, should NOT route via work mode
            chunks = list(
                stream_llm_response(
                    [{"role": "user", "content": "test"}],
                    backend="claude",
                    cwd="/tmp/worktree",
                    chat_mode="management",
                )
            )

            # Should still call _stream_via_cli but through normal fallback,
            # NOT the work-mode shortcut (which requires chat_mode="work")
            mock_cli.assert_called_once()
            _, kwargs = mock_cli.call_args
            # Normal fallback does NOT pass cwd
            assert kwargs.get("cwd") is None

    def test_no_cwd_even_work_mode_uses_normal_routing(self):
        """Work mode without cwd uses normal routing (no forced CLI)."""
        with (
            patch("app.services.conversation_streaming._find_cliproxy", return_value=None),
            patch("app.services.conversation_streaming._stream_via_cli") as mock_cli,
        ):
            mock_cli.return_value = iter(["response"])

            from app.services.conversation_streaming import stream_llm_response

            chunks = list(
                stream_llm_response(
                    [{"role": "user", "content": "test"}],
                    backend="claude",
                    cwd=None,
                    chat_mode="work",
                )
            )

            mock_cli.assert_called_once()
            _, kwargs = mock_cli.call_args
            # Falls through to normal CLI fallback (no cwd)
            assert kwargs.get("cwd") is None


# ===========================================================================
# assemble_system_prompt with instance_id
# ===========================================================================


class TestAssembleSystemPromptWithInstance:
    def test_includes_project_context(self, isolated_db):
        """System prompt includes project context when instance_id is set."""
        proj_id, sa_id, psa_id = _setup(
            isolated_db, chat_mode="work", worktree_path="/tmp/project-wt"
        )
        session_id, _ = SuperAgentSessionService.create_session(sa_id, instance_id=psa_id)

        prompt = SuperAgentSessionService.assemble_system_prompt(
            sa_id, session_id, chat_mode="work", instance_id=psa_id
        )

        assert "## Project Context" in prompt
        assert "Chat Mode Project" in prompt
        assert "Test project" in prompt
        assert "/tmp/project-wt" in prompt
        assert "Chat Mode: work" in prompt

    def test_includes_github_repo_in_context(self, isolated_db):
        """System prompt includes github_repo when available."""
        proj_id = create_project(
            name="GitHub Project",
            description="With repo",
            github_repo="org/repo",
        )
        sa_id = create_super_agent(name="GH SA", backend_type="claude")
        psa_id = create_project_sa_instance(proj_id, sa_id, worktree_path="/tmp/gh")
        session_id, _ = SuperAgentSessionService.create_session(sa_id, instance_id=psa_id)

        prompt = SuperAgentSessionService.assemble_system_prompt(
            sa_id, session_id, chat_mode="management", instance_id=psa_id
        )

        assert "Repository: org/repo" in prompt
        assert "Chat Mode: management" in prompt

    def test_no_project_context_without_instance(self, isolated_db):
        """System prompt has no project context when instance_id is None."""
        sa_id = create_super_agent(name="Plain SA", backend_type="claude")
        session_id, _ = SuperAgentSessionService.create_session(sa_id)

        prompt = SuperAgentSessionService.assemble_system_prompt(sa_id, session_id)

        assert "## Project Context" not in prompt

    def test_psa_id_as_super_agent_id_resolves_template(self, isolated_db):
        """When super_agent_id is psa-, resolves to template SA for documents."""
        proj_id, sa_id, psa_id = _setup(isolated_db)

        # Add a SOUL document to the template SA
        from app.db.super_agents import add_super_agent_document

        add_super_agent_document(sa_id, "SOUL", "Soul Doc", "I am a project agent.")

        session_id, _ = SuperAgentSessionService.create_session(sa_id, instance_id=psa_id)

        prompt = SuperAgentSessionService.assemble_system_prompt(
            psa_id, session_id, instance_id=psa_id
        )

        assert "I am a project agent." in prompt
        assert "## Project Context" in prompt


# ===========================================================================
# List sessions with psa- prefix
# ===========================================================================


class TestListSessionsWithPsaPrefix:
    def test_list_sessions_by_instance_id(self, client, isolated_db):
        """GET sessions with psa- prefix queries by instance_id."""
        proj_id, sa_id, psa_id = _setup(isolated_db)

        # Create sessions linked to this instance
        sess_id1 = add_super_agent_session(sa_id, instance_id=psa_id)
        sess_id2 = add_super_agent_session(sa_id, instance_id=psa_id)
        # Create session not linked
        add_super_agent_session(sa_id)

        resp = client.get(f"/admin/super-agents/{psa_id}/sessions")
        assert resp.status_code == 200
        body = resp.get_json()
        assert len(body["sessions"]) == 2
        session_ids = {s["id"] for s in body["sessions"]}
        assert sess_id1 in session_ids
        assert sess_id2 in session_ids

    def test_list_sessions_regular_sa(self, client, isolated_db):
        """GET sessions with regular SA ID uses standard query."""
        sa_id = create_super_agent(name="Regular SA", backend_type="claude")
        add_super_agent_session(sa_id)
        add_super_agent_session(sa_id)

        resp = client.get(f"/admin/super-agents/{sa_id}/sessions")
        assert resp.status_code == 200
        body = resp.get_json()
        assert len(body["sessions"]) == 2


# ===========================================================================
# create_session stores instance_id in memory
# ===========================================================================


class TestSessionInstanceIdInMemory:
    def test_create_session_stores_instance_id(self, isolated_db):
        """create_session stores instance_id in _active_sessions."""
        proj_id, sa_id, psa_id = _setup(isolated_db)
        session_id, _ = SuperAgentSessionService.create_session(sa_id, instance_id=psa_id)

        session = SuperAgentSessionService._active_sessions[session_id]
        assert session["instance_id"] == psa_id

    def test_create_session_without_instance(self, isolated_db):
        """create_session without instance_id stores None."""
        sa_id = create_super_agent(name="No Instance SA", backend_type="claude")
        session_id, _ = SuperAgentSessionService.create_session(sa_id)

        session = SuperAgentSessionService._active_sessions[session_id]
        assert session["instance_id"] is None

    def test_restore_sessions_loads_instance_id(self, isolated_db):
        """restore_active_sessions loads instance_id from DB."""
        proj_id, sa_id, psa_id = _setup(isolated_db)
        session_id, _ = SuperAgentSessionService.create_session(sa_id, instance_id=psa_id)

        # Clear in-memory state
        SuperAgentSessionService._active_sessions.clear()

        # Restore from DB
        SuperAgentSessionService.restore_active_sessions()

        session = SuperAgentSessionService._active_sessions.get(session_id)
        assert session is not None
        assert session["instance_id"] == psa_id


# ===========================================================================
# run_streaming_response passes new params
# ===========================================================================


class TestRunStreamingResponseParams:
    def test_passes_cwd_and_chat_mode(self, isolated_db):
        """run_streaming_response passes cwd and chat_mode to stream_llm_response."""
        sa_id = create_super_agent(name="Param SA", backend_type="claude")
        session_id, _ = SuperAgentSessionService.create_session(sa_id)

        with patch(_STREAM_MOCK) as mock_stream:
            mock_stream.return_value = iter(["ok"])

            from app.services.streaming_helper import run_streaming_response

            run_streaming_response(
                session_id=session_id,
                super_agent_id=sa_id,
                backend="claude",
                cwd="/tmp/cwd-test",
                chat_mode="work",
            )

            time.sleep(0.5)

            mock_stream.assert_called_once()
            call_kwargs = mock_stream.call_args.kwargs
            assert call_kwargs.get("cwd") == "/tmp/cwd-test"
            assert call_kwargs.get("chat_mode") == "work"

    def test_passes_instance_id_to_assemble_prompt(self, isolated_db):
        """run_streaming_response passes instance_id to assemble_system_prompt."""
        proj_id, sa_id, psa_id = _setup(isolated_db)
        session_id, _ = SuperAgentSessionService.create_session(sa_id, instance_id=psa_id)

        with (
            patch(_STREAM_MOCK) as mock_stream,
            patch.object(
                SuperAgentSessionService, "assemble_system_prompt", return_value=""
            ) as mock_prompt,
        ):
            mock_stream.return_value = iter(["ok"])

            from app.services.streaming_helper import run_streaming_response

            run_streaming_response(
                session_id=session_id,
                super_agent_id=sa_id,
                backend="claude",
                instance_id=psa_id,
                chat_mode="work",
            )

            time.sleep(0.5)

            mock_prompt.assert_called_once_with(
                sa_id, session_id, chat_mode="work", instance_id=psa_id
            )
