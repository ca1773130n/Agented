"""Migrated to Litestar :20002 in wave 63."""

from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

tag = Tag(name="super_agents", description="Migrated to Litestar")
super_agents_bp = APIBlueprint(
    "super_agents_bp",
    __name__,
    url_prefix="/admin/super-agents",
    abp_tags=[tag],
)


class SuperAgentPath(BaseModel):
    """Path param shim — kept here while super_agent_messages still imports it."""

    super_agent_id: str = Field(..., description="SuperAgent ID")
