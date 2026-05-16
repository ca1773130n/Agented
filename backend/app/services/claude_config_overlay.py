"""Session-scoped CLAUDE_CONFIG_DIR overlay for interactive permission
prompts (v0.7.69).

When a chat session opts in to web-panel permission prompts, we don't
want to mutate the user's real ``~/.claude/settings.json`` — that
would affect every other claude invocation. Instead:

1. Create a temp dir per session under ``/tmp``.
2. Symlink the user's existing config items (``plugins/``, ``mcp.json``,
   transcripts, etc.) into the temp dir so claude still sees skills,
   MCP servers, prior transcripts.
3. Generate a fresh ``settings.json`` in the temp dir merging the
   user's existing settings + a PreToolUse hook pointing at our
   ``agented_permission_hook.py`` script.
4. Set ``CLAUDE_CONFIG_DIR`` for the subprocess to the temp dir.

On session teardown, ``cleanup_session_overlay`` removes the temp dir.
The user's ``~/.claude`` is never touched.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# Items in the user's claude config dir that we symlink (passthrough)
# rather than override. Anything else we silently skip.
_PASSTHROUGH_ITEMS = {
    "plugins",
    "mcp.json",
    "projects",
    "backups",
    "cache",
    "context-mode",
    "session-env",
    "last-activity",
    "settings.local.json",
    "harnesssync_health_history.json",
}


def _hook_script_path() -> Path:
    """Resolve the absolute path to our hook script.

    The script lives at ``backend/scripts/agented_permission_hook.py``
    in the repo. We resolve via this module's location so the path is
    correct in any deployment layout.
    """
    return (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "agented_permission_hook.py"
    )


def _build_settings_json(user_settings_path: Optional[Path]) -> dict:
    """Read the user's settings.json (if any) and append the Agented
    permission hook entry. The hook's ``matcher`` of ``.*`` makes it
    fire for every tool call; the actual gate inside the script keys
    off ``AGENTED_PERMISSION_HOOK_ACTIVE`` so non-Agented invocations
    are untouched."""
    settings: dict = {}
    if user_settings_path and user_settings_path.exists():
        try:
            settings = json.loads(user_settings_path.read_text())
        except (json.JSONDecodeError, OSError):
            logger.warning(
                "claude_config_overlay: failed to parse %s, starting fresh",
                user_settings_path,
            )
            settings = {}

    hooks_block = settings.setdefault("hooks", {})
    pretooluse = hooks_block.setdefault("PreToolUse", [])
    # Drop any previously-installed entry pointing at our script
    # before adding a fresh one. Idempotent.
    script_path = str(_hook_script_path())
    pretooluse[:] = [
        e
        for e in pretooluse
        if not (
            isinstance(e, dict)
            and any(
                isinstance(h, dict) and h.get("command") == script_path
                for h in (e.get("hooks") or [])
            )
        )
    ]
    pretooluse.append(
        {
            "matcher": ".*",
            "hooks": [
                {
                    "type": "command",
                    "command": script_path,
                    "timeout": 310,  # >= backend long-poll + 5s slack
                }
            ],
        }
    )
    return settings


def prepare_session_overlay(
    session_id: str, user_config_dir: str
) -> Optional[str]:
    """Build the session-scoped overlay dir and return its path.

    Returns ``None`` if the user's config dir doesn't exist (we can't
    overlay something that isn't there). Caller falls back to the
    original ``CLAUDE_CONFIG_DIR`` value in that case.
    """
    user_dir = Path(os.path.expanduser(user_config_dir))
    if not user_dir.exists():
        logger.warning(
            "claude_config_overlay: user config dir %s missing, skipping overlay",
            user_dir,
        )
        return None

    overlay = Path(f"/tmp/agented-claude-overlay-{session_id}")
    if overlay.exists():
        # Stale from a previous run with the same id — nuke it.
        shutil.rmtree(overlay, ignore_errors=True)
    overlay.mkdir(parents=True, exist_ok=True)

    # Symlink passthrough items.
    for name in _PASSTHROUGH_ITEMS:
        src = user_dir / name
        if not src.exists():
            continue
        dst = overlay / name
        try:
            os.symlink(src, dst)
        except OSError as exc:
            logger.warning(
                "claude_config_overlay: symlink %s → %s failed: %s",
                src,
                dst,
                exc,
            )

    # Write merged settings.json.
    try:
        settings = _build_settings_json(user_dir / "settings.json")
        (overlay / "settings.json").write_text(
            json.dumps(settings, indent=2, ensure_ascii=False)
        )
    except Exception:
        logger.warning(
            "claude_config_overlay: failed to write merged settings.json",
            exc_info=True,
        )
        # Without settings.json the hook won't fire — clean up and bail.
        shutil.rmtree(overlay, ignore_errors=True)
        return None

    logger.info(
        "claude_config_overlay: prepared %s for session %s",
        overlay,
        session_id,
    )
    return str(overlay)


def cleanup_session_overlay(session_id: str) -> None:
    """Remove the session-scoped overlay dir. Best-effort — failures
    are logged but not raised so a teardown error doesn't take down
    the session-exit handler."""
    overlay = Path(f"/tmp/agented-claude-overlay-{session_id}")
    if not overlay.exists():
        return
    try:
        shutil.rmtree(overlay)
        logger.info(
            "claude_config_overlay: removed %s", overlay
        )
    except OSError as exc:
        logger.warning(
            "claude_config_overlay: failed to remove %s: %s", overlay, exc
        )
