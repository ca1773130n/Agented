"""SuperAgents cluster — super_agents + sessions + documents + exports (wave 63).

20 routes total. SSE session stream preserved via Litestar Stream.
super_agent_chat (2 SSE) and super_agent_messages (5) deferred.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import subprocess
import tempfile
import time
from http import HTTPStatus
from typing import Any, Optional

from litestar import MediaType, Router, delete, get, post, put
from litestar.exceptions import (
    ClientException,
    HTTPException,
    NotFoundException,
)
from litestar.response import Stream

from app.database import (
    add_super_agent_document,
    delete_super_agent,
    delete_super_agent_document,
    get_all_super_agents,
    get_super_agent,
    get_super_agent_document,
    get_super_agent_documents,
    get_super_agent_session,
    get_super_agent_sessions,
    update_super_agent,
    update_super_agent_document,
)
from app.database import create_super_agent as db_create_super_agent
from app.db.owned_entities import get_for_user

from ..auth import Caller

logger = logging.getLogger(__name__)


# ===========================================================================
# /admin/super-agents/* — CRUD (5 routes)
# ===========================================================================


@get("/", sync_to_thread=False)
def list_super_agents(
    caller: Caller, limit: Optional[int] = None, offset: Optional[int] = None
) -> dict[str, Any]:
    if caller.user_id:
        rows = get_for_user(
            "super_agents", caller.user_id, limit=limit, offset=offset or 0
        )
        return {"super_agents": rows, "total_count": len(rows)}
    from app.db.super_agents import count_all_super_agents

    return {
        "super_agents": get_all_super_agents(limit=limit, offset=offset or 0),
        "total_count": count_all_super_agents(),
    }


@get("/activity-status", sync_to_thread=False)
def super_agent_activity_status() -> dict[str, Any]:
    """Per-SA activity snapshot: ``has_active_session`` + ``is_streaming``.

    Cheap to call (two indexed reads + a dict snapshot of the in-memory
    ChatStateService), so the SA list page can poll it on a 5-10s
    cadence to render a "working now / active session / idle" pill on
    each card without round-tripping every SA's full session list.

    Returns::

        {
          "statuses": {
            "sa-X": {"active_sessions": 2, "is_streaming": true},
            ...
          }
        }

    SAs absent from the map have no active sessions.
    """
    from app.db.super_agents import get_active_session_counts_by_super_agent
    from app.db.super_agents import get_active_sessions_list
    from app.services.chat_state_service import ChatStateService

    counts = get_active_session_counts_by_super_agent()
    streaming = ChatStateService.get_streaming_session_ids()

    streaming_sa_ids: set[str] = set()
    if streaming:
        for sess in get_active_sessions_list():
            if sess.get("id") in streaming:
                streaming_sa_ids.add(sess.get("super_agent_id"))

    statuses: dict[str, dict] = {}
    for sa_id, active in counts.items():
        statuses[sa_id] = {
            "active_sessions": active,
            "is_streaming": sa_id in streaming_sa_ids,
        }
    return {"statuses": statuses}


@post("/", sync_to_thread=False)
def create_super_agent(data: dict, caller: Caller) -> dict[str, Any]:
    del caller
    if not data:
        raise ClientException(detail="JSON body required")
    name = data.get("name")
    if not name:
        raise ClientException(detail="name is required")
    try:
        sa_id = db_create_super_agent(
            name=name,
            description=data.get("description"),
            backend_type=data.get("backend_type", "claude"),
            preferred_model=data.get("preferred_model"),
            team_id=data.get("team_id"),
            parent_super_agent_id=data.get("parent_super_agent_id"),
            max_concurrent_sessions=data.get("max_concurrent_sessions", 10),
            config_json=data.get("config_json"),
        )
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="A super agent with this name or configuration already exists",
        ) from None
    except sqlite3.OperationalError:
        raise HTTPException(
            status_code=503, detail="Database unavailable, please retry"
        ) from None
    if not sa_id:
        raise HTTPException(status_code=500, detail="Failed to create super agent")
    return {"message": "SuperAgent created", "super_agent_id": sa_id}


@get("/{super_agent_id:str}", sync_to_thread=False)
def get_super_agent_endpoint(
    super_agent_id: str, caller: Caller
) -> dict[str, Any]:
    del caller
    sa_id = super_agent_id
    if sa_id.startswith("psa-"):
        from app.db.project_sa_instances import get_project_sa_instance

        instance = get_project_sa_instance(sa_id)
        if not instance:
            raise NotFoundException(detail="Instance not found")
        sa_id = instance["template_sa_id"]
    sa = get_super_agent(sa_id)
    if not sa:
        raise NotFoundException(detail="SuperAgent not found")
    return sa


@put("/{super_agent_id:str}", sync_to_thread=False)
def update_super_agent_endpoint(
    super_agent_id: str, data: dict, caller: Caller
) -> dict[str, Any]:
    del caller
    if not data:
        raise ClientException(detail="JSON body required")
    if not update_super_agent(
        super_agent_id,
        name=data.get("name"),
        description=data.get("description"),
        backend_type=data.get("backend_type"),
        preferred_model=data.get("preferred_model"),
        team_id=data.get("team_id"),
        parent_super_agent_id=data.get("parent_super_agent_id"),
        max_concurrent_sessions=data.get("max_concurrent_sessions"),
        enabled=data.get("enabled"),
        config_json=data.get("config_json"),
    ):
        raise NotFoundException(detail="SuperAgent not found or no changes made")
    return {"message": "SuperAgent updated"}


@delete("/{super_agent_id:str}", status_code=200, sync_to_thread=False)
def delete_super_agent_endpoint(
    super_agent_id: str, caller: Caller
) -> dict[str, Any]:
    del caller
    if not delete_super_agent(super_agent_id):
        raise NotFoundException(detail="SuperAgent not found")
    return {"message": "SuperAgent deleted"}


# ---------------------------------------------------------------------------
# Sessions (7 routes)
# ---------------------------------------------------------------------------


@get("/{super_agent_id:str}/sessions", sync_to_thread=False)
def list_sessions(super_agent_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    if super_agent_id.startswith("psa-"):
        from app.db.super_agents import get_sessions_for_instance

        return {"sessions": get_sessions_for_instance(super_agent_id)}
    return {"sessions": get_super_agent_sessions(super_agent_id)}


@post("/{super_agent_id:str}/sessions", sync_to_thread=False)
def create_session(
    super_agent_id: str, data: Optional[dict], caller: Caller
) -> dict[str, Any]:
    del caller
    from app.services.instance_service import InstanceService
    from app.services.super_agent_session_service import SuperAgentSessionService

    data = data or {}
    project_id = data.get("project_id")
    title = data.get("title")
    session_type = data.get("session_type", "worker")

    sa_id = super_agent_id
    instance_id = None
    if sa_id.startswith("psa-"):
        from app.db.project_sa_instances import get_project_sa_instance

        inst = get_project_sa_instance(sa_id)
        if not inst:
            raise NotFoundException(detail="Instance not found")
        instance_id = sa_id
        sa_id = inst["template_sa_id"]
        if not project_id:
            project_id = inst.get("project_id")

    if project_id and instance_id:
        result = InstanceService.create_session_worktree(
            project_id=project_id,
            super_agent_id=sa_id,
            instance_id=instance_id,
            title=title,
            session_type=session_type,
        )
        if not result:
            raise HTTPException(
                status_code=500, detail="Failed to create session worktree"
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
                raise NotFoundException(detail=error)
            raise ClientException(detail=error)

    from app.services.chat_state_service import ChatStateService

    ChatStateService.init_session(session_id)

    session = get_super_agent_session(session_id)
    return {
        "message": "Session created",
        "session_id": session_id,
        "worktree_path": session.get("worktree_path") if session else None,
        "branch_name": session.get("branch_name") if session else None,
        "session_type": session.get("session_type") if session else session_type,
    }


@get(
    "/{super_agent_id:str}/sessions/{session_id:str}", sync_to_thread=False
)
def get_session_endpoint(
    super_agent_id: str, session_id: str, caller: Caller
) -> dict[str, Any]:
    del caller, super_agent_id
    session = get_super_agent_session(session_id)
    if not session:
        raise NotFoundException(detail="Session not found")
    return session


@post(
    "/{super_agent_id:str}/sessions/{session_id:str}/message",
    sync_to_thread=False,
)
def send_session_message(
    super_agent_id: str, session_id: str, data: dict, caller: Caller
) -> dict[str, Any]:
    del caller, super_agent_id
    from app.services.super_agent_session_service import SuperAgentSessionService

    if not data or not data.get("message"):
        raise ClientException(detail="message is required")
    success, error = SuperAgentSessionService.send_message(
        session_id, data["message"]
    )
    if not success:
        if "not found" in error.lower():
            raise NotFoundException(detail=error)
        raise ClientException(detail=error)
    return {"message": "Message sent"}


@post(
    "/{super_agent_id:str}/sessions/{session_id:str}/end",
    sync_to_thread=False,
)
def end_session(
    super_agent_id: str, session_id: str, caller: Caller
) -> dict[str, Any]:
    del caller, super_agent_id
    from app.services.instance_service import InstanceService
    from app.services.super_agent_session_service import SuperAgentSessionService

    session = get_super_agent_session(session_id)
    success, error = SuperAgentSessionService.end_session(session_id)
    if not success:
        raise NotFoundException(detail=error)
    if session and session.get("worktree_path"):
        InstanceService.cleanup_session_worktree(session_id, session=session)

    from app.services.chat_state_service import ChatStateService

    ChatStateService.remove_session(session_id)
    return {"message": "Session ended"}


@get(
    "/{super_agent_id:str}/sessions/{session_id:str}/stream",
    media_type=MediaType.TEXT,
    sync_to_thread=False,
)
def stream_session(
    super_agent_id: str, session_id: str, caller: Caller
) -> Stream:
    del caller, super_agent_id
    from app.services.super_agent_session_service import SuperAgentSessionService

    def generate():
        while True:
            for line in SuperAgentSessionService.get_output_lines(session_id):
                yield (
                    "data: "
                    + json.dumps({"type": "output", "content": line})
                    + "\n\n"
                )
            yield "data: " + json.dumps({"type": "heartbeat"}) + "\n\n"
            time.sleep(5)

    return Stream(generate(), media_type="text/event-stream")


def _emit_git_action_activity(
    super_agent_id: str,
    session_id: str,
    action: str,
    response: dict[str, Any],
) -> None:
    """v0.7.7: best-effort emission of git-action events to the inspector.

    Observability side-channel — never raise. Mirrors the pattern in
    SuperAgentSessionService._record_activity.
    """
    try:
        from app.services import super_agent_activity_service

        success = bool(response.get("success"))
        super_agent_activity_service.record(
            super_agent_id=super_agent_id,
            session_id=session_id,
            event_type="git_action",
            payload={
                "command": action,
                "result": response,
                "success": success,
            },
            status="ok" if success else "error",
            error_message=None if success else str(response.get("output") or "")[:500],
        )
    except Exception:
        logger.warning(
            "Failed to record super-agent git_action activity",
            exc_info=True,
        )


@post(
    "/{super_agent_id:str}/sessions/{session_id:str}/git-action",
    sync_to_thread=False,
)
def git_action(
    super_agent_id: str, session_id: str, data: dict, caller: Caller
) -> Any:
    del caller
    from app.db.super_agents import update_super_agent_session

    if not data:
        raise ClientException(detail="JSON body required")
    action = data.get("action")
    if action not in ("commit", "push", "create_pr", "rebase", "diff"):
        raise ClientException(detail=f"Invalid action: {action}")

    session = get_super_agent_session(session_id)
    if not session:
        raise NotFoundException(detail="Session not found")
    worktree_path = session.get("worktree_path")
    branch_name = session.get("branch_name")
    if not worktree_path:
        raise ClientException(detail="Session has no worktree")

    response: dict[str, Any] = {"action": action, "success": False, "output": "Unknown action"}
    try:
        if action == "commit":
            message = data.get("message", "Work in progress")
            subprocess.run(
                ["git", "-C", worktree_path, "add", "-A"],
                capture_output=True, text=True, timeout=30,
            )
            result = subprocess.run(
                ["git", "-C", worktree_path, "commit", "-m", message],
                capture_output=True, text=True, timeout=30,
            )
            response = {
                "action": action,
                "success": result.returncode == 0,
                "output": (result.stdout if result.returncode == 0 else result.stderr).strip(),
            }
        elif action == "push":
            result = subprocess.run(
                ["git", "-C", worktree_path, "push", "-u", "origin", branch_name],
                capture_output=True, text=True, timeout=60,
            )
            response = {
                "action": action,
                "success": result.returncode == 0,
                "output": (result.stdout if result.returncode == 0 else result.stderr).strip(),
            }
        elif action == "create_pr":
            pr_title = data.get("pr_title", session.get("title") or f"Session {session_id}")
            pr_body = data.get("pr_body", "")
            result = subprocess.run(
                [
                    "gh", "pr", "create",
                    "--base", "main",
                    "--head", branch_name,
                    "--title", pr_title,
                    "--body", pr_body,
                ],
                capture_output=True, text=True, timeout=30, cwd=worktree_path,
            )
            if result.returncode != 0:
                response = {"action": action, "success": False, "output": result.stderr.strip()}
            else:
                pr_url = result.stdout.strip()
                update_super_agent_session(session_id, pr_url=pr_url)
                response = {"action": action, "success": True, "pr_url": pr_url}
        elif action == "rebase":
            project_id = session.get("project_id")
            if project_id:
                from app.db.projects import get_project as _get_project

                proj = _get_project(project_id)
                if proj and proj.get("local_path"):
                    subprocess.run(
                        ["git", "-C", proj["local_path"], "pull", "--ff-only"],
                        capture_output=True, text=True, timeout=60,
                    )
            result = subprocess.run(
                ["git", "-C", worktree_path, "rebase", "main"],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                subprocess.run(
                    ["git", "-C", worktree_path, "rebase", "--abort"],
                    capture_output=True, text=True, timeout=10,
                )
                response = {"action": action, "success": False, "output": result.stderr.strip()}
            else:
                response = {"action": action, "success": True, "output": result.stdout.strip()}
        elif action == "diff":
            result = subprocess.run(
                ["git", "-C", worktree_path, "diff", "main...HEAD", "--stat"],
                capture_output=True, text=True, timeout=30,
            )
            diff_detail = subprocess.run(
                ["git", "-C", worktree_path, "diff", "main...HEAD"],
                capture_output=True, text=True, timeout=30,
            )
            response = {
                "action": action,
                "success": True,
                "stat": result.stdout.strip(),
                "diff": diff_detail.stdout[:10000],
            }
    except subprocess.TimeoutExpired:
        _emit_git_action_activity(
            super_agent_id,
            session_id,
            action,
            {"action": action, "success": False, "output": f"Git {action} timed out"},
        )
        raise HTTPException(
            status_code=504, detail=f"Git {action} timed out"
        ) from None
    except Exception as exc:  # noqa: BLE001
        _emit_git_action_activity(
            super_agent_id,
            session_id,
            action,
            {"action": action, "success": False, "output": f"Git {action} failed: {exc}"},
        )
        raise HTTPException(
            status_code=500, detail=f"Git {action} failed: {exc}"
        ) from None

    _emit_git_action_activity(super_agent_id, session_id, action, response)
    return response


# ---------------------------------------------------------------------------
# Documents (5 routes)
# ---------------------------------------------------------------------------


@get("/{super_agent_id:str}/documents", sync_to_thread=False)
def list_documents(super_agent_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    return {"documents": get_super_agent_documents(super_agent_id)}


@post("/{super_agent_id:str}/documents", sync_to_thread=False)
def create_document(
    super_agent_id: str, data: dict, caller: Caller
) -> dict[str, Any]:
    del caller
    if not data:
        raise ClientException(detail="JSON body required")
    doc_type = data.get("doc_type")
    title = data.get("title")
    if not doc_type:
        raise ClientException(detail="doc_type is required")
    if not title:
        raise ClientException(detail="title is required")
    doc_id = add_super_agent_document(
        super_agent_id=super_agent_id,
        doc_type=doc_type,
        title=title,
        content=data.get("content", ""),
    )
    if doc_id is None:
        raise ClientException(
            detail="Invalid doc_type or failed to create document"
        )
    return {"message": "Document created", "document_id": doc_id}


@get(
    "/{super_agent_id:str}/documents/{doc_id:int}", sync_to_thread=False
)
def get_document_endpoint(
    super_agent_id: str, doc_id: int, caller: Caller
) -> dict[str, Any]:
    del caller, super_agent_id
    doc = get_super_agent_document(doc_id)
    if not doc:
        raise NotFoundException(detail="Document not found")
    return doc


@put(
    "/{super_agent_id:str}/documents/{doc_id:int}", sync_to_thread=False
)
def update_document_endpoint(
    super_agent_id: str, doc_id: int, data: dict, caller: Caller
) -> dict[str, Any]:
    del caller, super_agent_id
    if not data:
        raise ClientException(detail="JSON body required")
    if not update_super_agent_document(
        doc_id,
        title=data.get("title"),
        content=data.get("content"),
    ):
        raise NotFoundException(detail="Document not found or no changes made")
    return {"message": "Document updated"}


@delete(
    "/{super_agent_id:str}/documents/{doc_id:int}",
    status_code=200,
    sync_to_thread=False,
)
def delete_document_endpoint(
    super_agent_id: str, doc_id: int, caller: Caller
) -> dict[str, Any]:
    del caller, super_agent_id
    if not delete_super_agent_document(doc_id):
        raise NotFoundException(detail="Document not found")
    return {"message": "Document deleted"}


# ---------------------------------------------------------------------------
# v0.7.91 — SuperAgent → goal_loop Ouroboros bridge
# ---------------------------------------------------------------------------


@post("/{super_agent_id:str}/ouroboros-runs", sync_to_thread=False)
def start_ouroboros_run(
    super_agent_id: str, data: dict, caller: Caller
) -> dict[str, Any]:
    """v0.7.91 — bridge: spawn a goal_loop project session that
    inherits the SuperAgent's backend + model and runs in
    Ouroboros mode.

    The SA itself isn't rewritten — we just wire its identity
    (backend_type, preferred_model) into the goal_loop config
    so the judge calls land on the SA's backend rather than the
    project default. Ownership / activity / dead-end semantics
    are the goal_loop machinery's (see GoalLoopRunner v0.7.86–87).

    Body:
      * ``project_id`` (str, required) — the project providing
        ``cwd`` for the spawned session. Required because
        goal_loop sessions are project-scoped today.
      * ``goal`` (str, required) — the natural-language objective
        the SA should drive toward.
      * ``max_iterations`` (int, default 20)
      * ``max_wall_seconds`` (int, default 1800)
      * ``check_cmd`` (str | null) — operator-supplied
        deterministic check; goal_loop's judge prefers this
        over the LLM judge when present.
      * ``yolo_mode`` (bool, default false)

    Returns ``{session_id, super_agent_id, pid, status}``.
    """
    del caller
    sa = get_super_agent(super_agent_id)
    if not sa:
        raise NotFoundException(detail="SuperAgent not found")

    body = data or {}
    project_id = body.get("project_id")
    goal = (body.get("goal") or "").strip()
    if not project_id:
        raise ClientException(detail="project_id is required")
    if not goal:
        raise ClientException(detail="goal is required")

    from app.database import get_project
    from app.services.execution_type_handler import get_handler
    from app.services.project_workspace_service import ProjectWorkspaceService

    project = get_project(project_id)
    if not project:
        raise NotFoundException(detail="Project not found")

    try:
        cwd = ProjectWorkspaceService.resolve_working_directory(project_id)
    except ValueError as e:
        raise ClientException(detail=str(e)) from e

    handler = get_handler("goal_loop")
    if not handler:
        from litestar.exceptions import HTTPException

        raise HTTPException(
            status_code=500, detail="goal_loop handler is not registered"
        )

    # Mirror the SA's backend identity into the judge config so
    # judge calls go to the same backend the SA itself would use
    # (cost + behaviour parity).
    backend_kind = sa.get("backend_type") or "claude"
    preferred_model = sa.get("preferred_model")

    session_config = {
        "project_id": project_id,
        "cwd": cwd,
        "execution_mode": "autonomous",
        "yolo_mode": bool(body.get("yolo_mode")),
        "goal_loop_config": {
            "goal": goal,
            "check_cmd": body.get("check_cmd"),
            "max_iterations": int(body.get("max_iterations") or 20),
            "max_wall_seconds": int(body.get("max_wall_seconds") or 1800),
            "judge_backend_kind": backend_kind,
            "judge_model_override": preferred_model,
            # v0.7.87 default — explicit here for the audit trail.
            "ouroboros": True,
        },
    }
    result = handler.start(session_config)
    if "error" in result:
        from litestar.exceptions import HTTPException

        raise HTTPException(status_code=503, detail=result["error"])
    result["super_agent_id"] = super_agent_id
    return result


super_agents_router = Router(
    path="/admin/super-agents",
    route_handlers=[
        list_super_agents,
        super_agent_activity_status,
        create_super_agent,
        get_super_agent_endpoint,
        update_super_agent_endpoint,
        delete_super_agent_endpoint,
        list_sessions,
        create_session,
        get_session_endpoint,
        send_session_message,
        end_session,
        stream_session,
        git_action,
        # v0.7.91 — SA → goal_loop Ouroboros bridge
        start_ouroboros_run,
        list_documents,
        create_document,
        get_document_endpoint,
        update_document_endpoint,
        delete_document_endpoint,
    ],
)


# ===========================================================================
# /admin/super-agent-exports/* (3 routes)
# ===========================================================================


@post("/export", sync_to_thread=False)
def export_super_agent(data: dict) -> dict[str, Any]:
    from app.services.super_agent_export_service import SuperAgentExportService

    if not data:
        raise ClientException(detail="JSON body required")
    super_agent_id = data.get("super_agent_id")
    if not super_agent_id:
        raise ClientException(detail="super_agent_id is required")
    export_format = data.get("export_format", "zip")
    if export_format not in ("directory", "zip"):
        raise ClientException(
            detail="export_format must be 'directory' or 'zip'"
        )
    try:
        if export_format == "directory":
            output_dir = data.get("output_dir") or tempfile.mkdtemp(prefix="agented-sa-export-")
            return SuperAgentExportService.export_super_agent(
                super_agent_id=super_agent_id,
                output_dir=output_dir,
            )
        output_dir = data.get("output_dir") or tempfile.mkdtemp(prefix="agented-sa-export-")
        return SuperAgentExportService.export_as_zip(
            super_agent_id=super_agent_id,
            output_path=f"{output_dir}/super_agent_export.zip",
        )
    except ValueError as exc:
        raise NotFoundException(detail=str(exc)) from None
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500, detail=f"Export failed: {exc}"
        ) from None


@post("/import", status_code=HTTPStatus.CREATED, sync_to_thread=False)
def import_super_agent(data: dict) -> dict[str, Any]:
    from app.services.super_agent_export_service import SuperAgentExportService

    if not data:
        raise ClientException(detail="JSON body required")
    source_path = data.get("source_path")
    if not source_path:
        raise ClientException(detail="source_path is required")
    try:
        if source_path.endswith(".zip"):
            result = SuperAgentExportService.import_from_zip(source_path)
        else:
            result = SuperAgentExportService.import_from_directory(source_path)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result)
        return result
    except ValueError as exc:
        raise ClientException(detail=str(exc)) from None
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500, detail=f"Import failed: {exc}"
        ) from None


@post("/validate", sync_to_thread=False)
def validate_super_agent_package(data: dict) -> dict[str, Any]:
    from pathlib import Path

    from app.services.super_agent_export_service import (
        SuperAgentExportService,
        _read_json,
    )

    if not data:
        raise ClientException(detail="JSON body required")
    source_path = data.get("source_path")
    if not source_path:
        raise ClientException(detail="source_path is required")
    try:
        manifest_path = Path(source_path) / "manifest.json"
        if not manifest_path.exists():
            raise NotFoundException(detail="manifest.json not found")
        manifest = _read_json(manifest_path)
        return SuperAgentExportService.validate_manifest(manifest)
    except NotFoundException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500, detail=f"Validation failed: {exc}"
        ) from None


super_agent_exports_router = Router(
    path="/admin/super-agent-exports",
    route_handlers=[
        export_super_agent,
        import_super_agent,
        validate_super_agent_package,
    ],
)
