"""SuperAgent session management API endpoints."""

import json
import subprocess
import time
from http import HTTPStatus

from flask import Response, request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from app.models.common import error_response

from ..database import (
    get_super_agent_session,
    get_super_agent_sessions,
)
from ..db.super_agents import get_sessions_for_project, update_super_agent_session
from ..services.instance_service import InstanceService
from ..services.super_agent_session_service import SuperAgentSessionService
from .super_agents import SuperAgentPath

tag = Tag(name="super-agent-sessions", description="SuperAgent session operations")
super_agent_sessions_bp = APIBlueprint(
    "super_agent_sessions", __name__, url_prefix="/admin/super-agents", abp_tags=[tag]
)


class SessionPath(BaseModel):
    super_agent_id: str = Field(..., description="SuperAgent ID")
    session_id: str = Field(..., description="Session ID")


@super_agent_sessions_bp.get("/<super_agent_id>/sessions")
def list_sessions(path: SuperAgentPath):
    """List all sessions for a super agent or project-scoped instance."""
    if path.super_agent_id.startswith("psa-"):
        from ..db.super_agents import get_sessions_for_instance

        sessions = get_sessions_for_instance(path.super_agent_id)
    else:
        sessions = get_super_agent_sessions(path.super_agent_id)
    return {"sessions": sessions}, HTTPStatus.OK


@super_agent_sessions_bp.post("/<super_agent_id>/sessions")
def create_session(path: SuperAgentPath):
    """Create a new session for a super agent.

    If project_id is provided and the SA has an instance for that project,
    a worker session with its own git worktree is created.
    """
    data = request.get_json() or {}
    project_id = data.get("project_id")
    title = data.get("title")
    session_type = data.get("session_type", "worker")

    # Resolve the template SA ID for psa- prefixed IDs
    sa_id = path.super_agent_id
    instance_id = None
    if sa_id.startswith("psa-"):
        from ..db.project_sa_instances import get_project_sa_instance

        inst = get_project_sa_instance(sa_id)
        if not inst:
            return error_response("NOT_FOUND", "Instance not found", HTTPStatus.NOT_FOUND)
        instance_id = sa_id
        sa_id = inst["template_sa_id"]
        if not project_id:
            project_id = inst.get("project_id")

    if project_id and instance_id:
        # Create session with worktree
        result = InstanceService.create_session_worktree(
            project_id=project_id,
            super_agent_id=sa_id,
            instance_id=instance_id,
            title=title,
            session_type=session_type,
        )
        if not result:
            return error_response(
                "INTERNAL_ERROR",
                "Failed to create session worktree",
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )
        session_id = result["session_id"]
    else:
        session_id, error = SuperAgentSessionService.create_session(
            sa_id,
            instance_id=instance_id,
            project_id=project_id,
            title=title,
            session_type=session_type,
        )
        if error:
            if "not found" in error.lower():
                return error_response("NOT_FOUND", error, HTTPStatus.NOT_FOUND)
            return error_response("BAD_REQUEST", error, HTTPStatus.BAD_REQUEST)

    # Initialize chat state for versioned SSE delivery
    from ..services.chat_state_service import ChatStateService

    ChatStateService.init_session(session_id)

    session = get_super_agent_session(session_id)
    return {
        "message": "Session created",
        "session_id": session_id,
        "worktree_path": session.get("worktree_path") if session else None,
        "branch_name": session.get("branch_name") if session else None,
        "session_type": session.get("session_type") if session else session_type,
    }, HTTPStatus.CREATED


@super_agent_sessions_bp.get("/<super_agent_id>/sessions/<session_id>")
def get_session_endpoint(path: SessionPath):
    """Get a session by ID."""
    session = get_super_agent_session(path.session_id)
    if not session:
        return error_response("NOT_FOUND", "Session not found", HTTPStatus.NOT_FOUND)
    return session, HTTPStatus.OK


@super_agent_sessions_bp.post("/<super_agent_id>/sessions/<session_id>/message")
def send_session_message(path: SessionPath):
    """Send a message to a session."""
    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)

    message = data.get("message")
    if not message:
        return error_response("BAD_REQUEST", "message is required", HTTPStatus.BAD_REQUEST)

    success, error = SuperAgentSessionService.send_message(path.session_id, message)
    if not success:
        if "not found" in error.lower():
            return error_response("NOT_FOUND", error, HTTPStatus.NOT_FOUND)
        return error_response("BAD_REQUEST", error, HTTPStatus.BAD_REQUEST)
    return {"message": "Message sent"}, HTTPStatus.OK


