"""Data-retention router (PR-R, wave 83).

Replaces the 501 stubs at ``/admin/retention`` (PR-J3b) with a real CRUD
surface at ``/admin/retention-policies/*``. Persistence is real; the
``/cleanup`` endpoint *acknowledges* a request but does NOT delete from
other tables — destructive enforcement is the scope of a follow-up PR.

This router was previously a stub colocated in
``admin_tooling.py``; it now owns its own file because the surface has
grown a service layer + validation worth isolating.
"""

from __future__ import annotations

from typing import Any

from litestar import Router, delete, get, patch, post
from litestar.exceptions import ClientException, HTTPException

from app.services.retention_service import RetentionService


@get("/", sync_to_thread=False)
def list_retention_policies() -> dict[str, Any]:
    return {"policies": RetentionService.list_policies()}


@post("/", sync_to_thread=False)
def create_retention_policy(data: dict) -> dict[str, Any]:
    if not data:
        raise ClientException(detail="JSON body required")
    return RetentionService.create_policy(data)


@patch("/{policy_id:str}/toggle", sync_to_thread=False)
def toggle_retention_policy(policy_id: str, data: dict) -> dict[str, Any]:
    if not data or "enabled" not in data:
        raise ClientException(detail="enabled is required")
    enabled = bool(data["enabled"])
    if not RetentionService.set_enabled(policy_id, enabled):
        raise HTTPException(status_code=404, detail="Policy not found")
    return {"id": policy_id, "enabled": enabled}


@delete("/{policy_id:str}", status_code=204, sync_to_thread=False)
def delete_retention_policy(policy_id: str) -> None:
    if not RetentionService.delete_policy(policy_id):
        raise HTTPException(status_code=404, detail="Policy not found")
    return None


@post("/cleanup", sync_to_thread=False)
def run_cleanup() -> dict[str, Any]:
    return RetentionService.enqueue_cleanup()


retention_router = Router(
    path="/admin/retention-policies",
    route_handlers=[
        list_retention_policies,
        create_retention_policy,
        toggle_retention_policy,
        delete_retention_policy,
        run_cleanup,
    ],
)
