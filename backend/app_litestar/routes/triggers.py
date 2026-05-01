"""Trigger management routes (track A, wave 52).

Full /admin/triggers/* namespace ported. Streaming /generate/stream
uses Litestar's Stream response.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from litestar import MediaType, Router, delete, get, post, put
from litestar.exceptions import (
    ClientException,
    HTTPException,
    NotFoundException,
)
from litestar.response import Stream
from msgspec import Struct

from app.db.owned_entities import get_for_user
from app.db.triggers import get_trigger
from app.services.budget_service import BudgetService
from app.services.execution_service import ExecutionService
from app.services.trigger_service import TriggerService

from ..auth import Caller, require_role


def _result_or_raise(payload: tuple[dict, int]) -> dict:
    """Unwrap a (body, status) tuple from a service. Raise on non-2xx."""
    body, status = payload
    if status >= 400:
        raise HTTPException(status_code=status, detail=body)
    return body


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@get(
    "/",
    dependencies={"authorized": require_role("viewer", "operator", "editor", "admin")},
    sync_to_thread=False,
)
def list_triggers(
    authorized: Caller, limit: Optional[int] = None, offset: Optional[int] = None
) -> dict[str, Any]:
    """List triggers, scoped by user when authenticated."""
    if authorized.user_id:
        rows = get_for_user(
            "triggers", authorized.user_id, limit=limit, offset=offset or 0
        )
        return {"triggers": rows, "total_count": len(rows)}
    body, _ = TriggerService.list_triggers(limit=limit, offset=offset or 0)
    return body


@post(
    "/",
    dependencies={"authorized": require_role("editor", "admin")},
    sync_to_thread=False,
)
def create_trigger(data: dict, authorized: Caller) -> dict[str, Any]:
    del authorized
    if not data:
        raise ClientException(detail="JSON body required")
    return _result_or_raise(TriggerService.create_trigger(data))


@get(
    "/{trigger_id:str}",
    dependencies={"authorized": require_role("viewer", "operator", "editor", "admin")},
    sync_to_thread=False,
)
def get_trigger_detail(trigger_id: str, authorized: Caller) -> dict[str, Any]:
    del authorized
    return _result_or_raise(TriggerService.get_trigger_detail(trigger_id))


@put(
    "/{trigger_id:str}",
    dependencies={"authorized": require_role("editor", "admin")},
    sync_to_thread=False,
)
def update_trigger(trigger_id: str, data: dict, authorized: Caller) -> dict[str, Any]:
    del authorized
    if not data:
        raise ClientException(detail="JSON body required")
    return _result_or_raise(TriggerService.update_trigger(trigger_id, data))


@delete(
    "/{trigger_id:str}",
    dependencies={"authorized": require_role("editor", "admin")},
    status_code=200,
    sync_to_thread=False,
)
def delete_trigger(trigger_id: str, authorized: Caller) -> dict[str, Any]:
    del authorized
    return _result_or_raise(TriggerService.delete_trigger(trigger_id))


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


@get(
    "/{trigger_id:str}/paths",
    dependencies={"authorized": require_role("viewer", "operator", "editor", "admin")},
    sync_to_thread=False,
)
def list_trigger_paths(
    trigger_id: str,
    authorized: Caller,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
) -> dict[str, Any]:
    del authorized
    return _result_or_raise(
        TriggerService.list_paths(trigger_id, limit=limit, offset=offset or 0)
    )


@post(
    "/{trigger_id:str}/paths",
    dependencies={"authorized": require_role("editor", "admin")},
    sync_to_thread=False,
)
def add_trigger_path(
    trigger_id: str, data: dict, authorized: Caller
) -> dict[str, Any]:
    del authorized
    if not data:
        raise ClientException(detail="JSON body required")
    return _result_or_raise(TriggerService.add_path(trigger_id, data))


@delete(
    "/{trigger_id:str}/paths",
    dependencies={"authorized": require_role("editor", "admin")},
    status_code=200,
    sync_to_thread=False,
)
def remove_trigger_path(
    trigger_id: str, data: dict, authorized: Caller
) -> dict[str, Any]:
    del authorized
    if not data:
        raise ClientException(detail="JSON body required")
    return _result_or_raise(TriggerService.remove_path(trigger_id, data))


# ---------------------------------------------------------------------------
# Project assignments
# ---------------------------------------------------------------------------


class TriggerProjectBody(Struct):
    project_id: str = ""


@post(
    "/{trigger_id:str}/projects",
    dependencies={"authorized": require_role("editor", "admin")},
    sync_to_thread=False,
)
def add_trigger_project(
    trigger_id: str, data: TriggerProjectBody, authorized: Caller
) -> dict[str, Any]:
    del authorized
    if not data.project_id:
        raise ClientException(detail="project_id is required")
    return _result_or_raise(TriggerService.create_project(trigger_id, data.project_id))


@delete(
    "/{trigger_id:str}/projects/{project_id:str}",
    dependencies={"authorized": require_role("editor", "admin")},
    status_code=200,
    sync_to_thread=False,
)
def remove_trigger_project(
    trigger_id: str, project_id: str, authorized: Caller
) -> dict[str, Any]:
    del authorized
    return _result_or_raise(TriggerService.remove_project(trigger_id, project_id))


# ---------------------------------------------------------------------------
# Auto-resolve / status / run
# ---------------------------------------------------------------------------


class AutoResolveBody(Struct):
    auto_resolve: bool = False


@put(
    "/{trigger_id:str}/auto-resolve",
    dependencies={"authorized": require_role("editor", "admin")},
    sync_to_thread=False,
)
def set_auto_resolve(
    trigger_id: str, data: AutoResolveBody, authorized: Caller
) -> dict[str, Any]:
    del authorized
    return _result_or_raise(
        TriggerService.update_auto_resolve(trigger_id, bool(data.auto_resolve))
    )


@get(
    "/{trigger_id:str}/status",
    dependencies={"authorized": require_role("viewer", "operator", "editor", "admin")},
    sync_to_thread=False,
)
def get_trigger_status(trigger_id: str, authorized: Caller) -> dict[str, Any]:
    del authorized
    trigger = get_trigger(trigger_id)
    if not trigger:
        raise NotFoundException(detail="Trigger not found")
    return ExecutionService.get_status(trigger_id)


class RunTriggerBody(Struct):
    message: str = ""


@post(
    "/{trigger_id:str}/run",
    dependencies={"authorized": require_role("operator", "editor", "admin")},
    sync_to_thread=False,
)
def run_trigger(
    trigger_id: str, data: RunTriggerBody, authorized: Caller
) -> dict[str, Any]:
    del authorized
    return _result_or_raise(TriggerService.run(trigger_id, data.message))


# ---------------------------------------------------------------------------
# Prompt previews / history / rollback
# ---------------------------------------------------------------------------


@post(
    "/{trigger_id:str}/preview-prompt",
    dependencies={"authorized": require_role("viewer", "operator", "editor", "admin")},
    sync_to_thread=False,
)
def preview_trigger_prompt(
    trigger_id: str, data: dict, authorized: Caller
) -> dict[str, Any]:
    del authorized
    return _result_or_raise(TriggerService.preview_prompt(trigger_id, data or {}))


@get(
    "/{trigger_id:str}/prompt-history",
    dependencies={"authorized": require_role("viewer", "operator", "editor", "admin")},
    sync_to_thread=False,
)
def get_prompt_history(trigger_id: str, authorized: Caller) -> dict[str, Any]:
    del authorized
    from app.database import get_prompt_template_history

    if not get_trigger(trigger_id):
        raise NotFoundException(detail="Trigger not found")
    return {"history": get_prompt_template_history(trigger_id, limit=50)}


class RollbackBody(Struct):
    version_id: int = 0


@post(
    "/{trigger_id:str}/rollback-prompt",
    dependencies={"authorized": require_role("editor", "admin")},
    sync_to_thread=False,
)
def rollback_prompt(
    trigger_id: str, data: RollbackBody, authorized: Caller
) -> dict[str, Any]:
    del authorized
    if not data.version_id:
        raise ClientException(detail="version_id is required")
    return _result_or_raise(
        TriggerService.rollback_prompt_template(trigger_id, int(data.version_id))
    )


@post(
    "/{trigger_id:str}/preview-prompt-full",
    dependencies={"authorized": require_role("viewer", "operator", "editor", "admin")},
    sync_to_thread=False,
)
def preview_trigger_prompt_full(
    trigger_id: str, data: dict, authorized: Caller
) -> dict[str, Any]:
    del authorized
    return _result_or_raise(
        TriggerService.preview_prompt_full(trigger_id, data or {})
    )


# ---------------------------------------------------------------------------
# Cron validation
# ---------------------------------------------------------------------------


class CronBody(Struct):
    expression: str = ""
    timezone: Optional[str] = None


@post(
    "/validate-cron",
    dependencies={"authorized": require_role("viewer", "operator", "editor", "admin")},
    sync_to_thread=False,
)
def validate_cron_expression(
    data: CronBody, authorized: Caller
) -> dict[str, Any]:
    del authorized
    if not data.expression:
        raise ClientException(detail="Missing 'expression' field")

    try:
        import pytz
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        raise HTTPException(
            status_code=503, detail="APScheduler not installed"
        ) from None

    from app.utils.timezone import get_local_timezone

    timezone_str = data.timezone or get_local_timezone()
    try:
        tz = pytz.timezone(timezone_str)
    except Exception:
        raise ClientException(detail=f"Unknown timezone: {timezone_str}") from None

    try:
        trigger = CronTrigger.from_crontab(data.expression, timezone=tz)
        next_fires = []
        fire_time = datetime.now(tz)
        for _ in range(5):
            fire_time = trigger.get_next_fire_time(None, fire_time)
            if fire_time:
                next_fires.append(fire_time.isoformat())
                fire_time = fire_time + timedelta(seconds=1)
            else:
                break
        return {
            "valid": True,
            "expression": data.expression,
            "timezone": timezone_str,
            "next_fires": next_fires,
        }
    except (ValueError, TypeError) as e:
        raise ClientException(detail=f"Invalid cron expression: {e}") from None


# ---------------------------------------------------------------------------
# Dry-run / cost estimate
# ---------------------------------------------------------------------------


@post(
    "/{trigger_id:str}/dry-run",
    dependencies={"authorized": require_role("viewer", "operator", "editor", "admin")},
    sync_to_thread=False,
)
def dry_run_trigger(
    trigger_id: str, data: dict, authorized: Caller
) -> dict[str, Any]:
    del authorized
    return _result_or_raise(TriggerService.dry_run(trigger_id, data or {}))


@post(
    "/{trigger_id:str}/estimate-cost",
    dependencies={"authorized": require_role("viewer", "operator", "editor", "admin")},
    sync_to_thread=False,
)
def estimate_trigger_cost(
    trigger_id: str, data: dict, authorized: Caller
) -> dict[str, Any]:
    del authorized
    preview, status = TriggerService.preview_prompt(trigger_id, data or {})
    if status >= 400:
        raise HTTPException(status_code=status, detail=preview)
    prompt = preview["rendered_prompt"]
    trigger = get_trigger(trigger_id)
    model = trigger.get("model") or "claude-sonnet-4"
    estimate = BudgetService.estimate_cost(prompt, model, "trigger", trigger_id)
    return {"trigger_id": trigger_id, "model": model, "estimate": estimate}


# ---------------------------------------------------------------------------
# AI-generated trigger (SSE stream)
# ---------------------------------------------------------------------------


class GenerateStreamBody(Struct):
    description: str = ""


@post(
    "/generate/stream",
    dependencies={"authorized": require_role("editor", "admin")},
    media_type=MediaType.TEXT,
    sync_to_thread=False,
)
def generate_trigger_stream(
    data: GenerateStreamBody, authorized: Caller
) -> Stream:
    """Server-sent events from TriggerGenerationService."""
    del authorized
    from app.services.trigger_generation_service import TriggerGenerationService

    description = data.description.strip()
    if len(description) < 10:
        raise ClientException(detail="Description must be at least 10 characters")

    return Stream(
        TriggerGenerationService.generate_streaming(description),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


triggers_router = Router(
    path="/admin/triggers",
    route_handlers=[
        list_triggers,
        create_trigger,
        get_trigger_detail,
        update_trigger,
        delete_trigger,
        list_trigger_paths,
        add_trigger_path,
        remove_trigger_path,
        add_trigger_project,
        remove_trigger_project,
        set_auto_resolve,
        get_trigger_status,
        run_trigger,
        preview_trigger_prompt,
        get_prompt_history,
        rollback_prompt,
        preview_trigger_prompt_full,
        validate_cron_expression,
        dry_run_trigger,
        estimate_trigger_cost,
        generate_trigger_stream,
    ],
)


