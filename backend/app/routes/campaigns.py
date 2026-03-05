"""Campaign management API endpoints."""

from http import HTTPStatus

from flask_openapi3 import APIBlueprint, Tag

from app.models.common import error_response

from ..db.campaigns import (
    delete_campaign,
    get_campaign,
    list_campaign_executions,
    list_campaigns,
)
from ..models.campaign import (
    CampaignCreate,
    CampaignListQuery,
    CampaignPath,
    TriggerCampaignPath,
)
from ..services.campaign_service import get_campaign_results, start_campaign

tag = Tag(name="campaigns", description="Multi-repo campaign orchestration")
campaigns_bp = APIBlueprint("campaigns", __name__, url_prefix="/admin", abp_tags=[tag])


@campaigns_bp.post("/campaigns")
def create_campaign(body: CampaignCreate):
    """Start a new multi-repo campaign."""
    campaign_id = start_campaign(
        name=body.name,
        trigger_id=body.trigger_id,
        repo_urls=body.repo_urls,
    )
    if not campaign_id:
        return error_response(
            "INTERNAL_SERVER_ERROR", "Failed to create campaign", HTTPStatus.INTERNAL_SERVER_ERROR
        )

    campaign = get_campaign(campaign_id)
    return {"campaign": campaign}, HTTPStatus.CREATED


@campaigns_bp.get("/campaigns")
def list_all_campaigns(query: CampaignListQuery):
    """List all campaigns with optional filters."""
    campaigns = list_campaigns(
        trigger_id=query.trigger_id,
        status=query.status,
    )
    return {"campaigns": campaigns, "total": len(campaigns)}


@campaigns_bp.get("/campaigns/<campaign_id>")
def get_campaign_detail(path: CampaignPath):
    """Get campaign detail with all repo execution statuses."""
    campaign = get_campaign(path.campaign_id)
    if not campaign:
        return error_response("NOT_FOUND", "Campaign not found", HTTPStatus.NOT_FOUND)

    executions = list_campaign_executions(path.campaign_id)
    return {
        "campaign": campaign,
        "executions": executions,
    }


@campaigns_bp.get("/campaigns/<campaign_id>/results")
def get_campaign_results_view(path: CampaignPath):
    """Get consolidated campaign results grouped by repo."""
    results = get_campaign_results(path.campaign_id)
    if not results:
        return error_response("NOT_FOUND", "Campaign not found", HTTPStatus.NOT_FOUND)

    return results


@campaigns_bp.delete("/campaigns/<campaign_id>")
def delete_campaign_view(path: CampaignPath):
    """Delete a campaign record."""
    deleted = delete_campaign(path.campaign_id)
    if not deleted:
        return error_response("NOT_FOUND", "Campaign not found", HTTPStatus.NOT_FOUND)

    return {"deleted": True}


@campaigns_bp.get("/triggers/<trigger_id>/campaigns")
def list_trigger_campaigns(path: TriggerCampaignPath):
    """List campaigns for a specific trigger."""
    campaigns = list_campaigns(trigger_id=path.trigger_id)
    return {"campaigns": campaigns, "total": len(campaigns)}
