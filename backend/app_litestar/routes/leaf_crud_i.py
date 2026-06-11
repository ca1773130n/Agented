"""Wave 76 — leaf CRUD batch I (~15 routes).

setup CRUD + super_agent_messages CRUD + team_generation (async) +
chunks + super_agent_chat send. SSE streams stay on Flask:
- /api/setup/{id}/stream
- /admin/super-agents/{id}/messages/stream
- /admin/teams/generate/stream
- /admin/super-agents/{id}/sessions/{sid}/chat/stream
"""

from __future__ import annotations

import logging
import subprocess
import threading
import uuid
from http import HTTPStatus
from typing import Any, Optional

from litestar import Router, delete, get, post
from litestar.exceptions import (
    ClientException,
    HTTPException,
    NotFoundException,
)

from app.database import (
    get_project,
    get_super_agent,
    get_super_agent_session,
)
from app.db.chunk_results import (
    create_chunk_result,
    create_chunked_execution,
    get_chunk_results,
    get_chunked_execution,
    increment_completed_chunks,
    update_chunk_result,
    update_chunked_execution_status,
)
from app.db.triggers import get_trigger
from app.services.chunk_service import ChunkService
from app.services.setup_execution_service import SetupExecutionService
from app.services.setup_service import SetupBundleService
from app.services.super_agent_session_service import SuperAgentSessionService
from app.services.team_generation_service import TeamGenerationService
from app_litestar.auth_guards import requires_role
from app_litestar.rate_limit_guard import requires_rate_limit

logger = logging.getLogger(__name__)


# ===========================================================================
# /api/setup/* (5; /stream stays on Flask)
# ===========================================================================


