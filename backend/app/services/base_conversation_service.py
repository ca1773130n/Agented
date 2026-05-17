"""Abstract base conversation service for interactive entity creation with SSE streaming."""

import abc
import datetime
import json
import logging
import os
import secrets
import string
import threading
from dataclasses import asdict, dataclass
from http import HTTPStatus
from queue import Empty, Queue
from typing import Dict, Generator, List, Optional, Tuple

from app.models.common import error_response

from ..database import (
    create_design_conversation,
    delete_old_design_conversations,
    get_design_conversation,
    list_design_conversations,
    update_design_conversation,
)

logger = logging.getLogger(__name__)

# Stale conversation cleanup threshold in seconds (default 30 minutes).
# Override via STALE_CONVERSATION_THRESHOLD_SECS environment variable.
STALE_CONVERSATION_THRESHOLD = int(os.environ.get("STALE_CONVERSATION_THRESHOLD_SECS", "1800"))


class WordBoundaryAccumulator:
    """Accumulate streaming text and flush at word boundaries to reduce SSE event frequency.

    Instead of sending every byte as a separate SSE event (potentially 100+ events/sec),
    this accumulator buffers text until a word boundary (space, newline, tab) is encountered
    or the buffer exceeds max_buffer characters. This reduces SSE events to 5-20/sec while
    maintaining perceived real-time delivery.
    """

    def __init__(self, flush_callback, max_buffer: int = 80) -> None:
        self.buffer = ""
        self.flush_callback = flush_callback
        self.max_buffer = max_buffer

    def add(self, text: str) -> None:
        """Add text to the buffer. Flush if word boundary found or buffer is full."""
        self.buffer += text
        if len(self.buffer) >= self.max_buffer or self._has_boundary():
            self.flush()

    def _has_boundary(self) -> bool:
        """Check if the buffer contains a word boundary character."""
        return any(c in self.buffer for c in (" ", "\n", "\t"))

    def flush(self) -> None:
        """Flush the buffer contents via the callback."""
        if self.buffer:
            self.flush_callback(self.buffer)
            self.buffer = ""


@dataclass
class ConversationMessage:
    """A message in an entity creation conversation."""

    role: str  # 'user' | 'assistant' | 'system'
    content: str
    timestamp: str


