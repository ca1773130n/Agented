"""Version pin management API endpoints."""

from http import HTTPStatus
from typing import Optional

from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from app.models.common import error_response

from ..db.version_pins import (
    get_all_version_pins,
    get_version_history,
    get_version_pin,
    set_pin_unpinned,
    update_pin_status,
)

tag = Tag(name="version-pins", description="Skill and plugin version pinning")
version_pins_bp = APIBlueprint(
    "version_pins", __name__, url_prefix="/admin/version-pins", abp_tags=[tag]
)


# ---------------------------------------------------------------------------
# Path / body models
# ---------------------------------------------------------------------------


class PinIdPath(BaseModel):
    pin_id: str = Field(..., description="Version pin ID")


class ComponentIdPath(BaseModel):
    component_id: str = Field(..., description="Component ID")


class UpdatePinBody(BaseModel):
    pinned_version: str = Field(..., description="Version to pin to")
    status: Optional[str] = Field("pinned", description="Pin status")
    pinned_at: Optional[str] = Field(None, description="ISO-8601 timestamp of pin action")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@version_pins_bp.get("/")
def list_version_pins():
    """List all version pins."""
    pins = get_all_version_pins()
    return {"pins": pins, "total": len(pins)}, HTTPStatus.OK


@version_pins_bp.put("/<pin_id>")
def update_version_pin(path: PinIdPath, body: UpdatePinBody):
    """Update the pinned version and status for a pin."""
    existing = get_version_pin(path.pin_id)
    if not existing:
        return error_response("NOT_FOUND", "Version pin not found", HTTPStatus.NOT_FOUND)

    from datetime import datetime, timezone

    pinned_at = body.pinned_at or datetime.now(timezone.utc).isoformat()
    updated = update_pin_status(
        pin_id=path.pin_id,
        pinned_version=body.pinned_version,
        status=body.status or "pinned",
        pinned_at=pinned_at,
    )
    if not updated:
        return error_response(
            "INTERNAL_SERVER_ERROR", "Failed to update pin", HTTPStatus.INTERNAL_SERVER_ERROR
        )

    pin = get_version_pin(path.pin_id)
    return pin, HTTPStatus.OK


@version_pins_bp.post("/<pin_id>/unpin")
def unpin_version_pin(path: PinIdPath):
    """Set a pin to unpinned status."""
    existing = get_version_pin(path.pin_id)
    if not existing:
        return error_response("NOT_FOUND", "Version pin not found", HTTPStatus.NOT_FOUND)

    updated = set_pin_unpinned(path.pin_id)
    if not updated:
        return error_response(
            "INTERNAL_SERVER_ERROR", "Failed to unpin", HTTPStatus.INTERNAL_SERVER_ERROR
        )

    pin = get_version_pin(path.pin_id)
    return pin, HTTPStatus.OK


@version_pins_bp.post("/upgrade-all")
def upgrade_all_pins():
    """Batch upgrade all outdated pins to their latest version."""
    from datetime import datetime, timezone

    pins = get_all_version_pins()
    outdated = [p for p in pins if p.get("status") == "outdated"]
    now = datetime.now(timezone.utc).isoformat()

    upgraded = 0
    for pin in outdated:
        latest = pin.get("latest_version")
        if latest:
            ok = update_pin_status(
                pin_id=pin["id"],
                pinned_version=latest,
                status="pinned",
                pinned_at=now,
            )
            if ok:
                upgraded += 1

    return {"upgraded": upgraded, "total_outdated": len(outdated)}, HTTPStatus.OK


@version_pins_bp.get("/<component_id>/versions")
def get_component_version_history(path: ComponentIdPath):
    """Get version history for a component."""
    history = get_version_history(path.component_id)
    return {"history": history, "total": len(history)}, HTTPStatus.OK
