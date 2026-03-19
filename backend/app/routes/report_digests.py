"""Stub endpoints for report digest configuration."""

from http import HTTPStatus

from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

tag = Tag(name="report-digests", description="Report digest scheduling")
report_digests_bp = APIBlueprint("report_digests", __name__, url_prefix="/admin", abp_tags=[tag])


@report_digests_bp.get("/reports/digests")
def get_report_digests():
    """Stub: list all team digest configurations."""
    return {"digests": []}, HTTPStatus.OK


class DigestTeamPath(BaseModel):
    team_id: str = Field(..., description="Team ID")


@report_digests_bp.put("/reports/digests/<team_id>")
def update_report_digest(path: DigestTeamPath):
    """Stub: update digest configuration for a team."""
    return {"ok": True}, HTTPStatus.OK
