"""Tests for trigger configuration export/import service."""

import json
import tempfile

import yaml

from app.db import add_project_path, create_trigger, get_all_triggers, get_trigger
from app.services.config_export_service import (
    export_all_triggers,
    export_trigger,
    import_trigger,
    resolve_deep_link,
    validate_config,
)


def _seed_trigger(isolated_db):
    """Create a test trigger with paths for export testing."""
    # Use a real temp directory so symlink creation succeeds
    project_dir = tempfile.mkdtemp(prefix="test-project-")
    trigger_id = create_trigger(
        name="Test Export Bot",
        prompt_template="/test-export {paths}",
        backend_type="claude",
        trigger_source="webhook",
        match_field_path="event.group_id",
        match_field_value="99",
        text_field_path="event.text",
        detection_keyword="test-keyword",
        model="claude-3-opus",
        execution_mode="direct",
        timeout_seconds=300,
        allowed_tools="Bash,Read",
    )
    add_project_path(trigger_id, project_dir)
    return trigger_id, project_dir


def _seed_scheduled_trigger(isolated_db):
    """Create a scheduled trigger for testing schedule export."""
    trigger_id = create_trigger(
        name="Scheduled Test Bot",
        prompt_template="/scheduled-test {paths}",
        backend_type="claude",
        trigger_source="scheduled",
        schedule_type="weekly",
        schedule_time="09:00",
        schedule_day=1,
        schedule_timezone="US/Eastern",
    )
    return trigger_id


def test_export_produces_valid_yaml(isolated_db):
    """Test that YAML export can be parsed back without error."""
    trigger_id, project_dir = _seed_trigger(isolated_db)
    result = export_trigger(trigger_id, format="yaml")

    assert result is not None
    parsed = yaml.safe_load(result)
    assert parsed["version"] == "1.0"
    assert parsed["kind"] == "trigger"
    assert parsed["metadata"]["name"] == "Test Export Bot"
    assert parsed["spec"]["prompt_template"] == "/test-export {paths}"
    assert len(parsed["spec"]["paths"]) == 1
    assert parsed["spec"]["paths"][0]["local"] == project_dir


def test_export_produces_valid_json(isolated_db):
    """Test that JSON export can be parsed back without error."""
    trigger_id, _ = _seed_trigger(isolated_db)
    result = export_trigger(trigger_id, format="json")

    assert result is not None
    parsed = json.loads(result)
    assert parsed["version"] == "1.0"
    assert parsed["kind"] == "trigger"
    assert parsed["metadata"]["name"] == "Test Export Bot"


def test_export_excludes_sensitive_fields(isolated_db):
    """Test that webhook_secret is not included in exports."""
    trigger_id = create_trigger(
        name="Secret Bot",
        prompt_template="/secret {paths}",
        backend_type="claude",
        trigger_source="webhook",
        webhook_secret="super-secret-value",
    )
    result = export_trigger(trigger_id, format="yaml")
    assert "super-secret-value" not in result
    assert "webhook_secret" not in result


def test_import_creates_trigger(isolated_db):
    """Test that importing a config creates a new trigger with correct fields."""
    config_yaml = """
version: "1.0"
kind: trigger
metadata:
  name: Imported Bot
  backend_type: claude
  trigger_source: webhook
spec:
  prompt_template: "/imported {paths}"
  model: claude-3-opus
  execution_mode: direct
  timeout_seconds: 600
  enabled: true
  detection_keyword: "import-test"
  paths:
    - local: /tmp/imported-project
      type: local
      github_repo_url: null
"""
    trigger_id, status = import_trigger(config_yaml, format="yaml")
    assert status == "created"
    assert trigger_id is not None

    trigger = get_trigger(trigger_id)
    assert trigger["name"] == "Imported Bot"
    assert trigger["prompt_template"] == "/imported {paths}"
    assert trigger["model"] == "claude-3-opus"
    assert trigger["timeout_seconds"] == 600


def test_lossless_roundtrip(isolated_db):
    """Test export -> import -> export produces identical normalized YAML."""
    trigger_id, _ = _seed_trigger(isolated_db)

    # Export original
    yaml1 = export_trigger(trigger_id, format="yaml")

    # Import to create new trigger
    new_id, status = import_trigger(yaml1, format="yaml", upsert=False)
    assert status == "created"

    # Export the newly created trigger
    yaml2 = export_trigger(new_id, format="yaml")

    # Normalize: strip exported_at timestamps before comparison
    def normalize(y):
        parsed = yaml.safe_load(y)
        parsed["metadata"].pop("exported_at", None)
        return yaml.dump(parsed, default_flow_style=False, sort_keys=True)

    assert normalize(yaml1) == normalize(yaml2)


def test_validate_config_catches_malformed(isolated_db):
    """Test that validation catches malformed YAML."""
    valid, error = validate_config("not: valid: yaml: {{{", format="yaml")
    assert not valid
    assert error is not None


def test_validate_config_catches_missing_fields(isolated_db):
    """Test that validation catches missing required fields."""
    config = """
version: "1.0"
kind: trigger
metadata:
  name: Missing Fields
"""
    valid, error = validate_config(config, format="yaml")
    assert not valid
    assert "spec" in error or "Missing" in error


