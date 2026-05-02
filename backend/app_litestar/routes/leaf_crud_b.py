"""Wave 66 — leaf CRUD batch B (~36 routes).

marketplace + integrations admin + audit + pr_reviews.
Slack slash command webhook is deferred to the subprocess/webhook wave.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from litestar import Router, delete, get, post, put
from litestar.exceptions import (
    ClientException,
    HTTPException,
    NotFoundException,
)
from litestar.params import Parameter

from app.db import integrations as db_integrations
from app.models.common import PaginationQuery
from app.services.audit_log_service import AuditLogService
from app.services.audit_service import AuditService
from app.services.github_service import GitHubService
from app.services.integration_config_service import IntegrationConfigService
from app.services.pr_review_service import PrReviewService

from app.database import (
    add_marketplace_plugin,
    delete_marketplace,
    delete_marketplace_plugin,
    get_all_marketplaces,
    get_marketplace,
    get_marketplace_plugins,
    update_marketplace,
)
from app.database import (
    create_marketplace as db_create_marketplace,
)

logger = logging.getLogger(__name__)


def _result_or_raise(payload: tuple[dict, int]) -> Any:
    """Unwrap (body, status) from Flask service layer; raise for non-2xx."""
    body, status = payload
    if status >= 400:
        if status == 404:
            raise NotFoundException(detail=str(body.get("error") or body))
        raise HTTPException(status_code=status, detail=str(body.get("error") or body))
    return body


# ===========================================================================
# /admin/marketplaces/* (11)
# ===========================================================================


@get("/", sync_to_thread=False)
def list_marketplaces() -> dict[str, Any]:
    return {"marketplaces": get_all_marketplaces()}


@get("/search", sync_to_thread=False)
def search_marketplace_items(
    q: Optional[str] = None,
    type: str = "plugin",
) -> dict[str, Any]:
    from app.services.plugin_deploy_service import DeployService

    query = (q or "").strip().lower()
    item_type = type
    results: list[dict] = []
    for marketplace in get_all_marketplaces():
        try:
            discovered = DeployService.discover_available_plugins_cached(marketplace["id"])
            items_key = "skills" if item_type == "skill" else "plugins"
            for item in discovered.get(items_key, []):
                name = (item.get("name") or "").lower()
                desc = (item.get("description") or "").lower()
                if not query or query in name or query in desc:
                    results.append(
                        {
                            **item,
                            "marketplace_id": marketplace["id"],
                            "marketplace_name": marketplace["name"],
                        }
                    )
        except Exception:
            logger.debug("Skipping unreachable marketplace: %s", marketplace.get("url"))
            continue
    return {"results": results, "total": len(results), "query": query, "type": item_type}


@post("/search/refresh", sync_to_thread=False)
def refresh_marketplace_cache() -> dict[str, Any]:
    from app.services.plugin_deploy_service import DeployService

    DeployService.clear_marketplace_cache()
    return {"message": "Marketplace cache cleared"}


@post("/", status_code=201, sync_to_thread=False)
def create_marketplace(data: dict) -> dict[str, Any]:
    if not data:
        raise ClientException(detail="JSON body required")
    name = data.get("name")
    if not name:
        raise ClientException(detail="name is required")
    url = data.get("url")
    if not url:
        raise ClientException(detail="url is required")
    marketplace_type = data.get("type", "git")
    if marketplace_type == "git" and url.startswith(("https://", "http://")):
        if not GitHubService.validate_github_url_format(url):
            raise ClientException(
                detail=f"Invalid GitHub URL format: {url}. Expected format: https://github.com/owner/repo"
            )
    marketplace_id = db_create_marketplace(
        name=name,
        url=url,
        marketplace_type=marketplace_type,
        is_default=data.get("is_default", False),
    )
    if not marketplace_id:
        raise HTTPException(status_code=500, detail="Failed to create marketplace")
    return {"message": "Marketplace created", "marketplace": get_marketplace(marketplace_id)}


@get("/{marketplace_id:str}", sync_to_thread=False)
def get_marketplace_detail(marketplace_id: str) -> Any:
    marketplace = get_marketplace(marketplace_id)
    if not marketplace:
        raise NotFoundException(detail="Marketplace not found")
    return marketplace


@put("/{marketplace_id:str}", sync_to_thread=False)
def update_marketplace_endpoint(marketplace_id: str, data: dict) -> Any:
    if not data:
        raise ClientException(detail="JSON body required")
    if not update_marketplace(
        marketplace_id,
        name=data.get("name"),
        url=data.get("url"),
        marketplace_type=data.get("type"),
        is_default=data.get("is_default"),
    ):
        raise NotFoundException(detail="Marketplace not found or no changes made")
    return get_marketplace(marketplace_id)


@delete("/{marketplace_id:str}", status_code=200, sync_to_thread=False)
def delete_marketplace_endpoint(marketplace_id: str) -> dict[str, Any]:
    if not delete_marketplace(marketplace_id):
        raise NotFoundException(detail="Marketplace not found")
    return {"message": "Marketplace deleted"}


@get("/{marketplace_id:str}/plugins", sync_to_thread=False)
def list_marketplace_plugins(marketplace_id: str) -> dict[str, Any]:
    return {"plugins": get_marketplace_plugins(marketplace_id)}


@get("/{marketplace_id:str}/plugins/available", sync_to_thread=False)
def discover_marketplace_plugins(marketplace_id: str) -> Any:
    from app.services.plugin_deploy_service import DeployService

    try:
        return DeployService.discover_available_plugins(marketplace_id)
    except (ValueError, RuntimeError) as e:
        raise ClientException(detail=str(e)) from e


@post("/{marketplace_id:str}/plugins", status_code=201, sync_to_thread=False)
def install_plugin(marketplace_id: str, data: dict) -> dict[str, Any]:
    if not data:
        raise ClientException(detail="JSON body required")
    remote_name = data.get("remote_name")
    if not remote_name:
        raise ClientException(detail="remote_name is required")
    plugin_id = add_marketplace_plugin(
        marketplace_id=marketplace_id,
        remote_name=remote_name,
        plugin_id=data.get("plugin_id"),
        version=data.get("version"),
    )
    if not plugin_id:
        raise HTTPException(status_code=500, detail="Failed to install plugin")
    plugins = get_marketplace_plugins(marketplace_id)
    plugin = next((p for p in plugins if p["id"] == plugin_id), None)
    return {"message": "Plugin installed", "plugin": plugin}


@delete("/{marketplace_id:str}/plugins/{plugin_id:str}", status_code=200, sync_to_thread=False)
def uninstall_plugin(marketplace_id: str, plugin_id: str) -> dict[str, Any]:
    del marketplace_id
    if not delete_marketplace_plugin(plugin_id):
        raise NotFoundException(detail="Plugin not found")
    return {"message": "Plugin uninstalled"}


marketplace_router = Router(
    path="/admin/marketplaces",
    route_handlers=[
        list_marketplaces,
        search_marketplace_items,
        refresh_marketplace_cache,
        create_marketplace,
        get_marketplace_detail,
        update_marketplace_endpoint,
        delete_marketplace_endpoint,
        list_marketplace_plugins,
        discover_marketplace_plugins,
        install_plugin,
        uninstall_plugin,
    ],
)


# ===========================================================================
# /admin/integrations/* + /admin/triggers/{id}/integrations (8)
# ===========================================================================


@post("/integrations", status_code=201, sync_to_thread=False)
def create_integration(data: dict) -> Any:
    if not data:
        raise ClientException(detail="JSON body required")
    from app.models.integration import IntegrationCreate

    try:
        body = IntegrationCreate(**data)
        integration_id = IntegrationConfigService.create_integration(body)
    except ValueError as e:
        raise ClientException(detail=str(e)) from e
    return db_integrations.get_integration(integration_id)


@get("/integrations", sync_to_thread=False)
def list_integrations(
    type: Optional[str] = None,
    trigger_id: Optional[str] = None,
) -> list[dict]:
    return db_integrations.list_integrations(integration_type=type, trigger_id=trigger_id)


@get("/integrations/{integration_id:str}", sync_to_thread=False)
def get_integration(integration_id: str) -> Any:
    integration = db_integrations.get_integration(integration_id)
    if not integration:
        raise NotFoundException(detail="Integration not found")
    return integration


@put("/integrations/{integration_id:str}", sync_to_thread=False)
def update_integration(integration_id: str, data: dict) -> Any:
    from app.models.integration import IntegrationUpdate

    body = IntegrationUpdate(**(data or {}))
    if not db_integrations.update_integration(
        integration_id,
        name=body.name,
        config=body.config,
        trigger_id=body.trigger_id,
        enabled=body.enabled,
    ):
        raise NotFoundException(detail="Integration not found")
    AuditLogService.log(
        action="integration.update",
        entity_type="integration",
        entity_id=integration_id,
        outcome="updated",
    )
    return db_integrations.get_integration(integration_id)


@delete("/integrations/{integration_id:str}", status_code=200, sync_to_thread=False)
def delete_integration(integration_id: str) -> dict[str, Any]:
    if not db_integrations.delete_integration(integration_id):
        raise NotFoundException(detail="Integration not found")
    AuditLogService.log(
        action="integration.delete",
        entity_type="integration",
        entity_id=integration_id,
        outcome="deleted",
    )
    return {"status": "deleted"}


@post("/integrations/{integration_id:str}/test", sync_to_thread=False)
def test_integration(integration_id: str) -> dict[str, Any]:
    success, message = IntegrationConfigService.test_integration(integration_id)
    if not success:
        raise HTTPException(
            status_code=400, detail={"success": False, "message": message}
        )
    return {"success": True, "message": message}


@get("/triggers/{trigger_id:str}/integrations", sync_to_thread=False)
def list_trigger_integrations(trigger_id: str) -> list[dict]:
    return db_integrations.list_integrations_for_trigger(trigger_id)


@get("/integrations/slack/status", sync_to_thread=False)
def get_slack_status() -> dict[str, Any]:
    results = db_integrations.list_integrations(integration_type="slack")
    integration = next((r for r in results if r.get("enabled")), results[0] if results else None)
    if not integration:
        return {"connected": False, "id": None, "name": None}
    config = integration.get("config") or {}
    token = config.get("token") or config.get("bot_token") or ""
    return {
        "id": integration["id"],
        "name": integration.get("name"),
        "connected": bool(token),
    }


integrations_router = Router(
    path="/admin",
    route_handlers=[
        create_integration,
        list_integrations,
        get_integration,
        update_integration,
        delete_integration,
        test_integration,
        list_trigger_integrations,
        get_slack_status,
    ],
)


# ===========================================================================
# /api/audit/* (8)
# ===========================================================================


@get("/history", sync_to_thread=False)
def audit_history(
    limit: int = 50,
    offset: int = 0,
    project_path: str = "",
    trigger_id: str = "",
) -> Any:
    return _result_or_raise(
        AuditService.get_history(
            limit=limit, offset=offset, project_path=project_path, trigger_id=trigger_id
        )
    )


@get("/stats", sync_to_thread=False)
def audit_stats(project_path: str = "", trigger_id: str = "") -> Any:
    return _result_or_raise(
        AuditService.get_stats(project_path=project_path, trigger_id=trigger_id)
    )


@get("/projects", sync_to_thread=False)
def audit_projects() -> Any:
    return _result_or_raise(AuditService.get_projects())


@get("/{audit_id:str}", sync_to_thread=False)
def audit_detail(audit_id: str) -> Any:
    return _result_or_raise(AuditService.get_detail(audit_id))


@post("/", sync_to_thread=False)
def add_audit(data: dict) -> Any:
    if not data:
        raise ClientException(detail="JSON body required")
    return _result_or_raise(AuditService.add_audit(data))


@get("/reports/{audit_week:str}", sync_to_thread=False)
def audit_weekly_report(audit_week: str) -> Any:
    return _result_or_raise(AuditService.get_weekly_report(audit_week))


@get("/events", sync_to_thread=False)
def audit_events(limit: int = 100) -> dict[str, Any]:
    capped = min(limit, 500)
    events = AuditLogService.get_recent_events(limit=capped)
    return {"events": events, "total": len(events)}


@get("/events/persistent", sync_to_thread=False)
def audit_events_persistent(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    actor: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    from app.db.audit_events import count_audit_events, query_audit_events

    capped_limit = min(limit, 1000)
    capped_offset = max(offset, 0)
    events = query_audit_events(
        entity_type=entity_type,
        entity_id=entity_id,
        actor=actor,
        start_date=start_date,
        end_date=end_date,
        limit=capped_limit,
        offset=capped_offset,
    )
    total = count_audit_events(
        entity_type=entity_type,
        entity_id=entity_id,
        actor=actor,
        start_date=start_date,
        end_date=end_date,
    )
    return {"events": events, "total": total}


audit_router = Router(
    path="/api/audit",
    route_handlers=[
        audit_history,
        audit_stats,
        audit_projects,
        audit_detail,
        add_audit,
        audit_weekly_report,
        audit_events,
        audit_events_persistent,
    ],
)


# ===========================================================================
# /api/pr-reviews/* (8)
# ===========================================================================


@get("/", sync_to_thread=False)
def list_pr_reviews(
    limit: int = 50,
    offset: int = 0,
    pr_status: Optional[str] = None,
    review_status: Optional[str] = None,
) -> Any:
    return _result_or_raise(
        PrReviewService.list_reviews(
            limit=limit, offset=offset, pr_status=pr_status, review_status=review_status
        )
    )


@get("/stats", sync_to_thread=False)
def pr_review_stats() -> Any:
    return _result_or_raise(PrReviewService.get_stats())


@get("/learning-loop", sync_to_thread=False)
def pr_review_learning_loop() -> Any:
    return _result_or_raise(PrReviewService.get_learning_loop())


@get("/history", sync_to_thread=False)
def pr_review_history(days: int = 30) -> Any:
    return _result_or_raise(PrReviewService.get_history(days=days))


@get("/{review_id:int}", sync_to_thread=False)
def get_pr_review(review_id: int) -> Any:
    return _result_or_raise(PrReviewService.get_review(review_id))


@post("/", sync_to_thread=False)
def create_pr_review(data: dict) -> Any:
    if not data:
        raise ClientException(detail="JSON body required")
    return _result_or_raise(PrReviewService.create_review(data))


@put("/{review_id:int}", sync_to_thread=False)
def update_pr_review(review_id: int, data: dict) -> Any:
    if not data:
        raise ClientException(detail="JSON body required")
    return _result_or_raise(PrReviewService.update_review(review_id, data))


@delete("/{review_id:int}", status_code=200, sync_to_thread=False)
def delete_pr_review(review_id: int) -> Any:
    return _result_or_raise(PrReviewService.delete_review(review_id))


pr_reviews_router = Router(
    path="/api/pr-reviews",
    route_handlers=[
        list_pr_reviews,
        pr_review_stats,
        pr_review_learning_loop,
        pr_review_history,
        get_pr_review,
        create_pr_review,
        update_pr_review,
        delete_pr_review,
    ],
)
