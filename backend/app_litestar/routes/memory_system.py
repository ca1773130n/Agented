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
from app.services import tesserae_integration as ti


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
            capture_output=True, text=True, timeout=5,
        )
        candidate = (result.stdout or result.stderr or "").strip().splitlines()
        first = candidate[0] if candidate else ""
        if (
            result.returncode == 0
            and first
            and not first.lower().startswith("usage:")
        ):
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
            "SELECT id, name, local_path, tesserae_project_root "
            "FROM projects ORDER BY name COLLATE NOCASE"
        ).fetchall():
            root = row["tesserae_project_root"]
            entry: dict[str, Any] = {
                "project_id": row["id"],
                "project_name": row["name"],
                "local_path": row["local_path"],
                "tesserae_project_root": root,
                "enabled": bool(root),
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
                        entry["last_imported_at"] = (
                            datetime.fromtimestamp(mtime, tz=timezone.utc)
                            .isoformat()
                        )
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


@get("/system/memory/tesserae/projects", sync_to_thread=True)
def list_tesserae_projects() -> dict[str, Any]:
    """Per-project Tesserae state — for the Settings table."""
    return {"projects": _tesserae_per_project_state()}


# ---------------------------------------------------------------------------
# Per-project enable / disable / refresh
# ---------------------------------------------------------------------------

@post(
    "/system/memory/tesserae/projects/{project_id:str}",
    sync_to_thread=True,
)
def set_tesserae_for_project(
    project_id: str, data: Optional[dict[str, Any]] = None,
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
    if "root" not in payload:
        raise ValidationException(detail="missing 'root' in request body")
    raw_root = payload["root"]

    with get_connection() as conn:
        exists = conn.execute(
            "SELECT 1 FROM projects WHERE id = ?", (project_id,),
        ).fetchone()
        if not exists:
            raise NotFoundException(detail=f"project not found: {project_id}")

        if raw_root in (None, ""):
            conn.execute(
                "UPDATE projects SET tesserae_project_root = NULL "
                "WHERE id = ?", (project_id,),
            )
        else:
            if not isinstance(raw_root, str):
                raise ValidationException(detail="'root' must be a string or null")
            resolved = str(Path(raw_root).expanduser().resolve())
            conn.execute(
                "UPDATE projects SET tesserae_project_root = ? WHERE id = ?",
                (resolved, project_id),
            )
        conn.commit()

    # Return the fresh per-project state (single row).
    state = [
        p for p in _tesserae_per_project_state()
        if p["project_id"] == project_id
    ]
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
            "SELECT 1 FROM projects WHERE id = ?", (project_id,),
        ).fetchone()
    if not row:
        raise NotFoundException(detail=f"project not found: {project_id}")
    result = ti.export_sessions_to_tesserae(project_id)
    return {"project_id": project_id, **result}


memory_system_router = Router(
    path="/admin",
    route_handlers=[
        list_memory_systems,
        list_tesserae_projects,
        set_tesserae_for_project,
        refresh_tesserae_for_project,
    ],
)