@post("/start", status_code=201, sync_to_thread=False)
def start_setup(data: dict) -> dict[str, Any]:
    body = data or {}
    project_id = body.get("project_id")
    command = body.get("command")
    if not project_id:
        raise ClientException(detail="project_id is required")
    if not command:
        raise ClientException(detail="command is required")
    if not get_project(project_id):
        raise NotFoundException(detail="Project not found")
    try:
        execution_id = SetupExecutionService.start_setup(project_id=project_id, command=command)
    except ValueError as e:
        raise ClientException(detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start setup: {e}") from e
    return {"execution_id": execution_id, "status": "running"}


@post("/{execution_id:str}/respond", sync_to_thread=False)
def respond_setup(execution_id: str, data: dict) -> dict[str, Any]:
    if not SetupExecutionService.get_status(execution_id):
        raise NotFoundException(detail="Setup execution not found")
    body = data or {}
    if not SetupExecutionService.submit_response(
        execution_id=execution_id,
        interaction_id=body.get("interaction_id"),
        response=body.get("response", ""),
    ):
        raise NotFoundException(detail="No pending interaction found")
    return {"status": "ok"}


@get("/{execution_id:str}/status", sync_to_thread=False)
def setup_status(execution_id: str) -> Any:
    status = SetupExecutionService.get_status(execution_id)
    if not status:
        raise NotFoundException(detail="Setup execution not found")
    return status


@delete("/{execution_id:str}", status_code=200, sync_to_thread=False)
def cancel_setup(execution_id: str) -> dict[str, Any]:
    if not SetupExecutionService.get_status(execution_id):
        raise NotFoundException(detail="Setup execution not found")
    SetupExecutionService.cancel_setup(execution_id)
    return {"message": "Setup cancelled"}


@post(
    "/bundle-install",
    sync_to_thread=False,
    guards=[requires_role("admin"), requires_rate_limit(10, 3600.0)],
)
def bundle_install() -> Any:
    result, status = SetupBundleService.bundle_install()
    if status >= 400:
        raise HTTPException(status_code=status, detail=str(result))
    return result


setup_router = Router(
    path="/api/setup",
    route_handlers=[start_setup, respond_setup, setup_status, cancel_setup, bundle_install],
)


# ===========================================================================
# /admin/super-agents/{id}/messages/* (4; /stream stays on Flask)
# ===========================================================================


def _resolve_sa_id(sa_id: str) -> str:
    if sa_id.startswith("psa-"):
        from app.db.project_sa_instances import get_project_sa_instance

        instance = get_project_sa_instance(sa_id)
        if not instance:
            raise NotFoundException(detail="Instance not found")
        return instance["template_sa_id"]
    return sa_id


@post(
    "/{super_agent_id:str}/messages",
    status_code=201,
    sync_to_thread=False,
)
def send_agent_message(super_agent_id: str, data: dict) -> dict[str, Any]:
    from app.services.agent_message_bus_service import AgentMessageBusService

    if not data:
        raise ClientException(detail="JSON body required")
    content = (data.get("content") or "").strip()
    if not content:
        raise ClientException(detail="content is required")
    sa_id = _resolve_sa_id(super_agent_id)
    msg_id = AgentMessageBusService.send_message(
        from_agent_id=sa_id,
        to_agent_id=data.get("to_agent_id"),
        message_type=data.get("message_type", "message"),
        priority=data.get("priority", "normal"),
        subject=data.get("subject"),
        content=content,
        ttl_seconds=data.get("ttl_seconds"),
    )
    if not msg_id:
        raise HTTPException(status_code=500, detail="Failed to send message")
    return {"message": "Message sent", "message_id": msg_id}


@get("/{super_agent_id:str}/messages/inbox", sync_to_thread=False)
def get_inbox(super_agent_id: str, status: Optional[str] = None) -> dict[str, Any]:
    from app.db.messages import get_inbox_messages

    return {"messages": get_inbox_messages(super_agent_id, status=status)}


@get("/{super_agent_id:str}/messages/outbox", sync_to_thread=False)
def get_outbox(super_agent_id: str) -> dict[str, Any]:
    from app.db.messages import get_outbox_messages

    return {"messages": get_outbox_messages(super_agent_id)}


@post(
    "/{super_agent_id:str}/messages/{message_id:str}/read",
    sync_to_thread=False,
)
def mark_message_read(super_agent_id: str, message_id: str) -> dict[str, Any]:
    del super_agent_id
    from app.db.messages import update_message_status

    if not update_message_status(message_id, "read"):
        raise NotFoundException(detail="Message not found")
    return {"message": "Message marked as read"}


@delete(
    "/{super_agent_id:str}/messages/{message_id:str}",
    status_code=200,
    sync_to_thread=False,
)
def delete_agent_message(super_agent_id: str, message_id: str) -> dict[str, Any]:
    from app.db.messages import delete_message

    if not delete_message(message_id, super_agent_id):
        raise NotFoundException(detail="Message not found")
    return {"message": "Message deleted"}


super_agent_messages_router = Router(
    path="/admin/super-agents",
    route_handlers=[
        send_agent_message,
        get_inbox,
        get_outbox,
        mark_message_read,
        delete_agent_message,
    ],
)


# ===========================================================================
# /admin/teams/generate + /generate/{id} (2 async; SSE /generate/stream Flask-side)
# ===========================================================================


_generation_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()
_MAX_JOBS = 200


@post("/generate", status_code=202, sync_to_thread=False)
def generate_team_config(data: dict) -> dict[str, Any]:
    body = data or {}
    description = body.get("description", "")
    if not description or len(description) < 10:
        raise ClientException(detail="description is required and must be at least 10 characters")

    job_id = f"gen-{uuid.uuid4().hex[:8]}"
    with _jobs_lock:
        if len(_generation_jobs) >= _MAX_JOBS:
            oldest_key = next(iter(_generation_jobs))
            del _generation_jobs[oldest_key]
        _generation_jobs[job_id] = {"status": "pending"}

    def _run() -> None:
        try:
            result = TeamGenerationService.generate(description)
            with _jobs_lock:
                _generation_jobs[job_id] = {"status": "complete", **result}
        except subprocess.TimeoutExpired:
            with _jobs_lock:
                _generation_jobs[job_id] = {
                    "status": "error",
                    "error": (
                        "Team generation timed out. The AI service took too long to respond."
                        " Please try again."
                    ),
                }
        except RuntimeError as e:
            with _jobs_lock:
                _generation_jobs[job_id] = {"status": "error", "error": str(e)}
        except Exception as e:
            with _jobs_lock:
                _generation_jobs[job_id] = {
                    "status": "error",
                    "error": f"Team generation failed: {e}",
                }

    threading.Thread(target=_run, daemon=True).start()
    return {"job_id": job_id}


@get("/generate/{job_id:str}", sync_to_thread=False)
def get_generation_job(job_id: str) -> dict[str, Any]:
    with _jobs_lock:
        job = dict(_generation_jobs.get(job_id, {}))
    if not job:
        raise NotFoundException(detail="Job not found")
    if job["status"] == "error":
        error_msg = job.get("error", "Unknown error")
        is_unavailable = "timed out" in error_msg or "not found" in error_msg.lower()
        raise HTTPException(
            status_code=(
                HTTPStatus.SERVICE_UNAVAILABLE
                if is_unavailable
                else HTTPStatus.INTERNAL_SERVER_ERROR
            ),
            detail=error_msg,
        )
    return job


team_generation_router = Router(
    path="/admin/teams",
    route_handlers=[generate_team_config, get_generation_job],
)


# ===========================================================================
# /admin/bots/{id}/run-chunked + /admin/chunked-executions/* (3)
# ===========================================================================


_chunk_semaphore = threading.Semaphore(3)

# 07.M3 — upper bound on chunks (= spawned threads) per run_chunked request.
_MAX_CHUNKS_PER_REQUEST = 200


def _process_chunk(
    chunked_execution_id: str,
    chunk_result_id: str,
    chunk_content: str,
    total_chunks: int,
    bot_id: str,
) -> None:
    try:
        with _chunk_semaphore:
            bot_output = ""
            token_count = len(chunk_content) // 4
            try:
                from app.services.execution_service import ExecutionService

                bot = get_trigger(bot_id)
                if bot:
                    execution_id = ExecutionService.run_trigger(
                        trigger=bot, message_text=chunk_content, trigger_type="manual"
                    )
                    if execution_id:
                        import time

                        from app.services.execution_log_service import ExecutionLogService

                        for _ in range(120):
                            if not ExecutionLogService.is_running(execution_id):
                                log = ExecutionLogService.get_log(execution_id)
                                if log:
                                    bot_output = log.get("output", "")
                                    token_count = log.get("token_count", token_count)
                                break
                            time.sleep(1)
            except Exception as e:
                logger.warning("Bot execution for chunk %s failed: %s", chunk_result_id, e)
                bot_output = f"Error processing chunk: {e}"
            update_chunk_result(chunk_result_id, bot_output, token_count)
    except Exception as e:
        logger.error("Chunk processing error for %s: %s", chunk_result_id, e)
        update_chunk_result(chunk_result_id, f"Error: {e}", 0, status="failed")

    try:
        completed = increment_completed_chunks(chunked_execution_id)
        if completed >= total_chunks:
            _finalize_chunked_execution(chunked_execution_id)
    except Exception as e:
        logger.error("Failed to check chunk completion: %s", e)


def _finalize_chunked_execution(chunked_execution_id: str) -> None:
    try:
        results = get_chunk_results(chunked_execution_id)
        chunk_dicts = [
            {
                "chunk_index": r["chunk_index"],
                "bot_output": r.get("bot_output", ""),
                "chunk_content": r.get("chunk_content", ""),
                "token_count": r.get("token_count", 0),
            }
            for r in results
        ]
        merged = ChunkService.merge_chunk_results(chunk_dicts)
        update_chunked_execution_status(
            chunked_execution_id,
            status="completed",
            merged_output=merged["merged_output"],
            unique_findings_count=len(merged["unique_findings"]),
            duplicate_count=merged["duplicate_count"],
        )
    except Exception as e:
        logger.error("Failed to finalize chunked execution %s: %s", chunked_execution_id, e)
        update_chunked_execution_status(chunked_execution_id, status="failed")


@post("/bots/{bot_id:str}/run-chunked", status_code=201, sync_to_thread=False)
def run_chunked(bot_id: str, data: dict) -> dict[str, Any]:
    if not get_trigger(bot_id):
        raise NotFoundException(detail="Bot not found")
    body = data or {}
    content = body.get("content")
    if not content:
        raise ClientException(detail="Missing required field: content")
    chunks = ChunkService.chunk_code(content, max_chars=body.get("max_chunk_chars"))
    # 07.M3 — bound the number of chunks/threads spawned per request so a huge
    # payload can't fan out into an unbounded thread storm.
    if len(chunks) > _MAX_CHUNKS_PER_REQUEST:
        raise ClientException(
            detail=(
                f"Content produces too many chunks "
                f"({len(chunks)} > {_MAX_CHUNKS_PER_REQUEST}); split the request"
            )
        )
    chunked_execution_id = create_chunked_execution(bot_id, len(chunks))
    if not chunked_execution_id:
        raise HTTPException(status_code=500, detail="Failed to create chunked execution")
    for idx, chunk_content in enumerate(chunks):
        chunk_result_id = create_chunk_result(chunked_execution_id, idx, chunk_content)
        if chunk_result_id:
            threading.Thread(
                target=_process_chunk,
                args=(
                    chunked_execution_id,
                    chunk_result_id,
                    chunk_content,
                    len(chunks),
                    bot_id,
                ),
                daemon=True,
            ).start()
    return {
        "chunked_execution_id": chunked_execution_id,
        "bot_id": bot_id,
        "total_chunks": len(chunks),
        "status": "processing",
    }


@get("/chunked-executions/{chunked_execution_id:str}", sync_to_thread=False)
def chunked_execution_status(chunked_execution_id: str) -> Any:
    execution = get_chunked_execution(chunked_execution_id)
    if not execution:
        raise NotFoundException(detail="Chunked execution not found")
    return execution


@get(
    "/chunked-executions/{chunked_execution_id:str}/results",
    sync_to_thread=False,
)
def chunked_execution_results(chunked_execution_id: str) -> dict[str, Any]:
    execution = get_chunked_execution(chunked_execution_id)
    if not execution:
        raise NotFoundException(detail="Chunked execution not found")
    if execution["status"] not in ("completed", "failed"):
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail={
                "error": "Chunked execution is still processing",
                "status": execution["status"],
                "completed_chunks": execution["completed_chunks"],
                "total_chunks": execution["total_chunks"],
            },
        )
    return {
        "chunked_execution_id": chunked_execution_id,
        "total_chunks": execution["total_chunks"],
        "unique_findings_count": execution.get("unique_findings_count", 0),
        "duplicate_count": execution.get("duplicate_count", 0),
        "merged_output": execution.get("merged_output", ""),
        "status": execution["status"],
        "chunk_results": get_chunk_results(chunked_execution_id),
    }


