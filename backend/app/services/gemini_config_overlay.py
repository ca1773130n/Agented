"""Session-scoped ``GEMINI_HOME`` overlay (v0.7.71).

Gemini CLI reads its config from ``~/.gemini/settings.json`` and
MCP servers from a top-level ``mcpServers`` key in that JSON
(same shape as claude). Slash commands live under
``~/.gemini/commands/<name>.md``.

This module is the gemini analogue of ``codex_config_overlay.py``.
Hooks are not materialized (gemini has no hook concept yet).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from .cli_overlay_base import cleanup_cli_overlay, prepare_cli_overlay

logger = logging.getLogger(__name__)


_PASSTHROUGH = (
    "settings.json",
    "credentials.json",
    "auth.json",
    "history",
    "commands",
    "logs",
    "cache",
)

_OVERLAY_PREFIX = "agented-gemini-overlay"


def prepare_session_overlay(
    session_id: str, user_config_dir: str
) -> Optional[str]:
    return prepare_cli_overlay(
        session_id=session_id,
        user_config_dir=user_config_dir,
        overlay_prefix=_OVERLAY_PREFIX,
        passthrough_items=_PASSTHROUGH,
    )


def cleanup_session_overlay(session_id: str) -> None:
    cleanup_cli_overlay(session_id, _OVERLAY_PREFIX)


def apply_forge_bundle(overlay_dir: str, bundle: dict) -> None:
    if not bundle:
        return
    base = Path(overlay_dir)
    if not base.exists():
        logger.warning(
            "gemini_overlay: dir %s missing, skipping apply", overlay_dir
        )
        return
    _merge_settings_mcp(base, bundle.get("mcp_servers") or {})
    _write_commands(base, bundle.get("overlay_files") or {})


def _merge_settings_mcp(base: Path, mcp_servers: dict) -> None:
    if not mcp_servers:
        return
    settings_path = base / "settings.json"
    settings: dict = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
        except (json.JSONDecodeError, OSError):
            logger.warning(
                "gemini_overlay: existing settings.json invalid, overwriting"
            )
            settings = {}
    servers = settings.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        servers = {}
    servers.update(mcp_servers)
    settings["mcpServers"] = servers
    try:
        settings_path.write_text(json.dumps(settings, indent=2, ensure_ascii=False))
    except OSError as exc:
        logger.warning("gemini_overlay: write settings.json failed: %s", exc)


def _write_commands(base: Path, overlay_files: dict) -> None:
    cmd_dir = base / "commands"
    base_resolved = base.resolve()
    for rel, content in overlay_files.items():
        if not rel.startswith("commands/") or not rel.endswith(".md"):
            continue
        name = rel[len("commands/") : -len(".md")]
        target = (cmd_dir / f"{name}.md").resolve()
        try:
            target.relative_to(base_resolved)
        except ValueError:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.write_text(content, encoding="utf-8")
        except OSError as exc:
            logger.warning("gemini_overlay: write %s failed: %s", rel, exc)
