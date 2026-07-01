"""Wave 78 — final SSE streaming wave (14 endpoints).

Lifts every remaining `text/event-stream` route off Flask onto Litestar
using the `Stream` response. Each handler delegates to its existing
service-level subscribe generator; only the response wrapper changes.

Layout — one Router per stream-path family so the URL prefixes coexist
with the CRUD routers from earlier waves without collisions.
"""

from __future__ import annotations

from typing import Any

from litestar import Request, Router, get, post
from litestar.exceptions import (
    ClientException,
    NotFoundException,
)
from litestar.response import Stream

from app.database import get_project, get_super_agent_sessions
from app.services.agent_conversation_service import AgentConversationService
from app.services.agent_message_bus_service import AgentMessageBusService
from app.services.backend_cli_service import BackendCLIService
from app.services.chat_state_service import ChatStateService
from app.services.command_conversation_service import CommandConversationService
from app.services.execution_log_service import ExecutionLogService
from app.services.hook_conversation_service import HookConversationService
from app.services.plugin_conversation_service import PluginConversationService
from app.services.project_session_manager import ProjectSessionManager
from app.services.rule_conversation_service import RuleConversationService
from app.services.session_sharing_service import SessionSharingService
from app.services.setup_execution_service import SetupExecutionService
from app.services.team_generation_service import TeamGenerationService
from app_litestar.auth import Caller

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _sse_response(generator) -> Stream:
    return Stream(generator, media_type="text/event-stream", headers=SSE_HEADERS)


# ===========================================================================
# /admin/executions/{id}/stream
# ===========================================================================


@get("/{execution_id:str}/stream", media_type="text/event-stream", sync_to_thread=False)
def stream_execution(execution_id: str) -> Stream:
    if not ExecutionLogService.get_execution(execution_id):
        raise NotFoundException(detail="Execution not found")

    def generate():
        for event in ExecutionLogService.subscribe(execution_id):
            yield event

    return _sse_response(generate())


execution_stream_router = Router(
    path="/admin/executions",
    route_handlers=[stream_execution],
)


# ===========================================================================
# /api/{plugins,commands,hooks,rules,agents}/conversations/{conv_id}/stream
# ===========================================================================


def _make_conversation_stream(name: str, service: Any) -> Router:
    """Build a stream router for one conversation namespace.

    v0.7.83 — precheck ownership via the service's
    ``can_subscribe`` so an unauthorized caller gets a real HTTP
    404 instead of a 200 SSE stream with an in-band error event.
    Same shape as the skill stream route (codex WARN B / v0.7.78).
    """

    @get(
        "/{conv_id:str}/stream",
        media_type="text/event-stream",
        sync_to_thread=False,
        name=f"{name}_stream",
    )
    def stream_conversation(conv_id: str, caller: Caller) -> Stream:
        user_id = getattr(caller, "user_id", None) if caller else None
        if hasattr(service, "can_subscribe") and not service.can_subscribe(conv_id, user_id):
            raise NotFoundException(detail="Conversation not found")

        def generate():
            sub = (
                service.subscribe(conv_id, caller_user_id=user_id)
                if hasattr(service, "can_subscribe")
                else service.subscribe(conv_id)
            )
            for event in sub:
                yield event

        return _sse_response(generate())

    return Router(path=f"/api/{name}/conversations", route_handlers=[stream_conversation])


plugin_conversation_stream_router = _make_conversation_stream("plugins", PluginConversationService)
command_conversation_stream_router = _make_conversation_stream(
    "commands", CommandConversationService
)
hook_conversation_stream_router = _make_conversation_stream("hooks", HookConversationService)
rule_conversation_stream_router = _make_conversation_stream("rules", RuleConversationService)
agent_conversation_stream_router = _make_conversation_stream("agents", AgentConversationService)


# ===========================================================================
# /api/projects/{id}/chat/stream + /api/projects/{id}/sessions/{sid}/stream
# ===========================================================================


