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
from app.services import memory_graph
from app.services import tesserae_integration as ti
from app.services.project_workspace_service import ProjectWorkspaceService

# ---------------------------------------------------------------------------
# Status discovery
# ---------------------------------------------------------------------------


# The tesserae CLI version is stable for the process lifetime, but the
# memory-systems list endpoint spawned `tesserae --version` on EVERY page load —
# a per-load subprocess that showed up as a navigation delay. Cache the installed
# result process-wide (a fresh install is still picked up: the "not installed"
# branch below never populates the cache).
_cli_status_cache: dict[str, Any] = {}


def _tesserae_cli_status() -> dict[str, Any]:
    if _cli_status_cache:
        return _cli_status_cache
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
    result = {"installed": True, "version": version, "path": cli_path}
    _cli_status_cache.update(result)
    return result


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


@get("/system/memory/config", sync_to_thread=True)
def get_memory_config() -> dict[str, Any]:
    """Resolved Tesserae LLM backend + a live liveness ping via ``tesserae config
    status``: provider / effort / source / liveness_ok — ops visibility for the
    Memory surface. Also carries the 0.23/0.24 ``consolidation`` sleep-cycle
    status (enabled / running / cadence) from Agented's own daemon supervisor —
    Tesserae's CLI exposes no consolidation-status field, so this is the honest
    source, not a parsed indicator."""
    result = dict(ti.config_status())  # copy — config_status caches its dict
    try:
        from app.services.tesserae_engine_daemon import TesseraeEngineDaemon

        result["consolidation"] = TesseraeEngineDaemon.status()
    except Exception:  # surfacing status must never break the config read
        result["consolidation"] = None
    return result


@post("/system/memory/engine-refresh", sync_to_thread=True)
def engine_refresh() -> dict[str, Any]:
    """Kick off ``tesserae engine --all --once`` — one COALESCED recompile drain
    across every registered project (additive to Agented's own scheduler; ``--once``
    so there's no long-lived daemon to babysit). Dispatched async; poll the jobs
    endpoint."""
    job_id = ti.engine_refresh_async()
    return {"job_id": job_id, "op": "engine-refresh", "status": "running"}


@post("/system/memory/research", sync_to_thread=True)
def start_research(data: dict[str, Any]) -> dict[str, Any]:
    """Kick off ``tesserae research`` — the agentic plan→search→reflect→synthesize
    loop over the compiled graph. SLOW + LLM-backed, so dispatched async: returns a
    ``job_id`` the caller polls via the jobs endpoint (result carries the report
    markdown). Body: ``{query, breadth?, depth?, max_iters?, top_k?}``."""
    query = (data or {}).get("query")
    if not isinstance(query, str) or not query.strip():
        raise ValidationException(detail="query is required")

    def _int(name: str, default: int) -> int:
        val = (data or {}).get(name, default)
        if not isinstance(val, int) or isinstance(val, bool):
            raise ValidationException(detail=f"{name} must be an integer")
        return val

    job_id = ti.run_research_async(
        query,
        breadth=_int("breadth", 3),
        depth=_int("depth", 2),
        max_iters=_int("max_iters", 6),
        top_k=_int("top_k", 5),
    )
    return {"job_id": job_id, "op": "research", "status": "running"}


@get("/system/memory/graph/status", sync_to_thread=True)
def get_graph_status() -> dict[str, Any]:
    """Compiled knowledge-graph OVERVIEW via ``tesserae status --json``:
    node/edge/session counts + last-compile time — the "what does Tesserae know"
    header for the KG explorer."""
    return ti.graph_status()


@get("/system/memory/graph/query", sync_to_thread=True)
def query_graph(q: str, top_k: int = 8, kind: Optional[str] = None) -> dict[str, Any]:
    """Search the knowledge graph via ``tesserae query --json`` (raw BM25/semantic
    retrieval, NO LLM): ranked hits with title/kind/score/excerpt/node_id. ``kind``
    optionally restricts to one wiki kind; ``top_k`` caps hits (1-50)."""
    return ti.query_graph(q, top_k=top_k, kind=kind)


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


# --- Browsable knowledge graph (nodes/edges from the compiled graph.json) --------


def _resolve_graph_root(project: Optional[str]) -> str:
    """Filesystem root whose ``.tesserae/graph.json`` to browse — a project's
    Tesserae root when given + enabled, else Agented's own repo root."""
    if project:
        root = ti.get_tesserae_root(project)
        if root:
            return str(root)
    return str(ti._REPO_ROOT)


@get("/system/memory/graph/overview", sync_to_thread=True)
def graph_overview(project: Optional[str] = None, max_nodes: int = 50) -> dict[str, Any]:
    """A connected landing subgraph around the most-connected node (so the graph
    view is never empty) + the graph's total node/edge counts."""
    return memory_graph.overview(
        _resolve_graph_root(project), max_nodes=max(10, min(int(max_nodes), 150))
    )


