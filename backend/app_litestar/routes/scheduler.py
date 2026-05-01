"""Agent scheduler routes (track A, wave 51)."""

from __future__ import annotations

from typing import Any

from litestar import Router, get

from app.services.agent_scheduler_service import AgentSchedulerService


@get("/status", sync_to_thread=False)
def scheduler_status() -> dict[str, Any]:
    return AgentSchedulerService.get_scheduler_status()


@get("/sessions", sync_to_thread=False)
def scheduler_sessions() -> dict[str, Any]:
    status = AgentSchedulerService.get_scheduler_status()
    return {"sessions": status["sessions"]}


@get("/eligibility/{account_id:int}", sync_to_thread=False)
def scheduler_eligibility(account_id: int) -> dict[str, Any]:
    return AgentSchedulerService.check_eligibility(account_id)


scheduler_router = Router(
    path="/admin/scheduler",
    route_handlers=[scheduler_status, scheduler_sessions, scheduler_eligibility],
)
