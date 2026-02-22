"""Scheduler API endpoints for agent execution admission control."""

from http import HTTPStatus

from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..services.agent_scheduler_service import AgentSchedulerService

tag = Tag(name="scheduler", description="Agent execution scheduler and admission control")
scheduler_bp = APIBlueprint("scheduler", __name__, url_prefix="/admin/scheduler", abp_tags=[tag])


class AccountPath(BaseModel):
    account_id: int = Field(..., description="Backend account ID")


@scheduler_bp.get("/status")
def get_scheduler_status():
    """Get comprehensive scheduler status with all session states."""
    status = AgentSchedulerService.get_scheduler_status()
    return status, HTTPStatus.OK


@scheduler_bp.get("/sessions")
def get_scheduler_sessions():
    """Get all scheduler session states."""
    status = AgentSchedulerService.get_scheduler_status()
    return {"sessions": status["sessions"]}, HTTPStatus.OK


@scheduler_bp.get("/eligibility/<int:account_id>")
def get_eligibility(path: AccountPath):
    """Check eligibility for a specific account (useful for debugging)."""
    result = AgentSchedulerService.check_eligibility(path.account_id)
    return result, HTTPStatus.OK
