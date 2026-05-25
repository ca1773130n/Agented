"""Tesserae integration — per-project knowledge graph consolidator.

Tesserae compiles code + docs + agent sessions into a typed graph
(``CodeFile``, ``CodeMethod``, ``Session``, ``SessionTakeaway``,
``SessionDecision``, ``SessionInsight`` etc.) and exposes graph
queries via its MCP server + CLI. This module is the producer-side
plumbing that pushes Agented session history into Tesserae's
``HarnessSession`` import surface.

## How it wires up

The integration is OPT-IN per project. A project enables Tesserae by
setting ``projects.tesserae_project_root`` to the absolute path of its
Tesserae workspace (the directory containing ``.tesserae/``). Until
that column is set, the integration is a no-op.

## Why session-completion fires a FULL batch rebuild

``tesserae project sessions import`` is destructive — it removes prior
session JSON/MD files before writing the new set. So we can't
incrementally append one session; every import re-emits the full
session set for the project. For projects with ≤500 sessions this
is cheap (kilobytes of JSON, a single subprocess call). When a project
crosses that threshold a periodic batch importer should replace the
per-completion call — see ``_TESSERAE_BATCH_MAX_SESSIONS``.

## Best-effort posture

Every Tesserae call is wrapped in a try/except and logged. Failures
NEVER block the session-completion event chain — observability must
not break the producer.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)


_TESSERAE_CMD = shutil.which("tesserae") or "tesserae"
_TESSERAE_BATCH_MAX_SESSIONS = 500
_TESSERAE_IMPORT_TIMEOUT = 60  # subprocess timeout, seconds


# ---------------------------------------------------------------------------
# Project linkage
# ---------------------------------------------------------------------------

def get_tesserae_root(project_id: str) -> Optional[Path]:
    """Return the absolute Tesserae workspace path for a project, or
    ``None`` if Tesserae is not enabled for this project (column unset)
    or the project doesn't exist."""
    try:
        from app.db.connection import get_connection

        with get_connection() as conn:
            row = conn.execute(
                "SELECT tesserae_project_root FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
        if not row:
            return None
        raw = row["tesserae_project_root"]
        if not raw:
            return None
        return Path(raw).expanduser()
    except Exception:
        logger.warning(
            "tesserae: project lookup failed for %s",
            project_id, exc_info=True,
        )
        return None


def set_tesserae_root(project_id: str, root: Path) -> None:
    """Persist the Tesserae workspace path on the project. Idempotent
    re-set is fine."""
    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute(
            "UPDATE projects SET tesserae_project_root = ? WHERE id = ?",
            (str(root.resolve()), project_id),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Session normalization — Agented row → Tesserae HarnessSession dict
# ---------------------------------------------------------------------------

def _normalize_super_agent_session(row: dict) -> dict[str, Any]:
    """Map a ``super_agent_sessions`` row to Tesserae's HarnessSession
    shape. ``conversation_log`` may be a JSON array of role/content
    entries; we extract a redacted preview + counts but don't include
    the full transcript in the import (size + redaction concerns)."""
    log_raw = row.get("conversation_log") or "[]"
    try:
        parsed = json.loads(log_raw)
    except (TypeError, ValueError):
        parsed = []
    if not isinstance(parsed, list):
        parsed = []

    message_count = len(parsed)
    preview_chunks: list[str] = []
    for entry in parsed[:3]:
        if isinstance(entry, dict):
            content = entry.get("content")
            if isinstance(content, str):
                preview_chunks.append(content[:300])
    preview = "\n---\n".join(preview_chunks)[:1200]

    return {
        "harness": "claude",
        "agent_label": row.get("super_agent_id") or "super_agent",
        "started_at": row.get("started_at") or "",
        "ended_at": row.get("ended_at") or "",
        "message_count": message_count,
        "tool_call_count": 0,
        "tools_used": [],
        "files_touched": [],
        "commands_run": [],
        "decisions": [],
        "errors": [],
        "redacted_preview": preview,
        "title": row.get("name") or "",
        "summary": (preview[:240] if preview else ""),
    }


def _normalize_trigger_execution(row: dict) -> dict[str, Any]:
    """Map an ``execution_logs`` row to HarnessSession shape. Parses
    the Claude JSONL stream for tools_used + files_touched."""
    log_raw = row.get("stdout_log") or ""
    tools_used: set[str] = set()
    files_touched: set[str] = set()
    if log_raw:
        try:
            from app.services.harness_failure_annotator import _to_claude_jsonl
            bridged = _to_claude_jsonl(log_raw)
        except Exception:
            bridged = log_raw
        for line in bridged.splitlines():
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if obj.get("type") != "assistant":
                continue
            for block in (obj.get("message") or {}).get("content") or []:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use":
                    name = block.get("name")
                    if isinstance(name, str):
                        tools_used.add(name)
                    args = block.get("input") or {}
                    for key in ("file_path", "path", "filename"):
                        fp = args.get(key) if isinstance(args, dict) else None
                        if isinstance(fp, str):
                            files_touched.add(fp)

    return {
        "harness": row.get("backend_type") or "claude",
        "agent_label": row.get("trigger_id") or row.get("trigger_type") or "trigger",
        "started_at": row.get("started_at") or "",
        "ended_at": row.get("completed_at") or "",
        "message_count": 0,
        "tool_call_count": len(tools_used),
        "tools_used": sorted(tools_used),
        "files_touched": sorted(files_touched),
        "commands_run": [],
        "decisions": [],
        "errors": [],
        "redacted_preview": (log_raw[:1200] if log_raw else ""),
        "title": row.get("execution_id") or "",
        "summary": "",
    }


def _slug(text: str) -> str:
    """Tesserae-style slug. Mirrors ``tesserae.harness_sessions.safe_slug``."""
    out = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(text))
    out = out.strip("-")
    while "--" in out:
        out = out.replace("--", "-")
    return out or "session"


def _build_harness_session(
    session_kind: str,
    session_id: str,
    project_id: str,
    project_name: str,
    project_root: Path,
    decisions: list[str],
) -> Optional[dict[str, Any]]:
    """Compose one HarnessSession dict for ``tesserae project sessions
    import``. Returns ``None`` if the source row is missing or empty."""
    from app.db.connection import get_connection

    base: dict[str, Any] = {
        "id": f"agented:{session_kind}:{session_id}",
        "slug": _slug(session_id),
        "project_name": project_name,
        "project_root": str(project_root.resolve()),
        "metadata": {
            "source": "agented",
            "session_kind": session_kind,
            "session_id": session_id,
            "project_id": project_id,
        },
    }

    with get_connection() as conn:
        if session_kind == "super_agent":
            row = conn.execute(
                "SELECT * FROM super_agent_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if not row:
                return None
            base.update(_normalize_super_agent_session(dict(row)))
        elif session_kind == "trigger_execution":
            row = conn.execute(
                "SELECT * FROM execution_logs WHERE execution_id = ?",
                (session_id,),
            ).fetchone()
            if not row:
                return None
            base.update(_normalize_trigger_execution(dict(row)))
        else:
            # Other kinds (project_session, workflow, team_session) —
            # not normalized yet. Skip rather than emit a half-baked
            # record that would pollute Tesserae's graph.
            return None

    base["decisions"] = decisions
    return base


def _gather_project_decisions(project_id: str) -> dict[str, list[str]]:
    """Map session_id → list of takeaway content strings for applied
    takeaways. Tesserae's ``decisions`` field is meant for short
    action items, so we pass the first 200 chars of each."""
    from app.db.connection import get_connection

    out: dict[str, list[str]] = {}
    with get_connection() as conn:
        for row in conn.execute(
            "SELECT session_id, content FROM session_takeaways "
            "WHERE project_id = ? AND applied = 1 ORDER BY id ASC",
            (project_id,),
        ).fetchall():
            sid = row["session_id"]
            out.setdefault(sid, []).append((row["content"] or "")[:200])
    return out


# ---------------------------------------------------------------------------
# Batch export — every session for the project, normalized
# ---------------------------------------------------------------------------

def _gather_project_sessions(
    project_id: str,
    *,
    limit: int = _TESSERAE_BATCH_MAX_SESSIONS,
) -> list[tuple[str, str]]:
    """Return ``[(session_kind, session_id), ...]`` for the project,
    most-recent-first. Capped at ``limit``."""
    from app.db.connection import get_connection

    out: list[tuple[str, str]] = []
    with get_connection() as conn:
        # super_agent sessions linked by project_id column
        for row in conn.execute(
            "SELECT id FROM super_agent_sessions WHERE project_id = ? "
            "AND status = 'completed' ORDER BY id DESC LIMIT ?",
            (project_id, limit),
        ).fetchall():
            out.append(("super_agent", row["id"]))
        # trigger_executions linked via project_paths
        for row in conn.execute(
            "SELECT DISTINCT e.execution_id FROM execution_logs e "
            "JOIN project_paths pp ON pp.trigger_id = e.trigger_id "
            "WHERE pp.project_id = ? "
            "ORDER BY e.id DESC LIMIT ?",
            (project_id, limit),
        ).fetchall():
            out.append(("trigger_execution", row["execution_id"]))
    return out[:limit]


def _project_name(project_id: str) -> str:
    from app.db.connection import get_connection

    with get_connection() as conn:
        row = conn.execute(
            "SELECT name FROM projects WHERE id = ?", (project_id,),
        ).fetchone()
    return (row and row["name"]) or project_id


def export_sessions_to_tesserae(project_id: str) -> dict[str, Any]:
    """Normalize every completed session for the project and import
    the batch into Tesserae. Returns a result dict with counts.

    Best-effort: caller should treat exceptions as non-fatal.
    """
    root = get_tesserae_root(project_id)
    if root is None:
        return {"imported": 0, "skipped_reason": "tesserae_disabled"}
    if not (root / ".tesserae").is_dir():
        logger.warning(
            "tesserae: workspace not initialized at %s — run "
            "`tesserae project init` in that directory first",
            root,
        )
        return {"imported": 0, "skipped_reason": "tesserae_not_initialized"}

    name = _project_name(project_id)
    decisions_by_session = _gather_project_decisions(project_id)
    sessions = _gather_project_sessions(project_id)
    payload: list[dict[str, Any]] = []
    for kind, sid in sessions:
        rec = _build_harness_session(
            kind, sid, project_id, name, root,
            decisions=decisions_by_session.get(sid, []),
        )
        if rec is not None:
            payload.append(rec)

    if not payload:
        return {"imported": 0, "skipped_reason": "no_sessions"}

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", encoding="utf-8",
        prefix=f"agented-tesserae-{project_id}-", delete=False,
    ) as fh:
        json.dump(payload, fh, ensure_ascii=False)
        tmp_path = fh.name

    try:
        cmd = [
            _TESSERAE_CMD, "project", "sessions", "import",
            tmp_path, "--project", str(root),
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=_TESSERAE_IMPORT_TIMEOUT,
        )
        if result.returncode != 0:
            logger.warning(
                "tesserae: import exit=%s stderr=%s",
                result.returncode, (result.stderr or "").strip()[:300],
            )
            return {
                "imported": 0,
                "skipped_reason": f"import_failed:{result.returncode}",
            }
        return {"imported": len(payload), "stdout": result.stdout.strip()}
    except FileNotFoundError:
        logger.warning(
            "tesserae: CLI not found at %r — skip integration", _TESSERAE_CMD,
        )
        return {"imported": 0, "skipped_reason": "cli_missing"}
    except subprocess.TimeoutExpired:
        logger.warning("tesserae: import timed out after %ds",
                       _TESSERAE_IMPORT_TIMEOUT)
        return {"imported": 0, "skipped_reason": "timeout"}
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Session-completion handler — fires on every completed session
# ---------------------------------------------------------------------------

def on_session_complete(
    session_kind: str,
    session_id: str,
    project_id: Optional[str],
    status: str,
    output: Optional[dict],
) -> None:
    """Handler for ``execution_events.register_session_handler``.

    Tesserae sees only completed sessions on projects that have
    enabled the integration (``projects.tesserae_project_root`` set).
    Every completion triggers a full batch re-import — see module
    docstring for why.

    Best-effort: any error logged, never raised.
    """
    if not project_id:
        return
    if status not in ("completed", "success"):
        # Tesserae's value is in successful trajectories. Failures are
        # captured by the failure annotator + takeaway extractor.
        return
    root = get_tesserae_root(project_id)
    if root is None:
        return
    try:
        result = export_sessions_to_tesserae(project_id)
        logger.debug(
            "tesserae: imported %s sessions for %s after %s/%s",
            result.get("imported"), project_id, session_kind, session_id,
        )
    except Exception:
        logger.warning(
            "tesserae: export failed for %s after %s/%s",
            project_id, session_kind, session_id, exc_info=True,
        )


# ---------------------------------------------------------------------------
# Query — used by the evolver workspace builder
# ---------------------------------------------------------------------------

def ask_tesserae(
    project_id: str, question: str, *, top_k: int = 5,
) -> Optional[str]:
    """Run ``tesserae ask`` for the project's compiled graph. Returns
    Codex-friendly markdown / text or ``None`` on any failure (so the
    evolver workspace builder can fall back gracefully)."""
    root = get_tesserae_root(project_id)
    if root is None:
        return None
    cmd = [
        _TESSERAE_CMD, "ask", question,
        "--project", str(root),
        "--top-k", str(top_k),
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.warning("tesserae: ask failed: %s", exc)
        return None
    if result.returncode != 0:
        logger.warning(
            "tesserae: ask exit=%s stderr=%s",
            result.returncode, (result.stderr or "").strip()[:200],
        )
        return None
    return result.stdout or None
