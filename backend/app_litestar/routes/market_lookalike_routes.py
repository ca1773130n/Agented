"""Market-lookalike routes (phase 27 — the operator scan→review→accept loop).

The operator-facing surface for P5 of the competitive-intelligence work: a
project-scoped router that drives the 27-03 ``MarketLookalikeService`` —
provider-aware ``scan`` (BUY-gated), the market-lookalike review queue, one-click
``accept`` (→ a watched ``product_url`` competitor source) and ``dismiss``. It
mirrors ``discovery_routes`` verbatim (same IDOR guard + 404/409 mapping); the
accept/dismiss handlers delegate STRAIGHT THROUGH to the shared service:

* **POST** ``/{project_id}/lookalikes/scan`` — resolve the provider and (if keyed)
  call ``MarketLookalikeService.scan_project(project_id, seed=...)``; returns its
  dict verbatim (``{provider, outcome, scanned, suggestions}``). The
  ``outcome='not_configured'`` / ``provider=None`` BUY-gate case is a NORMAL 200 —
  NEVER a 4xx/5xx; the UI renders the "configure a provider" CTA. Declared
  ``sync_to_thread=True`` so the (potential) external provider call runs on the
  worker thread pool and never blocks the event loop (the discovery scan
  discipline).
* **GET** ``/{project_id}/lookalikes/suggestions`` — the market review queue:
  ``{provider: <active provider name or None>, suggestions: <market-kind rows>}``
  so the UI knows CTA-vs-queue without a second round-trip.
* **POST** ``/{project_id}/lookalikes/suggestions/{sid}/accept`` — promote a
  lookalike into a watched ``competitor_source`` (``product_url`` lane); returns
  ``{source, suggestion}``.
* **POST** ``/{project_id}/lookalikes/suggestions/{sid}/dismiss`` — flip the
  suggestion's status to ``dismissed`` (sticky across re-scans); returns
  ``{suggestion}``.

EVERY handler calls ``_assert_project_access(project_id, caller)`` FIRST — the
per-object IDOR guard (404, not 403, on a foreign/unknown project, so existence
never leaks; the P1 lesson). ``caller: Caller`` is injected app-wide so this
router needs no per-router dependency wiring. An accept/dismiss against an unknown
``sid`` (``ValueError``) → 404; a conflicting promote/dismiss (``PromotionConflict``)
→ 409 — VERBATIM from ``discovery_routes``.

NO live provider call ever runs in the default/CI install: ``active_provider()``
resolves to ``None`` when unconfigured, so the BUY-gate short-circuit holds and the
live integration is a deferred, configured-when-keyed seam.
"""

from __future__ import annotations

from typing import Any

from litestar import Router, get, post
from litestar.exceptions import ClientException, NotFoundException
from litestar.status_codes import HTTP_409_CONFLICT

from app.db.owned_entities import can_access
from app.db.projects import get_project
from app.services.discovery_service import PromotionConflict
from app.services.market_lookalike_service import MarketLookalikeService

from ..auth import Caller


def _assert_project_access(project_id: str, caller: Caller) -> None:
    """404 if the project doesn't exist OR the caller can't access it.

    Per-object ownership guard (IDOR): a market-lookalike suggestion belongs to a
    project, so only the project's owner or an admin may scan it, read its queue,
    or accept/dismiss a row. ``can_access`` passes NON-existent rows through (so
    handlers can 404), hence the explicit existence check first; a 404 (not 403)
    on denial avoids leaking which ids exist. Copied verbatim from
    ``discovery_routes._assert_project_access`` (the P1 IDOR lesson).
    """
    if not get_project(project_id):
        raise NotFoundException(detail="Project not found")
    if not can_access("projects", project_id, caller.user_id, caller.role):
        raise NotFoundException(detail="Project not found")


# ---------------------------------------------------------------------------
# Scan — provider-aware, BUY-gated, kept OFF the event loop
# ---------------------------------------------------------------------------