class BaseConversationService(abc.ABC):
    """Abstract base service for managing entity creation conversations with real-time SSE streaming.

    Subclasses MUST define their own class-level state dicts to avoid sharing state:
        _conversations: Dict[str, dict] = {}
        _subscribers: Dict[str, List[Queue]] = {}
        _start_times: Dict[str, datetime.datetime] = {}
        _lock = threading.Lock()
    """

    # Subclasses must override these
    _conversations: Dict[str, dict]
    _subscribers: Dict[str, List[Queue]]
    _start_times: Dict[str, datetime.datetime]
    _lock: threading.Lock

    @abc.abstractmethod
    def _get_system_prompt(cls) -> str:
        """Return the entity-specific system prompt."""
        ...

    @abc.abstractmethod
    def _get_conv_id_prefix(cls) -> str:
        """Return the conversation ID prefix (e.g. 'hook_', 'cmd_', 'rule_')."""
        ...

    @abc.abstractmethod
    def _get_entity_type(cls) -> str:
        """Return the entity type string (e.g. 'hook', 'command', 'rule')."""
        ...

    @abc.abstractmethod
    def _get_config_start_marker(cls) -> str:
        """Return the config start marker (e.g. '---HOOK_CONFIG---')."""
        ...

    @abc.abstractmethod
    def _get_config_end_marker(cls) -> str:
        """Return the config end marker (e.g. '---END_CONFIG---')."""
        ...

    @abc.abstractmethod
    def _finalize_entity(cls, conv_id: str) -> Tuple[dict, HTTPStatus]:
        """Extract config and persist the entity to the DB. Return (response_dict, status)."""
        ...

    @classmethod
    def _generate_conv_id(cls) -> str:
        """Generate a unique conversation ID with entity prefix."""
        chars = string.ascii_lowercase + string.digits
        return cls._get_conv_id_prefix() + "".join(secrets.choice(chars) for _ in range(16))

    @classmethod
    def start_conversation(
        cls, user_id: Optional[str] = None
    ) -> Tuple[dict, HTTPStatus]:
        """Start a new entity creation conversation.

        v0.7.83 — accepts an optional ``user_id`` from the route so
        the conv row is owned by the calling operator; ownership
        is enforced on every conv-id endpoint via ``_check_owner``.
        """
        # Clean up stale conversations first
        cls._cleanup_stale_conversations()

        conv_id = cls._generate_conv_id()

        initial_messages = [
            ConversationMessage(
                role="system",
                content=cls._get_system_prompt(),
                timestamp=datetime.datetime.now().isoformat(),
            )
        ]

        # v0.7.80 — append the kickoff user message BEFORE the
        # LLM call. Prior implementation passed the kickoff as a
        # parameter that was never added to ``conv["messages"]``;
        # the LLM saw only the system prompt and the upstream
        # rejected with "text content blocks must be non-empty".
        kickoff = ConversationMessage(
            role="user",
            content="Hello, I'd like to get started.",
            timestamp=datetime.datetime.now().isoformat(),
        )
        initial_messages.append(kickoff)

        with cls._lock:
            cls._conversations[conv_id] = {
                "messages": initial_messages,
                "processing": False,
                # v0.7.81 (issue #124 / WARN 3) — defer the
                # kickoff LLM call until the first SSE subscriber
                # connects so early frames don't broadcast into
                # an empty subscriber set.
                "needs_kickoff": True,
                # v0.7.83 — ownership stamped on the in-memory
                # cache so subsequent ownership checks don't need
                # a DB round-trip.
                "user_id": user_id,
            }
            cls._subscribers[conv_id] = []
            cls._start_times[conv_id] = datetime.datetime.now()

        # Persist to DB with user_id so list/ownership scoping
        # works post-restart.
        create_design_conversation(conv_id, cls._get_entity_type(), user_id=user_id)
        # v0.7.81 (issue #124 / WARN 1) — persist the kickoff
        # immediately so a backend crash before the LLM call
        # finishes doesn't leave the resume path with only the
        # system prompt.
        cls._persist_messages(conv_id)

        return {
            "conversation_id": conv_id,
            "message": "Conversation started",
        }, HTTPStatus.CREATED

    @classmethod
    def _check_owner(
        cls, conv_id: str, caller_user_id: Optional[str]
    ) -> Optional[Tuple[dict, HTTPStatus]]:
        """v0.7.83 — verify the calling user owns the conversation.
        Returns ``None`` when authorized, or an ``error_response``
        tuple when not. 404-not-403 to avoid existence disclosure,
        matching the skill-conversation pattern from v0.7.78.

        Allowed:
          * ``conv.user_id is None`` — legacy / bootstrap-mode
            rows are open to anyone. Production setups should
            always pass a caller user.
          * ``conv.user_id == caller_user_id`` — owner match.
        """
        conv = cls._conversations.get(conv_id)
        if not conv:
            return error_response(
                "NOT_FOUND", "Conversation not found", HTTPStatus.NOT_FOUND
            )
        owner = conv.get("user_id")
        if owner is None:
            return None
        if caller_user_id == owner:
            return None
        return error_response(
            "NOT_FOUND", "Conversation not found", HTTPStatus.NOT_FOUND
        )

    @classmethod
    def list_active(cls, user_id: Optional[str] = None) -> Tuple[dict, HTTPStatus]:
        """v0.7.83 — list this entity-type's recent active
        conversations for the calling user. Powers the wizard's
        auto-resume on cold-cache loads (new browser / fresh
        machine). Returns the same shape skill's ``list_active``
        returns so the frontend can share the resume helper.
        """
        from app.database import list_design_conversations as _list

        convs = _list(cls._get_entity_type(), "active", user_id=user_id)
        return {
            "active_conversations": [
                {
                    "id": c["id"],
                    "status": c["status"],
                    "updated_at": c["updated_at"],
                    "message_count": 0,
                }
                for c in convs
            ],
        }, HTTPStatus.OK

    @classmethod
    def _maybe_fire_kickoff(cls, conv_id: str) -> None:
        """v0.7.81 (issue #124 / WARN 2+3) — spawn the deferred
        kickoff LLM call on a non-daemon thread iff this
        conversation is still flagged ``needs_kickoff``. Caller
        must hold ``cls._lock`` when reading the flag; this
        method re-acquires the lock to atomically clear the flag.
        Non-daemon to match ``send_message``'s thread; daemon
        threads can be killed mid-persist during gunicorn
        graceful shutdown.
        """
        with cls._lock:
            conv = cls._conversations.get(conv_id)
            if not conv or not conv.get("needs_kickoff"):
                return
            conv["needs_kickoff"] = False
            kickoff_msg = next(
                (m for m in reversed(conv["messages"]) if m.role == "user"),
                None,
            )
        if kickoff_msg is None:
            logger.error(
                "skill_conv: needs_kickoff=True but no user message in %s",
                conv_id,
            )
            return
        threading.Thread(
            target=cls._process_with_claude,
            args=(conv_id, kickoff_msg.content),
        ).start()

    @classmethod
    def get_conversation(
        cls, conv_id: str, caller_user_id: Optional[str] = None
    ) -> Tuple[dict, HTTPStatus]:
        """Get conversation details and messages. Falls back to DB if not in memory."""
        if conv_id in cls._conversations:
            owner_err = cls._check_owner(conv_id, caller_user_id)
            if owner_err is not None:
                return owner_err
            conv = cls._conversations[conv_id]
            messages = [asdict(m) for m in conv["messages"] if m.role != "system"]
            return {
                "id": conv_id,
                "status": "active" if not conv.get("finalized") else "completed",
                "messages_parsed": messages,
            }, HTTPStatus.OK

        # Try loading from DB
        db_conv = get_design_conversation(conv_id)
        if not db_conv:
            return error_response("NOT_FOUND", "Conversation not found", HTTPStatus.NOT_FOUND)
        # v0.7.83 — cold-path ownership check before exposing
        # messages from a different operator.
        owner = db_conv.get("user_id")
        if owner is not None and owner != caller_user_id:
            return error_response(
                "NOT_FOUND", "Conversation not found", HTTPStatus.NOT_FOUND
            )

        try:
            messages_raw = json.loads(db_conv["messages"] or "[]")
            messages = [m for m in messages_raw if m.get("role") != "system"]
        except (json.JSONDecodeError, TypeError):
            messages = []

        return {
            "id": conv_id,
            "status": db_conv["status"],
            "messages_parsed": messages,
        }, HTTPStatus.OK

    @classmethod
    def send_message(
        cls,
        conv_id: str,
        message: str,
        backend: str | None = None,
        account_id: str | None = None,
        model: str | None = None,
        use_cli_agent: bool | None = None,
        caller_user_id: Optional[str] = None,
    ) -> Tuple[dict, HTTPStatus]:
        """Send a user message and process with the selected backend CLI.

        ``use_cli_agent`` overrides the global ``agent_yolo_mode`` setting
        for this turn. ``True``/``False`` are explicit overrides; ``None``
        defers to the global setting. Plumbed through from the
        AiChatPanel CLI runner toggle on the design pages.
        """
        if conv_id not in cls._conversations:
            # Try to resume from DB first
            resumed, status = cls.resume_conversation(conv_id, caller_user_id=caller_user_id)
            if status != HTTPStatus.OK:
                return error_response("NOT_FOUND", "Conversation not found", HTTPStatus.NOT_FOUND)

        owner_err = cls._check_owner(conv_id, caller_user_id)
        if owner_err is not None:
            return owner_err

        conv = cls._conversations[conv_id]
        if conv.get("processing"):
            return error_response("CONFLICT", "Conversation is processing", HTTPStatus.CONFLICT)

        user_msg = ConversationMessage(
            role="user",
            content=message,
            timestamp=datetime.datetime.now().isoformat(),
        )
        conv["messages"].append(user_msg)

        cls._broadcast(conv_id, "user_message", asdict(user_msg))

        threading.Thread(
            target=cls._process_with_claude,
            args=(conv_id, message),
            kwargs={
                "backend": backend,
                "account_id": account_id,
                "model": model,
                "use_cli_agent": use_cli_agent,
            },
        ).start()

        return {"message_id": conv_id, "status": "processing"}, HTTPStatus.OK

    @classmethod
    def subscribe(
        cls, conv_id: str, caller_user_id: Optional[str] = None
    ) -> Generator[str, None, None]:
        """Subscribe to SSE events for a conversation."""
        if conv_id not in cls._conversations:
            yield (f"event: error\ndata: {json.dumps({'error': 'Conversation not found'})}\n\n")
            return
        # v0.7.83 — ownership gate. Defensive in-stream fallback
        # mirrors the skill service; routes should precheck via
        # ``can_subscribe`` so unauthorized callers see an HTTP
        # 404 instead of a 200 with an in-band error event.
        if cls._check_owner(conv_id, caller_user_id) is not None:
            yield (f"event: error\ndata: {json.dumps({'error': 'Conversation not found'})}\n\n")
            return

        queue: Queue = Queue()
        with cls._lock:
            if conv_id in cls._subscribers:
                cls._subscribers[conv_id].append(queue)

        # v0.7.81 (issue #124 / WARN 3) — fire the deferred
        # kickoff after the queue is registered so any broadcast
        # the thread produces lands in this subscriber's queue.
        # Atomically clears ``needs_kickoff`` so a concurrent
        # second-tab subscribe can't double-spawn.
        cls._maybe_fire_kickoff(conv_id)

        try:
            conv = cls._conversations.get(conv_id)
            if conv:
                for msg in conv["messages"]:
                    if msg.role != "system":
                        yield f"event: message\ndata: {json.dumps(asdict(msg))}\n\n"

            while True:
                try:
                    event = queue.get(timeout=30)
                    if event is None:
                        break
                    yield event
                except Empty:
                    yield (
                        f"event: ping\ndata:"
                        f" {json.dumps({'time': datetime.datetime.now().isoformat()})}\n\n"
                    )
        finally:
            with cls._lock:
                if conv_id in cls._subscribers and queue in cls._subscribers[conv_id]:
                    cls._subscribers[conv_id].remove(queue)

    @classmethod
    def abandon_conversation(
        cls, conv_id: str, caller_user_id: Optional[str] = None
    ) -> Tuple[dict, HTTPStatus]:
        """Abandon a conversation without creating an entity."""
        if conv_id not in cls._conversations:
            # Check DB; also ownership-gate via the DB row's user_id
            db_conv = get_design_conversation(conv_id)
            if not db_conv:
                return error_response("NOT_FOUND", "Conversation not found", HTTPStatus.NOT_FOUND)
            owner = db_conv.get("user_id")
            if owner is not None and owner != caller_user_id:
                return error_response(
                    "NOT_FOUND", "Conversation not found", HTTPStatus.NOT_FOUND
                )
        else:
            owner_err = cls._check_owner(conv_id, caller_user_id)
            if owner_err is not None:
                return owner_err

        update_design_conversation(conv_id, status="abandoned")
        cls._cleanup_conversation(conv_id)
        return {"message": "Conversation abandoned"}, HTTPStatus.OK

    @classmethod
    def can_subscribe(
        cls, conv_id: str, caller_user_id: Optional[str]
    ) -> bool:
        """v0.7.83 — precheck used by SSE routes so an unauthorized
        subscriber gets a real HTTP 404 instead of a 200 + in-band
        error event. Mirrors skill's ``can_subscribe``.
        """
        if conv_id not in cls._conversations:
            # Try DB rehydrate via resume_conversation so a refreshed
            # wizard can subscribe to a persisted conv. We don't
            # actually call resume here (it loads into memory); we
            # just verify the DB row exists + ownership matches.
            db_conv = get_design_conversation(conv_id)
            if not db_conv:
                return False
            owner = db_conv.get("user_id")
            return owner is None or owner == caller_user_id
        return cls._check_owner(conv_id, caller_user_id) is None

    @classmethod
    def _broadcast(cls, conv_id: str, event_type: str, data: dict) -> None:
        """Broadcast an SSE event to all subscribers of a conversation."""
        if conv_id not in cls._subscribers:
            return

        event = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

        with cls._lock:
            for queue in cls._subscribers.get(conv_id, []):
                queue.put(event)

    @classmethod
    def _stream_and_accumulate(
        cls,
        conv_id: str,
        messages: list,
        model: str | None,
        backend: str | None,
        account_id: str | None,
        use_cli_agent: bool | None = None,
    ) -> str:
        """Stream LLM response and accumulate full text. Returns the complete response string.

        Routes through the CLI agent runner when ``use_cli_agent`` is
        ``True``, or when ``None`` *and* the global YOLO setting is on
        for a CLI-runnable backend (claude/codex/gemini). Otherwise
        falls through to the legacy ``stream_llm_response`` (CLIProxy).
        """
        from .cli_agent_runner_service import (
            is_yolo_mode_enabled,
            resolve_account_config_dir,
            should_route_via_cli_agent,
            stream_via_cli_agent,
        )
        from .conversation_streaming import stream_llm_response

        full_response_parts = []
        accumulator = WordBoundaryAccumulator(
            flush_callback=lambda text: cls._broadcast(conv_id, "response_chunk", {"content": text})
        )

        if should_route_via_cli_agent(backend, use_cli_agent):
            backend_norm = (backend or "").lower()
            config_dir = resolve_account_config_dir(account_id, backend_norm)
            stream_iter = stream_via_cli_agent(
                messages,
                backend=backend_norm,
                cwd=None,
                yolo=is_yolo_mode_enabled(),
                model=model,
                config_dir=config_dir,
            )
        else:
            stream_iter = stream_llm_response(
                messages, model=model, account_email=account_id, backend=backend
            )

        for chunk in stream_iter:
            full_response_parts.append(chunk)
            accumulator.add(chunk)

        accumulator.flush()

        response = "".join(full_response_parts).strip()
        if not response:
            response = "(No response generated)"
        return response

    @classmethod
    def _persist_message(cls, conv_id: str, role: str, content: str) -> None:
        """Append a message to the conversation and persist to DB."""
        conv = cls._conversations.get(conv_id)
        if conv is None:
            return
        msg = ConversationMessage(
            role=role,
            content=content,
            timestamp=datetime.datetime.now().isoformat(),
        )
        conv["messages"].append(msg)
        cls._persist_messages(conv_id)

    @classmethod
    def _process_with_claude(
        cls,
        conv_id: str,
        user_message: str,
        backend: str | None = None,
        account_id: str | None = None,
        model: str | None = None,
        use_cli_agent: bool | None = None,
    ) -> None:
        """Process a message using real-time LLM streaming via LiteLLM.

        Uses the shared stream_llm_response() utility for token-by-token streaming
        instead of buffered subprocess output. A WordBoundaryAccumulator reduces SSE
        event frequency to 5-20 events/sec at word-boundary intervals.

        When ``use_cli_agent`` is ``True`` (or defers to a YOLO-on global
        setting and the backend supports it), routes through the CLI
        agent runner so the design conversation can use tools.
        """
        conv = cls._conversations.get(conv_id)
        if conv is None:
            return

        conv["processing"] = True

        try:
            cls._broadcast(
                conv_id, "response_start", {"timestamp": datetime.datetime.now().isoformat()}
            )

            # Build messages from conversation history.
            #
            # v0.7.80 — defense in depth against the same proxy
            # error v0.7.76 fixed for skills: drop any message
            # whose content is missing or whitespace-only, since
            # CLIProxyAPI's OpenAI translation rejects empty
            # text content blocks. If after filtering there's no
            # user message at all, bail out with a broadcast
            # error instead of issuing a doomed LLM call.
            messages = [
                {"role": msg.role, "content": msg.content}
                for msg in conv["messages"]
                if msg.content and msg.content.strip()
            ]
            if not any(m["role"] == "user" for m in messages):
                logger.error(
                    "skipping LLM call for %s: no non-empty user message in history",
                    conv_id,
                )
                cls._broadcast(
                    conv_id,
                    "error",
                    {"error": "Cannot send to LLM: no user message in conversation."},
                )
                return

            response = cls._stream_and_accumulate(
                conv_id, messages, model, backend, account_id, use_cli_agent=use_cli_agent
            )

            cls._persist_message(conv_id, "assistant", response)

            cls._broadcast(
                conv_id,
                "response_complete",
                {"content": response, "backend": backend or "claude"},
            )

        except Exception as e:
            logger.exception("Error processing with Claude")
            try:
                cls._broadcast(conv_id, "error", {"error": str(e)})
            except Exception:
                logger.exception("Failed to broadcast error for conv %s", conv_id)
        finally:
            conv["processing"] = False

    @classmethod
    def _extract_config_from_conversation(cls, conv_id: str) -> Optional[dict]:
        """Extract JSON config from conversation using entity-specific markers.

        Searches backwards through assistant messages for the config start marker,
        extracts JSON between start and end markers, and parses it.
        Returns the parsed config dict or None if not found.
        """
        conv = cls._conversations.get(conv_id)
        if not conv:
            return None

        start_marker = cls._get_config_start_marker()
        end_marker = cls._get_config_end_marker()

        for msg in reversed(conv["messages"]):
            if msg.role == "assistant" and start_marker in msg.content:
                try:
                    start = msg.content.index(start_marker) + len(start_marker)
                    end = msg.content.index(end_marker)
                    config_str = msg.content[start:end].strip()
                    return json.loads(config_str)
                except (ValueError, json.JSONDecodeError) as e:
                    logger.error(f"Failed to parse entity config: {e}", exc_info=True)
                    continue

        return None

    @classmethod
    def _persist_messages(cls, conv_id: str) -> None:
        """Persist conversation messages to the database."""
        conv = cls._conversations.get(conv_id)
        if not conv:
            return
        messages_json = json.dumps([asdict(m) for m in conv["messages"]], default=str)
        update_design_conversation(conv_id, messages=messages_json)

    @classmethod
    def resume_conversation(
        cls, conv_id: str, caller_user_id: Optional[str] = None
    ) -> Tuple[dict, HTTPStatus]:
        """Resume a conversation from the database into memory.

        v0.7.83 — gates on ``user_id`` so a probing caller can't
        rehydrate another operator's conv. Same 404-not-403
        disclosure rule.
        """
        if conv_id in cls._conversations:
            owner_err = cls._check_owner(conv_id, caller_user_id)
            if owner_err is not None:
                return owner_err
            return {"message": "Conversation already active"}, HTTPStatus.OK

        db_conv = get_design_conversation(conv_id)
        if not db_conv:
            return error_response("NOT_FOUND", "Conversation not found", HTTPStatus.NOT_FOUND)

        owner = db_conv.get("user_id")
        if owner is not None and owner != caller_user_id:
            return error_response(
                "NOT_FOUND", "Conversation not found", HTTPStatus.NOT_FOUND
            )

        if db_conv["status"] != "active":
            return error_response(
                "INTERNAL_SERVER_ERROR", "Conversation is no longer active", HTTPStatus.GONE
            )

        try:
            messages_raw = json.loads(db_conv["messages"] or "[]")
        except (json.JSONDecodeError, TypeError):
            messages_raw = []

        # Reconstruct ConversationMessage objects
        messages = []
        for m in messages_raw:
            messages.append(
                ConversationMessage(
                    role=m.get("role", "user"),
                    content=m.get("content", ""),
                    timestamp=m.get("timestamp", datetime.datetime.now().isoformat()),
                )
            )

        # If no system prompt, prepend one
        if not messages or messages[0].role != "system":
            messages.insert(
                0,
                ConversationMessage(
                    role="system",
                    content=cls._get_system_prompt(),
                    timestamp=datetime.datetime.now().isoformat(),
                ),
            )

        with cls._lock:
            cls._conversations[conv_id] = {
                "messages": messages,
                "processing": False,
                # v0.7.83 — carry ownership forward from the DB
                # row so subsequent ownership checks against the
                # in-memory cache succeed for the original owner.
                "user_id": owner,
            }
            cls._subscribers[conv_id] = []
            cls._start_times[conv_id] = datetime.datetime.now()

        return {
            "message": "Conversation resumed",
            "conversation_id": conv_id,
        }, HTTPStatus.OK

    @classmethod
    def list_conversations(
        cls, user_id: Optional[str] = None
    ) -> Tuple[dict, HTTPStatus]:
        """List active/recent conversations of this entity type.

        v0.7.83 — scopes by ``user_id`` so a list call doesn't
        return convs from other operators.
        """
        convs = list_design_conversations(cls._get_entity_type(), "active", user_id=user_id)
        return {"conversations": convs}, HTTPStatus.OK

    @classmethod
    def _cleanup_stale_conversations(cls) -> None:
        """Clean up conversations that have been inactive for too long."""
        now = datetime.datetime.now()
        stale_ids = []
        with cls._lock:
            for conv_id, start_time in list(cls._start_times.items()):
                if (now - start_time).total_seconds() > STALE_CONVERSATION_THRESHOLD:
                    stale_ids.append(conv_id)

        for conv_id in stale_ids:
            update_design_conversation(conv_id, status="stale")
            cls._cleanup_conversation(conv_id)

        # Also clean up old DB entries
        delete_old_design_conversations()

    @classmethod
    def _cleanup_conversation(cls, conv_id: str) -> None:
        """Clean up a conversation and its resources."""
        with cls._lock:
            for queue in cls._subscribers.get(conv_id, []):
                queue.put(None)

            cls._conversations.pop(conv_id, None)
            cls._subscribers.pop(conv_id, None)
            cls._start_times.pop(conv_id, None)
