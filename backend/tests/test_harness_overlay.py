"""Tests for the per-execution harness overlay materializer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services import harness_overlay as ho


_BASE_HOOK = {
    "layer": "h2",
    "layer_id": "hl-test1",
    "name": "no-rm-rf",
    "spec": {
        "trigger": "pre_tool_use",
        "match": {"tool": "Bash", "arg_regex": {"command": "rm\\s+-rf"}},
        "action": {"kind": "block"},
        "message": "Refused: destructive command.",
    },
}


@pytest.fixture
def fake_claude_home(tmp_path, monkeypatch):
    """Redirect ~/.claude lookups + /tmp overlay path into tmp_path so we
    don't touch the developer's real Claude config."""
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    # Minimal user settings.json to verify it's preserved in the overlay.
    (claude / "settings.json").write_text(
        json.dumps({"theme": "dark", "hooks": {"Notification": []}})
    )
    monkeypatch.setenv("HOME", str(home))

    # Redirect /tmp overlay path so we don't fight stale /tmp dirs across
    # parallel test runs.
    monkeypatch.setattr(
        "app.services.claude_config_overlay.Path",
        _make_tmp_path_proxy(tmp_path),
    )
    return claude


def _make_tmp_path_proxy(tmp_root: Path):
    """Returns a callable that rewrites ``Path("/tmp/...")`` literals inside
    claude_config_overlay to live under ``tmp_root/tmp/...`` instead.

    Other Path("…") calls pass through unchanged."""
    real_path = Path

    def _proxy(arg=None):
        if isinstance(arg, str) and arg.startswith("/tmp/"):
            return real_path(str(tmp_root) + arg)
        if arg is None:
            return real_path()
        return real_path(arg)

    return _proxy


def test_no_hook_specs_returns_none(fake_claude_home):
    """An artifact without hook specs must not even touch the overlay
    infrastructure."""
    overlay_dir = ho.prepare_overlay_for_execution(
        "exec-no-hooks",
        {"system_prompt_overlay": "just text", "hook_specs": []},
    )
    assert overlay_dir is None


def test_h2_hook_wires_pretooluse_matcher(fake_claude_home):
    overlay_dir = ho.prepare_overlay_for_execution(
        "exec-h2",
        {"hook_specs": [_BASE_HOOK]},
    )
    assert overlay_dir is not None
    od = Path(overlay_dir)
    assert od.is_dir()

    # Sidecar exists and carries the spec verbatim.
    sidecar = od / "_agented_harness_hooks.json"
    raw = json.loads(sidecar.read_text())
    assert raw["execution_id"] == "exec-h2"
    assert raw["hook_specs"][0]["name"] == "no-rm-rf"

    # settings.json carries a PreToolUse matcher pointing at the dispatcher.
    settings = json.loads((od / "settings.json").read_text())
    pretool = settings["hooks"]["PreToolUse"]
    dispatcher = str(ho._dispatcher_script_path())
    assert any(
        h["command"] == dispatcher
        for entry in pretool
        for h in (entry.get("hooks") or [])
    )
    # User's existing theme setting survived the merge.
    assert settings["theme"] == "dark"


def test_post_tool_use_event_registered(fake_claude_home):
    h4 = {
        "layer": "h4",
        "layer_id": "hl-test2",
        "name": "retry-on-perm",
        "spec": {
            "trigger": "post_tool_use",
            "detector": {"kind": "regex_count",
                         "params": {"pattern": "permission denied"}},
            "response": {"kind": "inject_hint",
                         "params": {"text": "sudo it."}},
        },
    }
    overlay_dir = ho.prepare_overlay_for_execution(
        "exec-h4", {"hook_specs": [h4]},
    )
    settings = json.loads((Path(overlay_dir) / "settings.json").read_text())
    assert "PostToolUse" in settings["hooks"]


def test_one_matcher_per_event_not_per_spec(fake_claude_home):
    """Three H2 specs on PreToolUse should produce ONE matcher (the
    dispatcher fans out internally), not three."""
    specs = [
        {**_BASE_HOOK, "layer_id": f"hl-{i}", "name": f"rule-{i}"}
        for i in range(3)
    ]
    overlay_dir = ho.prepare_overlay_for_execution(
        "exec-fanout", {"hook_specs": specs},
    )
    settings = json.loads((Path(overlay_dir) / "settings.json").read_text())
    dispatcher = str(ho._dispatcher_script_path())
    dispatcher_entries = [
        entry for entry in settings["hooks"]["PreToolUse"]
        if any(h["command"] == dispatcher for h in (entry.get("hooks") or []))
    ]
    assert len(dispatcher_entries) == 1


def test_specs_without_recognised_trigger_return_none(fake_claude_home):
    """A spec with an unknown trigger string shouldn't create an overlay."""
    overlay_dir = ho.prepare_overlay_for_execution(
        "exec-bad-trigger",
        {"hook_specs": [{"layer": "h2", "spec": {"trigger": "made_up"}}]},
    )
    assert overlay_dir is None


def test_cleanup_removes_overlay(fake_claude_home):
    overlay_dir = ho.prepare_overlay_for_execution(
        "exec-cleanup", {"hook_specs": [_BASE_HOOK]},
    )
    assert overlay_dir is not None
    assert Path(overlay_dir).is_dir()

    ho.cleanup_overlay_for_execution("exec-cleanup")
    assert not Path(overlay_dir).exists()


def test_cleanup_is_idempotent(fake_claude_home):
    """Calling cleanup twice — or before any overlay was made — must not
    raise. The trigger-execution finally block depends on this."""
    ho.cleanup_overlay_for_execution("exec-never-existed")
    ho.cleanup_overlay_for_execution("exec-never-existed")  # again


def test_user_claude_dir_missing_returns_none(tmp_path, monkeypatch):
    """If the developer doesn't have ~/.claude at all, the overlay step
    silently no-ops and the spawn falls back to whatever Claude Code does
    by default."""
    monkeypatch.setenv("HOME", str(tmp_path))  # no ~/.claude under here
    overlay_dir = ho.prepare_overlay_for_execution(
        "exec-no-home", {"hook_specs": [_BASE_HOOK]},
    )
    assert overlay_dir is None
