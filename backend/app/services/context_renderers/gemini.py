"""Gemini renderer.

``gemini -p <prompt>`` — system prompt is prepended to the
``-p`` argument since gemini has no native system-prompt flag in
its CLI surface. ``GEMINI_HOME`` overlay materializes the
bundle's MCP servers (under ``settings.json``'s ``mcpServers``)
and slash commands (under ``commands/``).
"""

from __future__ import annotations

import logging
import os

from ..context_compiler_service import ContextBundle
from ..gemini_config_overlay import apply_forge_bundle, prepare_session_overlay
from .base import Renderer, subagent_prompt_block, universal_prompt_prepend

logger = logging.getLogger(__name__)


def _prefix_p_arg(cmd: list[str], text: str) -> list[str]:
    """Splice ``text`` above the ``-p`` prompt arg (gemini)."""
    if not text or not cmd:
        return cmd
    try:
        idx = cmd.index("-p")
    except ValueError:
        return cmd
    prompt_idx = idx + 1
    if prompt_idx >= len(cmd):
        return cmd
    new_cmd = list(cmd)
    new_cmd[prompt_idx] = f"{text}\n\n{cmd[prompt_idx]}"
    return new_cmd


def _ensure_overlay(env: dict, session_id: str) -> str | None:
    existing = env.get("GEMINI_HOME")
    if existing and os.path.isdir(existing):
        return existing
    base = existing or os.path.expanduser("~/.gemini")
    overlay = prepare_session_overlay(session_id, base)
    if overlay:
        env["GEMINI_HOME"] = overlay
    return overlay


class GeminiRenderer(Renderer):
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
        new_cmd = cmd
        if bundle.system_prompt_text:
            new_cmd = _prefix_p_arg(new_cmd, f"=== System ===\n{bundle.system_prompt_text}")
        # gemini has no native sub-agent concept → degrade to a named
        # prompt-prefix block (claude discovers sub-agents natively instead).
        new_cmd = _prefix_p_arg(new_cmd, subagent_prompt_block(bundle))
        new_cmd = universal_prompt_prepend(new_cmd, bundle)

        if bundle.overlay_files or bundle.mcp_servers:
            overlay = _ensure_overlay(new_env, session_id)
            if overlay:
                try:
                    apply_forge_bundle(overlay, bundle.to_dict())
                except Exception:
                    logger.warning("gemini_renderer: overlay apply failed", exc_info=True)
        return new_cmd, new_env
