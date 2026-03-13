"""Bot memory store API endpoints."""

from http import HTTPStatus
from typing import Optional

from flask import request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from app.models.common import error_response

from ..db.bot_memory import (
    clear_bot_memory,
    delete_memory_entry,
    get_bot_memory,
    upsert_memory_entry,
)
from ..db.connection import get_connection

tag = Tag(name="bot-memory", description="Per-bot persistent key-value memory store")
bot_memory_bp = APIBlueprint("bot_memory", __name__, url_prefix="/admin", abp_tags=[tag])


class BotMemoryPath(BaseModel):
    bot_id: str = Field(..., description="Bot (trigger) ID")


class BotMemoryKeyPath(BaseModel):
    bot_id: str = Field(..., description="Bot (trigger) ID")
    key: str = Field(..., description="Memory entry key")


class UpsertMemoryBody(BaseModel):
    value: str = Field(..., description="Memory entry value (JSON string or plain text)")
    expiresAt: Optional[str] = Field(None, description="Optional ISO-8601 expiry date")


def _list_bots_with_memory() -> list[dict]:
    """Return all bots that have at least one memory entry, with names from triggers."""
    with get_connection() as conn:
        cursor = conn.execute(
            """SELECT m.bot_id,
                      COALESCE(t.name, m.bot_id) AS bot_name,
                      COUNT(m.key) AS entry_count,
                      SUM(LENGTH(m.value)) AS used_bytes
               FROM bot_memory m
               LEFT JOIN triggers t ON t.id = m.bot_id
               GROUP BY m.bot_id
               ORDER BY bot_name""",
        )
        return [dict(row) for row in cursor.fetchall()]


@bot_memory_bp.get("/bots/memory")
def list_all_bot_memory():
    """List all bots that have memory entries, including entry counts and byte usage."""
    bots = _list_bots_with_memory()
    return {"bots": bots, "total": len(bots)}, HTTPStatus.OK


@bot_memory_bp.get("/bots/<bot_id>/memory")
def get_single_bot_memory(path: BotMemoryPath):
    """Return all memory entries for a specific bot."""
    entries = get_bot_memory(path.bot_id)
    used_bytes = sum(len(e["value"].encode("utf-8")) for e in entries)
    return {
        "bot_id": path.bot_id,
        "entries": entries,
        "used_bytes": used_bytes,
        "max_bytes": 65536,
    }, HTTPStatus.OK


@bot_memory_bp.put("/bots/<bot_id>/memory/<key>")
def upsert_memory_entry_route(path: BotMemoryKeyPath, body: UpsertMemoryBody):
    """Create or update a memory entry for the given bot and key."""
    entry = upsert_memory_entry(
        bot_id=path.bot_id,
        key=path.key,
        value=body.value,
        source="manual",
        expires_at=body.expiresAt,
    )
    if not entry:
        return error_response(
            "INTERNAL_SERVER_ERROR",
            "Failed to save memory entry",
            HTTPStatus.INTERNAL_SERVER_ERROR,
        )
    return entry, HTTPStatus.OK


@bot_memory_bp.delete("/bots/<bot_id>/memory/<key>")
def delete_memory_entry_route(path: BotMemoryKeyPath):
    """Delete a single memory entry by bot ID and key."""
    deleted = delete_memory_entry(path.bot_id, path.key)
    if not deleted:
        return error_response("NOT_FOUND", "Memory entry not found", HTTPStatus.NOT_FOUND)
    return {"message": f'Memory key "{path.key}" deleted'}, HTTPStatus.OK


@bot_memory_bp.delete("/bots/<bot_id>/memory")
def clear_bot_memory_route(path: BotMemoryPath):
    """Delete all memory entries for a bot."""
    clear_bot_memory(path.bot_id)
    return {"message": f"All memory cleared for bot {path.bot_id}"}, HTTPStatus.OK
