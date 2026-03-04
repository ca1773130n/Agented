"""Health monitoring API endpoints for bot health alerts and team reports."""

from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag

from ..db.health_alerts import acknowledge_alert, get_recent_alerts
from ..services.health_monitor_service import HealthMonitorService
from ..services.report_service import ReportService

tag = Tag(name="health-monitor", description="Bot health monitoring and alerting")
health_monitor_bp = APIBlueprint(
    "health_monitor", __name__, url_prefix="/admin/health-monitor", abp_tags=[tag]
)


@health_monitor_bp.get("/alerts")
def list_alerts():
    """List recent health alerts with optional filters."""
    limit = request.args.get("limit", 50, type=int)
    trigger_id = request.args.get("trigger_id", None, type=str)
    ack_param = request.args.get("acknowledged", None, type=str)

    acknowledged = None
    if ack_param is not None:
        acknowledged = ack_param.lower() in ("1", "true", "yes")

    alerts = get_recent_alerts(limit=limit, trigger_id=trigger_id, acknowledged=acknowledged)
    return {"alerts": alerts}, HTTPStatus.OK


@health_monitor_bp.get("/status")
def get_status():
    """Get health monitor status summary with alert counts."""
    status = HealthMonitorService.get_status()
    return status, HTTPStatus.OK


@health_monitor_bp.post("/alerts/<int:alert_id>/acknowledge")
def acknowledge(alert_id: int):
    """Acknowledge a health alert."""
    success = acknowledge_alert(alert_id)
    if success:
        return {"message": "Alert acknowledged"}, HTTPStatus.OK
    return {"error": "Alert not found"}, HTTPStatus.NOT_FOUND


@health_monitor_bp.get("/report")
def get_report():
    """Generate weekly team impact report."""
    team_id = request.args.get("team_id", None, type=str)
    report = ReportService.generate_weekly_report(team_id=team_id)
    return report, HTTPStatus.OK


@health_monitor_bp.post("/check")
def manual_check():
    """Manually trigger a health check cycle (for testing/debugging)."""
    HealthMonitorService._check_health()
    status = HealthMonitorService.get_status()
    return {"message": "Health check completed", **status}, HTTPStatus.OK
