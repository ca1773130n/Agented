"""Agent-assisted discovery routes (phase 24 — the operator discover→review loop).

The operator-facing surface for P2 of phase 24: from a project's watched
``github_repo`` competitor sources, surface ranked *similar* repos with a
human-readable "why", and let the operator promote the good ones into the P1
competitor monitor or dismiss the noise. A thin project-scoped router over the
24-01 DAO + 24-02 similarity/ranking + 24-03 ``DiscoveryService`` orchestration:

* **POST** ``/{project_id}/discovery/scan`` — run the heavy GitHub fan-out
  (``DiscoveryService.scan_project``) and persist ranked ``discovery_suggestion``
  rows; returns ``{scanned, suggestions, readme_mode}``. This is the ONE heavy,
  authenticated-GitHub method in the router, so the handler is declared
  ``sync_to_thread=True`` — it runs on the worker thread pool and NEVER blocks
  the event loop (the 24-03 COST WARNING).
* **GET** ``/{project_id}/discovery/suggestions`` — the active review queue:
  ``DiscoveryService.list_suggestions(project_id, statuses=['suggested'])``,
  ranked highest-score-first (NULLs last), each row carrying ``score`` + ``reason``
  + ``evidence`` (the 24-01/24-03 contract).
* **POST** ``/{project_id}/discovery/suggestions/{sid}/accept`` — promote a
  suggestion into a watched ``competitor_source`` via
  ``DiscoveryService.promote_suggestion`` (which calls
  ``add_source(origin='discovery')`` internally); returns ``{source, suggestion}``.
* **POST** ``/{project_id}/discovery/suggestions/{sid}/dismiss`` — flip the
  suggestion's status to ``dismissed`` (sticky across re-scans); returns
  ``{suggestion}``.

EVERY handler calls ``_assert_project_access(project_id, caller)`` FIRST — the
per-object IDOR guard copied verbatim from ``competitor_intel_routes.py`` (404,
not 403, on a foreign/unknown project, so existence never leaks; the P1 lesson).
``caller: Caller`` is injected app-wide (``main.py`` ``Provide(provide_caller)``)
so this router needs no per-router dependency wiring.

Persistence is the 24-01 raw-SQLite DAO via ``DiscoveryService`` — no DB code
here. An accept/dismiss against an unknown ``sid`` (``ValueError`` out of the
service) maps to a 404 (the suggestion id is also a per-object resource).
"""

from __future__ import annotations

from typing import Any

from litestar import Router, get, post
from litestar.exceptions import ClientException, NotFoundException
from litestar.status_codes import HTTP_409_CONFLICT

from app.db.owned_entities import can_access
from app.db.projects import get_project
from app.services.discovery_service import DiscoveryService, PromotionConflict

from ..auth import Caller


def _assert_project_access(project_id: str, caller: Caller) -> None:
    """404 if the project doesn't exist OR the caller can't access it.

    Per-object ownership guard (IDOR): a discovery suggestion belongs to a
    project, so only the project's owner or an admin may scan it, read its queue,
    or accept/dismiss a row. ``can_access`` passes NON-existent rows through (so
    handlers can 404), hence the explicit existence check first; a 404 (not 403)
    on denial avoids leaking which ids exist. Copied verbatim from
    ``competitor_intel_routes._assert_project_access`` (the P1 IDOR lesson).
    """
    if not get_project(project_id):
        raise NotFoundException(detail="Project not found")
    if not can_access("projects", project_id, caller.user_id, caller.role):
        raise NotFoundException(detail="Project not found")


# ---------------------------------------------------------------------------
# Scan — the heavy GitHub fan-out (kept OFF the event loop)
# ---------------------------------------------------------------------------


