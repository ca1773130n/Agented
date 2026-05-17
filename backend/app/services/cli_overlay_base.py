"""Shared scaffolding for per-CLI session-scoped config overlays.

``claude_config_overlay.py`` predates this module and stays separate
because it also owns the permission-hook glue. Codex/Gemini/Opencode
all just need: temp dir + symlink passthrough + (optionally) merge
overlay files / MCP config into that temp dir. This module is the
common skeleton.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Iterable, Optional

logger = logging.getLogger(__name__)


def prepare_cli_overlay(
    *,
    session_id: str,
    user_config_dir: str,
    overlay_prefix: str,
    passthrough_items: Iterable[str],
) -> Optional[str]:
    """Create ``/tmp/<overlay_prefix>-<session_id>`` and symlink the
    user's existing CLI config items so the spawned process still
    sees skills, MCP servers, transcripts, etc.

    Caller is responsible for additional materialization (e.g.
    writing the merged ``config.toml`` / ``mcp.json``) into the
    returned dir.

    Returns ``None`` if ``user_config_dir`` doesn't exist — caller
    falls back to the unmodified env var.
    """
    user_dir = Path(os.path.expanduser(user_config_dir))
    if not user_dir.exists():
        logger.warning(
            "cli_overlay_base: user config dir %s missing, skipping overlay",
            user_dir,
        )
        return None

    overlay = Path(f"/tmp/{overlay_prefix}-{session_id}")
    if overlay.exists():
        shutil.rmtree(overlay, ignore_errors=True)
    overlay.mkdir(parents=True, exist_ok=True)

    for name in passthrough_items:
        src = user_dir / name
        if not src.exists():
            continue
        dst = overlay / name
        try:
            os.symlink(src, dst)
        except OSError as exc:
            logger.warning(
                "cli_overlay_base: failed to symlink %s -> %s: %s",
                dst,
                src,
                exc,
            )

    return str(overlay)


def cleanup_cli_overlay(session_id: str, overlay_prefix: str) -> None:
    overlay = Path(f"/tmp/{overlay_prefix}-{session_id}")
    if not overlay.exists():
        return
    try:
        shutil.rmtree(overlay)
        logger.info("cli_overlay_base: removed %s", overlay)
    except OSError as exc:
        logger.warning("cli_overlay_base: failed to remove %s: %s", overlay, exc)
