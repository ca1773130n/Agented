"""Orchestration API routes for fallback chains and account health."""

# stdlib
from http import HTTPStatus

# third-party
from flask_openapi3 import APIBlueprint
from pydantic import BaseModel, Field

# database
from ..database import (
    delete_fallback_chain,
    get_fallback_chain,
    set_fallback_chain,
)

# models
from ..models.orchestration import SetFallbackChainRequest

# services
from ..services.orchestration_service import OrchestrationService
from ..services.rate_limit_service import RateLimitService

orchestration_bp = APIBlueprint("orchestration", __name__, url_prefix="/admin/orchestration")


# =============================================================================
# Path Parameter Models
# =============================================================================


class TriggerFallbackPath(BaseModel):
    """Path parameters for trigger fallback chain routes."""

    trigger_id: str = Field(..., description="Trigger ID")


class AccountClearPath(BaseModel):
    """Path parameters for account rate limit clear route."""

    account_id: int = Field(..., description="Account ID")


# =============================================================================
# Fallback Chain Routes
# =============================================================================


@orchestration_bp.get("/triggers/<trigger_id>/fallback-chain")
def get_trigger_fallback_chain(path: TriggerFallbackPath):
    """Get the fallback chain for a trigger."""
    chain = get_fallback_chain("trigger", path.trigger_id)
    entries = [
        {
            "backend_type": entry["backend_type"],
            "account_id": entry.get("account_id"),
            "chain_order": entry["chain_order"],
        }
        for entry in chain
    ]
    return {"chain": entries}, HTTPStatus.OK


@orchestration_bp.put("/triggers/<trigger_id>/fallback-chain")
def set_trigger_fallback_chain(path: TriggerFallbackPath, body: SetFallbackChainRequest):
    """Set (replace) the fallback chain for a trigger."""
    error = OrchestrationService.validate_fallback_chain_entries(body.entries)
    if error:
        return {"error": error}, HTTPStatus.BAD_REQUEST

    entries = [e.model_dump() for e in body.entries]
    success = set_fallback_chain("trigger", path.trigger_id, entries)

    if not success:
        return {"error": "Failed to set fallback chain"}, HTTPStatus.INTERNAL_SERVER_ERROR

    chain = get_fallback_chain("trigger", path.trigger_id)
    result_entries = [
        {
            "backend_type": entry["backend_type"],
            "account_id": entry.get("account_id"),
            "chain_order": entry["chain_order"],
        }
        for entry in chain
    ]
    return {"chain": result_entries}, HTTPStatus.OK


@orchestration_bp.delete("/triggers/<trigger_id>/fallback-chain")
def delete_trigger_fallback_chain(path: TriggerFallbackPath):
    """Delete the fallback chain for a trigger."""
    delete_fallback_chain("trigger", path.trigger_id)
    return "", HTTPStatus.NO_CONTENT


# =============================================================================
# Health & Rate Limit Routes
# =============================================================================


@orchestration_bp.get("/health")
def get_account_health():
    """Get health status of all accounts across all backends."""
    states = RateLimitService.get_all_account_states()
    return {"accounts": states}, HTTPStatus.OK


@orchestration_bp.post("/accounts/<int:account_id>/clear-rate-limit")
def clear_account_rate_limit(path: AccountClearPath):
    """Manually clear rate limit for an account."""
    success = RateLimitService.clear_rate_limit(path.account_id)
    if not success:
        return {"error": "Account not found"}, HTTPStatus.NOT_FOUND
    return {"message": "Rate limit cleared"}, HTTPStatus.OK
