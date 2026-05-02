"""Wave 67 — leaf CRUD batch C (~22 routes).

products + analytics + findings + report_digests + config_export.
"""

from __future__ import annotations

import random
import string
from typing import Any, Optional

from litestar import MediaType, Response, Router, delete, get, patch, post, put
from litestar.exceptions import (
    ClientException,
    HTTPException,
    NotFoundException,
)

from app.database import (
    count_products,
    delete_product,
    get_all_products,
    get_product,
    get_product_detail,
    update_product,
)
from app.database import (
    create_product as db_create_product,
)
from app.db.findings import (
    create_finding,
    delete_finding,
    get_finding,
    list_findings,
    update_finding,
)
from app.db.products import get_products_for_user
from app.logging_config import current_user_var
from app.services.analytics_service import AnalyticsService
from app.services.config_export_service import (
    export_all_triggers,
    export_trigger,
    import_trigger,
    validate_config,
)

from ..auth import Caller


# ===========================================================================
# /admin/products/* (5)
# ===========================================================================


@get("/", sync_to_thread=False)
def list_products(caller: Caller, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    user_id = caller.user_id or current_user_var.get()
    if user_id:
        products = get_products_for_user(user_id, limit=limit, offset=offset)
        return {"products": products, "total_count": len(products)}
    total_count = count_products()
    products = get_all_products(limit=limit, offset=offset)
    return {"products": products, "total_count": total_count}


@post("/", status_code=201, sync_to_thread=False)
def create_product(data: dict, caller: Caller) -> dict[str, Any]:
    if not data:
        raise ClientException(detail="JSON body required")
    name = (data.get("name") or "").strip()
    if not name:
        raise ClientException(detail="name is required")
    user_id = caller.user_id or current_user_var.get()
    product_id = db_create_product(
        name=name,
        description=data.get("description", ""),
        status=data.get("status") or "active",
        owner_team_id=data.get("owner_team_id"),
        user_id=user_id,
    )
    if not product_id:
        raise HTTPException(status_code=500, detail="Failed to create product")
    return {"message": "Product created", "product": get_product(product_id)}


@get("/{product_id:str}", sync_to_thread=False)
def get_product_detail_endpoint(product_id: str) -> Any:
    product = get_product_detail(product_id)
    if not product:
        raise NotFoundException(detail="Product not found")
    return product


@put("/{product_id:str}", sync_to_thread=False)
def update_product_endpoint(product_id: str, data: dict) -> Any:
    if not update_product(
        product_id,
        name=data.get("name"),
        description=data.get("description"),
        status=data.get("status"),
        owner_team_id=data.get("owner_team_id"),
    ):
        raise NotFoundException(detail="Product not found or no changes made")
    return get_product(product_id)


@delete("/{product_id:str}", status_code=200, sync_to_thread=False)
def delete_product_endpoint(product_id: str) -> dict[str, Any]:
    if not delete_product(product_id):
        raise NotFoundException(detail="Product not found")
    return {"message": "Product deleted"}


products_router = Router(
    path="/admin/products",
    route_handlers=[
        list_products,
        create_product,
        get_product_detail_endpoint,
        update_product_endpoint,
        delete_product_endpoint,
    ],
)


# ===========================================================================
# /admin/analytics/* (4)
# ===========================================================================


def _validate_group_by(group_by: str) -> None:
    if group_by not in ("day", "week", "month"):
        raise ClientException(detail="group_by must be 'day', 'week', or 'month'")


@get("/cost", sync_to_thread=False)
def cost_analytics(
    group_by: str = "day",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    entity_type: Optional[str] = None,
) -> Any:
    _validate_group_by(group_by)
    return AnalyticsService.get_cost_summary(
        entity_type=entity_type,
        group_by=group_by,
        start_date=start_date,
        end_date=end_date,
    )


@get("/executions", sync_to_thread=False)
def execution_analytics(
    group_by: str = "day",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    trigger_id: Optional[str] = None,
    team_id: Optional[str] = None,
) -> Any:
    _validate_group_by(group_by)
    return AnalyticsService.get_execution_summary(
        group_by=group_by,
        start_date=start_date,
        end_date=end_date,
        trigger_id=trigger_id,
        team_id=team_id,
    )


@get("/effectiveness", sync_to_thread=False)
def effectiveness_analytics(
    trigger_id: Optional[str] = None,
    group_by: str = "day",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Any:
    _validate_group_by(group_by)
    return AnalyticsService.get_effectiveness(
        trigger_id=trigger_id,
        group_by=group_by,
        start_date=start_date,
        end_date=end_date,
    )


@get("/team-leaderboard", sync_to_thread=False)
def team_leaderboard() -> dict[str, list]:
    return {"teams": []}


analytics_router = Router(
    path="/admin/analytics",
    route_handlers=[
        cost_analytics,
        execution_analytics,
        effectiveness_analytics,
        team_leaderboard,
    ],
)


# ===========================================================================
# /api/findings/* (4)
# ===========================================================================


@get("/", sync_to_thread=False)
def list_findings_route(
    status: Optional[str] = None,
    bot_id: Optional[str] = None,
    owner: Optional[str] = None,
) -> dict[str, Any]:
    items = list_findings(status=status, bot_id=bot_id, owner=owner)
    return {"findings": items}


@post("/", status_code=201, sync_to_thread=False)
def create_finding_route(data: dict) -> Any:
    if not data:
        raise ClientException(detail="JSON body required")
    finding_id = create_finding(data)
    finding = get_finding(finding_id)
    if not finding:
        raise HTTPException(status_code=500, detail="Failed to create finding")
    return finding


@patch("/{finding_id:str}", sync_to_thread=False)
def update_finding_route(finding_id: str, data: dict) -> Any:
    if not get_finding(finding_id):
        raise NotFoundException(detail="Finding not found")
    if not update_finding(finding_id, data or {}):
        raise ClientException(detail="No changes applied")
    return get_finding(finding_id)


@delete("/{finding_id:str}", status_code=204, sync_to_thread=False)
def delete_finding_route(finding_id: str) -> None:
    if not delete_finding(finding_id):
        raise NotFoundException(detail="Finding not found")


findings_router = Router(
    path="/api/findings",
    route_handlers=[
        list_findings_route,
        create_finding_route,
        update_finding_route,
        delete_finding_route,
    ],
)


# ===========================================================================
# /admin/reports/digests/* (3) — stubs
# ===========================================================================


@get("/digests", sync_to_thread=False)
def list_digests() -> dict[str, list]:
    return {"digests": []}


@post("/digests", status_code=201, sync_to_thread=False)
def create_digest(data: dict) -> dict[str, Any]:
    if not data:
        raise ClientException(detail="JSON body required")
    team_name = (data.get("team_name") or "").strip()
    if not team_name:
        raise ClientException(detail="team_name is required")
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return {
        "team_id": f"team-{suffix}",
        "team_name": team_name,
        "frequency": data.get("frequency", "weekly"),
        "channel": data.get("channel", "email"),
        "recipients": data.get("recipients", ""),
        "enabled": data.get("enabled", False),
        "last_generated": None,
    }


@put("/digests/{team_id:str}", sync_to_thread=False)
def update_digest(team_id: str, data: dict) -> dict[str, Any]:
    del team_id, data
    return {"ok": True}


report_digests_router = Router(
    path="/admin/reports",
    route_handlers=[list_digests, create_digest, update_digest],
)


# ===========================================================================
# Trigger config export/import (4)
# ===========================================================================


@get("/triggers/{trigger_id:str}/export", sync_to_thread=False)
def export_trigger_endpoint(trigger_id: str, format: str = "yaml") -> Response:
    if format not in ("yaml", "json"):
        raise ClientException(detail="format must be 'yaml' or 'json'")
    result = export_trigger(trigger_id, format=format)
    if result is None:
        raise NotFoundException(detail="Trigger not found")
    media_type = MediaType.JSON if format == "json" else "text/yaml"
    return Response(content=result, media_type=media_type)


@post("/triggers/import", sync_to_thread=False)
def import_trigger_endpoint(data: dict) -> dict[str, Any]:
    if not data:
        raise ClientException(detail="JSON body required")
    fmt = data.get("format")
    if fmt not in ("yaml", "json"):
        raise ClientException(detail="format must be 'yaml' or 'json'")
    config_str = data.get("config")
    if not config_str:
        raise ClientException(detail="config is required")
    try:
        trigger_id, status = import_trigger(
            config_str=config_str, format=fmt, upsert=data.get("upsert", False)
        )
    except ValueError as e:
        raise ClientException(detail=str(e)) from e
    from app.db import get_trigger as _get_trigger

    trigger = _get_trigger(trigger_id)
    name = trigger["name"] if trigger else ""
    return {
        "trigger_id": trigger_id,
        "name": name,
        "status": status,
        "message": f"Trigger {status} successfully",
    }


@post("/triggers/validate-config", sync_to_thread=False)
def validate_trigger_config(data: dict) -> dict[str, Any]:
    if not data:
        raise ClientException(detail="JSON body required")
    fmt = data.get("format")
    if fmt not in ("yaml", "json"):
        raise ClientException(detail="format must be 'yaml' or 'json'")
    valid, error = validate_config(data.get("config", ""), format=fmt)
    return {"valid": valid, "error": error}


@get("/triggers/export-all", sync_to_thread=False)
def export_all_triggers_endpoint(format: str = "yaml") -> Response:
    if format not in ("yaml", "json"):
        raise ClientException(detail="format must be 'yaml' or 'json'")
    result = export_all_triggers(format=format)
    media_type = MediaType.JSON if format == "json" else "text/yaml"
    return Response(content=result, media_type=media_type)


config_export_router = Router(
    path="/admin",
    route_handlers=[
        export_trigger_endpoint,
        import_trigger_endpoint,
        validate_trigger_config,
        export_all_triggers_endpoint,
    ],
)
