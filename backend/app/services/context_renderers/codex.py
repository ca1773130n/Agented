"""Codex renderer.

* Prepends ``=== System ===\\n<system_prompt_text>`` to the trailing
  prompt arg (``codex exec [...] <prompt>``). Codex has no native
  system-prompt flag.
* Creates a per-session ``CODEX_HOME`` overlay (when the user has a
  resolvable codex config dir) and materializes the bundle's MCP
  servers + slash commands into it.
* Splices the universal ``prompt_prepend`` (per-prompt attachments)
  into the prompt arg too.
"""

from __future__ import annotations

import logging
import os

from ..codex_config_overlay import apply_forge_bundle, prepare_session_overlay
from ..context_compiler_service import ContextBundle
from .base import (
    Renderer,
    prepend_to_trailing_prompt,
    subagent_prompt_block,
    universal_prompt_prepend,
)

logger = logging.getLogger(__name__)


def _prefix_prompt(cmd: list[str], system_text: str) -> list[str]:
    if not system_text:
        return cmd
    return prepend_to_trailing_prompt(cmd, f"=== System ===\n{system_text}")


def _ensure_overlay(env: dict, session_id: str) -> str | None:
    existing = env.get("CODEX_HOME")
    if existing and os.path.isdir(existing):
        return existing
    base = existing or os.path.expanduser("~/.codex")
    overlay = prepare_session_overlay(session_id, base)
    if overlay:
        env["CODEX_HOME"] = overlay
    return overlay


class CodexRenderer(Renderer):
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
        # codex has no native sub-agent concept → degrade to a named
        # prompt-prefix block (claude discovers sub-agents natively instead).
        new_cmd = prepend_to_trailing_prompt(new_cmd, subagent_prompt_block(bundle))
        new_cmd = universal_prompt_prepend(new_cmd, bundle)

        if bundle.overlay_files or bundle.mcp_servers:
            overlay = _ensure_overlay(new_env, session_id)
            if overlay:
                try:
                    apply_forge_bundle(overlay, bundle.to_dict())
                except Exception:
                    logger.warning("codex_renderer: overlay apply failed", exc_info=True)
        return new_cmd, new_env
