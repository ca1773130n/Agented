"""Claude Code renderer.

Two responsibilities:

* Append ``--append-system-prompt <text>`` to the cmd. This works
  regardless of whether an overlay dir exists, so it's
  load-bearing for the operator-visible "system prompt" channel.
* Trigger the overlay materialization helper when an overlay dir
  already exists. The session-creation route runs the renderer
  *before* PSM exists, so the overlay typically isn't ready yet —
  in that case the renderer skips overlay work and PSM picks it up
  later by calling ``claude_config_overlay.apply_forge_bundle``
  itself.

The end state is the same either way: by the time claude exec's,
the overlay has the bundle's hooks/commands/MCP/skills layered in.
"""

from __future__ import annotations

import logging
import os

from ..claude_config_overlay import apply_forge_bundle
from ..context_compiler_service import ContextBundle
from .base import Renderer

logger = logging.getLogger(__name__)


def _append_system_prompt(cmd: list[str], text: str) -> list[str]:
    """Insert ``--append-system-prompt <text>`` at the tail.

    The flag is idempotent — a second occurrence would just shadow
    the first — but skipping it keeps the cmdline tidy and the
    debug log easy to read.
    """
    if not text or "--append-system-prompt" in cmd:
        return cmd
    return [*cmd, "--append-system-prompt", text]


class ClaudeRenderer(Renderer):
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
        new_cmd = _append_system_prompt(cmd, bundle.system_prompt_text)
        # Sub-agents: claude discovers these NATIVELY from the overlay's
        # ``agents/<name>.md`` files (placed in bundle.overlay_files by the
        # compiler and written by apply_forge_bundle below). We deliberately do
        # NOT inline the sub-agent body into --append-system-prompt — that's the
        # codex/gemini/opencode degrade path, not claude's. This asymmetry is
        # the all-four-backends house rule documented in 17-RESEARCH.md.

        # If the env already points at an overlay dir, apply the
        # bundle right now. Otherwise PSM will create the overlay
        # later and apply the bundle then (via the ``forge_bundle``
        # session-config field).
        overlay = new_env.get("CLAUDE_CONFIG_DIR")
        if overlay and os.path.isdir(overlay):
            try:
                apply_forge_bundle(overlay, bundle.to_dict())
            except Exception:
                logger.warning("claude_renderer: overlay apply failed", exc_info=True)
        return new_cmd, new_env
