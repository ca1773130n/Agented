"""OpenCode renderer.

``opencode run --format json <prompt>`` — like codex, the prompt
is the trailing positional arg. ``OPENCODE_HOME`` overlay
materializes the bundle's MCP servers (under ``config.json``'s
``mcp`` key) and slash commands (under ``commands/``).
"""

from __future__ import annotations

import logging
import os

from ..context_compiler_service import ContextBundle
from ..opencode_config_overlay import apply_forge_bundle, prepare_session_overlay
from .base import Renderer, universal_prompt_prepend

logger = logging.getLogger(__name__)


def _prefix_prompt(cmd: list[str], system_text: str) -> list[str]:
    if not system_text or not cmd:
        return cmd
    last = cmd[-1]
    if not isinstance(last, str) or last.startswith("-"):
        return cmd
    return [*cmd[:-1], f"=== System ===\n{system_text}\n\n{last}"]


def _ensure_overlay(env: dict, session_id: str) -> str | None:
    existing = env.get("OPENCODE_HOME")
    if existing and os.path.isdir(existing):
        return existing
    base = existing or os.path.expanduser("~/.opencode")
    overlay = prepare_session_overlay(session_id, base)
    if overlay:
        env["OPENCODE_HOME"] = overlay
    return overlay


class OpencodeRenderer(Renderer):
    def apply(
        self,
        cmd: list[str],
        env: dict,
        bundle: ContextBundle,
        session_id: str,
    ) -> tuple[list[str], dict]:
        if bundle.is_empty():
            return cmd, env
        new_env = dict(env)
        new_cmd = _prefix_prompt(cmd, bundle.system_prompt_text)
        new_cmd = universal_prompt_prepend(new_cmd, bundle)

        if bundle.overlay_files or bundle.mcp_servers:
            overlay = _ensure_overlay(new_env, session_id)
            if overlay:
                try:
                    apply_forge_bundle(overlay, bundle.to_dict())
                except Exception:
                    logger.warning(
                        "opencode_renderer: overlay apply failed", exc_info=True
                    )
        return new_cmd, new_env
