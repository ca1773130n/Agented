"""Atomic create+bind+materialize for Forge primitives.

The codebase has NO transaction/saga abstraction spanning the DB and the
filesystem: ``get_connection()`` commits per call and
``materialize_primitives`` writes files outside any DB transaction. So
"atomic create" here is implemented as an EXPLICIT LIFO compensation in
``create_and_bind_and_materialize``: the function performs up to three forward
steps (create row → bind → materialize), tracking exactly which completed, and
on ANY mid-flow exception it undoes the completed steps in REVERSE order
(written files → binding → row), leaving NO orphaned row, binding, or repo
file.

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
from app.services.forge_materialization_service import (
    _finalize_manifest,
    materialize_primitives,
)
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

    On any mid-flow failure, completed steps are undone in reverse order
    (written files → binding → asset row) so no orphan remains, and the
    original exception is re-raised.

    Returns ``{"kind", "asset", "binding", "written"}`` on success.
    """
    if kind not in VALID_FORGE_BINDING_KINDS:
        raise ValueError(f"Unknown forge kind: {kind!r}")
    if kind not in _CREATE_FNS:
        raise ValueError(f"forge/create does not support kind {kind!r}")

    payload = dict(payload or {})

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
                role=payload.get("role"),
                enabled=bool(payload.get("enabled", True)),
            )
            binding_id = binding.get("id") if binding else None

        # --- Step 3: materialize ------------------------------------------
        if materialize:
            project = get_project(project_id)
            if not project:
                raise ValueError(f"Project not found: {project_id}")
            workspace_path = Path(
                ProjectWorkspaceService.resolve_working_directory(project_id)
            )
            result = materialize_primitives(project, [kind], workspace_path)
            written_rels = result.rel_paths()

        return {
            "kind": kind,
            "asset": asset,
            "binding": binding,
            "written": written_rels,
        }

    except Exception:
        # LIFO compensation — undo in reverse of the forward order. Each action
        # is isolated so a cleanup error cannot mask the original exception.
        _compensate(
            kind=kind,
            asset_id=asset_id,
            binding_id=binding_id,
            written_rels=written_rels,
            project=project,
            workspace_path=workspace_path,
        )
        raise


def _compensate(
    *,
    kind: str,
    asset_id: Any,
    binding_id: Optional[int],
    written_rels: list[str],
    project: Optional[dict],
    workspace_path: Optional[Path],
) -> None:
    """Undo completed steps in REVERSE (LIFO) order. Every action is wrapped so
    no cleanup failure can mask or replace the original error being unwound."""

    # 3 (last forward step) → undo first: remove written repo files, then
    # reconcile the manifest so the kind's bucket no longer references them.
    if written_rels and workspace_path is not None:
        for rel in written_rels:
            try:
                target = workspace_path / rel
                if target.exists():
                    target.unlink()
            except Exception:  # pragma: no cover - best effort cleanup
                logger.warning("forge compensation: could not unlink %s", rel)
        if project is not None:
            try:
                # Re-run materialization for the kind now that the row will be
                # gone — but the row still exists here, so instead reconcile the
                # manifest directly against an empty written set for the kind.
                from app.services.forge_materialization_service import (
                    MaterializationResult,
                )

                empty = MaterializationResult()
                _finalize_manifest(workspace_path, empty, [kind])
            except Exception:  # pragma: no cover - best effort cleanup
                logger.warning("forge compensation: manifest reconcile failed")

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
