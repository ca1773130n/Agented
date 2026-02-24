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

    def __init__(self, flush_callback, max_buffer: int = 80):
        self.buffer = ""
        self.flush_callback = flush_callback
        self.max_buffer = max_buffer

    def add(self, text: str):
        """Add text to the buffer. Flush if word boundary found or buffer is full."""
        self.buffer += text
        if len(self.buffer) >= self.max_buffer or self._has_boundary():
            self.flush()

    def _has_boundary(self) -> bool:
        """Check if the buffer contains a word boundary character."""
        return any(c in self.buffer for c in (" ", "\n", "\t"))

    def flush(self):
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
    def start_conversation(cls) -> Tuple[dict, HTTPStatus]:
        """Start a new entity creation conversation."""
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

        with cls._lock:
            cls._conversations[conv_id] = {"messages": initial_messages, "processing": False}
            cls._subscribers[conv_id] = []
            cls._start_times[conv_id] = datetime.datetime.now()

        # Persist to DB
        create_design_conversation(conv_id, cls._get_entity_type())

        # Trigger initial assistant greeting
        cls._process_with_claude(conv_id, "Hello, I'd like to get started.")

        return {
            "conversation_id": conv_id,
            "message": "Conversation started",
        }, HTTPStatus.CREATED

    @classmethod
    def get_conversation(cls, conv_id: str) -> Tuple[dict, HTTPStatus]:
        """Get conversation details and messages. Falls back to DB if not in memory."""
        if conv_id in cls._conversations:
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
            return {"error": "Conversation not found"}, HTTPStatus.NOT_FOUND

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
    ) -> Tuple[dict, HTTPStatus]:
        """Send a user message and process with the selected backend CLI."""
        if conv_id not in cls._conversations:
            # Try to resume from DB first
            resumed, status = cls.resume_conversation(conv_id)
            if status != HTTPStatus.OK:
                return {"error": "Conversation not found"}, HTTPStatus.NOT_FOUND

        conv = cls._conversations[conv_id]
        if conv.get("processing"):
            return {"error": "Conversation is processing"}, HTTPStatus.CONFLICT

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
            kwargs={"backend": backend, "account_id": account_id, "model": model},
        ).start()

        return {"message_id": conv_id, "status": "processing"}, HTTPStatus.OK

    @classmethod
    def subscribe(cls, conv_id: str) -> Generator[str, None, None]:
        """Subscribe to SSE events for a conversation."""
        if conv_id not in cls._conversations:
            yield (f"event: error\ndata:" f" {json.dumps({'error': 'Conversation not found'})}\n\n")
            return

        queue: Queue = Queue()
        with cls._lock:
            if conv_id in cls._subscribers:
                cls._subscribers[conv_id].append(queue)

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
    def abandon_conversation(cls, conv_id: str) -> Tuple[dict, HTTPStatus]:
        """Abandon a conversation without creating an entity."""
        if conv_id not in cls._conversations:
            # Check DB
            db_conv = get_design_conversation(conv_id)
            if not db_conv:
                return {"error": "Conversation not found"}, HTTPStatus.NOT_FOUND

        update_design_conversation(conv_id, status="abandoned")
        cls._cleanup_conversation(conv_id)
        return {"message": "Conversation abandoned"}, HTTPStatus.OK

    @classmethod
    def _broadcast(cls, conv_id: str, event_type: str, data: dict):
        """Broadcast an SSE event to all subscribers of a conversation."""
        if conv_id not in cls._subscribers:
            return

        event = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

        with cls._lock:
            for queue in cls._subscribers.get(conv_id, []):
                queue.put(event)

    @classmethod
    def _process_with_claude(
        cls,
        conv_id: str,
        user_message: str,
        backend: str | None = None,
        account_id: str | None = None,
        model: str | None = None,
    ):
        """Process a message using real-time LLM streaming via LiteLLM.

        Uses the shared stream_llm_response() utility for token-by-token streaming
        instead of buffered subprocess output. A WordBoundaryAccumulator reduces SSE
        event frequency to 5-20 events/sec at word-boundary intervals.
        """
        conv = cls._conversations.get(conv_id)
        if conv is None:
            return

        conv["processing"] = True

        try:
            cls._broadcast(
                conv_id, "response_start", {"timestamp": datetime.datetime.now().isoformat()}
            )
            from .conversation_streaming import stream_llm_response

            # Build messages from conversation history
            messages = []
            for msg in conv["messages"]:
                messages.append({"role": msg.role, "content": msg.content})

            # Stream response chunks in real-time
            full_response_parts = []
            accumulator = WordBoundaryAccumulator(
                flush_callback=lambda text: cls._broadcast(
                    conv_id, "response_chunk", {"content": text}
                )
            )

            for chunk in stream_llm_response(
                messages, model=model, account_email=account_id, backend=backend
            ):
                full_response_parts.append(chunk)
                accumulator.add(chunk)

            accumulator.flush()

            response = "".join(full_response_parts).strip()
            if not response:
                response = "(No response generated)"

            assistant_msg = ConversationMessage(
                role="assistant",
                content=response,
                timestamp=datetime.datetime.now().isoformat(),
            )
            conv["messages"].append(assistant_msg)

            cls._broadcast(
                conv_id,
                "response_complete",
                {"content": response, "backend": backend or "claude"},
            )

            # Persist messages to DB after each exchange
            cls._persist_messages(conv_id)

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
                    logger.error(f"Failed to parse entity config: {e}")
                    continue

        return None

    @classmethod
    def _persist_messages(cls, conv_id: str):
        """Persist conversation messages to the database."""
        conv = cls._conversations.get(conv_id)
        if not conv:
            return
        messages_json = json.dumps([asdict(m) for m in conv["messages"]], default=str)
        update_design_conversation(conv_id, messages=messages_json)

    @classmethod
    def resume_conversation(cls, conv_id: str) -> Tuple[dict, HTTPStatus]:
        """Resume a conversation from the database into memory."""
        if conv_id in cls._conversations:
            return {"message": "Conversation already active"}, HTTPStatus.OK

        db_conv = get_design_conversation(conv_id)
        if not db_conv:
            return {"error": "Conversation not found"}, HTTPStatus.NOT_FOUND

        if db_conv["status"] != "active":
            return {"error": "Conversation is no longer active"}, HTTPStatus.GONE

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
            cls._conversations[conv_id] = {"messages": messages, "processing": False}
            cls._subscribers[conv_id] = []
            cls._start_times[conv_id] = datetime.datetime.now()

        return {
            "message": "Conversation resumed",
            "conversation_id": conv_id,
        }, HTTPStatus.OK

    @classmethod
    def list_conversations(cls) -> Tuple[dict, HTTPStatus]:
        """List active/recent conversations of this entity type."""
        convs = list_design_conversations(cls._get_entity_type(), "active")
        return {"conversations": convs}, HTTPStatus.OK

    @classmethod
    def _cleanup_stale_conversations(cls):
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
    def _cleanup_conversation(cls, conv_id: str):
        """Clean up a conversation and its resources."""
        with cls._lock:
            for queue in cls._subscribers.get(conv_id, []):
                queue.put(None)

            cls._conversations.pop(conv_id, None)
            cls._subscribers.pop(conv_id, None)
            cls._start_times.pop(conv_id, None)
