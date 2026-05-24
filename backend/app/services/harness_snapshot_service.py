"""Snapshot the active harness IR for an execution (T2 integration).

This module is intentionally **capture-only**: it records WHICH harness
configuration would have been used for an execution but does NOT inject
the artifact into the spawned subprocess. Injection into Claude Code's
argv / env / config files is a separate follow-up because it changes
runtime agent behaviour.

What capture-only buys us:
    - T3's evolution loop can attribute trajectories to harness versions
      ("all failures from H3 v1 vs H3 v2") without us shipping the
      injection plumbing yet.
    - Zero risk to existing bots — bots without configured layers see
      no snapshot row, no DB writes, no overhead.

Contract:
    - Never raises. The caller's spawn path is never blocked by snapshot
      bookkeeping. Errors are logged at WARNING.
    - Returns ``None`` when there are no enabled layers for the bot (so
      we don't pollute the snapshot table with empty rows for every
      execution Agented runs).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import msgspec

from app.db import harness_layers as layers_repo
from app.db import harness_snapshots as snapshot_repo
from app.services.harness_compiler import get_translator
from app.services.harness_injector import (
    inject_artifact_into_cmd,
    inject_artifact_into_env,
)

logger = logging.getLogger(__name__)


def _injection_enabled() -> bool:
    """Emergency kill switch: ``AGENTED_HARNESS_INJECT=0`` disables runtime
    injection but still records snapshots. Useful when investigating a
    regression where the harness might be at fault."""
    return os.environ.get("AGENTED_HARNESS_INJECT", "1") != "0"


def snapshot_for_execution(
    *,
    execution_id: str,
    bot_id: str,
    harness_kind: str,
    trigger_id: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Build the harness artifact for this bot+kind and persist it.

    Args:
        execution_id: The execution_logs.execution_id string.
        bot_id: The trigger/bot id whose harness layers we compile.
        harness_kind: ``claude``, ``codex``, ``gemini``, ``opencode``...
            Only kinds with a registered ``HarnessTranslator`` produce a
            snapshot; the rest no-op silently.
        trigger_id: When provided, narrows layer selection to trigger-scoped
            overrides + global rows. Defaults to global-only.

    Returns:
        The artifact dict on success, or ``None`` when nothing was captured
        (no layers, unknown harness_kind, or a swallowed error).
    """
    try:
        rows = layers_repo.list_enabled_for_bot(bot_id, trigger_id=trigger_id)
        if not rows:
            return None

        try:
            translator = get_translator(harness_kind)
        except NotImplementedError:
            logger.debug(
                "harness_snapshot: no translator for harness_kind=%r; "
                "skipping snapshot for execution %s",
                harness_kind,
                execution_id,
            )
            return None

        artifact = translator.compile(bot_id, rows)
        artifact_dict = msgspec.to_builtins(artifact)
        snapshot_repo.upsert_snapshot(
            execution_id=execution_id,
            bot_id=bot_id,
            harness_kind=harness_kind,
            layer_versions=artifact.layer_versions,
            artifact=artifact_dict,
            applied=False,  # capture-only entry point — see prepare_harness_for_execution
        )
        return artifact_dict
    except Exception:  # noqa: BLE001 — must never raise into the spawn path
        logger.warning(
            "harness_snapshot: capture failed for execution=%s bot=%s kind=%s",
            execution_id,
            bot_id,
            harness_kind,
            exc_info=True,
        )
        return None


def prepare_harness_for_execution(
    *,
    execution_id: str,
    bot_id: str,
    harness_kind: str,
    cmd: list[str],
    env: Optional[dict[str, str]] = None,
    trigger_id: Optional[str] = None,
) -> tuple[list[str], Optional[dict[str, str]], Optional[dict[str, Any]], Optional[str]]:
    """Compile → inject (cmd + env overlay) → snapshot.

    The execution_service spawn path calls this once, between argv / env
    construction and ``subprocess.Popen``. Returns::

        (maybe_modified_cmd, maybe_modified_env, artifact_or_None, overlay_dir_or_None)

    - cmd carries ``--append-system-prompt <overlay>`` when the H3/H5
      overlay is non-empty.
    - env carries ``CLAUDE_CONFIG_DIR=<overlay_dir>`` when at least one
      H2/H4 hook event was wired into the per-execution overlay.
    - overlay_dir is the path the caller MUST clean up after the spawn
      ends (see ``harness_overlay.cleanup_overlay_for_execution``).

    The snapshot row's ``applied`` flag and the per-component
    ``injected_components`` dict honestly reflect what was wired.

    Both cmd and env come back unchanged when:
      - the bot has no enabled harness layers
      - the harness_kind has no registered translator
      - injection is disabled via ``AGENTED_HARNESS_INJECT=0``

    Never raises.
    """
    try:
        rows = layers_repo.list_enabled_for_bot(bot_id, trigger_id=trigger_id)
        if not rows:
            return cmd, env, None, None

        try:
            translator = get_translator(harness_kind)
        except NotImplementedError:
            logger.debug(
                "harness_inject: no translator for %r; skipping for %s",
                harness_kind, execution_id,
            )
            return cmd, env, None, None

        artifact = translator.compile(bot_id, rows)
        artifact_dict = msgspec.to_builtins(artifact)

        if _injection_enabled():
            new_cmd, cmd_components = inject_artifact_into_cmd(
                cmd, harness_kind, artifact_dict,
            )
            new_env, env_components, overlay_dir = inject_artifact_into_env(
                env, execution_id, harness_kind, artifact_dict,
            )
            injected = {**cmd_components, **env_components}
        else:
            logger.info(
                "harness_inject: AGENTED_HARNESS_INJECT=0 — snapshot only "
                "for execution %s", execution_id,
            )
            new_cmd, new_env, overlay_dir = cmd, env, None
            injected = {
                "system_prompt": False,
                "hooks": False,
                "tool_overrides": False,
            }

        applied = any(injected.values())
        snapshot_repo.upsert_snapshot(
            execution_id=execution_id,
            bot_id=bot_id,
            harness_kind=harness_kind,
            layer_versions=artifact.layer_versions,
            artifact={**artifact_dict, "injected_components": injected},
            applied=applied,
        )
        return new_cmd, new_env, artifact_dict, overlay_dir
    except Exception:  # noqa: BLE001 — never block the spawn
        logger.warning(
            "harness_inject: failed for execution=%s bot=%s kind=%s",
            execution_id, bot_id, harness_kind, exc_info=True,
        )
        return cmd, env, None, None
