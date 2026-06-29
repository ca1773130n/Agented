"""Wave 67 — leaf CRUD batch C (~22 routes).

products + analytics + findings + config_export.
"""

from __future__ import annotations

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
from app_litestar.route_helpers import MAX_LIST_LIMIT, clamp_limit

# 07.H3 — explicit field allowlist for finding writers (no mass-assignment).
_FINDING_CREATE_FIELDS = (
    "title",
    "description",
    "severity",
    "bot_id",
    "file_ref",
    "owner",
    "execution_id",
)
# update_finding only honors status/owner — allowlist mirrors the writer.
_FINDING_UPDATE_FIELDS = ("status", "owner")

# 07.M4 — string length caps for the product creator.
_NAME_MAX_LEN = 255
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
    # Admins see ALL products (oversight) — never hidden by a blank/legacy
    # user_id. Everyone else is scoped to their own; a non-admin with NO user_id
    # sees NOTHING (never the unscoped list — closes a latent leak for malformed
    # api-key rows).
    if caller.role == "admin":
        return {
            "products": get_all_products(limit=limit, offset=offset),
            "total_count": count_products(),
        }
    user_id = caller.user_id or current_user_var.get()
    products = get_products_for_user(user_id, limit=limit, offset=offset) if user_id else []
    return {"products": products, "total_count": len(products)}


@post("/", status_code=201, sync_to_thread=False)
def create_product(data: dict, caller: Caller) -> dict[str, Any]:
    if not data:
        raise ClientException(detail="JSON body required")
    name = (data.get("name") or "").strip()
    if not name:
        raise ClientException(detail="name is required")
    if len(name) > _NAME_MAX_LEN:  # 07.M4 — bound name length
        raise ClientException(detail=f"name must be at most {_NAME_MAX_LEN} characters")
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
    limit: Optional[int] = None,
    offset: int = 0,
) -> dict[str, Any]:
    items = list_findings(status=status, bot_id=bot_id, owner=owner)
    # 07.M2 — list_findings has no limit param; slice at the route layer so a
    # huge findings table can't flood one response.
    capped = clamp_limit(limit, default=MAX_LIST_LIMIT)
    start = max(offset, 0)
    return {"findings": items[start : start + capped]}


@post("/", status_code=201, sync_to_thread=False)
def create_finding_route(data: dict) -> Any:
    if not data:
        raise ClientException(detail="JSON body required")
    # 07.H3 — forward only allowlisted fields to the writer (no mass-assignment).
    payload = {k: data[k] for k in _FINDING_CREATE_FIELDS if k in data}
    finding_id = create_finding(payload)
    finding = get_finding(finding_id)
    if not finding:
        raise HTTPException(status_code=500, detail="Failed to create finding")
    return finding


@patch("/{finding_id:str}", sync_to_thread=False)
def update_finding_route(finding_id: str, data: dict) -> Any:
    if not get_finding(finding_id):
        raise NotFoundException(detail="Finding not found")
    # 07.H3 — allowlist update fields (writer only honors status/owner anyway).
    updates = {k: (data or {})[k] for k in _FINDING_UPDATE_FIELDS if k in (data or {})}
    if not update_finding(finding_id, updates):
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
