"""Admin-side misc routes (track A, wave 49).

Batches execution_search, rotation, specialized_bots — six small
read-only admin routes with no streaming.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from litestar import Router, get

# ---------------------------------------------------------------------------
# /admin/execution-search
# ---------------------------------------------------------------------------


@get("/admin/execution-search", sync_to_thread=False)
def execution_search(
    q: str,
    limit: int = 20,
    trigger_id: Optional[str] = None,
    status: Optional[str] = None,
    started_after: Optional[str] = None,
    started_before: Optional[str] = None,
    bot_name: Optional[str] = None,
) -> dict[str, Any]:
    from app.services.execution_search_service import ExecutionSearchService

    results = ExecutionSearchService.search(
        query=q,
        limit=limit,
        trigger_id=trigger_id,
        status=status,
        started_after=started_after,
        started_before=started_before,
        bot_name=bot_name,
    )
    return {"results": results, "total": len(results), "query": q}


@get("/admin/execution-search/stats", sync_to_thread=False)
def execution_search_stats() -> dict[str, Any]:
    from app.services.execution_search_service import ExecutionSearchService

    return ExecutionSearchService.get_search_stats()


# ---------------------------------------------------------------------------
# /admin/rotation/*
# ---------------------------------------------------------------------------


@get("/admin/rotation/status", sync_to_thread=False)
def rotation_status() -> dict[str, Any]:
    from app.services.execution_log_service import ExecutionLogService
    from app.services.process_manager import ProcessManager
    from app.services.rotation_evaluator import RotationEvaluator

    sessions = []
    for eid in ProcessManager.get_active_executions():
        execution = ExecutionLogService.get_execution(eid)
        if execution:
            sessions.append(
                {
                    "execution_id": eid,
                    "account_id": execution.get("account_id"),
                    "trigger_id": execution.get("trigger_id"),
                    "backend_type": execution.get("backend_type"),
                    "started_at": execution.get("started_at"),
                }
            )
    return {"sessions": sessions, "evaluator": RotationEvaluator.get_evaluator_status()}


@get("/admin/rotation/history", sync_to_thread=False)
def rotation_history(
    execution_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    from app.db.rotations import (
        count_rotation_events,
        get_rotation_events_enriched,
        get_rotation_events_enriched_by_execution,
    )

    if execution_id:
        events = get_rotation_events_enriched_by_execution(execution_id)
        total_count = len(events)
    else:
        events = get_rotation_events_enriched(limit, offset=offset)
        total_count = count_rotation_events()
    return {"events": events, "total_count": total_count}


# ---------------------------------------------------------------------------
# /admin/specialized-bots/*
# ---------------------------------------------------------------------------


def _skill_slug(prompt_template: str) -> str:
    command = prompt_template.split()[0] if prompt_template else ""
    return command.lstrip("/")


@get("/admin/specialized-bots/status", sync_to_thread=False)
def specialized_bot_status() -> dict[str, Any]:
    from app.db.triggers import PREDEFINED_TRIGGERS, get_trigger

    statuses = []
    for cfg in PREDEFINED_TRIGGERS:
        bot_id = cfg["id"]
        trigger = get_trigger(bot_id)
        slug = _skill_slug(cfg["prompt_template"])
        skill_path = os.path.join(".claude", "skills", slug, "INSTRUCTIONS.md")
        skill_file_exists = os.path.isfile(skill_path)
        trigger_exists = trigger is not None
        statuses.append(
            {
                "id": bot_id,
                "name": cfg["name"],
                "trigger_exists": trigger_exists,
                "skill_file_exists": skill_file_exists,
                "trigger_source": cfg["trigger_source"],
                "enabled": trigger_exists and skill_file_exists,
            }
        )
    return {"bots": statuses}


@get("/admin/specialized-bots/health", sync_to_thread=False)
def specialized_bot_health() -> dict[str, Any]:
    from app.services.execution_search_service import ExecutionSearchService
    from app.services.specialized_bot_service import SpecializedBotService

    search_stats = ExecutionSearchService.get_search_stats()
    return {
        "gh_authenticated": SpecializedBotService.check_gh_auth(),
        "osv_scanner_available": SpecializedBotService.check_osv_scanner(),
        "search_index_count": search_stats.get("indexed_documents", 0),
    }


admin_misc_router = Router(
    path="/",
    route_handlers=[
        execution_search,
        execution_search_stats,
        rotation_status,
        rotation_history,
        specialized_bot_status,
        specialized_bot_health,
    ],
)
