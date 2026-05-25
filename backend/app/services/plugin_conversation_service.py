"""Plugin conversation service for interactive plugin creation with SSE streaming."""

import datetime
import json
import logging
import secrets
import string
import threading
from dataclasses import asdict, dataclass
from http import HTTPStatus
from queue import Empty, Queue
from typing import Dict, Generator, List, Optional, Tuple

logger = logging.getLogger(__name__)

from app.models.common import error_response

from ..database import (
    add_plugin_component,
    create_plugin,
    get_plugin_detail,
)
from ..db import (
    create_plugin_conversation,
    get_plugin_conversation,
    list_active_plugin_conversations,
    upsert_plugin_conversation,
)

# Stale conversation cleanup threshold (30 minutes)
STALE_CONVERSATION_THRESHOLD = 1800

# System prompt for plugin creation conversation
PLUGIN_CREATION_SYSTEM_PROMPT = """You are an AI assistant helping to create a new Plugin for the Agented platform. Your job is to guide the user through designing their plugin step by step.

A plugin is a bundle of components that extends Agented's capabilities. Each plugin can contain multiple components of the following types:
- **skill** — A markdown instruction file for Claude to follow when performing a specific task
- **command** — A slash command that users can invoke (e.g., /deploy, /lint)
- **hook** — An event-driven action triggered by lifecycle events (e.g., PreToolUse, PostToolUse, Stop)
- **rule** — A validation or check rule (pre_check, post_check, or validation)

Help the user define:
1. **Plugin Name** — A short, descriptive name (e.g., "code-quality", "deployment-helper")
2. **Plugin Description** — What does this plugin do overall?
3. **Plugin Version** — Version string (default "1.0.0")
4. **Components** — The individual skills, commands, hooks, and/or rules that make up this plugin

For each component, gather:
- **name** — Component name
- **type** — One of: skill, command, hook, rule
- **content** — The actual content/instructions for the component

Ask clarifying questions and provide suggestions. Be conversational and helpful. You can suggest logical groupings of components.

When you have gathered enough information, summarize the plugin configuration and ask the user to confirm.

When the user confirms, output the final configuration in this exact format:
---PLUGIN_CONFIG---
{
  "name": "plugin-name",
  "description": "Brief description of the plugin",
  "version": "1.0.0",
  "components": [
    {
      "name": "component-name",
      "type": "skill",
      "content": "The component content..."
    }
  ]
}
---END_CONFIG---

Start by asking the user what kind of plugin they want to create and what problems it should solve."""


@dataclass
class ConversationMessage:
    """A message in a plugin creation conversation."""

    role: str  # 'user' | 'assistant' | 'system'
    content: str
    timestamp: str


