"""Regression guard: the claude session overlay MUST pass the account's OAuth
credentials through, or every spawned `claude` harness session (research,
autopilot, harness-round, grd_chat) dies with "Not logged in" despite a
configured account."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from app.services.claude_config_overlay import prepare_session_overlay


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
