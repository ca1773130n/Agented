"""Tests for the harness-injector pure function (T2 injection step)."""

from __future__ import annotations

from unittest.mock import patch

from app.services.harness_injector import (
    MAX_OVERLAY_BYTES,
    inject_artifact_into_cmd,
    inject_artifact_into_env,
)


_BASE_CMD = ["claude", "-p", "do the thing", "--output-format", "stream-json"]


def test_overlay_appended_for_claude():
    artifact = {"system_prompt_overlay": "Quote spaced cols."}
    new_cmd, components = inject_artifact_into_cmd(_BASE_CMD, "claude", artifact)
    assert new_cmd[-2:] == ["--append-system-prompt", "Quote spaced cols."]
    assert components == {
        "system_prompt": True,
        "hooks": False,
        "tool_overrides": False,
    }


def test_original_cmd_left_unmodified():
    """Pure function: caller's list must not be mutated in place."""
    artifact = {"system_prompt_overlay": "ok"}
    snapshot = list(_BASE_CMD)
    inject_artifact_into_cmd(_BASE_CMD, "claude", artifact)
    assert _BASE_CMD == snapshot


def test_empty_overlay_is_a_noop():
    artifact = {"system_prompt_overlay": "   \n  "}
    new_cmd, components = inject_artifact_into_cmd(_BASE_CMD, "claude", artifact)
    assert new_cmd == _BASE_CMD
    assert components["system_prompt"] is False


def test_non_claude_backend_is_a_noop():
    """Codex / gemini / opencode keep their argv until per-harness translators
    add their own injection surfaces."""
    artifact = {"system_prompt_overlay": "some overlay text"}
    for backend in ("codex", "gemini", "opencode", "unknown"):
        new_cmd, components = inject_artifact_into_cmd(_BASE_CMD, backend, artifact)
        assert new_cmd == _BASE_CMD
        assert components["system_prompt"] is False


def test_missing_artifact_is_a_noop():
    new_cmd, components = inject_artifact_into_cmd(_BASE_CMD, "claude", None)
    assert new_cmd == _BASE_CMD
    assert components == {
        "system_prompt": False,
        "hooks": False,
        "tool_overrides": False,
    }


def test_oversize_overlay_is_skipped():
    """A misconfigured overlay must not blow the argv limit."""
    huge = "x" * (MAX_OVERLAY_BYTES + 1)
    new_cmd, components = inject_artifact_into_cmd(
        _BASE_CMD, "claude", {"system_prompt_overlay": huge},
    )
    assert new_cmd == _BASE_CMD
    assert components["system_prompt"] is False


# ---------- env injection (T2 hook overlay) -------------------------------


def test_env_no_artifact_is_a_noop():
    env = {"PATH": "/usr/bin"}
    new_env, components, overlay = inject_artifact_into_env(
        env, "exec-x", "claude", None,
    )
    assert new_env is env
    assert components == {"hooks": False, "tool_overrides": False}
    assert overlay is None


def test_env_non_claude_backend_is_a_noop():
    env = {"PATH": "/usr/bin"}
    new_env, components, overlay = inject_artifact_into_env(
        env, "exec-x", "codex", {"hook_specs": [{}]},
    )
    assert new_env is env
    assert components["hooks"] is False
    assert overlay is None


def test_env_overlay_sets_claude_config_dir():
    """When the overlay materializer returns a dir, env gets the env var."""
    fake_overlay = "/tmp/agented-claude-overlay-exec-x"
    with patch(
        "app.services.harness_overlay.prepare_overlay_for_execution",
        return_value=fake_overlay,
    ):
        new_env, components, overlay = inject_artifact_into_env(
            {"PATH": "/usr/bin"}, "exec-x", "claude",
            {"hook_specs": [{"layer": "h2"}]},
        )
    assert overlay == fake_overlay
    assert new_env["CLAUDE_CONFIG_DIR"] == fake_overlay
    assert new_env["PATH"] == "/usr/bin"  # preserved
    assert components["hooks"] is True


def test_env_overlay_failure_is_a_noop():
    """If the overlay materializer returns None (e.g. ~/.claude missing),
    env is left unchanged."""
    with patch(
        "app.services.harness_overlay.prepare_overlay_for_execution",
        return_value=None,
    ):
        env = {"PATH": "/usr/bin"}
        new_env, components, overlay = inject_artifact_into_env(
            env, "exec-x", "claude", {"hook_specs": [{"layer": "h2"}]},
        )
    assert new_env is env
    assert components["hooks"] is False
    assert overlay is None


def test_env_none_input_becomes_dict_with_overlay():
    """env=None is valid (caller hasn't built env yet); we materialize a
    fresh dict carrying just CLAUDE_CONFIG_DIR."""
    with patch(
        "app.services.harness_overlay.prepare_overlay_for_execution",
        return_value="/tmp/some-overlay",
    ):
        new_env, _, _ = inject_artifact_into_env(
            None, "exec-x", "claude", {"hook_specs": [{"layer": "h2"}]},
        )
    assert new_env == {"CLAUDE_CONFIG_DIR": "/tmp/some-overlay"}


def test_hooks_and_tool_overrides_reported_unapplied():
    """Even when an artifact has hook_specs / tool_description_overrides, the
    T2 injection step only flows the overlay — the rest stays False so the
    snapshot row honestly reflects what was actually applied."""
    artifact = {
        "system_prompt_overlay": "rule",
        "hook_specs": [{"layer": "h2"}],
        "tool_description_overrides": {"Bash": "be careful"},
    }
    _, components = inject_artifact_into_cmd(_BASE_CMD, "claude", artifact)
    assert components == {
        "system_prompt": True,
        "hooks": False,
        "tool_overrides": False,
    }
