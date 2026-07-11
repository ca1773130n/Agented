"""Admin routes for bundled Memory-System integrations.

A "memory system" is an external tool that consolidates Agented's
session history into a persistent, queryable store. Currently:

  - **tesserae** — per-project compiled knowledge graph (code + docs +
    session history) used by the evolver workspace builder and
    available for retrieval via its MCP server / CLI.

Each memory system has:

  - **Global status** — CLI availability, version, project count
  - **Per-project state** — enabled/disabled, last-import timestamp,
    workspace path

Designed to absorb other memory-system integrations (MemPalace, Cognee,
etc.) in the same shape — the response envelope is generic on
``memory_system_id``.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import Any, Optional

from litestar import Router, get, post
from litestar.exceptions import NotFoundException, ValidationException

from app.db.connection import get_connection
from app.db.projects import get_project
from app.services import tesserae_integration as ti
from app.services.project_workspace_service import ProjectWorkspaceService

# ---------------------------------------------------------------------------
# Status discovery
# ---------------------------------------------------------------------------


def _tesserae_cli_status() -> dict[str, Any]:
    cli_path = shutil.which("tesserae")
    if not cli_path:
        return {"installed": False, "version": None, "path": None}
    # ``tesserae`` argparse doesn't define a ``--version`` flag — passing
    # one falls through to the main extract usage banner. Treat that
    # case as "version unknown" rather than displaying "usage: tesserae
    # [-h] [--source-kind ...]" in the operator UI.
    version: Optional[str] = None
    try:
        result = subprocess.run(
            ["tesserae", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        candidate = (result.stdout or result.stderr or "").strip().splitlines()
        first = candidate[0] if candidate else ""
        if result.returncode == 0 and first and not first.lower().startswith("usage:"):
            version = first
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return {"installed": True, "version": version, "path": cli_path}


def _tesserae_per_project_state() -> list[dict[str, Any]]:
    """One entry per project. ``enabled`` is True iff
    ``tesserae_project_root`` is set. ``workspace_initialized`` is True
    iff the ``.tesserae/`` directory exists at that root. ``imported_at``
    is the latest mtime of the harness_sessions manifest, when present.
    """
    from pathlib import Path

    rows: list[dict[str, Any]] = []
    with get_connection() as conn:
        for row in conn.execute(
            "SELECT id, name, local_path, tesserae_project_root, "
            "tesserae_distill_enabled "
            "FROM projects ORDER BY name COLLATE NOCASE"
        ).fetchall():
            root = row["tesserae_project_root"]
            entry: dict[str, Any] = {
                "project_id": row["id"],
                "project_name": row["name"],
                "local_path": row["local_path"],
                "tesserae_project_root": root,
                "enabled": bool(root),
                "distill_enabled": bool(row["tesserae_distill_enabled"]),
                "workspace_initialized": False,
                "session_count": 0,
                "last_imported_at": None,
            }
            if root:
                tess_dir = Path(root).expanduser() / ".tesserae"
                entry["workspace_initialized"] = tess_dir.is_dir()
                manifest = tess_dir / "harness_sessions" / "manifest.json"
                if manifest.is_file():
                    import json as _json

                    try:
                        data = _json.loads(manifest.read_text())
                        sessions = data.get("sessions") or []
                        entry["session_count"] = len(sessions)
                    except (OSError, ValueError):
                        pass
                    try:
                        from datetime import datetime, timezone

                        mtime = manifest.stat().st_mtime
                        entry["last_imported_at"] = datetime.fromtimestamp(
                            mtime, tz=timezone.utc
                        ).isoformat()
                    except OSError:
                        pass
            rows.append(entry)
    return rows


@get("/system/memory", sync_to_thread=True)
def list_memory_systems() -> dict[str, Any]:
    """Enumerate bundled Memory-System integrations with their global
    status.

    Designed to grow: new memory systems add an entry here without
    touching the operator UI's general layout.
    """
    return {
        "memory_systems": [
            {
                "id": "tesserae",
                "name": "Tesserae",
                "summary": (
                    "Per-project compiled knowledge graph of code, "
                    "docs, and agent-session history. Powers grounded "
                    "retrieval for the evolver workspace and exposes "
                    "an MCP server for live agent queries."
                ),
                "cli": _tesserae_cli_status(),
                "enabled_project_count": sum(
                    1 for p in _tesserae_per_project_state() if p["enabled"]
                ),
            },
        ],
    }


@get("/system/memory/activity-summary", sync_to_thread=True)
def get_activity_summary(
    period: str = "day",
    date: Optional[str] = None,
    project: Optional[str] = None,
    max_turns: Optional[int] = None,
    refresh: bool = False,
) -> dict[str, Any]:
    """Daily/weekly "what you did" digest via ``tesserae summary`` (markdown).

    Cached by default (a past day is immutable, today/week use a short TTL);
    ``refresh=true`` forces a fresh multi-project scan. ``max_turns`` (Tesserae
    0.16) bounds per-session scan cost on very large session days."""
    if period not in ("day", "week"):
        raise ValidationException(detail="period must be 'day' or 'week'")
    return ti.build_activity_summary(
        period=period, day=date, project=project, max_turns=max_turns, refresh=refresh
    )


@get("/system/memory/decisions", sync_to_thread=True)
def get_decisions(
    period: str = "day",
    date: Optional[str] = None,
    project: Optional[str] = None,
    include_agent: bool = True,
    max_turns: Optional[int] = None,
    refresh: bool = False,
) -> dict[str, Any]:
    """Human (AskUserQuestion) + agent decisions across projects, in a time
    window, via ``tesserae decisions --json`` (Tesserae 0.15.0). Cached by
    default; ``refresh=true`` forces a fresh scan. ``max_turns`` (0.16) caps
    per-session cost."""
    if period not in ("day", "week"):
        raise ValidationException(detail="period must be 'day' or 'week'")
    return ti.build_decisions(
        period=period,
        day=date,
        project=project,
        include_agent=include_agent,
        max_turns=max_turns,
        refresh=refresh,
    )


@get("/system/memory/doctor", sync_to_thread=True)
def get_memory_doctor(refresh: bool = False) -> dict[str, Any]:
    """Memory-graph health report via ``tesserae doctor --json`` (Tesserae 0.17):
    init / graph-parse / registry / staleness / lock checks with severities. Cached
    by default; ``refresh=true`` re-runs the checks."""
    return ti.build_doctor(refresh=refresh)


@get("/system/memory/lint", sync_to_thread=True)
def get_memory_lint(refresh: bool = False) -> dict[str, Any]:
    """Graph-QUALITY report via ``tesserae lint --json`` (distinct from doctor's
    operational health): unsupported claims, orphan/dangling links, wiki drift,
    staleness — each with a severity + code + suggested fix. Cached by default;
    ``refresh=true`` re-runs the lint."""
    return ti.build_lint(refresh=refresh)


@get("/system/memory/sessions", sync_to_thread=True)
def get_memory_sessions(
    project: Optional[str] = None, limit: Optional[int] = None
) -> dict[str, Any]:
    """Normalized agent-harness session history via ``tesserae sessions list --json``
    (Tesserae 0.16). ``limit`` caps to the newest N."""
    return ti.list_sessions(project=project, limit=limit)


@get("/system/memory/tesserae/projects", sync_to_thread=True)
def list_tesserae_projects() -> dict[str, Any]:
    """Per-project Tesserae state — for the Settings table."""
    return {"projects": _tesserae_per_project_state()}


# ---------------------------------------------------------------------------
# Per-project enable / disable / refresh
# ---------------------------------------------------------------------------


def _auto_resolve_tesserae_root(project: dict) -> Any:
    """Resolve a Tesserae workspace root for a project without asking the operator.

    Prefers the project's own ``local_path``; otherwise the default per-project
    workspace directory (``workspace_root/projects/{name}``). Raises when neither
    can be determined so the caller returns a clear error instead of silently
    binding the wrong path.
    """
    from pathlib import Path

    local = project.get("local_path")
    if local:
        return Path(local).expanduser().resolve()
    clone_dir = ProjectWorkspaceService._get_clone_dir(project)
    if clone_dir:
        return Path(clone_dir).resolve()
    raise ValidationException(
        detail="Cannot auto-resolve a Tesserae workspace for this project — set a "
        "local path (or a workspace_root in settings) first."
    )


@post(
    "/system/memory/tesserae/projects/{project_id:str}",
    sync_to_thread=True,
)
def set_tesserae_for_project(
    project_id: str,
    data: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Set or clear ``projects.tesserae_project_root`` for a project.

    Body:
      {"root": "/abs/path"}   → enable
      {"root": null}          → disable
      {"root": ""}            → disable (treated as null)

    Returns the updated per-project state row.
    """
    from pathlib import Path

    payload = data or {}
    raw_root = payload.get("root")
    # ``enabled`` is the explicit intent flag (new): true => enable (auto-resolve
    # the workspace from the project if no ``root`` given), false => disable. When
    # absent, fall back to the legacy root-only contract (path => enable, null =>
    # disable) so existing callers keep working.
    enabled = payload.get("enabled")
    if "root" not in payload and enabled is None:
        raise ValidationException(detail="missing 'root' or 'enabled' in request body")

    project = get_project(project_id)
    if not project:
        raise NotFoundException(detail=f"project not found: {project_id}")

    disable = enabled is False or (enabled is None and raw_root in (None, ""))

    if disable:
        # Clear the column AND disable the Tesserae MCP binding so the
        # team-leader SA stops getting tesserae_ask. Row in mcp_servers
        # stays for history.
        with get_connection() as conn:
            conn.execute(
                "UPDATE projects SET tesserae_project_root = NULL WHERE id = ?",
                (project_id,),
            )
            conn.commit()
        ti.unset_tesserae_root_bindings(project_id)
    else:
        # Enable. Use an explicit ``root`` if provided, otherwise auto-resolve the
        # project's own workspace — the operator shouldn't have to type a path the
        # app already knows.
        if isinstance(raw_root, str) and raw_root.strip():
            resolved_path = Path(raw_root).expanduser().resolve()
        else:
            resolved_path = _auto_resolve_tesserae_root(project)
        # set_tesserae_root does the column write AND upserts /
        # rebinds the per-project Tesserae MCP server.
        ti.set_tesserae_root(project_id, resolved_path)

    # Return the fresh per-project state (single row).
    state = [p for p in _tesserae_per_project_state() if p["project_id"] == project_id]
    return {"project": state[0] if state else None}


