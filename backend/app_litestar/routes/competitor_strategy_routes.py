"""Competitor-strategy HITL routes (v0.9.0 phase 26 — the P4 strategy loop).

The operator-facing surface for the *analyze → strategize → review* spine. A
thin project-scoped router over the 26-01 DAO (``app.db.competitor_strategies``)
+ the 26-02 ``CompetitorStrategyService.propose`` generator:

* **POST** ``/{project_id}/strategies/generate`` — synthesize the selected
  ``detected_signal`` ids into a behavior-only ``'proposed'`` strategy via
  ``CompetitorStrategyService.propose`` (the ONE LLM method here, so the handler
  is ``sync_to_thread=True`` — the multi-backend LLM call runs on the worker
  thread pool, off the event loop). Body ``{signal_ids, backend_kind?,
  model_override?}``; ``backend_kind`` defaults to ``'claude'`` and the optional
  knobs NEVER block (multi-backend, never claude-only).
* **GET** ``/{project_id}/strategies`` — the project's strategies, newest first
  (``list_strategies``).
* **POST** ``/{project_id}/strategies/{sid}/approve`` — flip ``proposed`` →
  ``approved`` (``set_status``).
* **POST** ``/{project_id}/strategies/{sid}/reject`` — flip → ``rejected``.
* **POST** ``/{project_id}/strategies/{sid}/edit`` — operator edit of
  ``title``/``body`` (``update_body``), which RESETS the legal clearance (§5B
  edit-resets-clearance).
* **POST** ``/{project_id}/strategies/{sid}/legal`` — affirm/deny ONE of the 7
  §5B checklist items (``record_legal_item``); returns the updated strategy so
  the UI sees ``legal_cleared_at`` flip at 7/7.

EVERY handler calls ``_assert_project_access(project_id, caller)`` FIRST — the
per-object IDOR guard copied verbatim from ``competitor_intel_routes.py`` (404,
not 403, on a foreign/unknown project, so existence never leaks; the P1 lesson).
``caller: Caller`` is injected app-wide (``main.py`` ``Provide(provide_caller)``)
so this router needs no per-router dependency wiring.

Every ``{sid}`` handler additionally passes ``project_id=`` to the DAO so a
strategy belonging to ANOTHER project is scoped out (the DAO returns None → 404):
access-guard + scope-guard, both required (the IDOR + cross-project lessons).

The implement step is the 26-04 ``POST /{project_id}/strategies/{sid}/materialize``
route, which re-enforces the non-bypassable ``mark_implementing`` gate
(``LegalGateNotCleared`` → 409, no plan on uncleared) and writes a ``ProjectPlan``
artifact ONLY (zero repo mutation). The DEFERRED auto-code-execution seam
(``start_autoimplement``) is intentionally exposed by NO HTTP route in this MVP.

Persistence is the 26-01 raw-SQLite DAO + the 26-02 service — no DB code here.
DAO ``ValueError`` (unknown legal item / illegal transition) → 400.
"""

from __future__ import annotations

from typing import Any

from litestar import Router, get, post
from litestar.exceptions import ClientException, NotFoundException
from litestar.status_codes import HTTP_409_CONFLICT

from app.db import competitor_strategies
from app.db.competitor_strategies import LegalGateNotCleared
from app.db.owned_entities import can_access
from app.db.projects import get_project
from app.services.competitor_strategy_service import CompetitorStrategyService

from ..auth import Caller


def _assert_project_access(project_id: str, caller: Caller) -> None:
    """404 if the project doesn't exist OR the caller can't access it.

    Per-object ownership guard (IDOR): a strategy belongs to a project, so only
    the project's owner or an admin may generate, read, or mutate it.
    ``can_access`` passes NON-existent rows through (so handlers can 404), hence
    the explicit existence check first; a 404 (not 403) on denial avoids leaking
    which ids exist. Copied verbatim from
    ``competitor_intel_routes._assert_project_access`` (the P1 IDOR lesson).
    """
    if not get_project(project_id):
        raise NotFoundException(detail="Project not found")
    if not can_access("projects", project_id, caller.user_id, caller.role):
        raise NotFoundException(detail="Project not found")


# ---------------------------------------------------------------------------
# Generate — the LLM fan-out (kept OFF the event loop)
# ---------------------------------------------------------------------------


