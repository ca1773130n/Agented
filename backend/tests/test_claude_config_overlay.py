"""Regression guard: the claude session overlay MUST pass the account's OAuth
credentials through, or every spawned `claude` harness session (research,
autopilot, harness-round, grd_chat) dies with "Not logged in" despite a
configured account."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from app.services.claude_config_overlay import (
    _hook_script_path,
    build_hook_settings_arg,
    prepare_session_overlay,
)


def test_build_hook_settings_arg_installs_agented_hook(tmp_path: Path):
    """Autonomous sessions get the Agented PreToolUse hook via --settings,
    shipping ONLY the hooks subset (auth stays file-based on the real dir)."""
    user_dir = tmp_path / "cfg"
    user_dir.mkdir()
    (user_dir / "settings.json").write_text("{}")

    arg = build_hook_settings_arg(str(user_dir))
    assert arg is not None
    payload = json.loads(arg)
    # Only the hooks key is shipped — no other real-dir settings leak in.
    assert set(payload.keys()) == {"hooks"}
    pre = payload["hooks"]["PreToolUse"]
    assert any(
        h.get("command") == str(_hook_script_path()) for e in pre for h in (e.get("hooks") or [])
    )


def test_build_hook_settings_arg_preserves_existing_hooks(tmp_path: Path):
    """A pre-existing PreToolUse hook in the real dir is preserved and the
    Agented hook is appended once (de-duped on repeat)."""
    user_dir = tmp_path / "cfg"
    user_dir.mkdir()
    (user_dir / "settings.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": ".*",
                            "hooks": [{"type": "command", "command": "/opt/other-hook.sh"}],
                        }
                    ]
                }
            }
        )
    )

    arg = build_hook_settings_arg(str(user_dir))
    pre = json.loads(arg)["hooks"]["PreToolUse"]
    commands = [h.get("command") for e in pre for h in (e.get("hooks") or [])]
    assert "/opt/other-hook.sh" in commands  # existing hook preserved
    assert commands.count(str(_hook_script_path())) == 1  # ours appended once

    # Idempotent: building again (as if settings already carried ours) de-dupes.
    (user_dir / "settings.json").write_text(json.dumps(json.loads(arg)))
    arg2 = build_hook_settings_arg(str(user_dir))
    pre2 = json.loads(arg2)["hooks"]["PreToolUse"]
    commands2 = [h.get("command") for e in pre2 for h in (e.get("hooks") or [])]
    assert commands2.count(str(_hook_script_path())) == 1


def test_build_hook_settings_arg_missing_dir_returns_none(tmp_path: Path):
    assert build_hook_settings_arg(str(tmp_path / "does-not-exist")) is None


def test_overlay_passes_through_oauth_credentials(tmp_path: Path):
    user_dir = tmp_path / "cfg"
    user_dir.mkdir()
    # The two files that actually hold the login.
    (user_dir / ".credentials.json").write_text(json.dumps({"claudeAiOauth": {"accessToken": "x"}}))
    (user_dir / ".oauth-token").write_text("token")
    (user_dir / "settings.json").write_text("{}")

    overlay = prepare_session_overlay("test-sess-creds", str(user_dir))
    try:
        assert overlay is not None
        for name in (".credentials.json", ".oauth-token"):
            dst = Path(overlay) / name
            assert dst.exists(), f"{name} missing from overlay — spawned claude would be logged out"
            assert dst.is_symlink()
    finally:
        shutil.rmtree(overlay, ignore_errors=True)
