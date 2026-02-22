"""Rule conversation service for interactive rule creation with SSE streaming."""

import datetime
import logging
import threading
from http import HTTPStatus
from queue import Queue
from typing import Dict, List, Tuple

from ..database import add_rule, get_rule
from .base_conversation_service import BaseConversationService

logger = logging.getLogger(__name__)

RULE_CREATION_SYSTEM_PROMPT = """You are an AI assistant helping to create a new Rule for the Hive platform. Your job is to guide the user through designing their rule step by step.

A rule defines validation logic, pre-checks, or post-checks that Claude applies during operations. Rules enforce standards, catch issues, and ensure quality.

Rule types:
- **pre_check** — Validates conditions before an action is taken
- **post_check** — Validates conditions after an action completes
- **validation** — General validation rule applied during processing

Help the user define:
1. **Rule Name** — A short, descriptive name (e.g., "no-console-log", "require-tests", "max-file-size")
2. **Rule Type** — One of: pre_check, post_check, validation
3. **Description** — What does this rule enforce?
4. **Condition** — When should this rule trigger? (e.g., "when modifying files in src/", "when PR has no tests")
5. **Action** — What should happen when the condition is met? (e.g., "warn about missing tests", "block commit", "suggest fix")

Ask clarifying questions and provide suggestions. Be conversational and helpful. Help the user think about edge cases and appropriate severity.

When you have gathered enough information, summarize the rule configuration and ask the user to confirm.

When the user confirms, output the final configuration in this exact format:
---RULE_CONFIG---
{
  "name": "rule-name",
  "rule_type": "validation",
  "description": "Brief description of what this rule enforces",
  "condition": "When this rule should trigger",
  "action": "What happens when the condition is met",
  "enabled": true
}
---END_CONFIG---

Start by asking the user what kind of rule they want to create and what standard or quality gate it should enforce."""


class RuleConversationService(BaseConversationService):
    """Service for managing rule creation conversations with real-time SSE streaming."""

    # Own class-level state (not shared with other entity services)
    _conversations: Dict[str, dict] = {}
    _subscribers: Dict[str, List[Queue]] = {}
    _start_times: Dict[str, datetime.datetime] = {}
    _lock = threading.Lock()

    @classmethod
    def _get_system_prompt(cls) -> str:
        return RULE_CREATION_SYSTEM_PROMPT

    @classmethod
    def _get_conv_id_prefix(cls) -> str:
        return "rule_"

    @classmethod
    def _get_entity_type(cls) -> str:
        return "rule"

    @classmethod
    def _get_config_start_marker(cls) -> str:
        return "---RULE_CONFIG---"

    @classmethod
    def _get_config_end_marker(cls) -> str:
        return "---END_CONFIG---"

    @classmethod
    def _finalize_entity(cls, conv_id: str) -> Tuple[dict, HTTPStatus]:
        """Finalize the conversation and create the rule."""
        if conv_id not in cls._conversations:
            return {"error": "Conversation not found"}, HTTPStatus.NOT_FOUND

        config = cls._extract_config_from_conversation(conv_id)
        if not config:
            return {
                "error": "No rule configuration found. Please continue the conversation."
            }, HTTPStatus.BAD_REQUEST

        name = config.get("name", "Untitled Rule")
        rule_type = config.get("rule_type", "validation")
        description = config.get("description", "")
        condition = config.get("condition", "")
        action = config.get("action", "")
        enabled = config.get("enabled", True)

        try:
            rule_id = add_rule(
                name=name,
                rule_type=rule_type,
                description=description,
                condition=condition,
                action=action,
                enabled=enabled,
            )

            if not rule_id:
                return {"error": "Failed to create rule"}, HTTPStatus.INTERNAL_SERVER_ERROR

            cls._conversations[conv_id]["finalized"] = True
            cls._cleanup_conversation(conv_id)

            rule = get_rule(rule_id)

            return {
                "message": "Rule created successfully",
                "rule_id": rule_id,
                "rule": rule,
            }, HTTPStatus.CREATED

        except Exception as e:
            logger.error(f"Failed to create rule: {e}")
            return {"error": f"Failed to create rule: {str(e)}"}, HTTPStatus.INTERNAL_SERVER_ERROR