@post("/{project_id:str}/strategies/generate", sync_to_thread=True)
def generate_strategy(project_id: str, data: dict | None, caller: Caller) -> dict[str, Any]:
    """Generate a behavior-only ``'proposed'`` strategy from selected signals.

    Body: ``{"signal_ids": [str, ...], "backend_kind"?: str, "model_override"?:
    str}``. ``signal_ids`` is required (a strategy is synthesized FROM signals);
    ``backend_kind`` defaults to ``'claude'`` and ``model_override`` is optional —
    neither blocks the call (multi-backend, never claude-only). Delegates to
    ``CompetitorStrategyService.propose`` — the taint-wrapped, multi-backend,
    degraded-never-raises LLM path (26-02) — which is the ONE heavy method here,
    so the handler is ``sync_to_thread=True`` (runs on the worker thread pool,
    never stalls the event loop).

    Returns ``{"strategy": <the proposed strategy + a degraded flag>}``.

    * empty / foreign ``signal_ids`` (``ValueError`` out of the service) → 400.
    """
    _assert_project_access(project_id, caller)
    body = data or {}
    signal_ids = body.get("signal_ids")
    if not signal_ids or not isinstance(signal_ids, list):
        raise ClientException(detail="signal_ids is required")
    backend_kind = body.get("backend_kind") or "claude"
    model_override = body.get("model_override")
    try:
        strategy = CompetitorStrategyService.propose(
            project_id,
            signal_ids,
            backend_kind=backend_kind,
            model_override=model_override,
        )
    except ValueError as exc:
        raise ClientException(detail=str(exc)) from None
    return {"strategy": strategy}


# ---------------------------------------------------------------------------
# Review queue — list + approve / reject / edit / legal
# ---------------------------------------------------------------------------


@get("/{project_id:str}/strategies", sync_to_thread=False)
def list_strategies(project_id: str, caller: Caller) -> dict[str, Any]:
    """The project's strategies, newest first (``created_at DESC``)."""
    _assert_project_access(project_id, caller)
    return {"strategies": competitor_strategies.list_strategies(project_id)}


@post("/{project_id:str}/strategies/{sid:str}/approve", sync_to_thread=False)
def approve_strategy(project_id: str, sid: str, caller: Caller) -> dict[str, Any]:
    """Flip a strategy ``proposed`` → ``approved``.

    Project-SCOPED (``project_id=`` passed to the DAO) so a strategy owned by
    another project 404s, not just an unknown id (the cross-project IDOR guard).

    * unknown / foreign-project ``sid`` → 404.
    * illegal transition (``ValueError``) → 400.
    """
    _assert_project_access(project_id, caller)
    return {"strategy": _set_status_or_404(sid, "approved", project_id)}


@post("/{project_id:str}/strategies/{sid:str}/reject", sync_to_thread=False)
def reject_strategy(project_id: str, sid: str, caller: Caller) -> dict[str, Any]:
    """Flip a strategy → ``rejected`` (project-scoped; same 404/400 contract)."""
    _assert_project_access(project_id, caller)
    return {"strategy": _set_status_or_404(sid, "rejected", project_id)}


@post("/{project_id:str}/strategies/{sid:str}/edit", sync_to_thread=False)
def edit_strategy(project_id: str, sid: str, data: dict | None, caller: Caller) -> dict[str, Any]:
    """Operator edit of ``title``/``body`` — RESETS legal clearance (§5B).

    Body ``{"title"?: str, "body"?: str}``; a None field leaves that column
    unchanged. ``update_body`` flips ``independent_authorship`` + ``no_copied_code``
    back to false and NULLs ``legal_cleared_at`` (re-affirmation after a plan
    change). Project-SCOPED.

    * unknown / foreign-project ``sid`` → 404.
    """
    _assert_project_access(project_id, caller)
    body = data or {}
    updated = competitor_strategies.update_body(
        sid,
        title=body.get("title"),
        body=body.get("body"),
        project_id=project_id,
    )
    if updated is None:
        raise NotFoundException(detail="Strategy not found")
    return {"strategy": updated}


