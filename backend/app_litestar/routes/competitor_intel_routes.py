"""Competitor-intelligence routes (phase 23, REQ-27 add / REQ-30 ranked signals).

The operator-facing surface for the competitive-intelligence MVP. A thin
project-scoped router over the wave-1/2/3 services + migration-171 tables:

* **POST** ``/{project_id}/competitor-intel/sources`` — add a watched source by
  URL (``CompetitorSourceService.add_source``); ``kind`` is auto-detected and the
  optional ``label`` NEVER blocks the insert (REQ-27 / wizard-defaults rule).
* **GET** ``/{project_id}/competitor-intel/sources`` — list the project's sources.
* **GET** ``/{project_id}/competitor-intel/signals`` — ranked ``detected_signal``
  rows for the project's sources, ``ORDER BY score DESC, created_at DESC``
  (the 23-03 ranking contract — highest competitive signal first).
* **GET** ``/{project_id}/competitor-intel/signals/stream`` — an SSE ``Stream``
  that emits one ``event: signal`` frame per newly-seen ranked signal and a
  terminal ``event: done``. COPIES the proven ``harness_setup_stream`` generator
  shape (grd_routes.py:845) / the trace SSE (agents_and_tracing.py:228) — it does
  NOT invent a new streaming mechanism: poll the DB ~1s, diff on signal id,
  ``yield "event: signal\\ndata: {json}\\n\\n"``, deadline ~600s.

Persistence is raw SQLite via ``app.database.get_connection`` (repo convention,
no ORM). The signal read joins ``detected_signal`` to ``competitor_source`` so a
signal is only surfaced for a source that belongs to ``project_id``.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from litestar import Router, get, post
from litestar.exceptions import ClientException, NotFoundException
from litestar.response import Stream

from app.database import get_connection
from app.db.owned_entities import can_access
from app.db.projects import get_project
from app.services.competitor_source_service import (
    KIND_HN_QUERY,
    CompetitorSourceService,
)

from ..auth import Caller

logger = logging.getLogger(__name__)

# Explicit ``kind`` values the add-source route accepts. The PRIMARY use is
# ``hn_query`` — a NON-URL identifier (a search query) that ``detect_kind`` can't
# host-route. Any other kind is auto-detected from the URL, so an explicit kind
# outside this allowlist is rejected rather than stored as a free-text typo.
# Only hn_query legitimately needs an explicit kind — its identifier is a search
# query, not a URL that detect_kind can classify. URL-based kinds MUST be
# host-detected; accepting them here would let a caller mislabel a source and
# point the wrong adapter at a bogus identifier.
_ALLOWED_EXPLICIT_KINDS = frozenset({KIND_HN_QUERY})

# Columns returned for a ranked signal row (detected_signal, migration 171).
# kind/url/label come from the joined competitor_source so the dashboard can
# label a signal without a second round-trip.
_SIGNAL_COLUMNS = (
    "s.id AS id",
    "s.source_id AS source_id",
    "s.summary AS summary",
    "s.signal_type AS signal_type",
    "s.score AS score",
    "s.created_at AS created_at",
    "src.kind AS kind",
    "src.url AS url",
    "src.label AS label",
)

# Poll cadence + deadline for the SSE stream — identical knobs to
# harness_setup_stream (1s poll, 10-minute ceiling).
_STREAM_POLL_SECONDS = 1.0
_STREAM_DEADLINE_SECONDS = 600.0


def _assert_project_access(project_id: str, caller: Caller) -> None:
    """404 if the project doesn't exist OR the caller can't access it.

    Per-object ownership guard (IDOR): a source/signal belongs to a project, so
    only the project's owner or an admin may read or write it. ``can_access``
    passes NON-existent rows through (so handlers can 404), hence the explicit
    existence check first; a 404 (not 403) on denial avoids leaking which ids
    exist. Mirrors projects._assert_project_access.
    """
    if not get_project(project_id):
        raise NotFoundException(detail="Project not found")
    if not can_access("projects", project_id, caller.user_id, caller.role):
        raise NotFoundException(detail="Project not found")


def _ranked_signals(project_id: str) -> list[dict[str, Any]]:
    """Ranked detected_signal rows for ``project_id``'s sources.

    Joins ``detected_signal`` → ``competitor_source`` (so a signal is scoped to
    the project) and orders by the 23-03 ranking key: ``score DESC`` then
    ``created_at DESC``. A NULL score sorts last (NULLS LAST emulation via the
    ``score IS NULL`` leading sort term) so a degraded/unscored signal never
    outranks a real one.
    """
    cols = ", ".join(_SIGNAL_COLUMNS)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT {cols}
            FROM detected_signal AS s
            JOIN competitor_source AS src ON src.id = s.source_id
            WHERE src.project_id = ?
            ORDER BY (s.score IS NULL), s.score DESC, s.created_at DESC, s.id DESC
            """,
            (project_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Sources (REQ-27)
# ---------------------------------------------------------------------------


@post("/{project_id:str}/competitor-intel/sources", status_code=201, sync_to_thread=False)
def add_competitor_source(project_id: str, data: dict | None, caller: Caller) -> dict[str, Any]:
    """Add a watched competitor source by URL (or query); return the persisted row.

    Body: ``{"url": str, "label"?: str, "kind"?: str}``. ``url`` is required (a
    source must point somewhere) — for an ``hn_query`` source the operator sends
    the SEARCH QUERY (a company / product name) in the ``url`` field (the
    identifier column), NOT a URL. ``label`` is OPTIONAL — a missing/blank label
    is fine and NEVER blocks the insert (REQ-27 / wizard-defaults rule); the
    service normalizes whitespace-only to NULL. ``kind`` is OPTIONAL: when omitted
    it is auto-detected from the URL host; when provided it MUST be one of the
    known kinds (``_ALLOWED_EXPLICIT_KINDS``) and is used verbatim — this is the
    path that lets a non-URL ``hn_query`` identifier through without host routing.
    """
    _assert_project_access(project_id, caller)
    body = data or {}
    url = body.get("url")
    if not url or not isinstance(url, str) or not url.strip():
        raise ClientException(detail="url is required")
    label = body.get("label")
    kind = body.get("kind")
    if kind is not None:
        if not isinstance(kind, str) or kind not in _ALLOWED_EXPLICIT_KINDS:
            raise ClientException(detail="unknown source kind")
    source = CompetitorSourceService.add_source(project_id, url.strip(), label=label, kind=kind)
    return {"source": source}


@get("/{project_id:str}/competitor-intel/sources", sync_to_thread=False)
def list_competitor_sources(project_id: str, caller: Caller) -> dict[str, Any]:
    """List the project's competitor sources, newest first."""
    _assert_project_access(project_id, caller)
    return {"sources": CompetitorSourceService.list_sources(project_id)}


# ---------------------------------------------------------------------------
# Signals (REQ-30) — ranked read + SSE stream
# ---------------------------------------------------------------------------


@get("/{project_id:str}/competitor-intel/signals", sync_to_thread=False)
def list_competitor_signals(project_id: str, caller: Caller) -> dict[str, Any]:
    """Ranked detected_signal rows for the project (score DESC, created_at DESC)."""
    _assert_project_access(project_id, caller)
    return {"signals": _ranked_signals(project_id)}


@get(
    "/{project_id:str}/competitor-intel/signals/stream",
    media_type="text/event-stream",
    sync_to_thread=False,
)
async def competitor_signals_stream(project_id: str, caller: Caller) -> Stream:
    """SSE stream of newly-detected ranked signals.

    Polls the DB every ~1s, emits an ``event: signal`` frame per signal id not
    yet seen (each frame carries the full ranked row), and a terminal
    ``event: done`` frame when the deadline is hit. Mirrors the proven
    ``harness_setup_stream`` Stream (grd_routes.py:845) / trace SSE
    (agents_and_tracing.py:228) — same poll/diff/yield/deadline shape; the diff
    key here is the signal ``id`` (signals are append-only, so an id is seen
    exactly once). The first poll replays the existing backlog so a late
    subscriber still gets the current ranked set.
    """
    _assert_project_access(project_id, caller)

    async def event_generator():
        seen: set[str] = set()
        deadline = asyncio.get_event_loop().time() + _STREAM_DEADLINE_SECONDS
        while True:
            for row in _ranked_signals(project_id):
                sig_id = row.get("id")
                if sig_id in seen:
                    continue
                seen.add(sig_id)
                yield f"event: signal\ndata: {json.dumps(row, default=str)}\n\n"
            if asyncio.get_event_loop().time() > deadline:
                yield (
                    "event: done\n"
                    f"data: {json.dumps({'reason': 'max_duration', 'count': len(seen)})}\n\n"
                )
                return
            await asyncio.sleep(_STREAM_POLL_SECONDS)

    return Stream(event_generator(), media_type="text/event-stream")


competitor_intel_router = Router(
    path="/api/projects",
    route_handlers=[
        add_competitor_source,
        list_competitor_sources,
        list_competitor_signals,
        competitor_signals_stream,
    ],
)