class PluginConversationService:
    """Service for managing plugin creation conversations with real-time SSE streaming."""

    # In-memory conversation state
    _conversations: Dict[str, dict] = {}
    # SSE subscribers
    _subscribers: Dict[str, List[Queue]] = {}
    # Track conversation start times for cleanup
    _start_times: Dict[str, datetime.datetime] = {}
    # Lock for thread-safe operations
    _lock = threading.Lock()

    @classmethod
    def _generate_conv_id(cls) -> str:
        """Generate a unique conversation ID."""
        chars = string.ascii_lowercase + string.digits
        return "plugin_" + "".join(secrets.choice(chars) for _ in range(16))

    @classmethod
    def start_conversation(
        cls, user_id: Optional[str] = None
    ) -> Tuple[dict, HTTPStatus]:
        """Start a new plugin creation conversation.

        v0.7.83 — accepts an optional ``user_id`` so the conv row
        is owned by the calling operator; ownership is enforced
        on every conv-id endpoint via ``_check_owner``.
        """
        conv_id = cls._generate_conv_id()

        initial_messages = [
            ConversationMessage(
                role="system",
                content=PLUGIN_CREATION_SYSTEM_PROMPT,
                timestamp=datetime.datetime.now().isoformat(),
            )
        ]

        # v0.7.80 — append the kickoff user message BEFORE
        # ``_process_with_claude`` runs. Same bug as the one
        # SkillConversationService had pre-v0.7.76: the kickoff
        # string was passed as a parameter that ``_process_with_claude``
        # never appended to ``conv["messages"]``, so the LLM call
        # saw only the system prompt and the upstream rejected
        # with "text content blocks must be non-empty".
        kickoff = ConversationMessage(
            role="user",
            content="Hello, I'd like to create a new plugin.",
            timestamp=datetime.datetime.now().isoformat(),
        )
        initial_messages.append(kickoff)

        with cls._lock:
            cls._conversations[conv_id] = {
                "messages": initial_messages,
                "processing": False,
                # v0.7.81 (issue #124 / WARN 3) — defer kickoff
                # until first SSE subscriber connects.
                "needs_kickoff": True,
                # v0.7.83 — ownership stamped on the in-memory
                # cache so subsequent ownership checks don't need
                # a DB round-trip.
                "user_id": user_id,
            }
            cls._subscribers[conv_id] = []
            cls._start_times[conv_id] = datetime.datetime.now()

        # v0.7.83 — persist to DB so /plugins/new survives page
        # refresh + backend restart, same as v0.7.78 did for
        # /skills/new. Failures are logged but don't block the
        # start (in-memory chat still works for the live session).
        try:
            create_plugin_conversation(
                conv_id,
                [asdict(m) for m in initial_messages],
                user_id=user_id,
            )
        except Exception:
            logger.warning(
                "plugin_conv: failed to persist new conversation %s",
                conv_id,
                exc_info=True,
            )

        return {
            "conversation_id": conv_id,
            "message": "Plugin creation conversation started",
        }, HTTPStatus.CREATED

    # ---------------------------------------------------------------
    # v0.7.83 — persistence + ownership helpers (mirror skill v0.7.78)
    # ---------------------------------------------------------------

    @classmethod
    def _ensure_loaded(cls, conv_id: str) -> bool:
        """Make sure the conversation is in the in-memory cache.
        If the wizard refreshed or the backend restarted,
        rehydrate from the DB. Returns True iff loaded.
        """
        with cls._lock:
            if conv_id in cls._conversations:
                return True
        try:
            row = get_plugin_conversation(conv_id)
        except Exception:
            logger.warning("plugin_conv: DB lookup failed for %s", conv_id, exc_info=True)
            return False
        if not row or row["status"] != "active":
            return False
        messages = [
            ConversationMessage(
                role=m["role"], content=m["content"], timestamp=m["timestamp"]
            )
            for m in row["messages"]
        ]
        with cls._lock:
            if conv_id in cls._conversations:
                return True
            cls._conversations[conv_id] = {
                "messages": messages,
                "processing": False,
                "user_id": row.get("user_id"),
            }
            cls._subscribers.setdefault(conv_id, [])
            cls._start_times[conv_id] = datetime.datetime.now()
        logger.info("plugin_conv: rehydrated %s from DB (%d messages)", conv_id, len(messages))
        return True

    @classmethod
    def _check_owner(
        cls, conv_id: str, caller_user_id: Optional[str]
    ) -> Optional[Tuple[dict, HTTPStatus]]:
        """v0.7.83 — verify the calling user owns the conversation.
        Returns None when authorized, or a 404 error_response when
        not (mirrors skill's 404-not-403 disclosure rule).
        """
        conv = cls._conversations.get(conv_id)
        if not conv:
            return error_response(
                "NOT_FOUND", "Conversation not found", HTTPStatus.NOT_FOUND
            )
        owner = conv.get("user_id")
        # v0.7.83 (codex WARN 2 / 2nd pass) — strict match including
        # ``None == None``. Authenticated callers cannot touch
        # NULL-owner (legacy) rows.
        if owner == caller_user_id:
            return None
        return error_response(
            "NOT_FOUND", "Conversation not found", HTTPStatus.NOT_FOUND
        )

    @classmethod
    def _persist(
        cls,
        conv_id: str,
        *,
        status: Optional[str] = None,
    ) -> None:
        """Write the current in-memory message list (and optional
        status) through to the DB. Logs and swallows errors so a
        DB hiccup doesn't break the live SSE stream.
        """
        conv = cls._conversations.get(conv_id)
        if conv is None:
            return
        try:
            upsert_plugin_conversation(
                conv_id,
                [asdict(m) for m in conv["messages"]],
                status=status,
            )
        except Exception:
            logger.warning(
                "plugin_conv: failed to persist conversation %s", conv_id, exc_info=True
            )

    @classmethod
    def list_active(cls, user_id: Optional[str] = None) -> Tuple[dict, HTTPStatus]:
        """List the operator's recent active plugin conversations
        so the wizard can resume from the DB when localStorage is
        empty (new browser / fresh machine).
        """
        try:
            convs = list_active_plugin_conversations(user_id=user_id, limit=10)
        except Exception:
            logger.warning("plugin_conv: DB list failed", exc_info=True)
            convs = []
        return {
            "active_conversations": [
                {
                    "id": c["id"],
                    "status": c["status"],
                    "updated_at": c["updated_at"],
                    "message_count": len(c.get("messages") or []),
                }
                for c in convs
            ],
        }, HTTPStatus.OK

    @classmethod
    def can_subscribe(
        cls, conv_id: str, caller_user_id: Optional[str]
    ) -> bool:
        """Precheck used by the SSE route so an unauthorized
        subscriber gets a real HTTP 404 instead of 200 + in-band
        error event. Mirrors skill's ``can_subscribe``.
        """
        if not cls._ensure_loaded(conv_id):
            return False
        return cls._check_owner(conv_id, caller_user_id) is None

    @classmethod
    def _maybe_fire_kickoff(cls, conv_id: str) -> None:
        """v0.7.81 (issue #124) — atomic check-and-clear of
        ``needs_kickoff``; on success, spawn the LLM call on a
        non-daemon thread.
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
            logger.error("plugin_conv: needs_kickoff=True but no user message in %s", conv_id)
            return
        threading.Thread(
            target=cls._process_with_claude,
            args=(conv_id, kickoff_msg.content),
        ).start()

    @classmethod
    def get_conversation(
        cls, conv_id: str, caller_user_id: Optional[str] = None
    ) -> Tuple[dict, HTTPStatus]:
        """Get conversation details and messages."""
        if not cls._ensure_loaded(conv_id):
            return error_response("NOT_FOUND", "Conversation not found", HTTPStatus.NOT_FOUND)
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

    @classmethod
    def send_message(
        cls,
        conv_id: str,
        message: str,
        backend: str | None = None,
        account_id: str | None = None,
        model: str | None = None,
        caller_user_id: Optional[str] = None,
    ) -> Tuple[dict, HTTPStatus]:
        """Send a user message and process with Claude."""
        if not cls._ensure_loaded(conv_id):
            return error_response("NOT_FOUND", "Conversation not found", HTTPStatus.NOT_FOUND)
        owner_err = cls._check_owner(conv_id, caller_user_id)
        if owner_err is not None:
            return owner_err

        # v0.7.83 (codex WARN 3 / 2nd pass) — serialize the
        # processing check + user-msg append + processing-set
        # under one lock so a second concurrent send_message
        # can't pass the check, append, and spawn a second
        # LLM thread that interleaves. Mirrors the skill v0.7.78
        # WARN 2 fix.
        with cls._lock:
            conv = cls._conversations[conv_id]
            if conv.get("processing"):
                return error_response(
                    "CONFLICT", "Conversation is processing", HTTPStatus.CONFLICT
                )
            conv["processing"] = True
            user_msg = ConversationMessage(
                role="user",
                content=message,
                timestamp=datetime.datetime.now().isoformat(),
            )
            conv["messages"].append(user_msg)

        # If any pre-thread step fails, reset the processing
        # flag so the operator can retry (mirrors skill WARN D
        # from v0.7.78 codex 2nd pass).
        try:
            # v0.7.83 — write-through after every user message so a
            # refresh between turns sees the full history.
            cls._persist(conv_id)
            cls._broadcast(conv_id, "user_message", asdict(user_msg))
            threading.Thread(
                target=cls._process_with_claude,
                args=(conv_id, message),
                kwargs={"backend": backend, "account_id": account_id, "model": model},
            ).start()
        except Exception:
            logger.error(
                "plugin_conv: failed to start LLM thread for %s; "
                "resetting processing flag",
                conv_id,
                exc_info=True,
            )
            with cls._lock:
                if conv_id in cls._conversations:
                    cls._conversations[conv_id]["processing"] = False
            raise

        return {"message_id": conv_id, "status": "processing"}, HTTPStatus.OK

    @classmethod
    def subscribe(
        cls, conv_id: str, caller_user_id: Optional[str] = None
    ) -> Generator[str, None, None]:
        """Subscribe to SSE events for a conversation."""
        if not cls._ensure_loaded(conv_id):
            yield f"event: error\ndata: {json.dumps({'error': 'Conversation not found'})}\n\n"
            return
        if cls._check_owner(conv_id, caller_user_id) is not None:
            yield f"event: error\ndata: {json.dumps({'error': 'Conversation not found'})}\n\n"
            return

        queue: Queue = Queue()
        with cls._lock:
            if conv_id in cls._subscribers:
                cls._subscribers[conv_id].append(queue)

        # v0.7.81 (issue #124 / WARN 3) — fire the deferred
        # kickoff after the queue is registered so any broadcast
        # the thread produces lands in this subscriber's queue.
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
                    yield f"event: ping\ndata: {json.dumps({'time': datetime.datetime.now().isoformat()})}\n\n"
        finally:
            with cls._lock:
                if conv_id in cls._subscribers and queue in cls._subscribers[conv_id]:
                    cls._subscribers[conv_id].remove(queue)

    @classmethod
    def finalize_plugin(
        cls, conv_id: str, caller_user_id: Optional[str] = None
    ) -> Tuple[dict, HTTPStatus]:
        """Finalize the conversation and create the plugin."""
        if not cls._ensure_loaded(conv_id):
            return error_response("NOT_FOUND", "Conversation not found", HTTPStatus.NOT_FOUND)
        owner_err = cls._check_owner(conv_id, caller_user_id)
        if owner_err is not None:
            return owner_err

        # v0.7.83 (codex WARN 3 / 3rd pass) — atomic check-and-set
        # of ``processing`` under the lock. The 2nd-pass fix only
        # *read* the flag inside the lock and then released it,
        # which let a concurrent ``send_message`` fire a new LLM
        # turn between the check and the actual finalize work.
        # Setting the flag ourselves blocks send_message until
        # finalize finishes (or errors out). Also re-fetches the
        # conv inside the lock so a concurrent ``abandon_conversation``
        # that already removed it gets a 404 here instead of a
        # KeyError later (codex WARN C.2 / 3rd pass).
        with cls._lock:
            conv = cls._conversations.get(conv_id)
            if conv is None:
                return error_response(
                    "NOT_FOUND", "Conversation not found", HTTPStatus.NOT_FOUND
                )
            if conv.get("processing"):
                return error_response(
                    "CONFLICT",
                    "Conversation is processing — wait for the current response to finish.",
                    HTTPStatus.CONFLICT,
                )
            conv["processing"] = True

        try:
            return cls._do_finalize_plugin(conv_id, conv)
        finally:
            # Reset processing on any exit that left the conv
            # in memory (success path calls _cleanup_conversation
            # which pops the entry, so this is a no-op there).
            with cls._lock:
                if conv_id in cls._conversations:
                    cls._conversations[conv_id]["processing"] = False

    @classmethod
    def _do_finalize_plugin(
        cls, conv_id: str, conv: dict
    ) -> Tuple[dict, HTTPStatus]:
        """v0.7.83 (codex WARN C / 3rd pass) — extracted body of
        ``finalize_plugin`` so the wrapper can hold the
        ``processing`` flag across the whole call and reset it
        on every exit path via ``finally``.
        """
        # Find the plugin config in the last assistant message
        plugin_config = None
        for msg in reversed(conv["messages"]):
            if msg.role == "assistant" and "---PLUGIN_CONFIG---" in msg.content:
                try:
                    start = msg.content.index("---PLUGIN_CONFIG---") + len("---PLUGIN_CONFIG---")
                    end = msg.content.index("---END_CONFIG---")
                    config_str = msg.content[start:end].strip()
                    plugin_config = json.loads(config_str)
                    break
                except (ValueError, json.JSONDecodeError) as e:
                    logger.error(f"Failed to parse plugin config: {e}", exc_info=True)
                    continue

        if not plugin_config:
            return {
                "error": "No plugin configuration found. Please continue the conversation."
            }, HTTPStatus.BAD_REQUEST

        plugin_name = plugin_config.get("name", "Untitled Plugin")
        description = plugin_config.get("description", "")
        version = plugin_config.get("version", "1.0.0")
        components = plugin_config.get("components", [])

        try:
            plugin_id = create_plugin(
                name=plugin_name,
                description=description,
                version=version,
                status="draft",
            )

            if not plugin_id:
                return error_response(
                    "INTERNAL_SERVER_ERROR",
                    "Failed to create plugin",
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )

            # Add components
            for comp in components:
                comp_name = comp.get("name", "unnamed")
                comp_type = comp.get("type", "skill")
                comp_content = comp.get("content", "")
                add_plugin_component(plugin_id, comp_name, comp_type, comp_content)

            # Mark conversation as finalized
            conv["finalized"] = True
            # v0.7.83 — persist finalized status so it's excluded
            # from the resume list.
            cls._persist(conv_id, status="finalized")

            cls._cleanup_conversation(conv_id)

            plugin = get_plugin_detail(plugin_id)

            return {
                "message": "Plugin created successfully",
                "plugin_id": plugin_id,
                "plugin": plugin,
            }, HTTPStatus.CREATED

        except Exception as e:
            logger.error(f"Failed to create plugin: {e}", exc_info=True)
            return error_response(
                "INTERNAL_SERVER_ERROR",
                f"Failed to create plugin: {str(e)}",
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    @classmethod
    def abandon_conversation(
        cls, conv_id: str, caller_user_id: Optional[str] = None
    ) -> Tuple[dict, HTTPStatus]:
        """Abandon a conversation without creating a plugin."""
        if not cls._ensure_loaded(conv_id):
            # Cold path: gate ownership against the DB row, then
            # flip status to abandoned so the resume list stops
            # surfacing it.
            try:
                row = get_plugin_conversation(conv_id)
                if row:
                    owner = row.get("user_id")
                    if owner != caller_user_id:  # v0.7.83 (codex WARN 2) — NULL owner only matches NULL caller
                        return error_response(
                            "NOT_FOUND",
                            "Conversation not found",
                            HTTPStatus.NOT_FOUND,
                        )
                    upsert_plugin_conversation(
                        conv_id, row["messages"], status="abandoned"
                    )
                    return {"message": "Conversation abandoned"}, HTTPStatus.OK
            except Exception:
                pass
            return error_response("NOT_FOUND", "Conversation not found", HTTPStatus.NOT_FOUND)

        owner_err = cls._check_owner(conv_id, caller_user_id)
        if owner_err is not None:
            return owner_err
        cls._persist(conv_id, status="abandoned")
        cls._cleanup_conversation(conv_id)
        return {"message": "Conversation abandoned"}, HTTPStatus.OK

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
    def _process_with_claude(
        cls,
        conv_id: str,
        user_message: str,
        backend: str | None = None,
        account_id: str | None = None,
        model: str | None = None,
    ) -> None:
        """Process a message with Claude using real-time LLM streaming."""
        if conv_id not in cls._conversations:
            return

        conv = cls._conversations[conv_id]
        conv["processing"] = True

        cls._broadcast(
            conv_id, "response_start", {"timestamp": datetime.datetime.now().isoformat()}
        )

        try:
            from .conversation_streaming import stream_llm_response

            # Build messages from conversation history. Filter
            # out empty/whitespace turns — CLIProxyAPI rejects
            # them as "text content blocks must be non-empty".
            from .conversation_filters import drop_empty_content_messages

            messages = drop_empty_content_messages(conv["messages"])
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

            # Stream response chunks in real-time
            full_response_parts = []
            for chunk in stream_llm_response(
                messages, model=model, account_email=account_id, backend=backend
            ):
                # Plugin conversations don't surface tool-use events;
                # filter to text chunks so we never accumulate a
                # ToolUseEvent into the response string.
                if not isinstance(chunk, str):
                    continue
                full_response_parts.append(chunk)
                cls._broadcast(conv_id, "response_chunk", {"content": chunk})

            response = "".join(full_response_parts).strip()
            if not response:
                response = "(No response generated)"

            assistant_msg = ConversationMessage(
                role="assistant",
                content=response,
                timestamp=datetime.datetime.now().isoformat(),
            )
            conv["messages"].append(assistant_msg)
            # v0.7.83 — persist after assistant reply so a refresh
            # between turns sees the full conversation.
            cls._persist(conv_id)

            cls._broadcast(
                conv_id,
                "response_complete",
                {"content": response, "backend": backend or "claude"},
            )

        except Exception as e:
            logger.error(f"Error processing with Claude: {e}", exc_info=True)
            cls._broadcast(conv_id, "error", {"error": str(e)})
        finally:
            conv["processing"] = False

    @classmethod
    def _cleanup_conversation(cls, conv_id: str) -> None:
        """Clean up a conversation and its resources."""
        with cls._lock:
            for queue in cls._subscribers.get(conv_id, []):
                queue.put(None)

            cls._conversations.pop(conv_id, None)
            cls._subscribers.pop(conv_id, None)
            cls._start_times.pop(conv_id, None)
