"""Specialized bot management API endpoints for status and health checks."""

import os

from flask_openapi3 import APIBlueprint, Tag

from ..db.triggers import PREDEFINED_TRIGGERS, get_trigger
from ..services.execution_search_service import ExecutionSearchService
from ..services.specialized_bot_service import SpecializedBotService

tag = Tag(name="specialized-bots", description="Specialized automation bot status and health")
specialized_bots_bp = APIBlueprint(
    "specialized_bots", __name__, url_prefix="/admin", abp_tags=[tag]
)


# Map prompt_template commands to skill slugs
# e.g. "/vulnerability-scan {paths}" -> "vulnerability-scan"
def _skill_slug(prompt_template: str) -> str:
    """Extract skill slug from a prompt template command."""
    command = prompt_template.split()[0] if prompt_template else ""
    return command.lstrip("/")


@specialized_bots_bp.get("/specialized-bots/status")
def get_specialized_bot_status():
    """Get availability status of all specialized bots."""
    statuses = []
    for bot_cfg in PREDEFINED_TRIGGERS:
        bot_id = bot_cfg["id"]
        trigger = get_trigger(bot_id)
        trigger_exists = trigger is not None

        slug = _skill_slug(bot_cfg["prompt_template"])
        skill_path = os.path.join(".claude", "skills", slug, "INSTRUCTIONS.md")
        skill_file_exists = os.path.isfile(skill_path)

        statuses.append(
            {
                "id": bot_id,
                "name": bot_cfg["name"],
                "trigger_exists": trigger_exists,
                "skill_file_exists": skill_file_exists,
                "trigger_source": bot_cfg["trigger_source"],
                "enabled": trigger_exists and skill_file_exists,
            }
        )

    return {"bots": statuses}


@specialized_bots_bp.get("/specialized-bots/health")
def get_specialized_bot_health():
    """Get health status of external dependencies needed by specialized bots."""
    search_stats = ExecutionSearchService.get_search_stats()
    return {
        "gh_authenticated": SpecializedBotService.check_gh_auth(),
        "osv_scanner_available": SpecializedBotService.check_osv_scanner(),
        "search_index_count": search_stats.get("indexed_documents", 0),
    }
