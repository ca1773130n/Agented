"""Admin routes for the GRD 0.5.0 research-steering settings.

Surfaces the two settings that decide what GRD's interactive research loop
actually does, per project, backed by that project's
``<local_path>/.planning/config.json`` — the file GRD itself reads. They are
deliberately NOT stored in Agented's ``settings`` table: a toggle there would
change nothing about how GRD behaves.

See :mod:`app.services.grd_config_service` for why the two travel together
(``autonomous_mode`` gates whether ``interactive_fallback`` is ever consulted).
"""

from __future__ import annotations

from typing import Any, Optional

from litestar import Router, get, post
from litestar.exceptions import NotFoundException, ValidationException

from app.services import grd_config_service as gcs


@get("/system/grd/steering/projects", sync_to_thread=True)
def list_grd_steering() -> dict[str, Any]:
    """One row per project: the two steering settings plus whether a GRD config
    exists at all (``configured``), so the UI can disable rather than mislead."""
    return {"projects": gcs.list_steering()}


@post("/system/grd/steering/projects/{project_id:str}", sync_to_thread=True)
def set_grd_steering(
    project_id: str,
    data: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Patch either or both settings for one project.

    Body: ``{"autonomous_mode"?: bool, "interactive_fallback"?: "recommended"|"panel"}``.
    Both optional, but at least one is required — an empty patch that returned
    200 would look like a saved change that never happened.
    """
    payload = data or {}
    autonomous_mode = payload.get("autonomous_mode")
    interactive_fallback = payload.get("interactive_fallback")
    if autonomous_mode is None and interactive_fallback is None:
        raise ValidationException(
            detail="body must set at least one of 'autonomous_mode', 'interactive_fallback'"
        )
    if autonomous_mode is not None and not isinstance(autonomous_mode, bool):
        raise ValidationException(detail="'autonomous_mode' must be a boolean")
    if interactive_fallback is not None and interactive_fallback not in gcs.FALLBACK_VALUES:
        raise ValidationException(
            detail=f"'interactive_fallback' must be one of {list(gcs.FALLBACK_VALUES)}"
        )
    try:
        project = gcs.set_steering(
            project_id,
            autonomous_mode=autonomous_mode,
            interactive_fallback=interactive_fallback,
        )
    except ValueError as exc:
        # "project not found" is a 404; every other refusal (no local_path, no
        # readable config, unwritable file) is a 400 — the request was valid but
        # this project cannot accept it.
        if "project not found" in str(exc):
            raise NotFoundException(detail=str(exc)) from exc
        raise ValidationException(detail=str(exc)) from exc
    return {"project": project}


grd_settings_router = Router(
    path="/admin",
    route_handlers=[
        list_grd_steering,
        set_grd_steering,
    ],
)