@get(
    "/{project_id:str}/chat/stream",
    media_type="text/event-stream",
    sync_to_thread=False,
)
def stream_project_chat(project_id: str, request: Request) -> Stream:
    project = get_project(project_id)
    if not project:
        raise NotFoundException(detail="Project not found")
    sa_id = project.get("manager_super_agent_id")
    if not sa_id:
        raise NotFoundException(detail="No manager agent configured")
    sessions = get_super_agent_sessions(sa_id)
    active = [s for s in sessions if s.get("status") == "active"]
    if not active:
        raise NotFoundException(detail="No active chat session")
    session_id = active[0]["id"]

    last_event_id = request.headers.get("Last-Event-ID", "0")
    try:
        last_seq = int(last_event_id)
    except (ValueError, TypeError):
        last_seq = 0

    def generate():
        for event in ChatStateService.subscribe(session_id, last_seq=last_seq):
            yield event

    return _sse_response(generate())


def _project_session_owner(session_id: str) -> str | None:
    """Return ``project_sessions.created_by`` for a session, or None if unknown.

    Delegates to the canonical ``get_project_session_owner`` helper. ``None``
    means the owner is UNKNOWN (absent row / NULL column / lookup error) and the
    gate MUST fail closed on it — a session with no recorded owner is not public.
    ``created_by`` is added in migration 178 (25-01) and backfilled on create.
    """
    from app.db.session_shares import get_project_session_owner

    return get_project_session_owner(session_id)


@get(
    "/{project_id:str}/sessions/{session_id:str}/stream",
    media_type="text/event-stream",
    sync_to_thread=False,
)
def stream_project_session(
    project_id: str, session_id: str, caller: Caller, request: Request
) -> Stream:
    """Stream a running project session (owner/token-gated — 25-01 locked #5).

    SECURITY (25 BLOCKER — fail CLOSED): previously ANY authenticated caller could
    stream ANY session, and a session with a NULL owner was streamable by anyone
    (fail OPEN). Now a caller may stream ONLY when they are:

      * an ``admin``, OR
      * the session's recorded owner (``created_by`` == caller), OR
      * a holder of a valid scoped share token (``?share_token=``).

    A NULL/unknown owner grants NOTHING to a non-admin, non-token caller — an
    unattributed session is treated as forbidden, not public. Every denied path
    raises ``NotFoundException`` (a 404 leaks less than a 403).
    """
    del project_id
    owner = _project_session_owner(session_id)
    user_id = getattr(caller, "user_id", None) if caller else None
    role = getattr(caller, "role", None) if caller else None
    authorized = role == "admin" or (
        owner is not None and user_id is not None and user_id == owner
    )
    if not authorized:
        share_token = request.query_params.get("share_token")
        if not (share_token and SessionSharingService.can_attach(share_token, session_id)):
            raise NotFoundException(detail="Session not found")

    def generate():
        for event in ProjectSessionManager.subscribe(session_id):
            yield event

    return _sse_response(generate())


@get(
    "/{token:str}/stream",
    media_type="text/event-stream",
    sync_to_thread=False,
)
def stream_shared_session(token: str) -> Stream:
    """Read/chat attach to a shared session by scoped token (25-01 live-share).

    A tokenless teammate enters by URL; the token is resolved IN-HANDLER (the path
    is in the ApiKeyMiddleware bypass set). On miss/expiry/revocation → 404
    (mirrors ``_make_conversation_stream``). On hit, join the EXISTING
    ``ProjectSessionManager.subscribe`` fan-out — the SAME generator, NOT a second
    broadcast path — so the teammate is just one more ``Queue`` in ``_subscribers``.
    """
    from app.db.session_shares import resolve_share_token

    row = resolve_share_token(token)
    if not row:
        raise NotFoundException(detail="Shared session not found")
    session_id = row["session_id"]

    def generate():
        for event in ProjectSessionManager.subscribe(session_id):
            yield event

    return _sse_response(generate())


project_stream_router = Router(
    path="/api/projects",
    route_handlers=[stream_project_chat, stream_project_session],
)

shared_session_stream_router = Router(
    path="/api/shared-sessions",
    route_handlers=[stream_shared_session],
)


# ===========================================================================
# /admin/backends/{id}/connect/{sid}/stream + /admin/backends/test/{tid}/stream
# ===========================================================================


