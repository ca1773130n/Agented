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
    list_project_forge_bindings,
    remove_project_forge_binding,
    replace_project_forge_bindings,
)
from app.services.context_compiler_service import ContextCompilerService
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


forge_bindings_router = Router(
    path="/admin/projects",
    route_handlers=[
        list_bindings_endpoint,
        replace_bindings_endpoint,
        add_binding_endpoint,
        remove_binding_endpoint,
        preview_bundle_endpoint,
    ],
)
