"""Per-session snapshot of which Forge primitives were active at start.

Capture-only: Forge's renderer chain owns the actual injection. We record
the project's enabled bindings + a deterministic hash so the evolver can
attribute trajectories to harness versions and compute pre/post-evolution
A/B impact.

Polymorphic — works for any session kind (trigger execution, workflow node,
super-agent session, project session). Never raises; the spawn/start path
must not be blocked by snapshot bookkeeping.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Optional

from app.db import harness_snapshots as snapshots_repo
from app.db.connection import get_connection

logger = logging.getLogger(__name__)


def capture_snapshot_for_session(
    *,
    session_kind: str,
    session_id: str,
    project_id: Optional[str],
    harness_kind: str,
) -> Optional[dict[str, Any]]:
    """Record the Forge snapshot for this session. Returns the saved row
    or ``None`` when nothing was captured."""
    try:
        resolved: list[dict[str, Any]] = []
        bundle_hash: Optional[str] = None
        if project_id:
            try:
                from app.db.project_forge_bindings import list_bindings

                bindings = list_bindings(project_id, enabled_only=True)
                resolved = [
                    {
                        "kind": b["kind"],
                        "asset_id": b["asset_id"],
                        "position": b.get("position"),
                        "role": b.get("role"),
                    }
                    for b in bindings
                ]
                bundle_hash = _hash_bindings(resolved)
            except Exception:
                logger.debug(
                    "harness_snapshot: bindings lookup failed for project %s",
                    project_id,
                    exc_info=True,
                )

        snapshots_repo.upsert_snapshot(
            session_kind=session_kind,
            session_id=session_id,
            project_id=project_id,
            harness_kind=harness_kind,
            bundle_hash=bundle_hash,
            resolved_bindings=resolved,
        )
        return snapshots_repo.get_snapshot(session_kind, session_id)
    except Exception:  # noqa: BLE001 — must never raise into the spawn path
        logger.warning(
            "harness_snapshot: capture failed for %s/%s",
            session_kind,
            session_id,
            exc_info=True,
        )
        return None


# ---------------------------------------------------------------------------
# Compat shim for the existing trigger-execution spawn site.
# ---------------------------------------------------------------------------


def capture_snapshot_for_execution(
    *,
    execution_id: str,
    trigger: dict[str, Any],
    harness_kind: str,
) -> Optional[dict[str, Any]]:
    """Legacy entry point still used from ``ExecutionService.run_trigger``.
    Resolves the project_id via the project_paths join and delegates to
    the session-scoped capture."""
    project_id = _resolve_trigger_project_id(trigger)
    return capture_snapshot_for_session(
        session_kind="trigger_execution",
        session_id=execution_id,
        project_id=project_id,
        harness_kind=harness_kind,
    )


def _resolve_trigger_project_id(trigger: dict[str, Any]) -> Optional[str]:
    explicit = trigger.get("project_id")
    if explicit:
        return str(explicit)
    trigger_id = trigger.get("id")
    if not trigger_id:
        return None
    try:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT project_id FROM project_paths "
                "WHERE trigger_id = ? AND project_id IS NOT NULL "
                "ORDER BY id ASC LIMIT 1",
                (trigger_id,),
            ).fetchone()
        return row["project_id"] if row else None
    except Exception:
        return None


def _hash_bindings(bindings: list[dict[str, Any]]) -> str:
    payload = json.dumps(
        sorted([(b["kind"], str(b["asset_id"])) for b in bindings]),
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