@super_agent_sessions_bp.post("/<super_agent_id>/sessions/<session_id>/end")
def end_session(path: SessionPath):
    """End a session and clean up its worktree if present."""
    # Get session before ending (for worktree cleanup)
    session = get_super_agent_session(path.session_id)

    success, error = SuperAgentSessionService.end_session(path.session_id)
    if not success:
        return error_response("NOT_FOUND", error, HTTPStatus.NOT_FOUND)

    # Clean up session worktree
    if session and session.get("worktree_path"):
        InstanceService.cleanup_session_worktree(path.session_id, session=session)

    # Clean up chat state and poison-pill subscriber queues
    from ..services.chat_state_service import ChatStateService

    ChatStateService.remove_session(path.session_id)

    return {"message": "Session ended"}, HTTPStatus.OK


@super_agent_sessions_bp.get("/<super_agent_id>/sessions/<session_id>/stream")
def stream_session(path: SessionPath):
    """Stream session output via Server-Sent Events (SSE).

    SSE Protocol:
    - Event 'data': {"type": "output", "content": str} -- output line from session
    - Event 'data': {"type": "heartbeat"} -- keepalive sent every 5 seconds

    Polls session output lines and emits them as SSE data events.
    """

    def generate():
        """Yield SSE output and heartbeat events for the session stream."""
        while True:
            # Check for output lines
            lines = SuperAgentSessionService.get_output_lines(path.session_id)
            for line in lines:
                yield f"data: {json.dumps({'type': 'output', 'content': line})}\n\n"
            # Send heartbeat
            yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
            time.sleep(5)

    return Response(generate(), mimetype="text/event-stream")


@super_agent_sessions_bp.post("/<super_agent_id>/sessions/<session_id>/git-action")
def git_action(path: SessionPath):
    """Execute a git action on a session's worktree.

    Supported actions: commit, push, create_pr, rebase, diff
    """
    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)

    action = data.get("action")
    if action not in ("commit", "push", "create_pr", "rebase", "diff"):
        return error_response("BAD_REQUEST", f"Invalid action: {action}", HTTPStatus.BAD_REQUEST)

    session = get_super_agent_session(path.session_id)
    if not session:
        return error_response("NOT_FOUND", "Session not found", HTTPStatus.NOT_FOUND)

    worktree_path = session.get("worktree_path")
    branch_name = session.get("branch_name")
    if not worktree_path:
        return error_response("BAD_REQUEST", "Session has no worktree", HTTPStatus.BAD_REQUEST)

    try:
        if action == "commit":
            message = data.get("message", "Work in progress")
            # Stage all changes and commit
            subprocess.run(
                ["git", "-C", worktree_path, "add", "-A"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            result = subprocess.run(
                ["git", "-C", worktree_path, "commit", "-m", message],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return {"action": action, "success": False, "output": result.stderr.strip()}
            return {"action": action, "success": True, "output": result.stdout.strip()}

        elif action == "push":
            result = subprocess.run(
                ["git", "-C", worktree_path, "push", "-u", "origin", branch_name],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                return {"action": action, "success": False, "output": result.stderr.strip()}
            return {"action": action, "success": True, "output": result.stdout.strip()}

        elif action == "create_pr":
            pr_title = data.get("pr_title", session.get("title") or f"Session {path.session_id}")
            pr_body = data.get("pr_body", "")
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "create",
                    "--base",
                    "main",
                    "--head",
                    branch_name,
                    "--title",
                    pr_title,
                    "--body",
                    pr_body,
                ],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=worktree_path,
            )
            if result.returncode != 0:
                return {"action": action, "success": False, "output": result.stderr.strip()}
            pr_url = result.stdout.strip()
            update_super_agent_session(path.session_id, pr_url=pr_url)
            return {"action": action, "success": True, "pr_url": pr_url}

        elif action == "rebase":
            # Pull latest main first, then rebase
            project_id = session.get("project_id")
            if project_id:
                from ..db.projects import get_project as _get_project

                proj = _get_project(project_id)
                if proj and proj.get("local_path"):
                    subprocess.run(
                        ["git", "-C", proj["local_path"], "pull", "--ff-only"],
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
            result = subprocess.run(
                ["git", "-C", worktree_path, "rebase", "main"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                # Abort failed rebase
                subprocess.run(
                    ["git", "-C", worktree_path, "rebase", "--abort"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                return {"action": action, "success": False, "output": result.stderr.strip()}
            return {"action": action, "success": True, "output": result.stdout.strip()}

        elif action == "diff":
            result = subprocess.run(
                ["git", "-C", worktree_path, "diff", "main...HEAD", "--stat"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            diff_detail = subprocess.run(
                ["git", "-C", worktree_path, "diff", "main...HEAD"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return {
                "action": action,
                "success": True,
                "stat": result.stdout.strip(),
                "diff": diff_detail.stdout[:10000],  # Limit output size
            }

    except subprocess.TimeoutExpired:
        return error_response("TIMEOUT", f"Git {action} timed out", HTTPStatus.GATEWAY_TIMEOUT)
    except Exception as e:
        return error_response(
            "INTERNAL_ERROR",
            f"Git {action} failed: {str(e)}",
            HTTPStatus.INTERNAL_SERVER_ERROR,
        )
