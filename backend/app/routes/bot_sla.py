"""Stub endpoints for bot SLA & uptime tracking."""

from http import HTTPStatus

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="bot-sla", description="Bot SLA & uptime tracking")
bot_sla_bp = APIBlueprint("bot_sla", __name__, url_prefix="/admin", abp_tags=[tag])


@bot_sla_bp.get("/bots/sla")
def get_bot_sla():
    """Stub: bot SLA and uptime entries."""
    return {"entries": []}, HTTPStatus.OK
