"""Hook conversation service for interactive hook creation with SSE streaming."""

import datetime
import logging
import threading
from http import HTTPStatus
from queue import Queue
from typing import Dict, List, Tuple

from ..database import add_hook, get_hook
from .base_conversation_service import BaseConversationService

logger = logging.getLogger(__name__)

HOOK_CREATION_SYSTEM_PROMPT = """You are an AI assistant helping to create a new Hook for the Hive platform. Your job is to guide the user through designing their hook step by step.

A hook is an event-driven action triggered by Claude Code lifecycle events. Hooks run automatically when specific events occur during a coding session.

Valid hook events:
- **PreToolUse** — Runs before a tool call (e.g., before file write, before bash command)
- **PostToolUse** — Runs after a tool call completes
- **Stop** — Runs when the main agent stops
- **SubagentStop** — Runs when a sub-agent (e.g., Task tool) stops
- **SessionStart** — Runs at the beginning of a session
- **SessionEnd** — Runs at the end of a session
- **UserPromptSubmit** — Runs when the user submits a prompt
- **PreCompact** — Runs before conversation compaction
- **Notification** — Runs when a notification is triggered

Help the user define:
1. **Hook Name** — A short, descriptive name (e.g., "lint-on-save", "security-check")
2. **Event** — Which lifecycle event triggers this hook (from the list above)
3. **Description** — What does this hook do?
4. **Content** — The actual hook script/instructions (bash command or instruction text)

Ask clarifying questions and provide suggestions. Be conversational and helpful.

When you have gathered enough information, summarize the hook configuration and ask the user to confirm.

When the user confirms, output the final configuration in this exact format:
---HOOK_CONFIG---
{
  "name": "hook-name",
  "event": "PreToolUse",
  "description": "Brief description of what this hook does",
  "content": "The hook script or instructions",
  "enabled": true
}
---END_CONFIG---

Start by asking the user what kind of hook they want to create and what event it should respond to."""


class HookConversationService(BaseConversationService):
    """Service for managing hook creation conversations with real-time SSE streaming."""

    # Own class-level state (not shared with other entity services)
    _conversations: Dict[str, dict] = {}
    _subscribers: Dict[str, List[Queue]] = {}
    _start_times: Dict[str, datetime.datetime] = {}
    _lock = threading.Lock()

    @classmethod
    def _get_system_prompt(cls) -> str:
        return HOOK_CREATION_SYSTEM_PROMPT

    @classmethod
    def _get_conv_id_prefix(cls) -> str:
        return "hook_"

    @classmethod
    def _get_entity_type(cls) -> str:
        return "hook"

    @classmethod
    def _get_config_start_marker(cls) -> str:
        return "---HOOK_CONFIG---"

    @classmethod
    def _get_config_end_marker(cls) -> str:
        return "---END_CONFIG---"

    @classmethod
    def _finalize_entity(cls, conv_id: str) -> Tuple[dict, HTTPStatus]:
        """Finalize the conversation and create the hook."""
        if conv_id not in cls._conversations:
            return {"error": "Conversation not found"}, HTTPStatus.NOT_FOUND

        config = cls._extract_config_from_conversation(conv_id)
        if not config:
            return {
                "error": "No hook configuration found. Please continue the conversation."
            }, HTTPStatus.BAD_REQUEST

        name = config.get("name", "Untitled Hook")
        event = config.get("event", "PreToolUse")
        description = config.get("description", "")
        content = config.get("content", "")
        enabled = config.get("enabled", True)

        try:
            hook_id = add_hook(
                name=name,
                event=event,
                description=description,
                content=content,
                enabled=enabled,
            )

            if not hook_id:
                return {"error": "Failed to create hook"}, HTTPStatus.INTERNAL_SERVER_ERROR

            cls._conversations[conv_id]["finalized"] = True
            cls._cleanup_conversation(conv_id)

            hook = get_hook(hook_id)

            return {
                "message": "Hook created successfully",
                "hook_id": hook_id,
                "hook": hook,
            }, HTTPStatus.CREATED

        except Exception as e:
            logger.error(f"Failed to create hook: {e}")
            return {"error": f"Failed to create hook: {str(e)}"}, HTTPStatus.INTERNAL_SERVER_ERROR
