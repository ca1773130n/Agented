"""Multi-backend fan-out and compound synthesis services.

AllModeService fans out a chat message to multiple AI backends simultaneously,
streaming each response through the existing SSE channel with backend-tagged
deltas. CompoundModeService extends this with a two-phase approach: fan-out
then synthesis via a primary backend.

Architecture:
    - One daemon thread per backend (not one SSE connection per backend)
    - All backends stream through a SINGLE SSE connection via ChatStateService
    - Frontend demultiplexes by reading the 'backend' field in each delta event
    - 30-second per-backend timeout terminates slow backends with backend_timeout
"""

import logging
import threading
import time
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class AllModeService:
    """Fan-out chat to multiple backends simultaneously.

    Uses one daemon thread per backend. Each thread calls stream_llm_response()
    and pushes deltas through ChatStateService with a 'backend' field for
    multiplexed SSE delivery. Frontend demultiplexes by reading the backend field.

    IMPORTANT: All backends stream through a SINGLE SSE connection (the session's
    existing ChatStateService subscription). Do NOT create separate SSE connections
    per backend -- that would hit the browser's 6-connection limit.
    """

    @classmethod
    def fan_out(
        cls,
        session_id: str,
        messages: list,
        backends: List[str],
        model: Optional[str] = None,
        account_email: Optional[str] = None,
        timeout: int = 30,
    ) -> dict:
        """Start parallel streaming to all backends. Returns immediately.

        Args:
            session_id: The chat session ID for delta delivery.
            messages: LLM message list (system + conversation history).
            backends: List of backend type names (e.g. ["claude", "gemini"]).
            model: Optional model override (applied to all backends).
            account_email: Optional account email for proxy routing.
            timeout: Per-backend timeout in seconds (default 30).

        Returns:
            execution_map: dict of {backend: "streaming"} for each backend.
        """
        execution_map = {}
        threads = []
        for backend in backends:
            execution_map[backend] = "streaming"
            thread = threading.Thread(
                target=cls._stream_backend,
                args=(session_id, backend, messages, model, account_email, timeout),
                daemon=True,
            )
            thread.start()
            threads.append(thread)

        # Completion waiter: push idle status after all backend threads finish
        def _on_all_complete():
            for t in threads:
                t.join(timeout=timeout + 10)
            from .chat_state_service import ChatStateService

            ChatStateService.push_status(session_id, "idle")

        threading.Thread(target=_on_all_complete, daemon=True).start()

        return execution_map

    @classmethod
    def _stream_backend(cls, session_id, backend, messages, model, account_email, timeout):
        """Stream a single backend response, pushing deltas with backend tag."""
        from .chat_state_service import ChatStateService
        from .conversation_streaming import stream_llm_response

        start = time.time()
        try:
            for chunk in stream_llm_response(
                messages, model=model, account_email=account_email, backend=backend
            ):
                if time.time() - start > timeout:
                    ChatStateService.push_delta(
                        session_id,
                        "backend_timeout",
                        {"backend": backend},
                    )
                    return
                if chunk:
                    ChatStateService.push_delta(
                        session_id,
                        "content_delta",
                        {"text": chunk, "backend": backend},
                    )
        except Exception as e:
            logger.exception("Backend %s streaming error for session %s", backend, session_id)
            ChatStateService.push_delta(
                session_id,
                "backend_error",
                {"backend": backend, "error": str(e)},
            )
            return

        ChatStateService.push_delta(
            session_id,
            "backend_complete",
            {"backend": backend},
        )


