"""Shared streaming helper for LLM response generation.

Extracted from super_agent_chat.py to be reusable by both the Playground
chat endpoint and the Sketch execution service.
"""

import logging
import threading
import traceback
from typing import Callable, Optional

from .chat_state_service import ChatStateService
from .super_agent_session_service import SuperAgentSessionService

logger = logging.getLogger(__name__)


def run_streaming_response(
    session_id: str,
    super_agent_id: str,
    backend: str,
    account_id: Optional[str] = None,
    model: Optional[str] = None,
    on_complete: Optional[Callable] = None,
    on_error: Optional[Callable] = None,
    cwd: Optional[str] = None,
    chat_mode: Optional[str] = None,
    instance_id: Optional[str] = None,
    use_cli_agent: Optional[bool] = None,
) -> None:
    """Launch a background thread that streams an LLM response.

    Assembles system prompt, builds message history, calls stream_llm_response(),
    pushes content_delta chunks via ChatStateService (SSE), persists the
    assistant message, and updates backend last used.

    Args:
        session_id: The session to stream into.
        super_agent_id: The super agent generating the response.
        backend: LLM backend type (e.g., 'claude', 'litellm').
        account_id: Optional account for API key resolution (passed as account_email).
        model: Optional model override.
        on_complete: Called after successful completion (no args).
        on_error: Called on error with (error_message: str).
        cwd: Optional working directory for CLI subprocess (work mode).
        chat_mode: Optional chat mode ('management' or 'work').
        instance_id: Optional project SA instance ID for project context.
        use_cli_agent: When ``True``, route through the CLI agent runner
            (claude/codex/gemini subprocess with tool privileges) instead
            of CLIProxyAPI. When ``None`` (default), reads the global
            ``agent_yolo_mode`` setting — on by default. Pass ``False``
            to force CLIProxyAPI even when YOLO is globally on (the
            ai-accounts chat panel uses this to keep its pure-token
            flow).
    """
    _session_id = session_id
    _super_agent_id = super_agent_id

    # Register the session in ChatStateService synchronously, BEFORE the
    # streaming thread is spawned. The frontend opens its SSE immediately
    # after the POST that triggered us returns; if the session isn't
    # already registered, `ChatStateService.subscribe()` yields a
    # "Session not found" error event and closes the stream. The user
    # sees that as a "Connection lost" toast on the panel.
    #
    # `init_session` is idempotent — when the caller (project chat,
    # super-agent session create) already registered the session it's a
    # no-op. Doing this here covers every caller of `run_streaming_response`
    # in one place: sketches, playground chat, autofix, agent chats.
    ChatStateService.init_session(_session_id)

    def _stream_response():
        try:
            from .cli_agent_runner_service import (
                is_yolo_mode_enabled,
                resolve_account_config_dir,
                should_route_via_cli_agent,
                stream_via_cli_agent,
            )
            from .conversation_streaming import stream_llm_response

            ChatStateService.push_status(_session_id, "streaming")

            system_prompt = SuperAgentSessionService.assemble_system_prompt(
                _super_agent_id,
                _session_id,
                chat_mode=chat_mode,
                instance_id=instance_id,
            )
            # Build LLM messages: system prompt first, then conversation log
            state = SuperAgentSessionService.get_session_state(_session_id)
            llm_messages = []
            if system_prompt:
                llm_messages.append({"role": "system", "content": system_prompt})
            if state and state.get("conversation_log"):
                # v0.7.97 — drop any conversation_log entry whose
                # content is missing or whitespace-only. CLIProxyAPI's
                # OpenAI translation rejects empty text content blocks
                # with "text content blocks must be non-empty", and
                # SuperAgent conversation_logs sometimes contain
                # empty-content turns (interrupted assistant streams,
                # tool-only messages where the tool serializer produced
                # no text payload, etc.). Mirrors the same defense the
                # other 3 conversation services already apply
                # (base/plugin/skill_conversation_service).
                for msg in state["conversation_log"]:
                    content = msg.get("content", "")
                    if not content or not content.strip():
                        continue
                    llm_messages.append(
                        {"role": msg.get("role", "user"), "content": content}
                    )

            # Routing decision lives in `should_route_via_cli_agent` so the
            # three streaming sites (this one, design conversations, project
            # chat) make the same choice. The helper also flips to the CLI
            # runner when CLIProxy is unreachable so a missing proxy can't
            # silently drop the SSE — see its docstring for the matrix.
            accumulated = []
            if should_route_via_cli_agent(backend, use_cli_agent):
                # Resolve the account's config directory so the spawned
                # CLI sees the right credential vault. Without this the
                # CLI loads ``~/.claude`` / ``~/.codex`` and reports
                # "Not logged in" — fatal because the harness has no
                # TTY to retry the login flow.
                config_dir = resolve_account_config_dir(account_id, backend)
                logger.info(
                    "Streaming via CLI agent runner (backend=%s, cwd=%s, config=%s)",
                    backend,
                    cwd,
                    config_dir,
                )
                stream_iter = stream_via_cli_agent(
                    llm_messages,
                    backend=backend,
                    cwd=cwd,
                    yolo=is_yolo_mode_enabled(),
                    model=model,
                    config_dir=config_dir,
                )
            else:
                stream_iter = stream_llm_response(
                    llm_messages,
                    model=model,
                    account_email=account_id,
                    backend=backend,
                    cwd=cwd,
                    chat_mode=chat_mode,
                )

            for chunk in stream_iter:
                if chunk:
                    accumulated.append(chunk)
                    ChatStateService.push_delta(_session_id, "content_delta", {"content": chunk})

            full_response = "".join(accumulated)
            if full_response:
                SuperAgentSessionService.add_assistant_message(
                    _session_id, full_response, backend=backend
                )
                # Track backend usage
                if backend:
                    try:
                        from ..db.backends import update_backend_last_used

                        update_backend_last_used(backend)
                    except Exception:
                        logger.error("Failed to update backend last used", exc_info=True)

            ChatStateService.push_delta(
                _session_id, "finish", {"content": full_response, "backend": backend}
            )
            ChatStateService.push_status(_session_id, "idle")

            if on_complete:
                on_complete()

        except Exception as e:
            error_msg = str(e)
            logger.exception("Streaming error for session %s", _session_id)
            from app.services.error_capture import capture_error

            capture_error(
                category="streaming_error",
                message=error_msg,
                stack_trace=traceback.format_exc(),
                context={"session_id": _session_id, "super_agent_id": _super_agent_id},
            )
            # v0.7.7: emit an activity event so the inspector timeline
            # surfaces model-streaming failures. Best-effort — must never
            # break the runtime.
            try:
                from app.services import super_agent_activity_service

                super_agent_activity_service.record(
                    super_agent_id=_super_agent_id,
                    session_id=_session_id,
                    event_type="error",
                    payload={
                        "source": "streaming_helper",
                        "backend": backend,
                        "model": model,
                    },
                    status="error",
                    error_message=error_msg,
                )
            except Exception:
                logger.warning(
                    "Failed to record super-agent streaming-error activity",
                    exc_info=True,
                )
            try:
                ChatStateService.push_delta(_session_id, "error", {"error": error_msg})
                ChatStateService.push_status(_session_id, "error")
            except Exception:
                logger.exception("Failed to propagate streaming error for session %s", _session_id)

            if on_error:
                on_error(error_msg)

    thread = threading.Thread(target=_stream_response, daemon=True)
    thread.start()