@get(
    "/{backend_id:str}/connect/{session_id:str}/stream",
    media_type="text/event-stream",
    sync_to_thread=False,
)
def stream_backend_connect(backend_id: str, session_id: str) -> Stream:
    del backend_id
    if not BackendCLIService.get_status(session_id):
        raise NotFoundException(detail="Session not found")

    def generate():
        for event in BackendCLIService.subscribe(session_id):
            yield event

    return _sse_response(generate())


@get(
    "/test/{test_id:str}/stream",
    media_type="text/event-stream",
    sync_to_thread=False,
)
def stream_backend_test(test_id: str) -> Stream:
    from app.services.backend_test_service import BackendTestService

    def generate():
        for event in BackendTestService.subscribe_test(test_id):
            yield event

    return _sse_response(generate())


backends_stream_router = Router(
    path="/admin/backends",
    route_handlers=[stream_backend_connect, stream_backend_test],
)


# ===========================================================================
# /api/setup/{execution_id}/stream
# ===========================================================================


@get(
    "/{execution_id:str}/stream",
    media_type="text/event-stream",
    sync_to_thread=False,
)
def stream_setup(execution_id: str) -> Stream:
    if not SetupExecutionService.get_status(execution_id):
        raise NotFoundException(detail="Setup execution not found")

    def generate():
        for event in SetupExecutionService.subscribe(execution_id):
            yield event

    return _sse_response(generate())


setup_stream_router = Router(
    path="/api/setup",
    route_handlers=[stream_setup],
)


# ===========================================================================
# /admin/super-agents/{id}/messages/stream + sessions/{sid}/chat/stream
# ===========================================================================


@get(
    "/{super_agent_id:str}/messages/stream",
    media_type="text/event-stream",
    sync_to_thread=False,
)
def stream_super_agent_messages(super_agent_id: str) -> Stream:
    def generate():
        yield from AgentMessageBusService.subscribe(super_agent_id)

    return _sse_response(generate())


def _ensure_chat_session_registered(session_id: str) -> bool:
    """Pre-register a REAL super-agent session in ChatStateService before the
    SSE subscribes.

    The leader chat opens this stream when its panel MOUNTS — before any
    message turn has registered the session (unlike the sketch/message flow,
    where the POST eagerly init_session's first). Without this, an idle or
    just-refreshed leader chat subscribes to an unregistered session and gets
    a "Session not found" error → the EventSource reconnect-loops. Registering
    a real session (idempotent) makes the subscriber wait for the first turn's
    deltas instead. A genuinely unknown session_id is left unregistered so
    subscribe still reports not-found. Returns True if registered.
    """
    from app.db.super_agents import get_super_agent_session

    if get_super_agent_session(session_id) is None:
        return False
    ChatStateService.init_session(session_id)
    return True


@get(
    "/{super_agent_id:str}/sessions/{session_id:str}/chat/stream",
    media_type="text/event-stream",
    sync_to_thread=False,
)
def stream_super_agent_chat(super_agent_id: str, session_id: str, request: Request) -> Stream:
    del super_agent_id
    last_event_id = request.headers.get("Last-Event-ID", "0")
    try:
        last_seq = int(last_event_id)
    except (ValueError, TypeError):
        last_seq = 0

    def generate():
        _ensure_chat_session_registered(session_id)
        yield from ChatStateService.subscribe(session_id, last_seq)

    return _sse_response(generate())


super_agents_stream_router = Router(
    path="/admin/super-agents",
    route_handlers=[stream_super_agent_messages, stream_super_agent_chat],
)


# ===========================================================================
# /admin/teams/generate/stream  (POST → SSE)
# ===========================================================================


@post("/generate/stream", media_type="text/event-stream")
async def stream_team_generation(data: dict) -> Stream:
    body = data or {}
    description = body.get("description", "")
    if not description or len(description) < 10:
        raise ClientException(detail="description is required and must be at least 10 characters")

    def generate():
        yield from TeamGenerationService.generate_streaming(description)

    return _sse_response(generate())


teams_stream_router = Router(
    path="/admin/teams",
    route_handlers=[stream_team_generation],
)