@post("/{project_id:str}/discovery/scan", sync_to_thread=True)
def run_discovery_scan(project_id: str, caller: Caller) -> dict[str, Any]:
    """Run the discovery scan for a project's watched github seeds.

    Delegates to ``DiscoveryService.scan_project`` — the heavy, read-only,
    authenticated GitHub fan-out (S1 shared-topics + S2 stargazer-overlap + an
    optional bounded README lens, internally capped). The handler is declared
    ``sync_to_thread=True`` so the blocking GitHub/IO work runs on the worker
    thread pool and never stalls the event loop (the 24-03 COST WARNING). The
    service's own caps (``TOP_N``, ``_README_CANDIDATE_CAP``) bound the fan-out;
    with no PAT the client short-circuits to zero candidates (no error).

    Returns ``{scanned, suggestions, readme_mode}`` — seeds processed, rows
    written this scan, and the resolved README lens.
    """
    _assert_project_access(project_id, caller)
    return DiscoveryService.scan_project(project_id)


# ---------------------------------------------------------------------------
# Suggestions — review queue + accept / dismiss
# ---------------------------------------------------------------------------


@get("/{project_id:str}/discovery/suggestions", sync_to_thread=False)
def list_discovery_suggestions(project_id: str, caller: Caller) -> dict[str, Any]:
    """The active review queue: ``status='suggested'`` rows, highest score first.

    Reads only the active queue (``statuses=['suggested']``) so an accepted /
    dismissed verdict drops out (the 24-01 sticky-verdict contract). Each row
    carries ``score`` + ``reason`` + ``evidence`` for the dashboard's "why" chip.
    """
    _assert_project_access(project_id, caller)
    return {"suggestions": DiscoveryService.list_suggestions(project_id, statuses=["suggested"])}


@post("/{project_id:str}/discovery/suggestions/{sid:str}/accept", sync_to_thread=False)
def accept_discovery_suggestion(project_id: str, sid: str, caller: Caller) -> dict[str, Any]:
    """Promote a suggestion into a watched ``competitor_source`` (origin='discovery').

    Delegates to ``DiscoveryService.promote_suggestion(project_id, sid)`` — which
    is project-SCOPED (a suggestion owned by another project 404s, not just an
    unknown id — the IDOR fix) and IDEMPOTENT (a re-accept of an already-added
    suggestion returns the existing source without duplicating it). Returns
    ``{source, suggestion}``.

    * unknown / foreign-project ``sid`` (``ValueError``) → 404.
    * accepting a ``dismissed`` suggestion (``PromotionConflict``) → 409.
    """
    _assert_project_access(project_id, caller)
    try:
        return DiscoveryService.promote_suggestion(project_id, sid)
    except PromotionConflict as exc:
        raise ClientException(detail=str(exc), status_code=HTTP_409_CONFLICT) from None
    except ValueError:
        raise NotFoundException(detail="Discovery suggestion not found") from None


@post("/{project_id:str}/discovery/suggestions/{sid:str}/dismiss", sync_to_thread=False)
def dismiss_discovery_suggestion(project_id: str, sid: str, caller: Caller) -> dict[str, Any]:
    """Dismiss a suggestion — flip its status to ``dismissed`` (sticky on re-scan).

    Delegates to ``DiscoveryService.dismiss_suggestion(project_id, sid)``, which is
    project-SCOPED (a suggestion owned by another project 404s — the IDOR fix) and
    CONDITIONAL (it refuses to clobber a row a concurrent promotion is mid-claim on).
    Returns ``{suggestion}``.

    * unknown / foreign-project ``sid`` (``ValueError``) → 404.
    * dismissing a row mid-promotion (``'claiming'`` — ``PromotionConflict``) → 409,
      so the dismiss can never orphan the promoter's just-added source.
    """
    _assert_project_access(project_id, caller)
    try:
        return DiscoveryService.dismiss_suggestion(project_id, sid)
    except PromotionConflict as exc:
        raise ClientException(detail=str(exc), status_code=HTTP_409_CONFLICT) from None
    except ValueError:
        raise NotFoundException(detail="Discovery suggestion not found") from None


discovery_router = Router(
    path="/api/projects",
    route_handlers=[
        run_discovery_scan,
        list_discovery_suggestions,
        accept_discovery_suggestion,
        dismiss_discovery_suggestion,
    ],
)
