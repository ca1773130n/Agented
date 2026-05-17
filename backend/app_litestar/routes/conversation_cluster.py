"""Wave 72 — conversation cluster CRUD (~25 routes).

plugin / command / hook / rule conversations. Each namespace exposes the
same shape: list (some), start, get, message, finalize, resume (some),
abandon. The SSE `/stream` endpoint stays on Flask until the dedicated
streaming wave because we want to lift the Litestar `Stream` pattern
across all conversation streams in one pass.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

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
from app_litestar.auth import Caller


def _caller_user_id(caller: Caller | None) -> Optional[str]:
    """v0.7.83 — single accessor so every conversation route
    uses the same source of truth for the operator id.
    """
    return getattr(caller, "user_id", None) if caller else None


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
    def start_conversation(caller: Caller) -> Any:
        return _result_or_raise(
            service.start_conversation(user_id=_caller_user_id(caller))
        )

    @get("/{conv_id:str}", sync_to_thread=False, name=f"{name_prefix}_get")
    def get_conversation(conv_id: str, caller: Caller) -> Any:
        return _result_or_raise(
            service.get_conversation(conv_id, caller_user_id=_caller_user_id(caller))
        )

    @post("/{conv_id:str}/message", sync_to_thread=False, name=f"{name_prefix}_message")
    def send_message(conv_id: str, data: dict, caller: Caller) -> Any:
        body = data or {}
        if not body.get("message"):
            raise ClientException(detail="message is required")
        # Per-call CLI-runner override from the AiChatPanel toggle. Only
        # bool values are honored; anything else falls back to the
        # global YOLO setting.
        raw_override = body.get("use_cli_agent")
        use_cli_agent = raw_override if isinstance(raw_override, bool) else None
        # v0.7.83 — Plugin's send_message doesn't accept
        # ``use_cli_agent`` (no CLI runner toggle on /plugins/new);
        # base service does. Pass conditionally.
        send_kwargs = {
            "backend": body.get("backend"),
            "account_id": body.get("account_id"),
            "model": body.get("model"),
            "caller_user_id": _caller_user_id(caller),
        }
        if service is not PluginConversationService:
            send_kwargs["use_cli_agent"] = use_cli_agent
        return _result_or_raise(
            service.send_message(conv_id, body["message"], **send_kwargs)
        )

    @post("/{conv_id:str}/finalize", sync_to_thread=False, name=f"{name_prefix}_finalize")
    def finalize_endpoint(conv_id: str, caller: Caller) -> Any:
        # v0.7.83 (codex BLOCK / 2nd pass) — every finalize now
        # gates ownership. Plugin's ``finalize_plugin`` does it
        # in-method; base subclasses use the new public
        # ``finalize_entity`` wrapper which gates ownership +
        # flips the DB status before/after calling the abstract
        # ``_finalize_entity``.
        return _result_or_raise(
            finalize(conv_id, caller_user_id=_caller_user_id(caller))
        )

    @post("/{conv_id:str}/abandon", sync_to_thread=False, name=f"{name_prefix}_abandon")
    def abandon_conversation(conv_id: str, caller: Caller) -> Any:
        return _result_or_raise(
            service.abandon_conversation(
                conv_id, caller_user_id=_caller_user_id(caller)
            )
        )

    @get("/active", sync_to_thread=False, name=f"{name_prefix}_active")
    def list_active(caller: Caller) -> Any:
        """v0.7.83 — list this entity-type's active conversations
        for the calling user. Powers the wizard's auto-resume on
        cold-cache loads.
        """
        return _result_or_raise(
            service.list_active(user_id=_caller_user_id(caller))
        )

    handlers: list = [
        start_conversation,
        get_conversation,
        send_message,
        finalize_endpoint,
        abandon_conversation,
        list_active,
    ]

    if include_list:
        @get("/", sync_to_thread=False, name=f"{name_prefix}_list")
        def list_conversations(caller: Caller) -> Any:
            return _result_or_raise(
                service.list_conversations(user_id=_caller_user_id(caller))
            )

        handlers.append(list_conversations)

    if include_resume:
        @post("/{conv_id:str}/resume", sync_to_thread=False, name=f"{name_prefix}_resume")
        def resume_conversation(conv_id: str, caller: Caller) -> Any:
            return _result_or_raise(
                service.resume_conversation(
                    conv_id, caller_user_id=_caller_user_id(caller)
                )
            )

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
    # v0.7.83 — switched from _finalize_entity (abstract,
    # no ownership check) to finalize_entity (public wrapper
    # that gates ownership + flips DB status). Same for hook
    # and rule below.
    finalize_method="finalize_entity",
    include_list=True,
    include_resume=True,
    name_prefix="command_conv",
)

hook_conversations_router = _make_conversation_router(
    path="/api/hooks/conversations",
    service=HookConversationService,
    finalize_method="finalize_entity",
    include_list=True,
    include_resume=True,
    name_prefix="hook_conv",
)

rule_conversations_router = _make_conversation_router(
    path="/api/rules/conversations",
    service=RuleConversationService,
    finalize_method="finalize_entity",
    include_list=True,
    include_resume=True,
    name_prefix="rule_conv",
)
