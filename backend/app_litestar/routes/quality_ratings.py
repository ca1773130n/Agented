"""Quality rating routes (track A, wave 50)."""

from __future__ import annotations

from typing import Any, Optional

from litestar import Router, get, post
from litestar.exceptions import ClientException
from msgspec import Struct

from app.db.quality_ratings import (
    get_bot_quality_stats,
    get_quality_entries,
    upsert_quality_rating,
)


class RatingBody(Struct):
    rating: int
    feedback: str = ""
    trigger_id: Optional[str] = None


@get("/admin/quality/entries", sync_to_thread=False)
def list_entries(
    trigger_id: Optional[str] = None, limit: int = 50, offset: int = 0
) -> dict[str, Any]:
    if not (1 <= limit <= 200):
        raise ClientException(detail="limit must be between 1 and 200")
    entries = get_quality_entries(
        trigger_id=trigger_id or None, limit=limit, offset=offset
    )
    return {"entries": entries, "total": len(entries)}


@post(
    "/admin/quality/entries/{execution_id:str}",
    status_code=200,
    sync_to_thread=False,
)
def submit_rating(execution_id: str, data: RatingBody) -> dict[str, Any]:
    if not (1 <= data.rating <= 5):
        raise ClientException(detail="rating must be 1-5")
    try:
        return upsert_quality_rating(
            execution_id=execution_id,
            trigger_id=data.trigger_id,
            rating=data.rating,
            feedback=data.feedback,
        )
    except ValueError as exc:
        raise ClientException(detail=str(exc)) from None


@get("/admin/quality/stats", sync_to_thread=False)
def quality_stats() -> dict[str, Any]:
    return {"bots": get_bot_quality_stats()}


quality_ratings_router = Router(
    path="/",
    route_handlers=[list_entries, submit_rating, quality_stats],
)
