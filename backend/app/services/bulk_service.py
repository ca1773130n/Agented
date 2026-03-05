"""Bulk operation service for batch entity management (API-05).

Processes bulk create/update/delete operations for agents, triggers, plugins, and hooks.
Each item is processed independently so one failure does not roll back successful items.
"""

import logging
from typing import Any

from ..database import (
    add_agent,
    add_hook,
    add_plugin,
    add_trigger,
    delete_agent,
    delete_hook,
    delete_plugin,
    delete_trigger,
    update_agent,
    update_hook,
    update_plugin,
    update_trigger,
)
from ..db.triggers import PREDEFINED_TRIGGER_IDS

logger = logging.getLogger(__name__)

VALID_ENTITY_TYPES = {"agent", "trigger", "plugin", "hook"}
VALID_ACTIONS = {"create", "update", "delete"}


class BulkService:
    """Processes bulk create/update/delete operations for entities (API-05)."""

    MAX_ITEMS = 100

    @staticmethod
    def process(entity_type: str, action: str, items: list) -> list[dict[str, Any]]:
        """Process bulk operations. Returns per-item results.

        Args:
            entity_type: One of "agent", "trigger", "plugin", "hook".
            action: One of "create", "update", "delete".
            items: List of item dicts to process.

        Returns:
            List of result dicts: {"index": int, "success": bool, "id": str|None, "error": str|None}

        Raises:
            ValueError: If entity_type, action, or items length is invalid.
        """
        if entity_type not in VALID_ENTITY_TYPES:
            raise ValueError(
                f"Invalid entity_type '{entity_type}'. Must be one of: {', '.join(sorted(VALID_ENTITY_TYPES))}"
            )
        if action not in VALID_ACTIONS:
            raise ValueError(
                f"Invalid action '{action}'. Must be one of: {', '.join(sorted(VALID_ACTIONS))}"
            )
        if len(items) > BulkService.MAX_ITEMS:
            raise ValueError(
                f"Too many items: {len(items)}. Maximum allowed is {BulkService.MAX_ITEMS}"
            )

        handler = _HANDLERS.get((entity_type, action))
        if not handler:
            raise ValueError(f"Unsupported combination: {entity_type}/{action}")

        results = []
        for i, item in enumerate(items):
            try:
                result = handler(item)
                results.append(result)
            except Exception as e:
                logger.warning(
                    "Bulk %s %s item %d failed: %s", action, entity_type, i, e
                )
                results.append({"index": i, "success": False, "id": None, "error": str(e)})

        # Ensure all results have correct indices
        for i, r in enumerate(results):
            r["index"] = i

        return results


# =============================================================================
# Per-entity-type handlers
# =============================================================================


def _create_agent(item: dict) -> dict:
    name = item.get("name")
    if not name:
        return {"index": 0, "success": False, "id": None, "error": "name is required"}
    agent_id = add_agent(
        name=name,
        description=item.get("description"),
        role=item.get("role"),
        goals=item.get("goals"),
        context=item.get("context"),
        backend_type=item.get("backend_type", "claude"),
        skills=item.get("skills"),
        system_prompt=item.get("system_prompt"),
    )
    if not agent_id:
        return {"index": 0, "success": False, "id": None, "error": "Failed to create agent"}
    return {"index": 0, "success": True, "id": agent_id, "error": None}


def _update_agent(item: dict) -> dict:
    agent_id = item.get("id")
    if not agent_id:
        return {"index": 0, "success": False, "id": None, "error": "id is required for update"}
    fields = {k: v for k, v in item.items() if k != "id" and v is not None}
    if not fields:
        return {"index": 0, "success": False, "id": agent_id, "error": "No fields to update"}
    success = update_agent(agent_id, **fields)
    if not success:
        return {"index": 0, "success": False, "id": agent_id, "error": "Agent not found or no changes"}
    return {"index": 0, "success": True, "id": agent_id, "error": None}


def _delete_agent(item: dict) -> dict:
    agent_id = item.get("id")
    if not agent_id:
        return {"index": 0, "success": False, "id": None, "error": "id is required for delete"}
    success = delete_agent(agent_id)
    if not success:
        return {"index": 0, "success": False, "id": agent_id, "error": "Agent not found"}
    return {"index": 0, "success": True, "id": agent_id, "error": None}


def _create_trigger(item: dict) -> dict:
    name = item.get("name")
    if not name:
        return {"index": 0, "success": False, "id": None, "error": "name is required"}
    prompt_template = item.get("prompt_template")
    if not prompt_template:
        return {"index": 0, "success": False, "id": None, "error": "prompt_template is required"}
    trigger_id = add_trigger(
        name=name,
        prompt_template=prompt_template,
        backend_type=item.get("backend_type", "claude"),
        trigger_source=item.get("trigger_source", "webhook"),
    )
    if not trigger_id:
        return {"index": 0, "success": False, "id": None, "error": "Failed to create trigger"}
    return {"index": 0, "success": True, "id": trigger_id, "error": None}


