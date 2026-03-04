"""Trigger configuration export/import service.

Provides YAML/JSON export and import of trigger configurations for GitOps
workflows. Supports upsert to update existing triggers by name match.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

import yaml

from app.db import (
    add_project_path,
    add_trigger,
    get_all_triggers,
    get_trigger,
    get_trigger_by_name,
    list_paths_for_trigger,
    remove_project_path,
    update_trigger,
)
from app.services.audit_log_service import AuditLogService

logger = logging.getLogger(__name__)

# Fields that must never appear in exported configs (security)
_SENSITIVE_FIELDS = {"webhook_secret"}

# Required top-level keys in a valid config
_REQUIRED_KEYS = {"version", "kind", "metadata", "spec"}

# Required metadata keys
_REQUIRED_METADATA = {"name", "backend_type", "trigger_source"}


def export_trigger(trigger_id: str, format: str = "yaml") -> Optional[str]:
    """Export a single trigger configuration as YAML or JSON.

    Args:
        trigger_id: The trigger ID to export.
        format: Output format, 'yaml' or 'json'.

    Returns:
        Serialized config string, or None if trigger not found.
    """
    trigger = get_trigger(trigger_id)
    if not trigger:
        return None

    paths = list_paths_for_trigger(trigger_id)
    config = _build_config_dict(trigger, paths)

    return _serialize(config, format)


def export_all_triggers(format: str = "yaml") -> str:
    """Export all triggers as a multi-document YAML stream or JSON array.

    Args:
        format: Output format, 'yaml' or 'json'.

    Returns:
        Serialized config string containing all triggers.
    """
    triggers = get_all_triggers()
    configs = []
    for trigger in triggers:
        paths = list_paths_for_trigger(trigger["id"])
        configs.append(_build_config_dict(trigger, paths))

    if format == "json":
        return json.dumps(configs, indent=2)
    else:
        return yaml.dump_all(configs, default_flow_style=False, sort_keys=False)


def import_trigger(
    config_str: str, format: str = "yaml", upsert: bool = False
) -> tuple[str, str]:
    """Import a trigger from a YAML or JSON config string.

    Args:
        config_str: The config string to import.
        format: Input format, 'yaml' or 'json'.
        upsert: If True, update existing trigger by name match instead of creating.

    Returns:
        Tuple of (trigger_id, status) where status is 'created' or 'updated'.

    Raises:
        ValueError: If config is invalid.
    """
    config = _parse(config_str, format)
    valid, error = _validate_parsed(config)
    if not valid:
        raise ValueError(error)

    metadata = config["metadata"]
    spec = config["spec"]
    name = metadata["name"]

    # Check for existing trigger by name when upserting
    existing = get_trigger_by_name(name) if upsert else None

    if existing:
        return _update_existing_trigger(existing, metadata, spec)
    else:
        return _create_new_trigger(metadata, spec)


def validate_config(config_str: str, format: str = "yaml") -> tuple[bool, Optional[str]]:
    """Validate a config string without importing.

    Args:
        config_str: The config string to validate.
        format: Input format, 'yaml' or 'json'.

    Returns:
        Tuple of (is_valid, error_message). error_message is None if valid.
    """
    try:
        config = _parse(config_str, format)
    except ValueError as e:
        return False, str(e)

    return _validate_parsed(config)


def resolve_deep_link(execution_id: str, line_number: Optional[int] = None) -> str:
    """Resolve a deep-link URL for an execution, optionally at a specific line.

    Args:
        execution_id: The execution ID.
        line_number: Optional line number for the anchor.

    Returns:
        Deep-link URL string.
    """
    base = f"/executions/{execution_id}"
    if line_number is not None:
        return f"{base}#line-{line_number}"
    return base


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_config_dict(trigger: dict, paths: list[dict]) -> dict:
    """Build the export config dict from a trigger and its paths."""
    config = {
        "version": "1.0",
        "kind": "trigger",
        "metadata": {
            "name": trigger["name"],
            "backend_type": trigger["backend_type"],
            "trigger_source": trigger["trigger_source"],
            "exported_at": datetime.now(timezone.utc).isoformat(),
        },
        "spec": {
            "prompt_template": trigger["prompt_template"],
            "model": trigger.get("model"),
            "execution_mode": trigger.get("execution_mode", "direct"),
            "timeout_seconds": trigger.get("timeout_seconds"),
            "allowed_tools": trigger.get("allowed_tools"),
            "enabled": bool(trigger.get("enabled", 1)),
            "detection_keyword": trigger.get("detection_keyword", ""),
            "match_field_path": trigger.get("match_field_path"),
            "match_field_value": trigger.get("match_field_value"),
            "text_field_path": trigger.get("text_field_path"),
            "paths": [
                {
                    "local": p["local_project_path"],
                    "type": p.get("path_type") or "local",
                    "github_repo_url": p.get("github_repo_url"),
                }
                for p in paths
            ],
        },
    }

    # Include schedule config for scheduled triggers
    if trigger.get("trigger_source") == "scheduled" or trigger.get("schedule_type"):
        config["spec"]["schedule"] = {
            "type": trigger.get("schedule_type"),
            "time": trigger.get("schedule_time"),
            "day": trigger.get("schedule_day"),
            "timezone": trigger.get("schedule_timezone", "Asia/Seoul"),
        }

    return config


def _serialize(config: dict, format: str) -> str:
    """Serialize a config dict to YAML or JSON."""
    if format == "json":
        return json.dumps(config, indent=2)
    return yaml.dump(config, default_flow_style=False, sort_keys=False)


def _parse(config_str: str, format: str) -> dict:
    """Parse a config string from YAML or JSON."""
    try:
        if format == "json":
            return json.loads(config_str)
        else:
            return yaml.safe_load(config_str)
    except (json.JSONDecodeError, yaml.YAMLError) as e:
        raise ValueError(f"Failed to parse {format}: {e}")


def _validate_parsed(config: dict) -> tuple[bool, Optional[str]]:
    """Validate the structure of a parsed config dict."""
    if not isinstance(config, dict):
        return False, "Config must be a mapping/dict"

    missing = _REQUIRED_KEYS - set(config.keys())
    if missing:
        return False, f"Missing required keys: {missing}"

    if config.get("kind") != "trigger":
        return False, f"Unsupported kind: {config.get('kind')}. Expected 'trigger'"

    metadata = config.get("metadata", {})
    if not isinstance(metadata, dict):
        return False, "metadata must be a mapping/dict"

    missing_meta = _REQUIRED_METADATA - set(metadata.keys())
    if missing_meta:
        return False, f"Missing required metadata keys: {missing_meta}"

    spec = config.get("spec", {})
    if not isinstance(spec, dict):
        return False, "spec must be a mapping/dict"

    if "prompt_template" not in spec:
        return False, "spec.prompt_template is required"

    return True, None


def _create_new_trigger(metadata: dict, spec: dict) -> tuple[str, str]:
    """Create a new trigger from parsed config."""
    schedule = spec.get("schedule", {})

    trigger_id = add_trigger(
        name=metadata["name"],
        prompt_template=spec["prompt_template"],
        backend_type=metadata["backend_type"],
        trigger_source=metadata["trigger_source"],
        match_field_path=spec.get("match_field_path"),
        match_field_value=spec.get("match_field_value"),
        text_field_path=spec.get("text_field_path"),
        detection_keyword=spec.get("detection_keyword", ""),
        model=spec.get("model"),
        execution_mode=spec.get("execution_mode", "direct"),
        timeout_seconds=spec.get("timeout_seconds"),
        allowed_tools=spec.get("allowed_tools"),
        schedule_type=schedule.get("type"),
        schedule_time=schedule.get("time"),
        schedule_day=schedule.get("day"),
        schedule_timezone=schedule.get("timezone", "Asia/Seoul"),
    )

    if not trigger_id:
        raise ValueError("Failed to create trigger (possible name collision)")

    # Create paths
    for p in spec.get("paths", []):
        add_project_path(trigger_id, p["local"])

    AuditLogService.log(
        action="config.import",
        entity_type="trigger",
        entity_id=trigger_id,
        outcome="created",
        details={"name": metadata["name"]},
    )

    return trigger_id, "created"


def _update_existing_trigger(existing: dict, metadata: dict, spec: dict) -> tuple[str, str]:
    """Update an existing trigger from parsed config."""
    trigger_id = existing["id"]
    schedule = spec.get("schedule", {})

    update_trigger(
        trigger_id=trigger_id,
        name=metadata["name"],
        prompt_template=spec["prompt_template"],
        backend_type=metadata["backend_type"],
        trigger_source=metadata["trigger_source"],
        match_field_path=spec.get("match_field_path"),
        match_field_value=spec.get("match_field_value"),
        text_field_path=spec.get("text_field_path"),
        detection_keyword=spec.get("detection_keyword", ""),
        model=spec.get("model"),
        execution_mode=spec.get("execution_mode", "direct"),
        timeout_seconds=spec.get("timeout_seconds"),
        allowed_tools=spec.get("allowed_tools"),
        schedule_type=schedule.get("type"),
        schedule_time=schedule.get("time"),
        schedule_day=schedule.get("day"),
        schedule_timezone=schedule.get("timezone", "Asia/Seoul"),
    )

    # Sync paths: remove old, add new
    old_paths = list_paths_for_trigger(trigger_id)
    for p in old_paths:
        remove_project_path(trigger_id, p["local_project_path"])

    for p in spec.get("paths", []):
        add_project_path(trigger_id, p["local"])

    AuditLogService.log(
        action="config.import",
        entity_type="trigger",
        entity_id=trigger_id,
        outcome="updated",
        details={"name": metadata["name"]},
    )

    return trigger_id, "updated"