@post(
    "/system/memory/tesserae/projects/{project_id:str}/distill",
    sync_to_thread=True,
)
def set_tesserae_distill_for_project(
    project_id: str,
    data: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Toggle AgentRunbook distillation for a project.

    Body: ``{"enabled": bool}``. When on, compile runs with ``--distill`` and
    the harness KG-signal path retrieves via ``tesserae context --multi-pool``.
    Returns the refreshed per-project state row.
    """
    payload = data or {}
    if "enabled" not in payload:
        raise ValidationException(detail="missing 'enabled' in request body")
    enabled = bool(payload["enabled"])
    with get_connection() as conn:
        exists = conn.execute(
            "SELECT 1 FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
    if not exists:
        raise NotFoundException(detail=f"project not found: {project_id}")
    ti.set_distill_enabled(project_id, enabled)
    state = [p for p in _tesserae_per_project_state() if p["project_id"] == project_id]
    return {"project": state[0] if state else None}


@post(
    "/system/memory/tesserae/projects/{project_id:str}/refresh",
    sync_to_thread=True,
)
def refresh_tesserae_for_project(project_id: str) -> dict[str, Any]:
    """Re-export every completed session for the project into Tesserae.

    Synchronous — Tesserae's CLI is fast enough for batch imports
    under the 500-session cap. Long-running operations move to an
    async job queue when projects routinely exceed that.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
    if not row:
        raise NotFoundException(detail=f"project not found: {project_id}")
    result = ti.export_sessions_to_tesserae(project_id)
    return {"project_id": project_id, **result}


@get(
    "/system/memory/tesserae/projects/{project_id:str}/status",
    sync_to_thread=True,
)
def tesserae_workspace_status(project_id: str) -> dict[str, Any]:
    """Cheap status read: initialized? compiled? graph size? session
    count? last-modified timestamps. No subprocess call."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
    if not row:
        raise NotFoundException(detail=f"project not found: {project_id}")
    return ti.workspace_status(project_id)


@post(
    "/system/memory/tesserae/projects/{project_id:str}/init",
    sync_to_thread=True,
)
def tesserae_init(project_id: str) -> dict[str, Any]:
    """``tesserae project init`` — create the .tesserae/ skeleton.
    Synchronous (instant)."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
    if not row:
        raise NotFoundException(detail=f"project not found: {project_id}")
    return ti.init_workspace(project_id).to_dict()


@post(
    "/system/memory/tesserae/projects/{project_id:str}/ingest",
    sync_to_thread=True,
)
def tesserae_ingest(
    project_id: str,
    data: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """``tesserae project ingest`` — pull markdown sources into the
    extraction queue. Body optional ``{paths: [str]}`` to override the
    default set (README/CLAUDE/AGENTS/CONVENTIONS/.planning)."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
    if not row:
        raise NotFoundException(detail=f"project not found: {project_id}")
    paths = None
    if data:
        raw = data.get("paths")
        if raw and isinstance(raw, list):
            paths = [str(p) for p in raw if isinstance(p, str)]
    return ti.ingest_paths(project_id, paths=paths).to_dict()


@post(
    "/system/memory/tesserae/projects/{project_id:str}/compile",
    sync_to_thread=True,
)
def tesserae_compile(project_id: str) -> dict[str, Any]:
    """``tesserae project compile`` — extract the typed knowledge
    graph. Long-running (minutes); dispatched async. Returns a
    ``job_id`` the caller polls via the jobs endpoint."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
    if not row:
        raise NotFoundException(detail=f"project not found: {project_id}")
    if ti.get_tesserae_root(project_id) is None:
        raise ValidationException(
            detail="Tesserae not enabled for this project",
        )
    job_id = ti.run_op_async(project_id, "compile")
    return {"job_id": job_id, "project_id": project_id, "op": "compile", "status": "running"}


@post(
    "/system/memory/tesserae/projects/{project_id:str}/build-site",
    sync_to_thread=True,
)
def tesserae_build_site(project_id: str) -> dict[str, Any]:
    """``tesserae project build-site`` — generate static HTML from
    the compiled graph. Long-running; dispatched async."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
    if not row:
        raise NotFoundException(detail=f"project not found: {project_id}")
    if ti.get_tesserae_root(project_id) is None:
        raise ValidationException(
            detail="Tesserae not enabled for this project",
        )
    job_id = ti.run_op_async(project_id, "build-site")
    return {"job_id": job_id, "project_id": project_id, "op": "build-site", "status": "running"}


@get(
    "/system/memory/tesserae/jobs/{job_id:str}",
    sync_to_thread=True,
)
def tesserae_job_status(job_id: str) -> dict[str, Any]:
    """Poll an async op job. Returns ``status`` in
    {running, completed, failed} plus the result dict when done.
    404 when the job_id is unknown (process restarted, etc.)."""
    job = ti.get_op_job(job_id)
    if not job:
        raise NotFoundException(detail=f"job not found: {job_id}")
    return job


memory_system_router = Router(
    path="/admin",
    route_handlers=[
        list_memory_systems,
        get_activity_summary,
        get_decisions,
        get_memory_doctor,
        get_memory_lint,
        get_memory_sessions,
        list_tesserae_projects,
        set_tesserae_for_project,
        set_tesserae_distill_for_project,
        refresh_tesserae_for_project,
        tesserae_workspace_status,
        tesserae_init,
        tesserae_ingest,
        tesserae_compile,
        tesserae_build_site,
        tesserae_job_status,
    ],
)