@post("/{project_id:str}/lookalikes/scan", sync_to_thread=True)
def run_lookalike_scan(
    project_id: str, caller: Caller, data: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Run a provider-aware market-lookalike scan for a project.

    Reads an optional ``seed`` from the JSON body and delegates to
    ``MarketLookalikeService.scan_project(project_id, seed=seed)``, returning its
    dict verbatim (``{provider, outcome, scanned, suggestions}``). The
    ``outcome='not_configured'`` / ``provider=None`` BUY-gate case is a NORMAL 200
    — NEVER a 4xx/5xx; the UI renders the "configure a provider" CTA. Declared
    ``sync_to_thread=True`` so the (potential) external provider call runs on the
    worker thread pool and never stalls the event loop.
    """
    _assert_project_access(project_id, caller)
    seed = (data or {}).get("seed")
    return MarketLookalikeService.scan_project(project_id, seed=seed)


# ---------------------------------------------------------------------------
# Suggestions — review queue + accept / dismiss
# ---------------------------------------------------------------------------


@get("/{project_id:str}/lookalikes/suggestions", sync_to_thread=False)
def list_lookalike_suggestions(project_id: str, caller: Caller) -> dict[str, Any]:
    """The market-lookalike review queue (``suggested``, market-kind only).

    Returns ``{provider: <active provider name or None>, suggestions: [...]}`` —
    the provider name (resolved via ``registry.active_provider()``) lets the UI
    pick CTA-vs-queue, and the suggestions are the market-kind rows only (the
    github_repo discovery queue never bleeds in).
    """
    _assert_project_access(project_id, caller)

    # Resolve the active provider name (or None) so the UI knows CTA-vs-queue.
    import app.services.lookalike_providers as _lp  # noqa: F401 (register-on-import)
    from app.services.lookalike_providers import registry

    provider = registry.active_provider()
    return {
        "provider": provider.name if provider is not None else None,
        "suggestions": MarketLookalikeService.list_suggestions(project_id),
    }


@post("/{project_id:str}/lookalikes/suggestions/{sid:str}/accept", sync_to_thread=False)
def accept_lookalike_suggestion(project_id: str, sid: str, caller: Caller) -> dict[str, Any]:
    """Promote a market lookalike into a watched ``competitor_source``.

    Delegates to ``MarketLookalikeService.promote_suggestion(project_id, sid)`` —
    project-SCOPED (a suggestion owned by another project 404s, not just an unknown
    id), IDEMPOTENT, and concurrency-safe. The promoted lookalike lands on the
    ``product_url`` lane. Returns ``{source, suggestion}``.

    * unknown / foreign-project ``sid`` (``ValueError``) → 404.
    * accepting a ``dismissed`` suggestion (``PromotionConflict``) → 409.
    """
    _assert_project_access(project_id, caller)
    try:
        return MarketLookalikeService.promote_suggestion(project_id, sid)
    except PromotionConflict as exc:
        raise ClientException(detail=str(exc), status_code=HTTP_409_CONFLICT) from None
    except ValueError:
        raise NotFoundException(detail="Market lookalike suggestion not found") from None


@post("/{project_id:str}/lookalikes/suggestions/{sid:str}/dismiss", sync_to_thread=False)
def dismiss_lookalike_suggestion(project_id: str, sid: str, caller: Caller) -> dict[str, Any]:
    """Dismiss a market lookalike — flip its status to ``dismissed`` (sticky).

    Delegates to ``MarketLookalikeService.dismiss_suggestion(project_id, sid)``,
    project-SCOPED and claim-safe. Returns ``{suggestion}``.

    * unknown / foreign-project ``sid`` (``ValueError``) → 404.
    * dismissing a row mid-promotion (``PromotionConflict``) → 409.
    """
    _assert_project_access(project_id, caller)
    try:
        return MarketLookalikeService.dismiss_suggestion(project_id, sid)
    except PromotionConflict as exc:
        raise ClientException(detail=str(exc), status_code=HTTP_409_CONFLICT) from None
    except ValueError:
        raise NotFoundException(detail="Market lookalike suggestion not found") from None


market_lookalike_router = Router(
    path="/api/projects",
    route_handlers=[
        run_lookalike_scan,
        list_lookalike_suggestions,
        accept_lookalike_suggestion,
        dismiss_lookalike_suggestion,
    ],
)
