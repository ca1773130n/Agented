"""Health check endpoints."""

from http import HTTPStatus

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="health", description="Health check endpoints")
health_bp = APIBlueprint("health", __name__, url_prefix="/health", abp_tags=[tag])


@health_bp.get("/liveness")
def liveness():
    """Liveness probe - service is alive."""
    return "", HTTPStatus.OK


@health_bp.get("/readiness")
def readiness():
    """Readiness probe with system health details."""
    from ..database import get_connection
    from ..services.process_manager import ProcessManager

    health = {"status": "ok", "components": {}}

    # DB check
    try:
        with get_connection() as conn:
            conn.execute("SELECT 1")
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            health["components"]["database"] = {
                "status": "ok",
                "journal_mode": mode,
            }
    except Exception as e:
        health["status"] = "degraded"
        health["components"]["database"] = {
            "status": "error",
            "error": str(e),
        }

    # Process manager check
    health["components"]["process_manager"] = {
        "status": "ok",
        "active_executions": ProcessManager.get_active_count(),
        "active_execution_ids": ProcessManager.get_active_executions(),
    }

    status_code = 200 if health["status"] == "ok" else 503
    return health, status_code