@post("/{project_id:str}/strategies/{sid:str}/legal", sync_to_thread=False)
def record_legal_item(
    project_id: str, sid: str, data: dict | None, caller: Caller
) -> dict[str, Any]:
    """Affirm/deny ONE §5B legal-checklist item; return the updated strategy.

    Body ``{"item_key": str, "value": bool}``. ``item_key`` must be one of the 7
    canonical ``LEGAL_CHECKLIST_ITEMS`` (else 400). Records the item via the DAO,
    which sets ``legal_cleared_at`` ONLY when all 7 are affirmed — so the UI sees
    the gate flip at 7/7. This route NEVER bypasses the gate: it records items
    only (promotion to ``implementing`` is gated by ``mark_implementing``, wired
    in 26-04, not here). Project-SCOPED.

    * unknown / foreign-project ``sid`` → 404.
    * unknown ``item_key`` (``ValueError``) → 400.
    """
    _assert_project_access(project_id, caller)
    body = data or {}
    item_key = body.get("item_key")
    if not item_key or not isinstance(item_key, str):
        raise ClientException(detail="item_key is required")
    value = body.get("value")
    # §5B gate: only a real JSON boolean may affirm/deny an item. A truthy
    # non-bool ("false", "0", "no", 1, …) must NOT be coerced — that would let
    # a caller "affirm" all 7 with junk and bypass the legal gate.
    if not isinstance(value, bool):
        raise ClientException(detail="value must be a boolean")
    try:
        updated = competitor_strategies.record_legal_item(
            sid, item_key, value, project_id=project_id
        )
    except ValueError as exc:
        raise ClientException(detail=str(exc)) from None
    if updated is None:
        raise NotFoundException(detail="Strategy not found")
    return {"strategy": updated}


# ---------------------------------------------------------------------------
# Materialize — the conservative IMPLEMENT step (PLAN artifact, zero repo mutation)
# ---------------------------------------------------------------------------


@post("/{project_id:str}/strategies/{sid:str}/materialize", sync_to_thread=False)
def materialize_strategy(project_id: str, sid: str, caller: Caller) -> dict[str, Any]:
    """Materialize an approved + §5B-cleared strategy into a ``ProjectPlan``.

    The conservative IMPLEMENT step of P4: it builds a ``ProjectPlan``
    (``tasks_json`` from the strategy) under the project's current milestone/phase,
    stamps ``strategy.plan_id`` + ``status='implementing'`` via the
    ``mark_implementing`` DAO gate, and mutates NO repo files (no
    ExecutionService / goal_loop_runner / subprocess on this path).

    ``_assert_project_access`` runs FIRST (404, not 403 — the P1 IDOR lesson); the
    service additionally scopes the strategy read to ``project_id`` so a
    cross-project ``sid`` 404s. The §5B legal gate is re-enforced inside
    ``materialize`` (``mark_implementing`` raises ``LegalGateNotCleared`` while
    ``legal_cleared_at IS NULL`` and NO plan is created) — surfaced here as 409,
    non-bypassable.

    * unknown / foreign-project ``sid`` → 404.
    * not-approved (``ValueError``) / no target phase → 400.
    * §5B gate not cleared (``LegalGateNotCleared``) → 409.
    """
    _assert_project_access(project_id, caller)
    try:
        return CompetitorStrategyService.materialize(project_id, sid)
    except LegalGateNotCleared as exc:
        raise ClientException(detail=str(exc), status_code=HTTP_409_CONFLICT) from None
    except ValueError as exc:
        detail = str(exc)
        if "not found" in detail:
            raise NotFoundException(detail="Strategy not found") from None
        raise ClientException(detail=detail) from None


def _set_status_or_404(sid: str, status: str, project_id: str) -> dict[str, Any]:
    """Shared approve/reject helper: DAO ``set_status`` → 404 on miss, 400 on illegal.

    ``set_status`` returns None for an unknown / foreign-project strategy (scope
    guard) → 404, and raises ``ValueError`` for an illegal transition → 400.
    """
    try:
        updated = competitor_strategies.set_status(sid, status, project_id=project_id)
    except ValueError as exc:
        raise ClientException(detail=str(exc)) from None
    if updated is None:
        raise NotFoundException(detail="Strategy not found")
    return updated


strategy_router = Router(
    path="/api/projects",
    route_handlers=[
        generate_strategy,
        list_strategies,
        approve_strategy,
        reject_strategy,
        edit_strategy,
        record_legal_item,
        materialize_strategy,
    ],
)
