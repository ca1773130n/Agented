"""Inject a compiled ``HarnessBuildArtifact`` into a spawn.

Two surfaces today:

- **cmd** (``inject_artifact_into_cmd``): appends ``--append-system-prompt
  <overlay>`` for Claude Code when the overlay text is non-empty and below
  ``MAX_OVERLAY_BYTES``. Pure; no side effects.
- **env** (``inject_artifact_into_env``): materializes a per-execution
  Claude Code config overlay carrying the H2/H4 hook specs, then points
  ``CLAUDE_CONFIG_DIR`` at it. Side-effectful (creates a /tmp dir); the
  caller is responsible for cleaning the overlay up after the spawn ends.

Tool-description overrides (H3) are still recorded on the artifact but not
yet materialized — they would need to be folded into the system prompt
overlay (Claude Code can't override built-in tool descriptions natively).

Both functions never raise. They return components dicts that honestly
reflect what was wired, so the snapshot row can distinguish "we know about
these hooks but didn't apply them" from "they're live".
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Cap so a huge accidental overlay never inflates argv past the OS limit.
# 32 KB leaves plenty of headroom under typical 128 KB ARG_MAX on Linux/macOS.
MAX_OVERLAY_BYTES = 32 * 1024


def inject_artifact_into_cmd(
    cmd: list[str],
    harness_kind: str,
    artifact: dict[str, Any] | None,
) -> tuple[list[str], dict[str, bool]]:
    """Return ``(new_cmd, components_injected)``.

    ``components_injected`` is a flat ``{"system_prompt": bool, "hooks": bool,
    "tool_overrides": bool}`` dict so the snapshot row can record exactly
    what flowed through to the spawn. Layers that were skipped (deferred or
    not applicable to this harness_kind) come back as ``False``.

    Never raises. On any unexpected error, returns the original cmd
    unchanged and a fully-False components dict.
    """
    components = {"system_prompt": False, "hooks": False, "tool_overrides": False}
    if not artifact or harness_kind != "claude":
        return cmd, components

    try:
        overlay = (artifact.get("system_prompt_overlay") or "").strip()
        if not overlay:
            return cmd, components

        if len(overlay.encode("utf-8")) > MAX_OVERLAY_BYTES:
            logger.warning(
                "harness_injector: overlay exceeds %d bytes; skipping injection",
                MAX_OVERLAY_BYTES,
            )
            return cmd, components

        new_cmd = list(cmd) + ["--append-system-prompt", overlay]
        components["system_prompt"] = True
        return new_cmd, components
    except Exception:  # noqa: BLE001 — never block spawn
        logger.warning("harness_injector: unexpected failure", exc_info=True)
        return cmd, {"system_prompt": False, "hooks": False, "tool_overrides": False}


def inject_artifact_into_env(
    env: Optional[dict[str, str]],
    execution_id: str,
    harness_kind: str,
    artifact: Optional[dict[str, Any]],
) -> tuple[Optional[dict[str, str]], dict[str, bool], Optional[str]]:
    """Return ``(new_env, components_injected, overlay_dir_or_None)``.

    Materializes the Claude Code config overlay if ``artifact`` carries
    hook specs and ``harness_kind == "claude"``. Sets ``CLAUDE_CONFIG_DIR``
    on the returned env so Claude Code reads our overlay instead of
    ``~/.claude``. The user's real config is symlinked into the overlay
    (passthrough), so auth / MCP / plugins still work.

    On any failure (overlay infra missing, write error, no hook events
    used), returns ``(env, {hooks: False, ...}, None)`` and leaves env
    untouched.

    The caller MUST clean up the returned overlay dir after the spawn ends
    via ``harness_overlay.cleanup_overlay_for_execution(execution_id)``.
    """
    components = {"hooks": False, "tool_overrides": False}
    if not artifact or harness_kind != "claude":
        return env, components, None

    try:
        from .harness_overlay import prepare_overlay_for_execution

        overlay_dir = prepare_overlay_for_execution(execution_id, artifact)
        if overlay_dir is None:
            return env, components, None

        new_env = dict(env) if env is not None else {}
        new_env["CLAUDE_CONFIG_DIR"] = overlay_dir
        components["hooks"] = True
        return new_env, components, overlay_dir
    except Exception:  # noqa: BLE001 — never block spawn
        logger.warning(
            "harness_injector: env injection failed for %s",
            execution_id, exc_info=True,
        )
        return env, components, None
