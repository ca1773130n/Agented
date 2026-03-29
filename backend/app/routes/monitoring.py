"""Monitoring API endpoints for rate limit window tracking."""

import logging
from http import HTTPStatus

logger = logging.getLogger(__name__)

from flask import request
from flask_openapi3 import APIBlueprint, Tag

from app.models.common import error_response

from ..database import get_monitoring_config, get_snapshot_history
from ..models.common import PaginationQuery
from ..services.monitoring_service import MonitoringService

tag = Tag(name="monitoring", description="Rate limit monitoring configuration and status")
monitoring_bp = APIBlueprint("monitoring", __name__, url_prefix="/admin/monitoring", abp_tags=[tag])


@monitoring_bp.get("/config")
def get_config():
    """Get current monitoring configuration."""
    config = get_monitoring_config()
    return config, HTTPStatus.OK


@monitoring_bp.post("/config")
def post_config():
    """Save monitoring configuration and reconfigure the APScheduler job."""
    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)

    # Validate polling_minutes
    polling_minutes = data.get("polling_minutes", 5)
    if polling_minutes not in (1, 5, 15, 30, 60):
        return error_response(
            "BAD_REQUEST",
            "polling_minutes must be one of [1, 5, 15, 30, 60]",
            HTTPStatus.BAD_REQUEST,
        )

    # Validate accounts structure — must be a dict of str → dict
    accounts = data.get("accounts", {})
    if not isinstance(accounts, dict):
        return error_response(
            "BAD_REQUEST", "accounts must be a JSON object", HTTPStatus.BAD_REQUEST
        )
    for k, v in accounts.items():
        if not isinstance(k, str):
            return error_response(
                "BAD_REQUEST",
                f"accounts keys must be strings, got {type(k).__name__}",
                HTTPStatus.BAD_REQUEST,
            )
        if not isinstance(v, dict):
            return error_response(
                "BAD_REQUEST",
                f"accounts[{k!r}] must be a JSON object, got {type(v).__name__}",
                HTTPStatus.BAD_REQUEST,
            )

    # Build config dict
    config = {
        "enabled": bool(data.get("enabled", False)),
        "polling_minutes": polling_minutes,
        "accounts": accounts,
    }

    # Reconfigure the monitoring service (saves to DB + re-registers job)
    MonitoringService.reconfigure(config)

    return config, HTTPStatus.OK


@monitoring_bp.get("/status")
def get_status():
    """Get latest monitoring status with snapshots, consumption rates, and ETA projections."""
    status = MonitoringService.get_monitoring_status()
    return status, HTTPStatus.OK


@monitoring_bp.post("/poll")
def poll_now():
    """Trigger an immediate monitoring poll and return fresh status."""
    try:
        MonitoringService._poll_usage()
    except Exception as e:
        # Log but don't fail — return whatever status we have
        logger.warning("Monitoring poll had errors: %s", e)

    status = MonitoringService.get_monitoring_status()
    return status, HTTPStatus.OK


@monitoring_bp.get("/history")
def get_history(query: PaginationQuery):
    """Get snapshot history for a specific account and window type.

    Query params:
        account_id (required): Backend account ID
        window_type (required): Window type (e.g., '5h_sliding', 'weekly', 'rpd', 'tpm_60s')
        minutes (optional): How far back to look, default 360 (6 hours)
        limit (optional): Max records to return
        offset (optional): Number of records to skip
    """
    account_id = request.args.get("account_id", type=int)
    window_type = request.args.get("window_type")
    minutes = request.args.get("minutes", 360, type=int)

    if account_id is None or not window_type:
        return error_response(
            "BAD_REQUEST",
            "account_id and window_type are required query parameters",
            HTTPStatus.BAD_REQUEST,
        )

    history = get_snapshot_history(
        account_id,
        window_type,
        since_minutes=minutes,
        limit=query.limit,
        offset=query.offset or 0,
    )

    formatted = [
        {
            "tokens_used": s["tokens_used"],
            "percentage": s["percentage"],
            "recorded_at": s["recorded_at"],
        }
        for s in history
    ]

    return {
        "account_id": account_id,
        "window_type": window_type,
        "history": formatted,
        "total_count": len(formatted),
    }, HTTPStatus.OK