chunks_router = Router(
    path="/admin",
    route_handlers=[run_chunked, chunked_execution_status, chunked_execution_results],
)


# ===========================================================================
# /admin/super-agents/{id}/sessions/{sid}/chat (1; /chat/stream stays on Flask)
# ===========================================================================


def _resolve_chat_session(data: dict, super_agent_id: str, session_id: str) -> dict[str, Any]:
    from app.db.project_sa_instances import get_project_sa_instance

    session = get_super_agent_session(session_id)
    if not session:
        raise NotFoundException(detail="Session not found")
    status = session.get("status")
    if status in ("paused", "completed") or not SuperAgentSessionService.get_session_state(
        session_id
    ):
        success, err = SuperAgentSessionService.resume_session(session_id)
        if not success:
            raise ClientException(detail=err or "Failed to reactivate session")

    backend = data.get("backend", "auto")
    effective_backend = backend if backend != "auto" else None
    instance = None
    if super_agent_id.startswith("psa-"):
        instance = get_project_sa_instance(super_agent_id)
        if not instance:
            raise NotFoundException(detail="Instance not found")
        if not effective_backend:
            sa = get_super_agent(instance["template_sa_id"])
            effective_backend = (sa.get("backend_type") if sa else None) or "claude"
    else:
        if not effective_backend:
            sa = get_super_agent(super_agent_id)
            effective_backend = (sa.get("backend_type") if sa else None) or "claude"
        if not instance and session.get("instance_id"):
            instance = get_project_sa_instance(session["instance_id"])

    chat_mode = data.get("chat_mode")
    if not chat_mode and instance:
        chat_mode = instance.get("default_chat_mode", "management")

    cwd = None
    session_wt = session.get("worktree_path")
    if session_wt:
        cwd = session_wt
    elif session.get("session_type") == "leader" and session.get("project_id"):
        from app.db.projects import get_project as _get_project

        proj = _get_project(session["project_id"])
        if proj:
            cwd = proj.get("local_path")
    elif instance and chat_mode == "work":
        cwd = instance.get("worktree_path")

    return {
        "session": session,
        "effective_backend": effective_backend,
        "account_id": data.get("account_id"),
        "model": data.get("model"),
        "instance": instance,
        "chat_mode": chat_mode,
        "cwd": cwd,
    }