@get("/system/memory/graph/nodes", sync_to_thread=True)
def graph_search_nodes(
    q: str, project: Optional[str] = None, limit: int = 25
) -> dict[str, Any]:
    """Search graph NODES by name/alias/description — ranked, clickable results
    (each has id/name/type/degree) that open a focused subgraph."""
    return {
        "nodes": memory_graph.search_nodes(
            _resolve_graph_root(project), q, limit=max(1, min(int(limit), 100))
        )
    }


@get("/system/memory/graph/subgraph", sync_to_thread=True)
def graph_subgraph(
    node_id: str, project: Optional[str] = None, hops: int = 1, max_nodes: int = 60
) -> dict[str, Any]:
    """The node + its N-hop neighborhood (nodes + connecting edges) for visualization.
    ``node_id`` is a query param (ids contain ':')."""
    return memory_graph.subgraph(
        _resolve_graph_root(project),
        node_id,
        hops=max(1, min(int(hops), 3)),
        max_nodes=max(10, min(int(max_nodes), 200)),
    )


@get("/system/memory/graph/node", sync_to_thread=True)
def graph_node_detail(node_id: str, project: Optional[str] = None) -> dict[str, Any]:
    """Full detail for one node: description, aliases, source, and typed neighbors."""
    detail = memory_graph.node_detail(_resolve_graph_root(project), node_id)
    if detail is None:
        raise NotFoundException(detail=f"node not found: {node_id}")
    return detail


# --- Persistent async query dispatcher + history (leave-the-page + read-later) ---

_MEMORY_QUERY_KINDS = {
    "doctor": lambda p: ti.build_doctor(refresh=True),
    "lint": lambda p: ti.build_lint(refresh=True),
    "config": lambda p: ti.config_status(),
    "graph_status": lambda p: ti.graph_status(),
    "activity_summary": lambda p: ti.build_activity_summary(
        period=p.get("period", "day"),
        day=p.get("date"),
        project=p.get("project"),
        max_turns=p.get("max_turns"),
        refresh=True,
    ),
    "decisions": lambda p: ti.build_decisions(
        period=p.get("period", "day"),
        day=p.get("date"),
        project=p.get("project"),
        include_agent=p.get("include_agent", True),
        max_turns=p.get("max_turns"),
        refresh=True,
    ),
    "graph_query": lambda p: ti.query_graph(
        str(p.get("q", "")), top_k=int(p.get("top_k", 8)), kind=p.get("kind")
    ),
    "sessions": lambda p: ti.list_sessions(project=p.get("project"), limit=p.get("limit")),
}


def _memory_job_label(kind: str, params: dict) -> str:
    if kind == "graph_query":
        return str(params.get("q", ""))[:120]
    if kind in ("activity_summary", "decisions"):
        return f"{params.get('period', 'day')} · {params.get('project') or 'all projects'}"
    if kind == "sessions" and params.get("project"):
        return str(params["project"])
    return kind


@post("/system/memory/query", sync_to_thread=False)
def run_memory_query(data: dict[str, Any]) -> dict[str, Any]:
    """Run a memory/observability query as a PERSISTED BACKGROUND job so the operator
    can navigate away and read the result (and past results) later. Body
    ``{kind, params?}``; returns ``{job_id, kind, status}``. Poll via
    ``/system/memory/tesserae/jobs/{job_id}``; list history via ``/system/memory/jobs``.
    """
    kind = (data or {}).get("kind")
    params = (data or {}).get("params") or {}
    if not isinstance(params, dict):
        raise ValidationException(detail="params must be an object")
    if kind == "research":
        return start_research(params)  # typed launcher (validates ints + persists)
    fn_factory = _MEMORY_QUERY_KINDS.get(kind)
    if fn_factory is None:
        raise ValidationException(
            detail=f"unknown memory query kind: {kind!r} "
            f"(expected one of {sorted(_MEMORY_QUERY_KINDS) + ['research']})"
        )
    job_id = ti.run_memory_job(
        kind,
        lambda: fn_factory(params),
        label=_memory_job_label(kind, params),
        params=params,
        project=params.get("project"),
    )
    return {"job_id": job_id, "kind": kind, "status": "running"}


@get("/system/memory/jobs", sync_to_thread=True)
def list_memory_jobs(kind: Optional[str] = None, limit: int = 50) -> dict[str, Any]:
    """History of memory queries, newest first, WITHOUT result blobs (read one via the
    poll endpoint ``/system/memory/tesserae/jobs/{job_id}``). Optional ``kind`` filter."""
    from app.db import memory_jobs

    return {"jobs": memory_jobs.list_jobs(kind=kind, limit=limit)}


memory_system_router = Router(
    path="/admin",
    route_handlers=[
        run_memory_query,
        list_memory_jobs,
        list_memory_systems,
        get_activity_summary,
        get_decisions,
        get_memory_doctor,
        get_memory_lint,
        get_graph_status,
        query_graph,
        graph_overview,
        graph_search_nodes,
        graph_subgraph,
        graph_node_detail,
        get_memory_config,
        engine_refresh,
        start_research,
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