class CompoundModeService:
    """Two-phase compound mode: fan-out then synthesis.

    Phase 1: Fan out to all backends (same threading model as AllModeService)
    Phase 2: Collect responses, send synthesis prompt to primary backend

    Response collection uses threading.Event per backend and a dict accumulator.
    A waiter thread blocks until all backends complete (or timeout), then builds
    a synthesis prompt and streams from the primary backend.
    """

    # Collected responses per session: {session_id: {backend: text}}
    _collectors: Dict[str, dict] = {}
    _events: Dict[str, Dict[str, threading.Event]] = {}
    _lock = threading.Lock()

    @classmethod
    def start(
        cls,
        session_id: str,
        messages: list,
        backends: List[str],
        primary_backend: str,
        model: Optional[str] = None,
        account_email: Optional[str] = None,
        timeout: int = 30,
        synthesis_max_tokens: int = 1000,
    ) -> dict:
        """Start compound mode: fan-out then synthesis.

        Args:
            session_id: The chat session ID.
            messages: LLM message list.
            backends: List of backend type names.
            primary_backend: Backend to use for synthesis phase.
            model: Optional model override.
            account_email: Optional account email for proxy routing.
            timeout: Per-backend timeout in seconds.
            synthesis_max_tokens: Max tokens for synthesis response.

        Returns:
            execution_map: dict of {backend: "streaming"}.
        """
        # Initialize collector
        with cls._lock:
            cls._collectors[session_id] = {}
            cls._events[session_id] = {b: threading.Event() for b in backends}

        # Fan out with collection wrapper
        execution_map = {}
        for backend in backends:
            execution_map[backend] = "streaming"
            thread = threading.Thread(
                target=cls._stream_and_collect,
                args=(session_id, backend, messages, model, account_email, timeout),
                daemon=True,
            )
            thread.start()

        # Start synthesis waiter thread
        threading.Thread(
            target=cls._wait_and_synthesize,
            args=(
                session_id,
                backends,
                primary_backend,
                messages,
                model,
                account_email,
                timeout,
                synthesis_max_tokens,
            ),
            daemon=True,
        ).start()

        return execution_map

    @classmethod
    def _stream_and_collect(cls, session_id, backend, messages, model, account_email, timeout):
        """Stream backend and collect full response for synthesis."""
        from .chat_state_service import ChatStateService
        from .conversation_streaming import stream_llm_response

        start = time.time()
        collected = []
        try:
            for chunk in stream_llm_response(
                messages, model=model, account_email=account_email, backend=backend
            ):
                if time.time() - start > timeout:
                    ChatStateService.push_delta(
                        session_id,
                        "backend_timeout",
                        {"backend": backend},
                    )
                    break
                if chunk:
                    collected.append(chunk)
                    ChatStateService.push_delta(
                        session_id,
                        "content_delta",
                        {"text": chunk, "backend": backend},
                    )
        except Exception as e:
            logger.exception("Backend %s streaming error for session %s", backend, session_id)
            ChatStateService.push_delta(
                session_id,
                "backend_error",
                {"backend": backend, "error": str(e)},
            )

        # Store collected response and signal completion
        full_text = "".join(collected)
        with cls._lock:
            if session_id in cls._collectors:
                cls._collectors[session_id][backend] = full_text
            if session_id in cls._events and backend in cls._events[session_id]:
                cls._events[session_id][backend].set()

        ChatStateService.push_delta(
            session_id,
            "backend_complete",
            {"backend": backend},
        )

    @classmethod
    def _wait_and_synthesize(
        cls,
        session_id,
        backends,
        primary_backend,
        original_messages,
        model,
        account_email,
        timeout,
        synthesis_max_tokens,
    ):
        """Wait for all backends, then synthesize."""
        from .chat_state_service import ChatStateService
        from .conversation_streaming import stream_llm_response

        # Wait for all backends (with total timeout)
        with cls._lock:
            events = cls._events.get(session_id, {})

        for backend in backends:
            event = events.get(backend)
            if event and not event.wait(timeout=timeout):
                logger.warning(
                    "Backend %s timed out during compound wait for session %s",
                    backend,
                    session_id,
                )

        # Get collected responses
        with cls._lock:
            collected = cls._collectors.pop(session_id, {})
            cls._events.pop(session_id, None)

        if not collected:
            ChatStateService.push_delta(
                session_id,
                "compound_error",
                {"error": "No backend responses collected for synthesis"},
            )
            ChatStateService.push_status(session_id, "idle")
            return

        # Build synthesis prompt
        # Truncate each response to first ~1000 tokens (approx 4000 chars) to avoid
        # context overflow
        MAX_CHARS_PER_RESPONSE = 4000
        response_parts = []
        for backend, text in collected.items():
            truncated = text[:MAX_CHARS_PER_RESPONSE]
            if len(text) > MAX_CHARS_PER_RESPONSE:
                truncated += "... [truncated]"
            response_parts.append(f"## {backend.upper()} Response:\n{truncated}")

        synthesis_prompt = (
            "You received the following responses from different AI backends "
            "to the same question. Synthesize them into a single comprehensive answer. "
            "Note which backends agree/disagree and provide the best combined answer "
            "with attribution.\n\n" + "\n\n".join(response_parts)
        )

        synthesis_messages = original_messages[:-1] + [  # Keep system messages
            {"role": "user", "content": synthesis_prompt}
        ]

        # Signal synthesis phase starting
        ChatStateService.push_delta(
            session_id,
            "synthesis_start",
            {
                "primary_backend": primary_backend,
                "backends_collected": list(collected.keys()),
            },
        )

        # Stream synthesis from primary backend
        try:
            for chunk in stream_llm_response(
                synthesis_messages,
                model=model,
                account_email=account_email,
                backend=primary_backend,
            ):
                if chunk:
                    ChatStateService.push_delta(
                        session_id,
                        "synthesis_delta",
                        {"text": chunk, "backend": primary_backend},
                    )
        except Exception as e:
            logger.exception("Synthesis error for session %s via %s", session_id, primary_backend)
            ChatStateService.push_delta(
                session_id,
                "synthesis_error",
                {"error": str(e)},
            )
            ChatStateService.push_status(session_id, "idle")
            return

        ChatStateService.push_delta(
            session_id,
            "synthesis_complete",
            {"primary_backend": primary_backend},
        )
        ChatStateService.push_status(session_id, "idle")
