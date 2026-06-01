"""Wave 69 — leaf CRUD batch E (~30 routes).

monitoring + health_monitor + orchestration + onboarding + project_instances
+ repo_bot_defaults + bot_pipes.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from typing import Any, Optional

from litestar import Router, delete, get, patch, post, put
from litestar.exceptions import (
    ClientException,
    HTTPException,
    NotFoundException,
)

from app.database import (
    delete_fallback_chain,
    get_fallback_chain,
    get_monitoring_config,
    get_snapshot_history,
    set_fallback_chain,
)
from app.db.bot_pipes import (
    create_pipe,
    get_all_pipes,
    get_pipe_executions,
    update_pipe,
)
from app.db.health_alerts import acknowledge_alert, get_recent_alerts
from app.db.onboarding import get_steps, upsert_steps
from app.db.project_sa_instances import (
    get_project_sa_instance,
    get_project_sa_instances_for_project,
)
from app.db.projects import get_project
from app.db.super_agents import get_sessions_for_instance, get_super_agent
from app.db.triggers import (
    add_github_repo,
    get_all_triggers,
    get_execution_logs_for_trigger,
    get_trigger,
    list_paths_for_trigger,
    remove_github_repo,
    update_trigger,
)
from app.services.health_monitor_service import HealthMonitorService
from app.services.instance_service import InstanceService
from app.services.monitoring_service import MonitoringService
from app.services.orchestration_service import OrchestrationService
from app.services.rate_limit_service import RateLimitService
from app.services.report_service import ReportService

logger = logging.getLogger(__name__)


# ===========================================================================
# /admin/monitoring/* (5)
# ===========================================================================


@get("/config", sync_to_thread=False)
def monitoring_config() -> Any:
    return get_monitoring_config()


@post("/config", sync_to_thread=False)
def save_monitoring_config(data: dict) -> dict[str, Any]:
    if not data:
        raise ClientException(detail="JSON body required")
    polling_minutes = data.get("polling_minutes", 5)
    if polling_minutes not in (1, 5, 15, 30, 60):
        raise ClientException(detail="polling_minutes must be one of [1, 5, 15, 30, 60]")
    accounts = data.get("accounts", {})
    if not isinstance(accounts, dict):
        raise ClientException(detail="accounts must be a JSON object")
    for key, value in accounts.items():
        if not isinstance(key, str):
            raise ClientException(
                detail=f"accounts keys must be strings, got {type(key).__name__}"
            )
        if not isinstance(value, dict):
            raise ClientException(
                detail=f"accounts[{key!r}] must be a JSON object, got {type(value).__name__}"
            )
    config = {
        "enabled": bool(data.get("enabled", False)),
        "polling_minutes": polling_minutes,
        "accounts": accounts,
    }
    MonitoringService.reconfigure(config)
    return config


@get("/status", sync_to_thread=False)
def monitoring_status() -> Any:
    return MonitoringService.get_monitoring_status()


@post("/poll", sync_to_thread=False)
def monitoring_poll() -> Any:
    try:
        MonitoringService._poll_usage()
    except Exception as e:
        logger.warning("Monitoring poll had errors: %s", e)
    return MonitoringService.get_monitoring_status()


@get("/credentials", sync_to_thread=False)
def monitoring_credentials() -> dict[str, Any]:
    """Per-account OAuth credential status for the Token Usage
    Dashboard + AI Backends page.

    Returns the same accounts ``/status`` enumerates, plus a
    ``credential_status`` field per row. ``"missing"`` rows
    include a copy-pasteable ``remediation`` shell command and
    the ``expected_location`` that was checked (keychain entry
    or file path), so operators don't need to grep the backend
    log to figure out why an account isn't producing snapshots.
    """
    from app.database import get_all_accounts_with_health
    from app.services.provider_usage_client import CredentialResolver

    try:
        accounts = get_all_accounts_with_health()
    except Exception:
        logger.warning("Credential status: account load failed", exc_info=True)
        accounts = []

    out = []
    for a in accounts:
        backend_type = a.get("backend_type") or "claude"
        status = CredentialResolver.check_credentials(a, backend_type)
        out.append(
            {
                "account_id": a.get("id"),
                "account_name": a.get("account_name") or a.get("name"),
                "backend_type": backend_type,
                "config_path": a.get("config_path"),
                "credential_status": status.get("status"),
                "remediation": status.get("remediation"),
                "expected_location": status.get("expected_location"),
            }
        )
    return {"accounts": out}


@get("/history", sync_to_thread=False)
def monitoring_history(
    account_id: Optional[int] = None,
    window_type: Optional[str] = None,
    minutes: int = 360,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    if account_id is None or not window_type:
        raise ClientException(
            detail="account_id and window_type are required query parameters"
        )
    history = get_snapshot_history(
        account_id, window_type, since_minutes=minutes, limit=limit, offset=offset
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
    }


@post("/history-batch", sync_to_thread=False)
def monitoring_history_batch(data: dict[str, Any]) -> dict[str, Any]:
    """Return snapshot history for MANY (account_id, window_type) windows in
    ONE request.

    The Cost dashboard charts a history per window per account (~12-36
    series). Fetching each as an individual GET /history call bursts past
    the per-key admin rate limit (30/min, see RateLimitMiddleware) → 429
    storm → trend charts render with missing data (wrong shapes/legends).
    One batched read avoids the burst entirely.

    Body: ``{"windows": [{"account_id": int, "window_type": str}, ...],
             "minutes": int, "limit": int}``
    Returns: ``{"histories": {"<account_id>_<window_type>":
             {account_id, window_type, history: [...]}}}``.
    """
    windows = data.get("windows") or []
    minutes = int(data.get("minutes", 360))
    # Max points returned per window. The chart needs the trend to span the
    # WHOLE selected window (e.g. 30 days), evenly downsampled — not the
    # oldest 50 rows that ``get_snapshot_history`` (ORDER BY ASC LIMIT 50)
    # would otherwise return, which made a 30-day selection show only the
    # first few hours of monitoring.
    max_points = max(50, min(int(data.get("max_points", 400)), 2000))

    def _downsample(rows: list, cap: int) -> list:
        if len(rows) <= cap:
            return rows
        step = len(rows) / cap
        out = [rows[int(i * step)] for i in range(cap)]
        out[-1] = rows[-1]  # always keep the most-recent point
        return out

    histories: dict[str, Any] = {}
    for w in windows:
        aid = w.get("account_id")
        wt = w.get("window_type")
        if aid is None or not wt:
            continue
        # Fetch the full window (bounded), then downsample for the chart.
        rows = get_snapshot_history(aid, wt, since_minutes=minutes, limit=20000, offset=0)
        rows = _downsample(rows, max_points)
        histories[f"{aid}_{wt}"] = {
            "account_id": aid,
            "window_type": wt,
            "history": [
                {
                    "tokens_used": s["tokens_used"],
                    "percentage": s["percentage"],
                    "recorded_at": s["recorded_at"],
                }
                for s in rows
            ],
        }
    return {"histories": histories}


monitoring_router = Router(
    path="/admin/monitoring",
    route_handlers=[
        monitoring_config,
        save_monitoring_config,
        monitoring_status,
        monitoring_poll,
        monitoring_credentials,
        monitoring_history,
        monitoring_history_batch,
    ],
)


# ===========================================================================
# /admin/health-monitor/* (5)
# ===========================================================================


@get("/alerts", sync_to_thread=False)
def list_health_alerts(
    limit: int = 50,
    trigger_id: Optional[str] = None,
    acknowledged: Optional[str] = None,
) -> dict[str, Any]:
    ack = None
    if acknowledged is not None:
        ack = acknowledged.lower() in ("1", "true", "yes")
    alerts = get_recent_alerts(limit=limit, trigger_id=trigger_id, acknowledged=ack)
    return {"alerts": alerts}


@get("/status", sync_to_thread=False)
def health_status() -> Any:
    return HealthMonitorService.get_status()


@post("/alerts/{alert_id:int}/acknowledge", sync_to_thread=False)
def acknowledge_health_alert(alert_id: int) -> dict[str, Any]:
    if not acknowledge_alert(alert_id):
        raise NotFoundException(detail="Alert not found")
    return {"message": "Alert acknowledged"}


@get("/report", sync_to_thread=False)
def health_report(team_id: Optional[str] = None) -> Any:
    return ReportService.generate_weekly_report(team_id=team_id)


@post("/check", sync_to_thread=False)
def manual_health_check() -> dict[str, Any]:
    HealthMonitorService._check_health()
    return {"message": "Health check completed", **HealthMonitorService.get_status()}


health_monitor_router = Router(
    path="/admin/health-monitor",
    route_handlers=[
        list_health_alerts,
        health_status,
        acknowledge_health_alert,
        health_report,
        manual_health_check,
    ],
)


# ===========================================================================
# /admin/orchestration/* (5)
# ===========================================================================


def _format_chain(chain: list) -> list[dict[str, Any]]:
    return [
        {
            "backend_type": entry["backend_type"],
            "account_id": entry.get("account_id"),
            "chain_order": entry["chain_order"],
        }
        for entry in chain
    ]


@get("/triggers/{trigger_id:str}/fallback-chain", sync_to_thread=False)
def get_orchestration_chain(trigger_id: str) -> dict[str, Any]:
    return {"chain": _format_chain(get_fallback_chain("trigger", trigger_id))}


@put("/triggers/{trigger_id:str}/fallback-chain", sync_to_thread=False)
def set_orchestration_chain(trigger_id: str, data: dict) -> dict[str, Any]:
    from app.models.orchestration import SetFallbackChainRequest

    body = SetFallbackChainRequest(**(data or {}))
    error = OrchestrationService.validate_fallback_chain_entries(body.entries)
    if error:
        raise ClientException(detail=error)
    entries = [e.model_dump() for e in body.entries]
    if not set_fallback_chain("trigger", trigger_id, entries):
        raise HTTPException(status_code=500, detail="Failed to set fallback chain")
    return {"chain": _format_chain(get_fallback_chain("trigger", trigger_id))}


@delete(
    "/triggers/{trigger_id:str}/fallback-chain",
    status_code=204,
    sync_to_thread=False,
)
def delete_orchestration_chain(trigger_id: str) -> None:
    delete_fallback_chain("trigger", trigger_id)


@get("/health", sync_to_thread=False)
def orchestration_health() -> dict[str, Any]:
    return {"accounts": RateLimitService.get_all_account_states()}


@post("/accounts/{account_id:int}/clear-rate-limit", sync_to_thread=False)
def clear_account_rate_limit(account_id: int) -> dict[str, Any]:
    if not RateLimitService.clear_rate_limit(account_id):
        raise NotFoundException(detail="Account not found")
    return {"message": "Rate limit cleared"}


orchestration_router = Router(
    path="/admin/orchestration",
    route_handlers=[
        get_orchestration_chain,
        set_orchestration_chain,
        delete_orchestration_chain,
        orchestration_health,
        clear_account_rate_limit,
    ],
)


# ===========================================================================
# /admin/onboarding/* (3)
# ===========================================================================

ONBOARDING_TRIGGER_ID = "bot-onboarding"


@get("/config", sync_to_thread=False)
def onboarding_config(trigger_id: str = ONBOARDING_TRIGGER_ID) -> dict[str, Any]:
    trigger = get_trigger(trigger_id)
    if not trigger:
        return {"trigger": None, "steps": []}
    return {"trigger": trigger, "steps": get_steps(trigger_id)}


@put("/config", sync_to_thread=False)
def save_onboarding_config(data: dict) -> dict[str, Any]:
    body = data or {}
    trigger_id = body.get("trigger_id")
    if not trigger_id:
        raise ClientException(detail="trigger_id is required")
    if not get_trigger(trigger_id):
        raise NotFoundException(detail=f"Trigger '{trigger_id}' not found")
    update_kwargs: dict[str, Any] = {}
    if body.get("enabled") is not None:
        update_kwargs["enabled"] = 1 if body["enabled"] else 0
    if body.get("trigger_event") is not None:
        update_kwargs["trigger_source"] = body["trigger_event"]
    if update_kwargs:
        update_trigger(trigger_id, **update_kwargs)
    upsert_steps(trigger_id, body.get("steps", []) or [])
    return {
        "message": "Onboarding configuration saved",
        "trigger": get_trigger(trigger_id),
        "steps": get_steps(trigger_id),
    }


@get("/runs", sync_to_thread=False)
def onboarding_runs(trigger_id: str = ONBOARDING_TRIGGER_ID) -> dict[str, Any]:
    logs = get_execution_logs_for_trigger(trigger_id, limit=20)
    return {"runs": logs, "total": len(logs)}


onboarding_router = Router(
    path="/admin/onboarding",
    route_handlers=[onboarding_config, save_onboarding_config, onboarding_runs],
)


# ===========================================================================
# /admin/projects/{id}/instances/* (4)
# ===========================================================================


def _ensure_instance_in_project(project_id: str, instance_id: str) -> dict:
    instance = get_project_sa_instance(instance_id)
    if not instance:
        raise NotFoundException(detail="Instance not found")
    if instance["project_id"] != project_id:
        raise NotFoundException(detail="Instance not found in this project")
    return instance


@post("/{project_id:str}/instances", status_code=201, sync_to_thread=False)
def create_instance(project_id: str, data: dict) -> Any:
    if not get_project(project_id):
        raise NotFoundException(detail="Project not found")
    body = data or {}
    team_id = body.get("team_id")
    super_agent_id = body.get("super_agent_id")
    if not team_id and not super_agent_id:
        raise ClientException(
            detail="At least one of team_id or super_agent_id must be provided"
        )
    try:
        if team_id:
            result = InstanceService.create_team_instances(project_id, team_id)
        else:
            result = InstanceService.create_sa_instance(project_id, super_agent_id)
    except sqlite3.IntegrityError as e:
        raise HTTPException(
            status_code=409,
            detail="Instance already exists for this project and template",
        ) from e
    if result is None:
        raise ClientException(
            detail="Failed to create instance (project or template not found)"
        )
    return result


@get("/{project_id:str}/instances", sync_to_thread=False)
def list_instances(project_id: str) -> dict[str, Any]:
    instances = get_project_sa_instances_for_project(project_id)
    enriched = []
    for inst in instances:
        sa = get_super_agent(inst["template_sa_id"])
        if sa:
            inst["sa_name"] = sa.get("name")
            inst["sa_description"] = sa.get("description")
            inst["sa_backend_type"] = sa.get("backend_type")
        enriched.append(inst)
    return {"instances": enriched}


@get("/{project_id:str}/instances/{instance_id:str}", sync_to_thread=False)
def get_instance(project_id: str, instance_id: str) -> Any:
    instance = _ensure_instance_in_project(project_id, instance_id)
    sa = get_super_agent(instance["template_sa_id"])
    if sa:
        instance["sa_name"] = sa.get("name")
        instance["sa_description"] = sa.get("description")
        instance["sa_backend_type"] = sa.get("backend_type")
    instance["sessions"] = get_sessions_for_instance(instance_id)
    return instance


@delete(
    "/{project_id:str}/instances/{instance_id:str}",
    status_code=200,
    sync_to_thread=False,
)
def delete_instance(project_id: str, instance_id: str) -> dict[str, Any]:
    _ensure_instance_in_project(project_id, instance_id)
    InstanceService.delete_instance(instance_id)
    return {"message": "Instance deleted"}


project_instances_router = Router(
    path="/admin/projects",
    route_handlers=[create_instance, list_instances, get_instance, delete_instance],
)


# ===========================================================================
# /admin/repo-bot-defaults/* (4)
# ===========================================================================


def _slug_to_repo(slug: str) -> str:
    return slug.replace("__", "/", 1)


def _build_bindings(triggers: list) -> list:
    repo_map: dict[str, dict[str, Any]] = {}
    for trigger in triggers:
        paths = list_paths_for_trigger(trigger["id"])
        github_paths = [
            p for p in paths if p.get("path_type") == "github" and p.get("github_repo_url")
        ]
        for path in github_paths:
            repo_url = path["github_repo_url"].rstrip("/")
            match = re.match(r"https?://[^/]+/(.+)", repo_url)
            repo = match.group(1) if match else repo_url
            if repo not in repo_map:
                repo_map[repo] = {
                    "bots": set(),
                    "project_count": 0,
                    "enabled": trigger["enabled"],
                }
            repo_map[repo]["bots"].add(trigger["id"])
            if not trigger["enabled"]:
                repo_map[repo]["enabled"] = False
    return [
        {
            "repo": repo,
            "bots": sorted(data["bots"]),
            "projectCount": data["project_count"],
            "enabled": bool(data["enabled"]),
        }
        for repo, data in repo_map.items()
    ]


def _available_bots(triggers: list) -> list:
    type_map = {"github": "review", "webhook": "security", "scheduled": "security", "manual": "docs"}
    return [
        {
            "id": t["id"],
            "name": t["name"],
            "type": type_map.get(t.get("trigger_source", ""), "review"),
        }
        for t in triggers
    ]


@get("/", sync_to_thread=False)
def list_repo_defaults() -> dict[str, Any]:
    triggers = get_all_triggers()
    return {"bindings": _build_bindings(triggers), "bots": _available_bots(triggers)}


@post("/", status_code=201, sync_to_thread=False)
def create_repo_default(data: dict) -> dict[str, Any]:
    if not data:
        raise ClientException(detail="JSON body required")
    repo = (data.get("repo") or "").strip()
    bot_ids = data.get("bot_ids") or []
    if not repo:
        raise ClientException(detail="repo is required")
    if not bot_ids:
        raise ClientException(detail="bot_ids must be a non-empty list")
    github_repo_url = repo if repo.startswith("http") else f"https://github.com/{repo}"
    triggers = {t["id"]: t for t in get_all_triggers()}
    added: list[str] = []
    errors: list[str] = []
    for bot_id in bot_ids:
        if bot_id not in triggers:
            errors.append(f"Bot {bot_id} not found")
            continue
        if add_github_repo(bot_id, github_repo_url):
            added.append(bot_id)
    return {"repo": repo, "bound_bots": added, "errors": errors}


@put("/{repo_slug:str}", sync_to_thread=False)
def toggle_repo_default(repo_slug: str, data: dict) -> dict[str, Any]:
    if data is None or "enabled" not in (data or {}):
        raise ClientException(detail="enabled (bool) is required")
    enabled = data["enabled"]
    if not isinstance(enabled, bool):
        raise ClientException(detail="enabled (bool) is required")
    repo = _slug_to_repo(repo_slug)
    prefix = repo if repo.startswith("http") else f"https://github.com/{repo}"
    updated: list[str] = []
    for trigger in get_all_triggers():
        for p in list_paths_for_trigger(trigger["id"]):
            purl = (p.get("github_repo_url") or "").rstrip("/")
            if purl == prefix.rstrip("/"):
                update_trigger(trigger["id"], enabled=int(enabled))
                updated.append(trigger["id"])
                break
    if not updated:
        raise NotFoundException(detail=f"No bindings found for repo {repo}")
    return {"repo": repo, "enabled": enabled, "updated_triggers": updated}


@delete("/{repo_slug:str}", status_code=200, sync_to_thread=False)
def delete_repo_default(repo_slug: str) -> dict[str, Any]:
    repo = _slug_to_repo(repo_slug)
    github_repo_url = repo if repo.startswith("http") else f"https://github.com/{repo}"
    removed: list[str] = []
    for trigger in get_all_triggers():
        if remove_github_repo(trigger["id"], github_repo_url):
            removed.append(trigger["id"])
    if not removed:
        raise NotFoundException(detail=f"No bindings found for repo {repo}")
    return {"repo": repo, "removed_triggers": removed}


repo_bot_defaults_router = Router(
    path="/admin/repo-bot-defaults",
    route_handlers=[
        list_repo_defaults,
        create_repo_default,
        toggle_repo_default,
        delete_repo_default,
    ],
)


# ===========================================================================
# /admin/bot-pipes/* (4)
# ===========================================================================


@get("/", sync_to_thread=False)
def list_bot_pipes() -> dict[str, Any]:
    return {"pipes": get_all_pipes()}


@post("/", status_code=201, sync_to_thread=False)
def create_bot_pipe(data: dict) -> dict[str, Any]:
    if not data:
        raise ClientException(detail="JSON body required")
    name = (data.get("name") or "").strip()
    source_bot_id = (data.get("source_bot_id") or "").strip()
    dest_bot_id = (data.get("dest_bot_id") or "").strip()
    if not name or not source_bot_id or not dest_bot_id:
        raise ClientException(
            detail="name, source_bot_id and dest_bot_id are required"
        )
    pipe = create_pipe(
        {
            "name": name,
            "source_bot_id": source_bot_id,
            "dest_bot_id": dest_bot_id,
            "transform": data.get("transform", "passthrough"),
            "enabled": data.get("enabled", True),
        }
    )
    return {"message": "Pipe created", "pipe": pipe}


@patch("/{pipe_id:str}", sync_to_thread=False)
def update_bot_pipe(pipe_id: str, data: dict) -> dict[str, Any]:
    body = {k: v for k, v in (data or {}).items() if v is not None}
    pipe = update_pipe(pipe_id, body)
    if pipe is None:
        raise NotFoundException(detail="Pipe not found")
    return {"message": "Pipe updated", "pipe": pipe}


@get("/executions", sync_to_thread=False)
def list_pipe_executions() -> dict[str, Any]:
    return {"executions": get_pipe_executions(limit=50)}


bot_pipes_router = Router(
    path="/admin/bot-pipes",
    route_handlers=[list_bot_pipes, create_bot_pipe, update_bot_pipe, list_pipe_executions],
)
