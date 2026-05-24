"""Admin routes for Life-Harness layer rows + per-bot run history (T-final).

Read + toggle operations for ``harness_layers``. Create / supersede stay in
the evolution flow (Codex-proposed via :file:`harness_evolution.py` routes).
The UI surface here is intentionally narrow — operators inspect what's
configured, toggle enabled/disabled, and see which recent executions ran
under which layer versions.
"""

from __future__ import annotations

from typing import Any, Optional

from litestar import Router, get, patch
from litestar.exceptions import NotFoundException

from app.db import harness_layers as layers_repo
from app.db import harness_snapshots as snapshots_repo


@get("/bots/{bot_id:str}/harness/layers", sync_to_thread=False)
def list_bot_layers(
    bot_id: str, layer: Optional[str] = None,
) -> dict[str, Any]:
    """List enabled layers for the bot, grouped by layer kind.

    Optional ``?layer=h2`` narrows to a single kind.
    """
    layers_filter = [layer] if layer else None
    rows = layers_repo.list_enabled_for_bot(bot_id, layers=layers_filter)
    grouped: dict[str, list[dict]] = {"h2": [], "h3": [], "h4": [], "h5": []}
    for r in rows:
        if r["layer"] in grouped:
            grouped[r["layer"]].append(r)
    return {"bot_id": bot_id, "layers": grouped}


@get("/harness/layers/{layer_id:str}", sync_to_thread=False)
def get_single_layer(layer_id: str) -> dict[str, Any]:
    row = layers_repo.get_layer(layer_id)
    if row is None:
        raise NotFoundException(detail=f"layer not found: {layer_id}")
    return row


@patch("/harness/layers/{layer_id:str}", sync_to_thread=False)
def toggle_layer(
    layer_id: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Body: ``{"enabled": true|false}``. Returns the updated row."""
    if "enabled" not in data:
        raise NotFoundException(detail="missing field 'enabled' in body")
    layers_repo.set_enabled(layer_id, bool(data["enabled"]))
    row = layers_repo.get_layer(layer_id)
    if row is None:
        raise NotFoundException(detail=f"layer not found: {layer_id}")
    return row


@get("/bots/{bot_id:str}/harness/run-history", sync_to_thread=False)
def bot_run_history(bot_id: str, limit: int = 20) -> dict[str, Any]:
    """Recent execution snapshots for the bot, with the layer version
    map active at spawn time. Powers the per-bot run-history view that
    correlates harness state with execution outcomes."""
    capped = max(1, min(int(limit or 20), 200))
    snaps = snapshots_repo.list_for_bot(bot_id)[:capped]
    return {
        "bot_id": bot_id,
        "snapshots": [
            {
                "execution_id": s["execution_id"],
                "harness_kind": s["harness_kind"],
                "layer_versions": s["layer_versions"],
                "applied": s["applied"],
                "created_at": s["created_at"],
            }
            for s in snaps
        ],
    }


harness_layers_router = Router(
    path="/admin",
    route_handlers=[
        list_bot_layers,
        get_single_layer,
        toggle_layer,
        bot_run_history,
    ],
)
