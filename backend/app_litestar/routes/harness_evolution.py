"""Admin routes for Life-Harness evolution rounds (project-scoped)."""

from __future__ import annotations

from typing import Any, Optional

from litestar import Router, get, post, put
from litestar.exceptions import NotFoundException

from app.db import harness_evolution as evolution_repo


@post("/projects/{project_id:str}/evolution/dry-run", sync_to_thread=True)
def dry_run_round(
    project_id: str,
    data: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    from app.services.harness_evolver import run_evolution_round

    opts = data or {}
    result = run_evolution_round(
        project_id,
        since=opts.get("since"),
        until=opts.get("until"),
        limit=int(opts.get("limit", 25)),
        dry_run=True,
        force=bool(opts.get("force", False)),
    )
    return _result_payload(result)


@post("/projects/{project_id:str}/evolution/apply", sync_to_thread=True)
def live_round(
    project_id: str,
    data: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    from app.services.harness_evolver import run_evolution_round

    opts = data or {}
    result = run_evolution_round(
        project_id,
        since=opts.get("since"),
        until=opts.get("until"),
        limit=int(opts.get("limit", 25)),
        dry_run=False,
        force=bool(opts.get("force", False)),
    )
    return _result_payload(result)


@get("/projects/{project_id:str}/evolution/rounds", sync_to_thread=False)
def list_project_rounds(project_id: str, limit: int = 20) -> dict[str, Any]:
    capped = max(1, min(int(limit or 20), 100))
    return {
        "project_id": project_id,
        "rounds": evolution_repo.list_for_project(project_id, limit=capped),
    }


@get("/evolution/rounds", sync_to_thread=False)
def list_all_rounds(
    limit: int = 50,
    status: Optional[str] = None,
) -> dict[str, Any]:
    capped = max(1, min(int(limit or 50), 200))
    return {"rounds": evolution_repo.list_all(limit=capped, status=status)}


@get("/evolution/rounds/{round_id:str}", sync_to_thread=False)
def get_round_detail(round_id: str) -> dict[str, Any]:
    row = evolution_repo.get_round(round_id)
    if row is None:
        raise NotFoundException(detail=f"round not found: {round_id}")
    return row


@get("/evolution/rounds/{round_id:str}/impact", sync_to_thread=False)
def get_round_impact(round_id: str, window: int = 20) -> dict[str, Any]:
    from app.services.harness_evolution_impact import compute_impact

    capped = max(1, min(int(window or 20), 200))
    return compute_impact(round_id, window_size=capped)


@post("/evolution/rounds/{round_id:str}/apply", sync_to_thread=True)
def approve_round(round_id: str) -> dict[str, Any]:
    from app.services.harness_evolver import apply_dry_run_round

    return _result_payload(apply_dry_run_round(round_id))


@post("/evolution/rounds/{round_id:str}/abort", sync_to_thread=True)
def abort_round(
    round_id: str,
    data: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    from app.services.harness_evolver import abort_dry_run_round

    reason = (data or {}).get("reason")
    return _result_payload(abort_dry_run_round(round_id, reason=reason))


@post("/evolution/rounds/{round_id:str}/revert", sync_to_thread=True)
def revert_round_route(
    round_id: str,
    data: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    from app.services.harness_evolution_rollback import revert_round

    force = bool((data or {}).get("force"))
    result = revert_round(round_id, force=force)
    return {"round_id": round_id, **result.model_dump()}


@get("/projects/{project_id:str}/autonomy", sync_to_thread=False)
def get_autonomy_config(project_id: str) -> dict[str, Any]:
    from app.db.project_autonomy_config import get_policy
    from app.models.autonomy_policy import AutonomyPolicy

    p = get_policy(project_id)
    return {
        "project_id": project_id,
        "policy": (p or AutonomyPolicy()).model_dump(),
        "configured": p is not None,
    }


@put("/projects/{project_id:str}/autonomy", sync_to_thread=True)
def set_autonomy_config(
    project_id: str,
    data: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    from app.db.project_autonomy_config import upsert_policy
    from app.models.autonomy_policy import AutonomyPolicy

    policy = AutonomyPolicy.model_validate((data or {}).get("policy") or {})
    upsert_policy(project_id, policy)
    return {"project_id": project_id, "policy": policy.model_dump()}


def _result_payload(result) -> dict[str, Any]:
    return {
        "round_id": result.round_id,
        "status": result.status,
        "applied_asset_ids": result.applied_asset_ids,
        "error": result.error,
        "notes": result.notes,
    }


harness_evolution_router = Router(
    path="/admin",
    route_handlers=[
        dry_run_round,
        live_round,
        list_project_rounds,
        list_all_rounds,
        get_round_detail,
        get_round_impact,
        approve_round,
        abort_round,
        revert_round_route,
        get_autonomy_config,
        set_autonomy_config,
    ],
)
