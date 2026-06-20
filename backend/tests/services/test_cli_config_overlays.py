"""Tests for the four per-CLI config overlays and their
``apply_forge_bundle`` materialization helpers.

Each backend's overlay is exercised with the same canonical bundle
shape so behavior parity stays obvious; the assertions then differ
based on each CLI's expected on-disk layout.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services import (
    claude_config_overlay,
    codex_config_overlay,
    gemini_config_overlay,
    opencode_config_overlay,
)

CANONICAL_BUNDLE = {
    "overlay_files": {
        "commands/deploy.md": "ship it",
        "commands/audit.md": "look around",
    },
    "overlay_symlinks": {},
    "mcp_servers": {
        "context7": {
            "command": "npx",
            "args": ["-y", "mcp-context7"],
            "env": {"FOO": "bar"},
        },
        "github": {"url": "https://mcp.example.com/github"},
    },
    "prompt_prepend": "",
    "system_prompt_text": "",
}


@pytest.fixture
def user_dir(tmp_path):
    user = tmp_path / "user_cfg"
    user.mkdir()
    return user


# -----------------------------------------------------------------
# Claude
# -----------------------------------------------------------------


def test_claude_apply_writes_commands_and_merges_mcp(tmp_path):
    overlay = tmp_path / "overlay"
    overlay.mkdir()
    # Pre-populate mcp.json with one user-managed entry — must be
    # preserved after merge.
    (overlay / "mcp.json").write_text(json.dumps({"mcpServers": {"existing": {"command": "x"}}}))

    claude_config_overlay.apply_forge_bundle(str(overlay), CANONICAL_BUNDLE)

    assert (overlay / "commands" / "deploy.md").read_text() == "ship it"
    assert (overlay / "commands" / "audit.md").read_text() == "look around"
    merged = json.loads((overlay / "mcp.json").read_text())
    assert merged["mcpServers"]["existing"] == {"command": "x"}
    assert merged["mcpServers"]["context7"]["command"] == "npx"
    assert merged["mcpServers"]["github"]["url"].startswith("https://")


def test_claude_apply_materializes_hooks(tmp_path):
    overlay = tmp_path / "overlay"
    overlay.mkdir()
    bundle = {
        "overlay_files": {
            "_agented_hooks.json": json.dumps(
                [
                    {
                        "name": "guard-bash",
                        "event": "PreToolUse",
                        "matcher": "Bash",
                        "content": "echo gate",
                    }
                ]
            )
        },
        "mcp_servers": {},
        "overlay_symlinks": {},
    }
    claude_config_overlay.apply_forge_bundle(str(overlay), bundle)

    script = overlay / "hooks" / "guard-bash.sh"
    assert script.exists()
    assert script.stat().st_mode & 0o100  # owner-executable
    settings = json.loads((overlay / "settings.json").read_text())
    assert settings["hooks"]["PreToolUse"][0]["matcher"] == "Bash"
    assert settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == str(script)


def test_claude_apply_refuses_path_escape(tmp_path):
    overlay = tmp_path / "overlay"
    overlay.mkdir()
    bundle = {
        "overlay_files": {"../escape.md": "should not land outside"},
        "mcp_servers": {},
        "overlay_symlinks": {},
    }
    claude_config_overlay.apply_forge_bundle(str(overlay), bundle)
    assert not (tmp_path / "escape.md").exists()


def test_claude_apply_noop_on_empty():
    # Doesn't crash on missing overlay.
    claude_config_overlay.apply_forge_bundle("/nonexistent/path", CANONICAL_BUNDLE)
    claude_config_overlay.apply_forge_bundle("/tmp", {})


# -----------------------------------------------------------------
# Codex
# -----------------------------------------------------------------


def test_codex_prepare_symlinks_user_items(tmp_path):
    user = tmp_path / "codex_home"
    user.mkdir()
    (user / "auth.json").write_text('{"token":"abc"}')
    (user / "config.toml").write_text('[ui]\ntheme = "dark"\n')

    overlay = codex_config_overlay.prepare_session_overlay("sess-1", str(user))
    assert overlay is not None
    assert (Path(overlay) / "auth.json").is_symlink()
    assert (Path(overlay) / "config.toml").is_symlink()
    codex_config_overlay.cleanup_session_overlay("sess-1")


def test_codex_apply_appends_mcp_section(tmp_path):
    overlay = tmp_path / "codex_overlay"
    overlay.mkdir()
    (overlay / "config.toml").write_text('[ui]\ntheme = "dark"\n')

    codex_config_overlay.apply_forge_bundle(str(overlay), CANONICAL_BUNDLE)

    toml_text = (overlay / "config.toml").read_text()
    # Existing user content preserved.
    assert "[ui]" in toml_text
    assert 'theme = "dark"' in toml_text
    # Our MCP sections appended.
    assert "[mcp_servers.context7]" in toml_text
    assert 'command = "npx"' in toml_text
    assert 'args = ["-y", "mcp-context7"]' in toml_text
    assert "[mcp_servers.github]" in toml_text
    assert 'url = "https://mcp.example.com/github"' in toml_text


def test_codex_apply_writes_prompts_from_commands(tmp_path):
    overlay = tmp_path / "codex_overlay"
    overlay.mkdir()
    codex_config_overlay.apply_forge_bundle(str(overlay), CANONICAL_BUNDLE)
    assert (overlay / "prompts" / "deploy.md").read_text() == "ship it"
    assert (overlay / "prompts" / "audit.md").read_text() == "look around"


# -----------------------------------------------------------------
# Gemini
# -----------------------------------------------------------------


def test_gemini_apply_merges_mcp_into_settings(tmp_path):
    overlay = tmp_path / "gemini_overlay"
    overlay.mkdir()
    (overlay / "settings.json").write_text(
        json.dumps({"theme": "dark", "mcpServers": {"existing": {"command": "x"}}})
    )

    gemini_config_overlay.apply_forge_bundle(str(overlay), CANONICAL_BUNDLE)

    merged = json.loads((overlay / "settings.json").read_text())
    assert merged["theme"] == "dark"
    assert "existing" in merged["mcpServers"]
    assert merged["mcpServers"]["context7"]["command"] == "npx"


def test_gemini_apply_writes_commands(tmp_path):
    overlay = tmp_path / "gemini_overlay"
    overlay.mkdir()
    gemini_config_overlay.apply_forge_bundle(str(overlay), CANONICAL_BUNDLE)
    assert (overlay / "commands" / "deploy.md").read_text() == "ship it"


# -----------------------------------------------------------------
# Opencode
# -----------------------------------------------------------------


def test_opencode_apply_merges_mcp_into_config(tmp_path):
    overlay = tmp_path / "opencode_overlay"
    overlay.mkdir()
    (overlay / "config.json").write_text(
        json.dumps({"editor": "vim", "mcp": {"existing": {"command": "x"}}})
    )

    opencode_config_overlay.apply_forge_bundle(str(overlay), CANONICAL_BUNDLE)

    merged = json.loads((overlay / "config.json").read_text())
    assert merged["editor"] == "vim"
    assert "existing" in merged["mcp"]
    assert merged["mcp"]["context7"]["command"] == "npx"


def test_opencode_apply_writes_commands(tmp_path):
    overlay = tmp_path / "opencode_overlay"
    overlay.mkdir()
    opencode_config_overlay.apply_forge_bundle(str(overlay), CANONICAL_BUNDLE)
    assert (overlay / "commands" / "deploy.md").read_text() == "ship it"
