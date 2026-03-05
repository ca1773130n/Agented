"""Tests for prompt version history, rollback, and full preview."""

from unittest.mock import patch

from app.db.triggers import (
    add_trigger,
    get_prompt_template_history,
    get_trigger,
    log_prompt_template_change,
)


def test_log_template_change_with_diff(isolated_db):
    """Log a change with old/new templates; verify diff_text is non-empty."""
    trigger_id = add_trigger(name="test-bot", prompt_template="old prompt")
    assert trigger_id is not None

    result = log_prompt_template_change(
        trigger_id, old_template="old prompt", new_template="new prompt"
    )
    assert result is True

    history = get_prompt_template_history(trigger_id)
    assert len(history) == 1
    assert history[0]["diff_text"] != ""


def test_log_template_change_with_author(isolated_db):
    """Log with author='user'; verify author field stored."""
    trigger_id = add_trigger(name="author-bot", prompt_template="v1")
    log_prompt_template_change(trigger_id, "v1", "v2", author="user")

    history = get_prompt_template_history(trigger_id)
    assert history[0]["author"] == "user"


def test_get_history_returns_entries(isolated_db):
    """Log 3 changes; get history returns 3 entries in reverse chronological order."""
    trigger_id = add_trigger(name="multi-bot", prompt_template="v0")

    for i in range(3):
        log_prompt_template_change(trigger_id, f"v{i}", f"v{i+1}", author=f"user{i}")

    history = get_prompt_template_history(trigger_id)
    assert len(history) == 3
    # Newest first
    assert history[0]["new_template"] == "v3"
    assert history[-1]["new_template"] == "v1"


def test_rollback_prompt_template(client):
    """Create trigger, log changes, rollback to version 1; verify prompt matches."""
    # Create trigger
    create_resp = client.post(
        "/admin/triggers/",
        json={"name": "rollback-bot", "prompt_template": "version 0"},
    )
    assert create_resp.status_code == 201
    trigger_id = create_resp.get_json()["trigger_id"]

    # Log changes
    log_prompt_template_change(trigger_id, "version 0", "version 1", author="user")
    from app.db.triggers import update_trigger
    update_trigger(trigger_id, prompt_template="version 1")

    log_prompt_template_change(trigger_id, "version 1", "version 2", author="user")
    update_trigger(trigger_id, prompt_template="version 2")

    # Get history to find version 1's id
    history = get_prompt_template_history(trigger_id)
    # history[0] = v1->v2 (newest), history[1] = v0->v1
    version_1_entry = history[1]  # The entry where new_template = "version 1"
    assert version_1_entry["new_template"] == "version 1"

    # Rollback
    resp = client.post(
        f"/admin/triggers/{trigger_id}/rollback-prompt",
        json={"version_id": version_1_entry["id"]},
    )
    assert resp.status_code == 200

    # Verify trigger prompt was rolled back
    trigger = get_trigger(trigger_id)
    assert trigger["prompt_template"] == "version 1"


def test_rollback_creates_history_entry(client):
    """After rollback, verify new history entry created with author='rollback'."""
    create_resp = client.post(
        "/admin/triggers/",
        json={"name": "rollback-history-bot", "prompt_template": "original"},
    )
    trigger_id = create_resp.get_json()["trigger_id"]

    log_prompt_template_change(trigger_id, "original", "modified", author="user")
    from app.db.triggers import update_trigger
    update_trigger(trigger_id, prompt_template="modified")

    history_before = get_prompt_template_history(trigger_id)
    version_id = history_before[0]["id"]

    # Rollback to "modified" (which is the current state, but tests the mechanism)
    client.post(
        f"/admin/triggers/{trigger_id}/rollback-prompt",
        json={"version_id": version_id},
    )

    history_after = get_prompt_template_history(trigger_id)
    assert len(history_after) == len(history_before) + 1
    assert history_after[0]["author"] == "rollback"


