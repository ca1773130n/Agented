"""Admin routes for the Life-Harness T3 evolution loop.

Surfaces five operations against ``harness_evolution_rounds``:

    POST /admin/bots/{bot_id}/evolution/dry-run
        Trigger a dry-run round: Codex builds a patch, we validate it,
        and store it in ``awaiting_approval`` for human approval.

    POST /admin/bots/{bot_id}/evolution/apply
        Trigger a live round (Codex + validate + apply in one shot).
        Equivalent to dry-run + immediate apply; useful for trusted bots.

    GET  /admin/bots/{bot_id}/evolution/rounds
        List recent rounds for the bot, newest first.

    GET  /admin/evolution/rounds/{round_id}
        Round detail (input layers, proposed patch, applied ids, notes).

    POST /admin/evolution/rounds/{round_id}/apply
        Promote an ``awaiting_approval`` round to ``applied`` — operator
        signed off on Codex's proposal.

    POST /admin/evolution/rounds/{round_id}/abort
        Reject an ``awaiting_approval`` round.
"""

from __future__ import annotations

from typing import Any, Optional

from litestar import Router, get, post
from litestar.exceptions import NotFoundException

from app.db import harness_evolution as evolution_repo


@post("/bots/{bot_id:str}/evolution/dry-run", sync_to_thread=True)
def dry_run_round(
    bot_id: str,
    data: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Body (optional): ``{"since": ISO, "until": ISO, "limit": int,
    "force": bool}``."""
    from app.services.harness_evolver import run_evolution_round

    opts = data or {}
    result = run_evolution_round(
        bot_id,
        since=opts.get("since"),
        until=opts.get("until"),
        limit=int(opts.get("limit", 25)),
        dry_run=True,
        force=bool(opts.get("force", False)),
    )
    return _result_payload(result)


@post("/bots/{bot_id:str}/evolution/apply", sync_to_thread=True)
def live_round(
    bot_id: str,
    data: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Body (optional): ``{"since": ISO, "until": ISO, "limit": int,
    "force": bool}``."""
    from app.services.harness_evolver import run_evolution_round

    opts = data or {}
    result = run_evolution_round(
        bot_id,
        since=opts.get("since"),
        until=opts.get("until"),
        limit=int(opts.get("limit", 25)),
        dry_run=False,
        force=bool(opts.get("force", False)),
    )
    return _result_payload(result)


@get("/bots/{bot_id:str}/evolution/rounds", sync_to_thread=False)
def list_rounds(bot_id: str, limit: int = 20) -> dict[str, Any]:
    capped = max(1, min(int(limit or 20), 100))
    rounds = evolution_repo.list_for_bot(bot_id, limit=capped)
    return {"bot_id": bot_id, "rounds": rounds}


@get("/evolution/rounds", sync_to_thread=False)
def list_all_rounds(
    limit: int = 50, status: Optional[str] = None,
) -> dict[str, Any]:
    """Cross-bot listing of recent evolution rounds. Optional ``status``
    filter (``pending`` / ``running`` / ``awaiting_approval`` / ``applied``
    / ``failed`` / ``aborted``)."""
    capped = max(1, min(int(limit or 50), 200))
    rounds = evolution_repo.list_all(limit=capped, status=status)
    return {"rounds": rounds}


@get("/evolution/rounds/{round_id:str}", sync_to_thread=False)
def get_round_detail(round_id: str) -> dict[str, Any]:
    row = evolution_repo.get_round(round_id)
    if row is None:
        raise NotFoundException(detail=f"round not found: {round_id}")
    return row


@get("/evolution/rounds/{round_id:str}/impact", sync_to_thread=False)
def get_round_impact(round_id: str, window: int = 20) -> dict[str, Any]:
    """Observational A/B comparing the N executions before vs after the round.

    Returns ``{"available": False, "reason": "..."}`` when the round can't
    be compared (not applied, or not found). Otherwise carries ``before``,
    ``after``, ``delta`` aggregates.
    """
    from app.services.harness_evolution_impact import compute_impact

    capped = max(1, min(int(window or 20), 200))
    return compute_impact(round_id, window_size=capped)


@post("/evolution/rounds/{round_id:str}/apply", sync_to_thread=True)
def approve_round(round_id: str) -> dict[str, Any]:
    from app.services.harness_evolver import apply_dry_run_round

    result = apply_dry_run_round(round_id)
    return _result_payload(result)


@post("/evolution/rounds/{round_id:str}/abort", sync_to_thread=True)
def abort_round(
    round_id: str,
    data: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    from app.services.harness_evolver import abort_dry_run_round

    reason = (data or {}).get("reason")
    result = abort_dry_run_round(round_id, reason=reason)
    return _result_payload(result)


def _result_payload(result) -> dict[str, Any]:
    return {
        "round_id": result.round_id,
        "status": result.status,
        "applied_layer_ids": result.applied_layer_ids,
        "error": result.error,
        "notes": result.notes,
    }


harness_evolution_router = Router(
    path="/admin",
    route_handlers=[
        dry_run_round,
        live_round,
        list_rounds,
        list_all_rounds,
        get_round_detail,
        get_round_impact,
        approve_round,
        abort_round,
    ],
)
