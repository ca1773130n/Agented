"""Atomic create+bind+materialize for Forge primitives.

The codebase has NO transaction/saga abstraction spanning the DB and the
filesystem: ``get_connection()`` commits per call and
``materialize_primitives`` writes files outside any DB transaction. So
"atomic create" here is implemented as an EXPLICIT compensation in
``create_and_bind_and_materialize``: the function performs up to three forward
steps (create row → bind → materialize), tracking exactly which completed, and
on ANY mid-flow exception it undoes the completed steps (binding → row, then a
file reconcile against the rolled-back DB), leaving NO orphaned row, binding,
or repo file.

Each compensation action is wrapped in its own try/except so a cleanup failure
cannot mask the original exception; the original error is always re-raised.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Optional

from app.db import (
    VALID_FORGE_BINDING_KINDS,
    add_project_forge_binding,
    create_command,
    create_hook,
    create_mcp_server,
    create_rule,
    create_subagent,
    delete_command,
    delete_hook,
    delete_mcp_server,
    delete_rule,
    delete_subagent,
    get_project,
    remove_project_forge_binding,
)
from app.services.forge_materialization_service import materialize_primitives
from app.services.project_workspace_service import ProjectWorkspaceService

logger = logging.getLogger(__name__)


# Per-kind create dispatch. Each create fn takes **payload kwargs and returns
# the new asset id (int for rule/command/hook; str for subagent/mcp_server) or
# None/raises on failure.
_CREATE_FNS: dict[str, Callable[..., Any]] = {
    "subagent": create_subagent,
    "rule": create_rule,
    "command": create_command,
    "hook": create_hook,
    "mcp_server": create_mcp_server,
}

# Per-kind delete dispatch for compensation. ids match the create return type.
_DELETE_FNS: dict[str, Callable[[Any], bool]] = {
    "subagent": delete_subagent,
    "rule": delete_rule,
    "command": delete_command,
    "hook": delete_hook,
    "mcp_server": delete_mcp_server,
}


def _coerce_asset_id(kind: str, raw: Any) -> Any:
    """rule/command/hook ids are INT; subagent/mcp_server are STR."""
    if kind in ("rule", "command", "hook"):
        return int(raw)
    return str(raw)


def create_and_bind_and_materialize(
    project_id: str,
    kind: str,
    payload: dict,
    bind: bool = True,
    materialize: bool = True,
) -> dict:
    """Create a Forge asset, optionally bind it to the project, and optionally
    materialize it to the project's repo — atomically via LIFO compensation.

    On any mid-flow failure, completed steps are undone (binding → asset row,
    then a file reconcile against the rolled-back DB) so no orphan remains,
    and the original exception is re-raised.

    Returns ``{"kind", "asset", "binding", "written"}`` on success.
    """
    if kind not in VALID_FORGE_BINDING_KINDS:
        raise ValueError(f"Unknown forge kind: {kind!r}")
    if kind not in _CREATE_FNS:
        raise ValueError(f"forge/create does not support kind {kind!r}")

    payload = dict(payload or {})
    # ``role`` belongs to the BINDING, not the asset row — pop it before the
    # **payload splat so the per-kind create fn (none of which take a ``role``
    # param) doesn't blow up with a TypeError.
    bind_role = payload.pop("role", None)

    # Compensation bookkeeping — only set once the corresponding step succeeds.
    asset_id: Any = None
    binding_id: Optional[int] = None
    written_rels: list[str] = []
    project: Optional[dict] = None
    workspace_path: Optional[Path] = None

    try:
        # --- Step 1: create the asset row -------------------------------
        created = _CREATE_FNS[kind](**payload)
        if created is None:
            raise RuntimeError(f"create_{kind} returned no id (creation failed)")
        # subagent/mcp_server create fns return the full row dict; rule/command/
        # hook return the int lastrowid.
        if isinstance(created, dict):
            asset = created
            asset_id = _coerce_asset_id(kind, created.get("id"))
        else:
            asset_id = _coerce_asset_id(kind, created)
            asset = {"id": asset_id}

        binding: Optional[dict] = None

        # --- Step 2: bind --------------------------------------------------
        if bind:
            binding = add_project_forge_binding(
                project_id,
                kind,
                str(asset_id),
                role=bind_role,
                enabled=bool(payload.get("enabled", True)),
            )
            binding_id = binding.get("id") if binding else None

        # --- Step 3: materialize ------------------------------------------
        if materialize:
            project = get_project(project_id)
            if not project:
                raise ValueError(f"Project not found: {project_id}")
            workspace_path = Path(ProjectWorkspaceService.resolve_working_directory(project_id))
            result = materialize_primitives(project, [kind], workspace_path)
            written_rels = result.rel_paths()

        return {
            "kind": kind,
            "asset": asset,
            "binding": binding,
            "written": written_rels,
        }

    except Exception:
        # Compensation — undo the DB steps in reverse, then reconcile files
        # against the rolled-back DB. Each action is isolated so a cleanup
        # error cannot mask the original exception.
        _compensate(
            kind=kind,
            asset_id=asset_id,
            binding_id=binding_id,
            project=project,
            workspace_path=workspace_path,
        )
        raise


def _compensate(
    *,
    kind: str,
    asset_id: Any,
    binding_id: Optional[int],
    project: Optional[dict],
    workspace_path: Optional[Path],
) -> None:
    """Undo completed DB steps in reverse (binding → row), then reconcile repo
    files by re-materializing the kind against the rolled-back DB. Every action
    is wrapped so no cleanup failure can mask the original error being unwound.

    File reconcile MUST come after the DB undo and MUST NOT just unlink this
    run's written paths: ``materialize_primitives`` rewrites EVERY bound asset
    of the kind, so the written set includes pre-existing assets' files —
    unlinking them all would wipe the kind. Re-materializing instead deletes
    only the new asset's file (its row/binding are gone) and leaves the other
    assets' files and the manifest consistent."""

    # 2 → undo the binding.
    if binding_id is not None:
        try:
            remove_project_forge_binding(binding_id)
        except Exception:  # pragma: no cover - best effort cleanup
            logger.warning("forge compensation: could not remove binding %s", binding_id)

    # 1 → undo the asset row.
    if asset_id is not None:
        try:
            _DELETE_FNS[kind](asset_id)
        except Exception:  # pragma: no cover - best effort cleanup
            logger.warning("forge compensation: could not delete %s %s", kind, asset_id)

    # 3 → reconcile files/manifest against the now-rolled-back DB.
    if project is not None and workspace_path is not None:
        try:
            materialize_primitives(project, [kind], workspace_path)
        except Exception:  # pragma: no cover - best effort cleanup
            logger.warning("forge compensation: file reconcile failed", exc_info=True)