def _update_trigger(item: dict) -> dict:
    trigger_id = item.get("id")
    if not trigger_id:
        return {"index": 0, "success": False, "id": None, "error": "id is required for update"}
    fields = {k: v for k, v in item.items() if k != "id" and v is not None}
    if not fields:
        return {"index": 0, "success": False, "id": trigger_id, "error": "No fields to update"}
    success = update_trigger(trigger_id, **fields)
    if not success:
        return {
            "index": 0, "success": False, "id": trigger_id,
            "error": "Trigger not found or no changes",
        }
    return {"index": 0, "success": True, "id": trigger_id, "error": None}


def _delete_trigger(item: dict) -> dict:
    trigger_id = item.get("id")
    if not trigger_id:
        return {"index": 0, "success": False, "id": None, "error": "id is required for delete"}
    if trigger_id in PREDEFINED_TRIGGER_IDS:
        return {
            "index": 0, "success": False, "id": trigger_id,
            "error": "Cannot delete predefined trigger",
        }
    success = delete_trigger(trigger_id)
    if not success:
        return {"index": 0, "success": False, "id": trigger_id, "error": "Trigger not found"}
    return {"index": 0, "success": True, "id": trigger_id, "error": None}


def _create_plugin(item: dict) -> dict:
    name = item.get("name")
    if not name:
        return {"index": 0, "success": False, "id": None, "error": "name is required"}
    plugin_id = add_plugin(
        name=name,
        description=item.get("description"),
        version=item.get("version", "1.0.0"),
        status=item.get("status", "draft"),
        author=item.get("author"),
    )
    if not plugin_id:
        return {"index": 0, "success": False, "id": None, "error": "Failed to create plugin"}
    return {"index": 0, "success": True, "id": plugin_id, "error": None}


def _update_plugin(item: dict) -> dict:
    plugin_id = item.get("id")
    if not plugin_id:
        return {"index": 0, "success": False, "id": None, "error": "id is required for update"}
    fields = {k: v for k, v in item.items() if k != "id" and v is not None}
    if not fields:
        return {"index": 0, "success": False, "id": plugin_id, "error": "No fields to update"}
    success = update_plugin(plugin_id, **fields)
    if not success:
        return {
            "index": 0, "success": False, "id": plugin_id,
            "error": "Plugin not found or no changes",
        }
    return {"index": 0, "success": True, "id": plugin_id, "error": None}


def _delete_plugin(item: dict) -> dict:
    plugin_id = item.get("id")
    if not plugin_id:
        return {"index": 0, "success": False, "id": None, "error": "id is required for delete"}
    success = delete_plugin(plugin_id)
    if not success:
        return {"index": 0, "success": False, "id": plugin_id, "error": "Plugin not found"}
    return {"index": 0, "success": True, "id": plugin_id, "error": None}


def _create_hook(item: dict) -> dict:
    name = item.get("name")
    if not name:
        return {"index": 0, "success": False, "id": None, "error": "name is required"}
    event = item.get("event")
    if not event:
        return {"index": 0, "success": False, "id": None, "error": "event is required"}
    hook_id = add_hook(
        name=name,
        event=event,
        description=item.get("description"),
        content=item.get("content"),
        enabled=item.get("enabled", True),
    )
    if hook_id is None:
        return {"index": 0, "success": False, "id": None, "error": "Failed to create hook"}
    return {"index": 0, "success": True, "id": hook_id, "error": None}


def _update_hook(item: dict) -> dict:
    hook_id = item.get("id")
    if hook_id is None:
        return {"index": 0, "success": False, "id": None, "error": "id is required for update"}
    fields = {k: v for k, v in item.items() if k != "id" and v is not None}
    if not fields:
        return {"index": 0, "success": False, "id": hook_id, "error": "No fields to update"}
    success = update_hook(hook_id, **fields)
    if not success:
        return {
            "index": 0, "success": False, "id": hook_id,
            "error": "Hook not found or no changes",
        }
    return {"index": 0, "success": True, "id": hook_id, "error": None}


def _delete_hook(item: dict) -> dict:
    hook_id = item.get("id")
    if hook_id is None:
        return {"index": 0, "success": False, "id": None, "error": "id is required for delete"}
    success = delete_hook(hook_id)
    if not success:
        return {"index": 0, "success": False, "id": hook_id, "error": "Hook not found"}
    return {"index": 0, "success": True, "id": hook_id, "error": None}


# Handler lookup table: (entity_type, action) -> handler function
_HANDLERS = {
    ("agent", "create"): _create_agent,
    ("agent", "update"): _update_agent,
    ("agent", "delete"): _delete_agent,
    ("trigger", "create"): _create_trigger,
    ("trigger", "update"): _update_trigger,
    ("trigger", "delete"): _delete_trigger,
    ("plugin", "create"): _create_plugin,
    ("plugin", "update"): _update_plugin,
    ("plugin", "delete"): _delete_plugin,
    ("hook", "create"): _create_hook,
    ("hook", "update"): _update_hook,
    ("hook", "delete"): _delete_hook,
}
