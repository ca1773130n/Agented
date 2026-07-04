"""Workflow conversation service for interactive workflow design with SSE streaming.

Mirrors CommandConversationService / RuleConversationService: a concrete
BaseConversationService that streams a real LLM (resolved from the caller's
configured account) to design an automation workflow, then materializes it
into a `workflows` row + first `workflow_versions` graph on finalize.

This replaces the WorkflowPlaygroundPage's old keyword-matching stub — the
playground now chats with a real assistant like every other design surface.
"""

import datetime
import json
import logging
import threading
from http import HTTPStatus
from queue import Queue
from typing import Dict, List, Tuple

from app.models.common import error_response

from ..db.workflows import add_workflow_version_raw, create_workflow, get_workflow
from .base_conversation_service import BaseConversationService

logger = logging.getLogger(__name__)

WORKFLOW_DESIGN_SYSTEM_PROMPT = """You are an AI assistant helping to design an automation Workflow for the Agented platform. A workflow is a directed graph of nodes connected by edges that runs a multi-step automation.

Node types available:
- **trigger** — how the workflow starts (manual, webhook, schedule, github)
- **command** — run a shell command
- **script** — run a script file
- **agent** — invoke an AI agent / bot
- **conditional** — branch on a condition (e.g. exit_code == 0)
- **transform** — transform data passed between steps

Be genuinely conversational and helpful. Answer the user's questions directly, in the user's own language. If they ask a question (for example "what format is the workflow saved in?"), ANSWER it — never repeat a fixed menu. Ask clarifying questions and suggest concrete steps.

When you and the user have agreed on a design, output the final workflow in this EXACT format (and nothing else after it):
---WORKFLOW_CONFIG---
{
  "name": "workflow-name",
  "description": "what this workflow does",
  "graph": {
    "nodes": [
      { "id": "trigger-1", "type": "trigger", "label": "Start", "config": { "trigger_subtype": "manual" } },
      { "id": "command-1", "type": "command", "label": "Build", "config": { "command": "npm run build" } }
    ],
    "edges": [ { "source": "trigger-1", "target": "command-1" } ],
    "settings": {}
  }
}
---END_CONFIG---

Start by asking what the workflow should automate."""


class WorkflowConversationService(BaseConversationService):
    """Manage workflow-design conversations with real-time SSE streaming."""

    # Own class-level state (not shared with other entity services).
    _conversations: Dict[str, dict] = {}
    _subscribers: Dict[str, List[Queue]] = {}
    _start_times: Dict[str, datetime.datetime] = {}
    _lock = threading.Lock()

    @classmethod
    def _get_system_prompt(cls) -> str:
        return WORKFLOW_DESIGN_SYSTEM_PROMPT

    @classmethod
    def _get_conv_id_prefix(cls) -> str:
        return "wf_"

    @classmethod
    def _get_entity_type(cls) -> str:
        return "workflow"

    @classmethod
    def _get_config_start_marker(cls) -> str:
        return "---WORKFLOW_CONFIG---"

    @classmethod
    def _get_config_end_marker(cls) -> str:
        return "---END_CONFIG---"

    @classmethod
    def _finalize_entity(cls, conv_id: str) -> Tuple[dict, HTTPStatus]:
        """Finalize the conversation: create the workflow + its first graph version."""
        if conv_id not in cls._conversations:
            return error_response("NOT_FOUND", "Conversation not found", HTTPStatus.NOT_FOUND)

        config = cls._extract_config_from_conversation(conv_id)
        if not config:
            return {
                "error": "No workflow configuration found. Please continue the conversation."
            }, HTTPStatus.BAD_REQUEST

        name = config.get("name", "Untitled Workflow")
        description = config.get("description", "")
        graph = config.get("graph")

        try:
            workflow_id = create_workflow(name=name, description=description)
            if not workflow_id:
                return error_response(
                    "INTERNAL_SERVER_ERROR",
                    "Failed to create workflow",
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )

            # Store the designed graph as the first version (best-effort — the
            # workflow row already exists even if the graph is malformed).
            version = None
            if graph:
                version, version_error = add_workflow_version_raw(workflow_id, json.dumps(graph))
                if version is None:
                    logger.warning(
                        "workflow %s created but graph version failed: %s",
                        workflow_id,
                        version_error,
                    )

            cls._conversations[conv_id]["finalized"] = True
            cls._cleanup_conversation(conv_id)

            return {
                "message": "Workflow created successfully",
                "workflow_id": workflow_id,
                "version": version,
                "workflow": get_workflow(workflow_id),
            }, HTTPStatus.CREATED

        except Exception as e:  # noqa: BLE001 — surface any create failure to the caller
            logger.error(f"Failed to create workflow: {e}", exc_info=True)
            return {
                "error": f"Failed to create workflow: {str(e)}"
            }, HTTPStatus.INTERNAL_SERVER_ERROR
