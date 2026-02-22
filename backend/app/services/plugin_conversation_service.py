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
from typing import Dict, Generator, List, Tuple

logger = logging.getLogger(__name__)

from ..database import (
    add_plugin,
    add_plugin_component,
    get_plugin_detail,
)

# Stale conversation cleanup threshold (30 minutes)
STALE_CONVERSATION_THRESHOLD = 1800

# System prompt for plugin creation conversation
PLUGIN_CREATION_SYSTEM_PROMPT = """You are an AI assistant helping to create a new Plugin for the Hive platform. Your job is to guide the user through designing their plugin step by step.

A plugin is a bundle of components that extends Hive's capabilities. Each plugin can contain multiple components of the following types:
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
    def start_conversation(cls) -> Tuple[dict, HTTPStatus]:
        """Start a new plugin creation conversation."""
        conv_id = cls._generate_conv_id()

        initial_messages = [
            ConversationMessage(
                role="system",
                content=PLUGIN_CREATION_SYSTEM_PROMPT,
                timestamp=datetime.datetime.now().isoformat(),
            )
        ]

        with cls._lock:
            cls._conversations[conv_id] = {"messages": initial_messages, "processing": False}
            cls._subscribers[conv_id] = []
            cls._start_times[conv_id] = datetime.datetime.now()

        # Trigger initial assistant greeting
        cls._process_with_claude(conv_id, "Hello, I'd like to create a new plugin.")

        return {
            "conversation_id": conv_id,
            "message": "Plugin creation conversation started",
        }, HTTPStatus.CREATED

    @classmethod
    def get_conversation(cls, conv_id: str) -> Tuple[dict, HTTPStatus]:
        """Get conversation details and messages."""
        if conv_id not in cls._conversations:
            return {"error": "Conversation not found"}, HTTPStatus.NOT_FOUND

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
    ) -> Tuple[dict, HTTPStatus]:
        """Send a user message and process with Claude."""
        if conv_id not in cls._conversations:
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
            yield f"event: error\ndata: {json.dumps({'error': 'Conversation not found'})}\n\n"
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
                    yield f"event: ping\ndata: {json.dumps({'time': datetime.datetime.now().isoformat()})}\n\n"
        finally:
            with cls._lock:
                if conv_id in cls._subscribers and queue in cls._subscribers[conv_id]:
                    cls._subscribers[conv_id].remove(queue)

    @classmethod
    def finalize_plugin(cls, conv_id: str) -> Tuple[dict, HTTPStatus]:
        """Finalize the conversation and create the plugin."""
        if conv_id not in cls._conversations:
            return {"error": "Conversation not found"}, HTTPStatus.NOT_FOUND

        conv = cls._conversations[conv_id]

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
                    logger.error(f"Failed to parse plugin config: {e}")
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
            plugin_id = add_plugin(
                name=plugin_name,
                description=description,
                version=version,
                status="draft",
            )

            if not plugin_id:
                return {"error": "Failed to create plugin"}, HTTPStatus.INTERNAL_SERVER_ERROR

            # Add components
            for comp in components:
                comp_name = comp.get("name", "unnamed")
                comp_type = comp.get("type", "skill")
                comp_content = comp.get("content", "")
                add_plugin_component(plugin_id, comp_name, comp_type, comp_content)

            # Mark conversation as finalized
            conv["finalized"] = True

            cls._cleanup_conversation(conv_id)

            plugin = get_plugin_detail(plugin_id)

            return {
                "message": "Plugin created successfully",
                "plugin_id": plugin_id,
                "plugin": plugin,
            }, HTTPStatus.CREATED

        except Exception as e:
            logger.error(f"Failed to create plugin: {e}")
            return {"error": f"Failed to create plugin: {str(e)}"}, HTTPStatus.INTERNAL_SERVER_ERROR

    @classmethod
    def abandon_conversation(cls, conv_id: str) -> Tuple[dict, HTTPStatus]:
        """Abandon a conversation without creating a plugin."""
        if conv_id not in cls._conversations:
            return {"error": "Conversation not found"}, HTTPStatus.NOT_FOUND

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

            # Build messages from conversation history
            messages = []
            for msg in conv["messages"]:
                messages.append({"role": msg.role, "content": msg.content})

            # Stream response chunks in real-time
            full_response_parts = []
            for chunk in stream_llm_response(
                messages, model=model, account_email=account_id, backend=backend
            ):
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

            cls._broadcast(
                conv_id,
                "response_complete",
                {"content": response, "backend": backend or "claude"},
            )

        except Exception as e:
            logger.error(f"Error processing with Claude: {e}")
            cls._broadcast(conv_id, "error", {"error": str(e)})
        finally:
            conv["processing"] = False

    @classmethod
    def _cleanup_conversation(cls, conv_id: str):
        """Clean up a conversation and its resources."""
        with cls._lock:
            for queue in cls._subscribers.get(conv_id, []):
                queue.put(None)

            cls._conversations.pop(conv_id, None)
            cls._subscribers.pop(conv_id, None)
            cls._start_times.pop(conv_id, None)
