"""Stub endpoints for report digest configuration."""

import random
import string
from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

tag = Tag(name="report-digests", description="Report digest scheduling")
report_digests_bp = APIBlueprint("report_digests", __name__, url_prefix="/admin", abp_tags=[tag])


@report_digests_bp.get("/reports/digests")
def get_report_digests():
    """Stub: list all team digest configurations."""
    return {"digests": []}, HTTPStatus.OK


class DigestCreateBody(BaseModel):
    team_name: str = Field(..., description="Display name for the team")
    frequency: str = Field("weekly", description="Frequency: daily or weekly")
    channel: str = Field("email", description="Delivery channel: email or slack")
    recipients: str = Field("", description="Recipients (email or Slack channel)")
    enabled: bool = Field(False, description="Whether digest is enabled")


@report_digests_bp.post("/reports/digests")
def create_report_digest(body: DigestCreateBody):
    """Stub: create a new digest configuration."""
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    team_id = f"team-{suffix}"
    return {
        "team_id": team_id,
        "team_name": body.team_name,
        "frequency": body.frequency,
        "channel": body.channel,
        "recipients": body.recipients,
        "enabled": body.enabled,
        "last_generated": None,
    }, HTTPStatus.CREATED


class DigestTeamPath(BaseModel):
    team_id: str = Field(..., description="Team ID")


@report_digests_bp.put("/reports/digests/<team_id>")
def update_report_digest(path: DigestTeamPath):
    """Stub: update digest configuration for a team."""
    return {"ok": True}, HTTPStatus.OK
