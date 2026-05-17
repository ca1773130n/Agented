"""Session-scoped ``OPENCODE_HOME`` overlay (v0.7.71).

OpenCode reads its config from ``~/.opencode/config.json`` and
discovers MCP servers either inline there (``mcp`` key) or via
auto-discovered server packages under ``plugins/``. Slash commands
live under ``~/.opencode/commands/<name>.md``.

Same pattern as gemini_config_overlay — JSON merge for MCP.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from .cli_overlay_base import cleanup_cli_overlay, prepare_cli_overlay

logger = logging.getLogger(__name__)


_PASSTHROUGH = (
    "config.json",
    "auth.json",
    "credentials.json",
    "plugins",
    "commands",
    "history",
    "logs",
    "cache",
)

_OVERLAY_PREFIX = "agented-opencode-overlay"


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
            "opencode_overlay: dir %s missing, skipping apply", overlay_dir
        )
        return
    _merge_config_mcp(base, bundle.get("mcp_servers") or {})
    _write_commands(base, bundle.get("overlay_files") or {})


def _merge_config_mcp(base: Path, mcp_servers: dict) -> None:
    if not mcp_servers:
        return
    config_path = base / "config.json"
    config: dict = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text())
        except (json.JSONDecodeError, OSError):
            logger.warning(
                "opencode_overlay: existing config.json invalid, overwriting"
            )
            config = {}
    mcp = config.setdefault("mcp", {})
    if not isinstance(mcp, dict):
        mcp = {}
    mcp.update(mcp_servers)
    config["mcp"] = mcp
    try:
        config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False))
    except OSError as exc:
        logger.warning("opencode_overlay: write config.json failed: %s", exc)


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
            logger.warning("opencode_overlay: write %s failed: %s", rel, exc)
