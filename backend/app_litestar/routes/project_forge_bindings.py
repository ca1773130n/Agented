"""CRUD + preview for project Forge bindings.

Routes:

* ``GET    /admin/projects/{id}/forge-bindings``
* ``PUT    /admin/projects/{id}/forge-bindings`` — replace entire set
* ``POST   /admin/projects/{id}/forge-bindings`` — add one
* ``DELETE /admin/projects/{id}/forge-bindings/{binding_id}``
* ``POST   /admin/projects/{id}/forge-context/preview`` —
  compile a bundle without spawning anything; the operator sees
  what would get sent.
"""

from __future__ import annotations

import logging
from typing import Any

from litestar import Router, delete, get, post, put
from litestar.exceptions import ClientException, NotFoundException

from app.db import (
    VALID_FORGE_BINDING_KINDS,
    add_project_forge_binding,
    get_project,
    list_forge_bundle_items,
    list_project_forge_bindings,
    remove_project_forge_binding,
    replace_project_forge_bindings,
)
from app.db.connection import get_connection
from app.db.forge_bundles import _add_binding
from app.services.context_compiler_service import ContextCompilerService
from app.services.forge_create_service import create_and_bind_and_materialize
from app.services.project_workspace_service import ProjectWorkspaceService

from ..auth import Caller

logger = logging.getLogger(__name__)


def _ensure_project(project_id: str) -> dict:
    project = get_project(project_id)
    if not project:
        raise NotFoundException(detail="Project not found")
    return project


@get("/{project_id:str}/forge-bindings", sync_to_thread=False)
def list_bindings_endpoint(project_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    _ensure_project(project_id)
    return {"bindings": list_project_forge_bindings(project_id)}


@put("/{project_id:str}/forge-bindings", sync_to_thread=False)
def replace_bindings_endpoint(
    project_id: str, data: dict, caller: Caller
) -> dict[str, Any]:
    del caller
    _ensure_project(project_id)
    bindings = (data or {}).get("bindings") or []
    if not isinstance(bindings, list):
        raise ClientException(detail="bindings must be a list")
    return {"bindings": replace_project_forge_bindings(project_id, bindings)}


@post("/{project_id:str}/forge-bindings", status_code=201, sync_to_thread=False)
def add_binding_endpoint(
    project_id: str, data: dict, caller: Caller
) -> dict[str, Any]:
    del caller
    _ensure_project(project_id)
    body = data or {}
    kind = body.get("kind")
    asset_id = body.get("asset_id")
    if not kind or not asset_id:
        raise ClientException(detail="kind and asset_id are required")
    if kind not in VALID_FORGE_BINDING_KINDS:
        raise ClientException(
            detail=f"kind must be one of {sorted(VALID_FORGE_BINDING_KINDS)}"
        )
    binding = add_project_forge_binding(
        project_id,
        kind,
        str(asset_id),
        role=body.get("role"),
        enabled=bool(body.get("enabled", True)),
    )
    return {"binding": binding}


@delete(
    "/{project_id:str}/forge-bindings/{binding_id:int}",
    status_code=204,
    sync_to_thread=False,
)
def remove_binding_endpoint(
    project_id: str, binding_id: int, caller: Caller
) -> None:
    del caller
    _ensure_project(project_id)
    if not remove_project_forge_binding(binding_id):
        raise NotFoundException(detail="Binding not found")


@post("/{project_id:str}/forge-context/preview", sync_to_thread=False)
def preview_bundle_endpoint(
    project_id: str, data: dict, caller: Caller
) -> dict[str, Any]:
    del caller
    _ensure_project(project_id)
    body = data or {}
    project_root: str | None = None
    try:
        project_root = ProjectWorkspaceService.resolve_working_directory(project_id)
    except Exception:
        # Preview must work even on a project without a cloned
        # workspace yet — file attachments will just be skipped.
        project_root = None
    bundle = ContextCompilerService.compile(
        project_id,
        session_overrides=body.get("session_overrides"),
        attachments=body.get("attachments"),
        project_root=project_root,
    )
    return {"bundle": bundle.to_preview_dict()}


@post("/{project_id:str}/forge/create", status_code=201, sync_to_thread=False)
def forge_create_endpoint(
    project_id: str, data: dict, caller: Caller
) -> dict[str, Any]:
    """Atomic create+bind+materialize: create a Forge asset, bind it, and
    materialize it to the repo in ONE flow with LIFO compensation on failure.

    Body: ``{kind, payload, bind?, materialize?}``. A bad kind → 400; a
    mid-flow failure surfaces as 5xx via the existing exception handlers after
    compensation has undone every completed step (no orphan).
    """
    del caller
    _ensure_project(project_id)
    body = data or {}
    kind = body.get("kind")
    payload = body.get("payload") or {}
    if not kind:
        raise ClientException(detail="kind is required")
    if not isinstance(payload, dict):
        raise ClientException(detail="payload must be an object")
    try:
        result = create_and_bind_and_materialize(
            project_id,
            kind,
            payload,
            bind=bool(body.get("bind", True)),
            materialize=bool(body.get("materialize", True)),
        )
    except ValueError as exc:
        # Bad kind / unsupported kind / project-not-found surface as 400.
        raise ClientException(detail=str(exc)) from exc
    return result


@post("/{project_id:str}/forge/bundles/{bundle_id:str}/bind", sync_to_thread=False)
def bundle_bind_endpoint(
    project_id: str, bundle_id: str, caller: Caller
) -> dict[str, Any]:
    """Bind every item of a cross-kind bundle to the project in ONE
    transaction using the conn-accepting ``_add_binding`` from 17-03. If any
    item raises, the connection block does not commit (the whole bind rolls
    back) and the error surfaces — no partial bind."""
    del caller
    _ensure_project(project_id)
    items = list_forge_bundle_items(bundle_id)
    if not items:
        raise NotFoundException(detail="Bundle has no items (or does not exist)")
    with get_connection() as conn:
        for item in items:
            _add_binding(
                conn,
                project_id,
                item["kind"],
                str(item["asset_id"]),
                position=item.get("position", 0),
            )
        conn.commit()
    return {"bundle_id": bundle_id, "bound": len(items)}


forge_bindings_router = Router(
    path="/admin/projects",
    route_handlers=[
        list_bindings_endpoint,
        replace_bindings_endpoint,
        add_binding_endpoint,
        remove_binding_endpoint,
        preview_bundle_endpoint,
        forge_create_endpoint,
        bundle_bind_endpoint,
    ],
)