def test_validate_config_catches_missing_metadata(isolated_db):
    """Test that validation catches missing metadata keys."""
    config = """
version: "1.0"
kind: trigger
metadata:
  name: Missing Backend
spec:
  prompt_template: "/test"
"""
    valid, error = validate_config(config, format="yaml")
    assert not valid
    assert "backend_type" in error


def test_import_missing_prompt_template(isolated_db):
    """Test that import rejects config without prompt_template."""
    config = """
version: "1.0"
kind: trigger
metadata:
  name: No Prompt
  backend_type: claude
  trigger_source: webhook
spec:
  model: claude-3-opus
"""
    valid, error = validate_config(config, format="yaml")
    assert not valid
    assert "prompt_template" in error


def test_scheduled_trigger_export_includes_schedule(isolated_db):
    """Test that scheduled trigger export includes schedule config."""
    trigger_id = _seed_scheduled_trigger(isolated_db)
    result = export_trigger(trigger_id, format="yaml")
    parsed = yaml.safe_load(result)

    assert "schedule" in parsed["spec"]
    assert parsed["spec"]["schedule"]["type"] == "weekly"
    assert parsed["spec"]["schedule"]["time"] == "09:00"
    assert parsed["spec"]["schedule"]["day"] == 1
    assert parsed["spec"]["schedule"]["timezone"] == "US/Eastern"


def test_upsert_updates_existing_trigger(isolated_db):
    """Test that upsert=True updates an existing trigger by name match."""
    # Create original trigger
    original_id = create_trigger(
        name="Upsert Target",
        prompt_template="/original {paths}",
        backend_type="claude",
        trigger_source="webhook",
    )

    # Import with same name and upsert=True
    config = """
version: "1.0"
kind: trigger
metadata:
  name: Upsert Target
  backend_type: claude
  trigger_source: webhook
spec:
  prompt_template: "/updated {paths}"
  model: claude-3-opus
  enabled: true
  detection_keyword: ""
"""
    trigger_id, status = import_trigger(config, format="yaml", upsert=True)
    assert status == "updated"
    assert trigger_id == original_id

    # Verify update applied
    trigger = get_trigger(original_id)
    assert trigger["prompt_template"] == "/updated {paths}"
    assert trigger["model"] == "claude-3-opus"

    # Verify no duplicate created
    all_triggers = get_all_triggers()
    upsert_targets = [t for t in all_triggers if t["name"] == "Upsert Target"]
    assert len(upsert_targets) == 1


def test_upsert_false_creates_new_with_existing_name(isolated_db):
    """Test that upsert=False creates a new trigger even if name exists."""
    # Create original trigger
    original_id = create_trigger(
        name="Dup Name Bot",
        prompt_template="/original {paths}",
        backend_type="claude",
        trigger_source="webhook",
    )

    config = """
version: "1.0"
kind: trigger
metadata:
  name: Dup Name Bot
  backend_type: claude
  trigger_source: webhook
spec:
  prompt_template: "/new version {paths}"
  enabled: true
  detection_keyword: ""
"""
    trigger_id, status = import_trigger(config, format="yaml", upsert=False)
    assert status == "created"
    assert trigger_id != original_id


def test_deep_link_url_without_line_number(isolated_db):
    """Test deep-link URL generation without line number."""
    url = resolve_deep_link("exec-trig-abc123-20260101T120000-xyz1")
    assert url == "/executions/exec-trig-abc123-20260101T120000-xyz1"


def test_deep_link_url_with_line_number(isolated_db):
    """Test deep-link URL generation with line number."""
    url = resolve_deep_link("exec-trig-abc123-20260101T120000-xyz1", line_number=42)
    assert url == "/executions/exec-trig-abc123-20260101T120000-xyz1#line-42"


def test_export_all_triggers_yaml(isolated_db):
    """Test export all triggers as multi-document YAML."""
    _seed_trigger(isolated_db)  # returns tuple, don't need it
    result = export_all_triggers(format="yaml")
    assert result is not None

    # Should parse as multiple documents
    docs = list(yaml.safe_load_all(result))
    # At least the seeded trigger + predefined ones
    assert len(docs) >= 1


def test_export_all_triggers_json(isolated_db):
    """Test export all triggers as JSON array."""
    _seed_trigger(isolated_db)  # returns tuple, don't need it
    result = export_all_triggers(format="json")
    parsed = json.loads(result)
    assert isinstance(parsed, list)
    assert len(parsed) >= 1


def test_export_nonexistent_trigger(isolated_db):
    """Test export returns None for nonexistent trigger."""
    result = export_trigger("trig-nonexist", format="yaml")
    assert result is None


def test_import_json_format(isolated_db):
    """Test import from JSON format."""
    config = json.dumps(
        {
            "version": "1.0",
            "kind": "trigger",
            "metadata": {
                "name": "JSON Import Bot",
                "backend_type": "claude",
                "trigger_source": "webhook",
            },
            "spec": {
                "prompt_template": "/json-import {paths}",
                "enabled": True,
                "detection_keyword": "",
            },
        }
    )

    trigger_id, status = import_trigger(config, format="json")
    assert status == "created"
    trigger = get_trigger(trigger_id)
    assert trigger["name"] == "JSON Import Bot"