@post(
    "/{super_agent_id:str}/sessions/{session_id:str}/chat",
    sync_to_thread=False,
)
def send_chat_message(super_agent_id: str, session_id: str, data: dict) -> dict[str, Any]:
    from app.db.ids import generate_message_id
    from app.services.chat_state_service import ChatStateService
    from app.services.streaming_helper import run_streaming_response

    body = data or {}
    if not body:
        raise ClientException(detail="JSON body required")
    content = (body.get("content") or "").strip()
    if not content:
        raise ClientException(detail="content is required")

    resolved = _resolve_chat_session(body, super_agent_id, session_id)
    effective_backend = resolved["effective_backend"]
    account_id = resolved["account_id"]
    model = resolved["model"]
    cwd = resolved["cwd"]
    chat_mode = resolved["chat_mode"]
    instance = resolved["instance"]
    _session_row = resolved["session"]

    # Determine RAG enablement: only leader sessions with a project get RAG.
    _session_project_id = _session_row.get("project_id")
    rag_enabled = _session_row.get("session_type") == "leader" and bool(_session_project_id)
    rag_project_id = _session_project_id if rag_enabled else None

    # Per-call CLI runner override from the AiChatPanel toggle. Non-bool
    # values fall back to None so the global ``agent_yolo_mode`` setting
    # decides — keeps the override unambiguous.
    raw_override = body.get("use_cli_agent")
    use_cli_agent = raw_override if isinstance(raw_override, bool) else None

    success, error = SuperAgentSessionService.send_message(
        session_id, content, backend=effective_backend
    )
    if not success:
        raise ClientException(detail=error)

    # Register the session in ChatStateService BEFORE pushing the user
    # message delta. `push_delta` silently no-ops on unregistered sessions,
    # so without this call the user's typed message would never reach
    # any reconnecting subscriber. `init_session` is idempotent.
    ChatStateService.init_session(session_id)

    message_id = generate_message_id()
    ChatStateService.push_delta(
        session_id,
        "message",
        {"role": "user", "content": content, "message_id": message_id},
    )
    run_streaming_response(
        session_id=session_id,
        super_agent_id=super_agent_id,
        backend=effective_backend,
        account_id=account_id,
        model=model,
        cwd=cwd,
        chat_mode=chat_mode,
        instance_id=instance["id"] if instance else None,
        use_cli_agent=use_cli_agent,
        rag_enabled=rag_enabled,
        rag_project_id=rag_project_id,
    )
    return {"status": "ok", "message_id": message_id}


super_agent_chat_router = Router(
    path="/admin/super-agents",
    route_handlers=[send_chat_message],
)
