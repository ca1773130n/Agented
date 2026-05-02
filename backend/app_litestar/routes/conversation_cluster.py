"""Wave 72 — conversation cluster CRUD (~25 routes).

plugin / command / hook / rule conversations. Each namespace exposes the
same shape: list (some), start, get, message, finalize, resume (some),
abandon. The SSE `/stream` endpoint stays on Flask until the dedicated
streaming wave because we want to lift the Litestar `Stream` pattern
across all conversation streams in one pass.
"""

from __future__ import annotations

from typing import Any, Callable

from litestar import Router, get, post
from litestar.exceptions import (
    ClientException,
    HTTPException,
    NotFoundException,
)

from app.services.command_conversation_service import CommandConversationService
from app.services.hook_conversation_service import HookConversationService
from app.services.plugin_conversation_service import PluginConversationService
from app.services.rule_conversation_service import RuleConversationService


def _result_or_raise(payload: tuple[Any, int]) -> Any:
    body, status = payload
    if status >= 400:
        msg = body.get("error") if isinstance(body, dict) else body
        if status == 404:
            raise NotFoundException(detail=str(msg))
        raise HTTPException(status_code=status, detail=str(msg))
    return body


def _make_conversation_router(
    *,
    path: str,
    service: Any,
    finalize_method: str,
    include_list: bool,
    include_resume: bool,
    name_prefix: str,
) -> Router:
    """Build a Litestar `Router` for one conversation namespace.

    `name_prefix` keeps handler names unique so several routers can share
    the same Litestar app without colliding on operation IDs.
    """

    finalize: Callable = getattr(service, finalize_method)

    @post("/start", sync_to_thread=False, name=f"{name_prefix}_start")
    def start_conversation() -> Any:
        return _result_or_raise(service.start_conversation())

    @get("/{conv_id:str}", sync_to_thread=False, name=f"{name_prefix}_get")
    def get_conversation(conv_id: str) -> Any:
        return _result_or_raise(service.get_conversation(conv_id))

    @post("/{conv_id:str}/message", sync_to_thread=False, name=f"{name_prefix}_message")
    def send_message(conv_id: str, data: dict) -> Any:
        body = data or {}
        if not body.get("message"):
            raise ClientException(detail="message is required")
        return _result_or_raise(
            service.send_message(
                conv_id,
                body["message"],
                backend=body.get("backend"),
                account_id=body.get("account_id"),
                model=body.get("model"),
            )
        )

    @post("/{conv_id:str}/finalize", sync_to_thread=False, name=f"{name_prefix}_finalize")
    def finalize_endpoint(conv_id: str) -> Any:
        return _result_or_raise(finalize(conv_id))

    @post("/{conv_id:str}/abandon", sync_to_thread=False, name=f"{name_prefix}_abandon")
    def abandon_conversation(conv_id: str) -> Any:
        return _result_or_raise(service.abandon_conversation(conv_id))

    handlers: list = [
        start_conversation,
        get_conversation,
        send_message,
        finalize_endpoint,
        abandon_conversation,
    ]

    if include_list:
        @get("/", sync_to_thread=False, name=f"{name_prefix}_list")
        def list_conversations() -> Any:
            return _result_or_raise(service.list_conversations())

        handlers.append(list_conversations)

    if include_resume:
        @post("/{conv_id:str}/resume", sync_to_thread=False, name=f"{name_prefix}_resume")
        def resume_conversation(conv_id: str) -> Any:
            return _result_or_raise(service.resume_conversation(conv_id))

        handlers.append(resume_conversation)

    return Router(path=path, route_handlers=handlers)


plugin_conversations_router = _make_conversation_router(
    path="/api/plugins/conversations",
    service=PluginConversationService,
    finalize_method="finalize_plugin",
    include_list=False,
    include_resume=False,
    name_prefix="plugin_conv",
)

command_conversations_router = _make_conversation_router(
    path="/api/commands/conversations",
    service=CommandConversationService,
    finalize_method="_finalize_entity",
    include_list=True,
    include_resume=True,
    name_prefix="command_conv",
)

hook_conversations_router = _make_conversation_router(
    path="/api/hooks/conversations",
    service=HookConversationService,
    finalize_method="_finalize_entity",
    include_list=True,
    include_resume=True,
    name_prefix="hook_conv",
)

rule_conversations_router = _make_conversation_router(
    path="/api/rules/conversations",
    service=RuleConversationService,
    finalize_method="_finalize_entity",
    include_list=True,
    include_resume=True,
    name_prefix="rule_conv",
)
