"""Per-execution Claude Code config overlay for Life-Harness hook specs.

Layers on top of ``claude_config_overlay.prepare_session_overlay``:

    1. ``prepare_session_overlay`` builds a temp dir under /tmp, symlinks
       passthrough items from ``~/.claude/``, writes a merged settings.json
       (carrying the existing permission-prompt PreToolUse hook).
    2. We then write a sidecar ``_agented_harness_hooks.json`` carrying the
       harness IR's hook_specs verbatim, and register our dispatcher script
       as a ``.*``-matcher entry under each event the specs target.

At runtime, Claude Code reads ``CLAUDE_CONFIG_DIR``, fires our dispatcher on
each tool call, and the dispatcher (a maintained script at
``backend/scripts/agented_harness_hook.py``) walks the sidecar's rules.

Scope today: H2 ``block`` + H4 ``inject_hint`` (regex_count). Everything else
is recorded in the sidecar but the dispatcher no-ops it. ``injected_components
["hooks"]`` reflects whether anything was actually wired into settings.json.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from .claude_config_overlay import (
    cleanup_session_overlay,
    prepare_session_overlay,
)

logger = logging.getLogger(__name__)

_USER_CLAUDE_DIR = "~/.claude"

_EVENT_FOR_TRIGGER = {
    "pre_tool_use": "PreToolUse",
    "post_tool_use": "PostToolUse",
}


def _dispatcher_script_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "agented_harness_hook.py"
    )


def prepare_overlay_for_execution(
    execution_id: str, artifact: dict[str, Any]
) -> Optional[str]:
    """Materialize the overlay dir for this execution's hook specs.

    Returns the overlay dir path when at least one event was wired, or
    ``None`` when nothing happened (no specs, no recognised events, or
    overlay infrastructure unavailable). Never raises.
    """
    hook_specs = artifact.get("hook_specs") or []
    events_used: set[str] = set()
    for spec in hook_specs:
        trigger = (spec.get("spec") or {}).get("trigger")
        ev = _EVENT_FOR_TRIGGER.get(trigger)
        if ev:
            events_used.add(ev)
    if not events_used:
        return None

    overlay = prepare_session_overlay(execution_id, _USER_CLAUDE_DIR)
    if overlay is None:
        return None

    overlay_path = Path(overlay)

    sidecar = overlay_path / "_agented_harness_hooks.json"
    try:
        sidecar.write_text(
            json.dumps(
                {"execution_id": execution_id, "hook_specs": hook_specs},
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
    except OSError:
        logger.warning(
            "harness_overlay: failed to write sidecar for %s",
            execution_id, exc_info=True,
        )
        cleanup_session_overlay(execution_id)
        return None

    settings_path = overlay_path / "settings.json"
    try:
        settings: dict = (
            json.loads(settings_path.read_text())
            if settings_path.exists() else {}
        )
    except (OSError, json.JSONDecodeError):
        settings = {}

    hooks_block = settings.setdefault("hooks", {})
    dispatcher = str(_dispatcher_script_path())

    # One matcher per event used. ``.*`` because the dispatcher does its
    # own per-spec matching; fan-out in Claude Code's matcher list would
    # just fire the dispatcher repeatedly.
    for event in sorted(events_used):
        event_block = hooks_block.setdefault(event, [])
        if not isinstance(event_block, list):
            event_block = []
            hooks_block[event] = event_block
        event_block.append({
            "matcher": ".*",
            "hooks": [{
                "type": "command",
                "command": dispatcher,
                "timeout": 30,
            }],
        })

    try:
        settings_path.write_text(
            json.dumps(settings, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        logger.warning(
            "harness_overlay: failed to update settings.json for %s",
            execution_id, exc_info=True,
        )
        cleanup_session_overlay(execution_id)
        return None

    return overlay


def cleanup_overlay_for_execution(execution_id: str) -> None:
    """Idempotent best-effort overlay teardown."""
    cleanup_session_overlay(execution_id)


# --------------------------------------------------------------------------
# Periodic GC for orphan overlays
# --------------------------------------------------------------------------

_OVERLAY_GLOB = "agented-claude-overlay-*"
_DEFAULT_MAX_AGE_HOURS = 2


def cleanup_stale_overlays(*, max_age_hours: int = _DEFAULT_MAX_AGE_HOURS) -> dict:
    """Remove ``/tmp/agented-claude-overlay-*`` dirs older than the threshold.

    Called at backend startup to mop up after crashes / SIGKILLs where the
    per-execution ``finally:`` block didn't get to run. Two-hour default
    gives in-flight long executions plenty of slack while still cleaning up
    multi-day-old orphans.

    Returns ``{"removed": N, "kept": N, "errors": N}`` for diagnostic logs.
    Never raises — startup must succeed even when /tmp is hostile.
    """
    import os
    import shutil
    import time
    from pathlib import Path

    removed = 0
    kept = 0
    errors = 0

    cutoff = time.time() - max_age_hours * 3600
    try:
        for path in Path("/tmp").glob(_OVERLAY_GLOB):
            try:
                if not path.is_dir():
                    continue
                mtime = path.stat().st_mtime
                if mtime >= cutoff:
                    kept += 1
                    continue
                # Use rmtree with onerror so a single bad child doesn't
                # abort the whole sweep. ignore_errors swallows everything.
                shutil.rmtree(path, ignore_errors=True)
                if path.exists():
                    errors += 1
                else:
                    removed += 1
            except OSError:
                errors += 1
    except OSError:
        # /tmp glob failed entirely; report and move on.
        errors += 1

    if removed or errors:
        logger.info(
            "harness_overlay: GC swept removed=%d kept=%d errors=%d "
            "(max_age_hours=%d)",
            removed, kept, errors, max_age_hours,
        )
    return {"removed": removed, "kept": kept, "errors": errors}