def test_rollback_nonexistent_trigger(client):
    """Rollback on non-existent trigger returns 404."""
    resp = client.post(
        "/admin/triggers/nonexistent/rollback-prompt",
        json={"version_id": 1},
    )
    assert resp.status_code == 404


def test_rollback_version_mismatch(client):
    """Rollback with version_id belonging to different trigger returns error."""
    # Create two triggers
    resp1 = client.post(
        "/admin/triggers/",
        json={"name": "bot-A", "prompt_template": "prompt A"},
    )
    resp2 = client.post(
        "/admin/triggers/",
        json={"name": "bot-B", "prompt_template": "prompt B"},
    )
    trigger_id_a = resp1.get_json()["trigger_id"]
    trigger_id_b = resp2.get_json()["trigger_id"]

    # Log change on trigger A
    log_prompt_template_change(trigger_id_a, "prompt A", "prompt A v2", author="user")

    history_a = get_prompt_template_history(trigger_id_a)
    version_id_a = history_a[0]["id"]

    # Try to rollback trigger B using trigger A's version
    resp = client.post(
        f"/admin/triggers/{trigger_id_b}/rollback-prompt",
        json={"version_id": version_id_a},
    )
    # Should fail -- version not found for trigger B
    assert resp.status_code == 404


def test_preview_prompt_full_returns_all_fields(client):
    """Create trigger, call preview_prompt_full; verify response fields."""
    create_resp = client.post(
        "/admin/triggers/",
        json={"name": "preview-bot", "prompt_template": "Hello {message} at {paths}"},
    )
    trigger_id = create_resp.get_json()["trigger_id"]

    resp = client.post(
        f"/admin/triggers/{trigger_id}/preview-prompt-full",
        json={"message": "world", "paths": "/my/project"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "rendered_prompt" in data
    assert "cli_command" in data
    assert "cli_command_parts" in data
    assert "backend_type" in data
    assert "trigger_name" in data
    assert data["trigger_name"] == "preview-bot"
    # Check that placeholders were substituted
    assert "world" in data["rendered_prompt"]
    assert "/my/project" in data["rendered_prompt"]


def test_preview_prompt_full_does_not_spawn_process(client):
    """Call preview_prompt_full; verify no subprocess.Popen was called."""
    create_resp = client.post(
        "/admin/triggers/",
        json={"name": "no-exec-bot", "prompt_template": "Test {message}"},
    )
    trigger_id = create_resp.get_json()["trigger_id"]

    with patch("subprocess.Popen") as mock_popen:
        resp = client.post(
            f"/admin/triggers/{trigger_id}/preview-prompt-full",
            json={"message": "test"},
        )
        assert resp.status_code == 200
        mock_popen.assert_not_called()


def test_prompt_history_endpoint(client):
    """GET /admin/triggers/{id}/prompt-history returns history list."""
    create_resp = client.post(
        "/admin/triggers/",
        json={"name": "history-endpoint-bot", "prompt_template": "initial"},
    )
    trigger_id = create_resp.get_json()["trigger_id"]

    log_prompt_template_change(trigger_id, "initial", "updated", author="test")

    resp = client.get(f"/admin/triggers/{trigger_id}/prompt-history")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "history" in data
    assert len(data["history"]) == 1
    assert data["history"][0]["author"] == "test"


def test_rollback_endpoint(client):
    """POST /admin/triggers/{id}/rollback-prompt with version_id returns success."""
    create_resp = client.post(
        "/admin/triggers/",
        json={"name": "rollback-endpoint-bot", "prompt_template": "start"},
    )
    trigger_id = create_resp.get_json()["trigger_id"]

    log_prompt_template_change(trigger_id, "start", "changed", author="user")
    from app.db.triggers import update_trigger
    update_trigger(trigger_id, prompt_template="changed")

    history = get_prompt_template_history(trigger_id)
    version_id = history[0]["id"]

    resp = client.post(
        f"/admin/triggers/{trigger_id}/rollback-prompt",
        json={"version_id": version_id},
    )
    assert resp.status_code == 200
    assert "message" in resp.get_json()
