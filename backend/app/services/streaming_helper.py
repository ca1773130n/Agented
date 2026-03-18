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
    """
    _session_id = session_id
    _super_agent_id = super_agent_id

    def _stream_response():
        try:
            from .conversation_streaming import stream_llm_response

            ChatStateService.push_status(_session_id, "streaming")

            system_prompt = SuperAgentSessionService.assemble_system_prompt(
                _super_agent_id, _session_id
            )
            # Build LLM messages: system prompt first, then conversation log
            state = SuperAgentSessionService.get_session_state(_session_id)
            llm_messages = []
            if system_prompt:
                llm_messages.append({"role": "system", "content": system_prompt})
            if state and state.get("conversation_log"):
                for msg in state["conversation_log"]:
                    llm_messages.append(
                        {"role": msg.get("role", "user"), "content": msg.get("content", "")}
                    )

            accumulated = []
            for chunk in stream_llm_response(
                llm_messages,
                model=model,
                account_email=account_id,
                backend=backend,
            ):
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
            try:
                ChatStateService.push_delta(_session_id, "error", {"error": error_msg})
                ChatStateService.push_status(_session_id, "error")
            except Exception:
                logger.exception("Failed to propagate streaming error for session %s", _session_id)

            if on_error:
                on_error(error_msg)

    thread = threading.Thread(target=_stream_response, daemon=True)
    thread.start()
