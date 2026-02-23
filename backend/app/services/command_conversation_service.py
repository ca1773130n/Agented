"""Command conversation service for interactive command creation with SSE streaming."""

import datetime
import json
import logging
import threading
from http import HTTPStatus
from queue import Queue
from typing import Dict, List, Tuple

from ..database import add_command, get_command
from .base_conversation_service import BaseConversationService

logger = logging.getLogger(__name__)

COMMAND_CREATION_SYSTEM_PROMPT = """You are an AI assistant helping to create a new Slash Command for the Agented platform. Your job is to guide the user through designing their command step by step.

A slash command is invoked by the user with a / prefix (e.g., /deploy, /lint, /review). Commands provide reusable instructions that Claude follows when the command is triggered.

Help the user define:
1. **Command Name** — The name without the / prefix (e.g., "deploy", "lint", "review")
2. **Description** — A brief description of what this command does
3. **Content** — The markdown instructions that Claude follows when the command is invoked
4. **Arguments** — Optional arguments the command accepts, each with:
   - **name** — Argument name
   - **type** — Argument type (string, number, boolean, file_path, etc.)
   - **description** — What this argument is for

Ask clarifying questions and provide suggestions. Be conversational and helpful. Help the user craft clear, effective instructions.

When you have gathered enough information, summarize the command configuration and ask the user to confirm.

When the user confirms, output the final configuration in this exact format:
---COMMAND_CONFIG---
{
  "name": "command-name",
  "description": "Brief description of what this command does",
  "content": "The markdown instructions for Claude to follow...",
  "arguments": [
    {
      "name": "arg-name",
      "type": "string",
      "description": "What this argument is for"
    }
  ],
  "enabled": true
}
---END_CONFIG---

Start by asking the user what kind of slash command they want to create and what problem it should solve."""


class CommandConversationService(BaseConversationService):
    """Service for managing command creation conversations with real-time SSE streaming."""

    # Own class-level state (not shared with other entity services)
    _conversations: Dict[str, dict] = {}
    _subscribers: Dict[str, List[Queue]] = {}
    _start_times: Dict[str, datetime.datetime] = {}
    _lock = threading.Lock()

    @classmethod
    def _get_system_prompt(cls) -> str:
        return COMMAND_CREATION_SYSTEM_PROMPT

    @classmethod
    def _get_conv_id_prefix(cls) -> str:
        return "cmd_"

    @classmethod
    def _get_entity_type(cls) -> str:
        return "command"

    @classmethod
    def _get_config_start_marker(cls) -> str:
        return "---COMMAND_CONFIG---"

    @classmethod
    def _get_config_end_marker(cls) -> str:
        return "---END_CONFIG---"

    @classmethod
    def _finalize_entity(cls, conv_id: str) -> Tuple[dict, HTTPStatus]:
        """Finalize the conversation and create the command."""
        if conv_id not in cls._conversations:
            return {"error": "Conversation not found"}, HTTPStatus.NOT_FOUND

        config = cls._extract_config_from_conversation(conv_id)
        if not config:
            return {
                "error": "No command configuration found. Please continue the conversation."
            }, HTTPStatus.BAD_REQUEST

        name = config.get("name", "Untitled Command")
        description = config.get("description", "")
        content = config.get("content", "")
        arguments = config.get("arguments", [])
        enabled = config.get("enabled", True)

        # Serialize arguments list to JSON string for DB storage
        arguments_str = json.dumps(arguments) if arguments else None

        try:
            command_id = add_command(
                name=name,
                description=description,
                content=content,
                arguments=arguments_str,
                enabled=enabled,
            )

            if not command_id:
                return {"error": "Failed to create command"}, HTTPStatus.INTERNAL_SERVER_ERROR

            cls._conversations[conv_id]["finalized"] = True
            cls._cleanup_conversation(conv_id)

            command = get_command(command_id)

            return {
                "message": "Command created successfully",
                "command_id": command_id,
                "command": command,
            }, HTTPStatus.CREATED

        except Exception as e:
            logger.error(f"Failed to create command: {e}")
            return {
                "error": f"Failed to create command: {str(e)}"
            }, HTTPStatus.INTERNAL_SERVER_ERROR
