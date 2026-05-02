"""Wave 65 — leaf CRUD batch A (28 routes, 5 routers).

bookmarks + prompt_snippets + scope_filters + trigger_conditions + bot_memory.
"""

from __future__ import annotations

import re
from typing import Any, List, Optional

from litestar import Router, delete, get, post, put
from litestar.exceptions import (
    ClientException,
    HTTPException,
    NotFoundException,
)
from litestar.params import Parameter

from app.db.bot_memory import (
    clear_bot_memory,
    delete_memory_entry,
    get_bot_memory,
    upsert_memory_entry,
)
from app.db.connection import get_connection
from app.db.prompt_snippets import (
    delete_snippet,
    get_all_snippets,
    get_snippet,
    get_snippet_by_name,
    update_snippet,
)
from app.db.prompt_snippets import create_snippet as db_create_snippet
from app.db.scope_filters import (
    add_pattern,
    delete_pattern,
    get_scope_filter,
    list_scope_filters,
    update_scope_filter,
    upsert_scope_filter,
)
from app.db.trigger_conditions import (
    create_trigger_condition,
    delete_trigger_condition,
    get_trigger_condition,
    list_trigger_conditions,
    update_trigger_condition,
)
from app.services.bookmark_service import (
    create_bookmark,
    delete_bookmark,
    get_bookmark,
    get_bookmarks_for_bot,
    search_bookmarks,
    update_bookmark,
)
from app.services.prompt_snippet_service import SnippetService


# ===========================================================================
# /admin/bookmarks/* + /admin/triggers/{id}/bookmarks (6)
# ===========================================================================


@post("/bookmarks", sync_to_thread=False)
def create_bookmark_endpoint(data: dict) -> Any:
    if not data:
        raise ClientException(detail="JSON body required")
    bookmark_id = create_bookmark(
        execution_id=data.get("execution_id"),
        trigger_id=data.get("trigger_id"),
        title=data.get("title", ""),
        notes=data.get("notes"),
        tags=data.get("tags"),
        line_number=data.get("line_number"),
    )
    if not bookmark_id:
        raise HTTPException(status_code=500, detail="Failed to create bookmark")
    return get_bookmark(bookmark_id)


@get("/bookmarks", sync_to_thread=False)
def list_bookmarks(
    trigger_id: Optional[str] = None,
    tags: Optional[str] = None,
    search: Optional[str] = Parameter(query="query", default=None, required=False),
) -> dict[str, Any]:
    if trigger_id:
        bookmarks = get_bookmarks_for_bot(trigger_id)
    else:
        tags_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
        bookmarks = search_bookmarks(query=search, tags=tags_list)
    return {"bookmarks": bookmarks, "total": len(bookmarks)}


@get("/bookmarks/{bookmark_id:str}", sync_to_thread=False)
def get_bookmark_endpoint(bookmark_id: str) -> Any:
    bookmark = get_bookmark(bookmark_id)
    if not bookmark:
        raise NotFoundException(detail="Bookmark not found")
    return bookmark


@put("/bookmarks/{bookmark_id:str}", sync_to_thread=False)
def update_bookmark_endpoint(bookmark_id: str, data: dict) -> Any:
    if not get_bookmark(bookmark_id):
        raise NotFoundException(detail="Bookmark not found")
    if not update_bookmark(
        bookmark_id=bookmark_id,
        title=data.get("title"),
        notes=data.get("notes"),
        tags=data.get("tags"),
    ):
        raise ClientException(detail="No changes applied")
    return get_bookmark(bookmark_id)


@delete("/bookmarks/{bookmark_id:str}", status_code=200, sync_to_thread=False)
def delete_bookmark_endpoint(bookmark_id: str) -> dict[str, Any]:
    if not delete_bookmark(bookmark_id):
        raise NotFoundException(detail="Bookmark not found")
    return {"message": "Bookmark deleted"}


@get("/triggers/{trigger_id:str}/bookmarks", sync_to_thread=False)
def list_trigger_bookmarks(trigger_id: str) -> dict[str, Any]:
    bookmarks = get_bookmarks_for_bot(trigger_id)
    return {"bookmarks": bookmarks, "total": len(bookmarks)}


bookmarks_router = Router(
    path="/admin",
    route_handlers=[
        create_bookmark_endpoint,
        list_bookmarks,
        get_bookmark_endpoint,
        update_bookmark_endpoint,
        delete_bookmark_endpoint,
        list_trigger_bookmarks,
    ],
)


# ===========================================================================
# /admin/prompt-snippets/* (6)
# ===========================================================================


_SNIPPET_NAME_RE = re.compile(r"^[\w][\w-]*$")


@get("/", sync_to_thread=False)
def list_snippets() -> dict[str, Any]:
    return {"snippets": get_all_snippets()}


@post("/", sync_to_thread=False)
def create_snippet(data: dict) -> Any:
    if not data:
        raise ClientException(detail="JSON body required")
    name = (data.get("name") or "").strip()
    content = (data.get("content") or "").strip()
    if not name:
        raise ClientException(detail="name is required")
    if not content:
        raise ClientException(detail="content is required")
    if not _SNIPPET_NAME_RE.match(name):
        raise ClientException(
            detail="name must start with a word character and contain only word characters and hyphens"
        )
    if get_snippet_by_name(name):
        raise HTTPException(
            status_code=409, detail=f"A snippet named '{name}' already exists"
        )
    snippet_id = db_create_snippet(
        name=name, content=content, description=data.get("description", "")
    )
    if not snippet_id:
        raise HTTPException(status_code=500, detail="Failed to create snippet")
    return {"message": "Snippet created", "snippet": get_snippet(snippet_id)}


@post("/resolve", sync_to_thread=False)
def resolve_snippets(data: dict) -> dict[str, Any]:
    if not data:
        raise ClientException(detail="JSON body required")
    text = data.get("text", "")
    if not text:
        raise ClientException(detail="text is required")
    return {"original": text, "resolved": SnippetService.resolve_snippets(text)}


@get("/{snippet_id:str}", sync_to_thread=False)
def get_snippet_detail(snippet_id: str) -> Any:
    snippet = get_snippet(snippet_id)
    if not snippet:
        raise NotFoundException(detail="Snippet not found")
    return snippet


@put("/{snippet_id:str}", sync_to_thread=False)
def update_snippet_endpoint(snippet_id: str, data: dict) -> Any:
    snippet = get_snippet(snippet_id)
    if not snippet:
        raise NotFoundException(detail="Snippet not found")
    name = data.get("name")
    if name is not None:
        name = name.strip()
        if not _SNIPPET_NAME_RE.match(name):
            raise ClientException(
                detail="name must start with a word character and contain only word characters and hyphens"
            )
        if name != snippet["name"] and get_snippet_by_name(name):
            raise HTTPException(
                status_code=409, detail=f"A snippet named '{name}' already exists"
            )
    if not update_snippet(
        snippet_id,
        name=data.get("name"),
        content=data.get("content"),
        description=data.get("description"),
    ):
        raise ClientException(detail="No changes made")
    return {"message": "Snippet updated", "snippet": get_snippet(snippet_id)}


@delete("/{snippet_id:str}", status_code=200, sync_to_thread=False)
def delete_snippet_endpoint(snippet_id: str) -> dict[str, Any]:
    if not get_snippet(snippet_id):
        raise NotFoundException(detail="Snippet not found")
    if not delete_snippet(snippet_id):
        raise HTTPException(status_code=500, detail="Failed to delete snippet")
    return {"message": "Snippet deleted"}


prompt_snippets_router = Router(
    path="/admin/prompt-snippets",
    route_handlers=[
        list_snippets,
        create_snippet,
        resolve_snippets,
        get_snippet_detail,
        update_snippet_endpoint,
        delete_snippet_endpoint,
    ],
)


# ===========================================================================
# /admin/scope-filters/* (6)
# ===========================================================================


@get("/scope-filters", sync_to_thread=False)
def list_filters() -> dict[str, Any]:
    filters = list_scope_filters()
    return {"filters": filters, "total": len(filters)}


@get("/scope-filters/{filter_id:str}", sync_to_thread=False)
def get_filter(filter_id: str) -> Any:
    sf = get_scope_filter(filter_id)
    if sf is None:
        raise NotFoundException(detail="Scope filter not found")
    return sf


@post("/scope-filters", sync_to_thread=False)
def create_or_update_filter(data: dict) -> dict[str, Any]:
    if not data or not data.get("trigger_id"):
        raise ClientException(detail="trigger_id is required")
    filter_id = upsert_scope_filter(
        trigger_id=data["trigger_id"],
        mode=data.get("mode", "denylist"),
        enabled=data.get("enabled", True),
    )
    return {"message": "Scope filter saved", "filter": get_scope_filter(filter_id)}


@put("/scope-filters/{filter_id:str}", sync_to_thread=False)
def update_filter(filter_id: str, data: dict) -> Any:
    if not update_scope_filter(
        filter_id=filter_id,
        mode=data.get("mode"),
        enabled=data.get("enabled"),
    ):
        raise NotFoundException(detail="Scope filter not found or no changes")
    return get_scope_filter(filter_id)


@post("/scope-filters/{filter_id:str}/patterns", sync_to_thread=False)
def add_filter_pattern(filter_id: str, data: dict) -> dict[str, Any]:
    sf = get_scope_filter(filter_id)
    if sf is None:
        raise NotFoundException(detail="Scope filter not found")
    if not data:
        raise ClientException(detail="JSON body required")
    pattern_id = add_pattern(
        filter_id=filter_id,
        type=data.get("type", ""),
        pattern=data.get("pattern", ""),
        description=data.get("description", ""),
    )
    updated = get_scope_filter(filter_id)
    new_pattern = next(
        (p for p in (updated or {}).get("patterns", []) if p["id"] == pattern_id),
        None,
    )
    return {"message": "Pattern added", "pattern": new_pattern}


@delete(
    "/scope-filters/{filter_id:str}/patterns/{pattern_id:str}",
    status_code=200,
    sync_to_thread=False,
)
def delete_filter_pattern(filter_id: str, pattern_id: str) -> dict[str, Any]:
    del filter_id
    if not delete_pattern(pattern_id):
        raise NotFoundException(detail="Pattern not found")
    return {"message": "Pattern deleted"}


scope_filters_router = Router(
    path="/admin",
    route_handlers=[
        list_filters,
        get_filter,
        create_or_update_filter,
        update_filter,
        add_filter_pattern,
        delete_filter_pattern,
    ],
)


# ===========================================================================
# /admin/triggers/{id}/conditions + /admin/trigger-conditions/{id}/* (5)
# ===========================================================================


@get("/triggers/{trigger_id:str}/conditions", sync_to_thread=False)
def list_conditions(trigger_id: str) -> dict[str, Any]:
    rules = list_trigger_conditions(trigger_id)
    return {"rules": rules, "total": len(rules)}


@post("/triggers/{trigger_id:str}/conditions", sync_to_thread=False)
def create_condition(trigger_id: str, data: dict) -> dict[str, Any]:
    if not data or not data.get("name"):
        raise ClientException(detail="name is required")
    condition_id = create_trigger_condition(
        trigger_id=trigger_id,
        name=data["name"],
        description=data.get("description", ""),
        enabled=data.get("enabled", True),
        logic=data.get("logic", "AND"),
        conditions=data.get("conditions", []),
    )
    if not condition_id:
        raise HTTPException(
            status_code=500, detail="Failed to create condition rule"
        )
    return {
        "message": "Condition rule created",
        "rule": get_trigger_condition(condition_id),
    }


@get("/trigger-conditions/{condition_id:str}", sync_to_thread=False)
def get_condition(condition_id: str) -> Any:
    rule = get_trigger_condition(condition_id)
    if not rule:
        raise NotFoundException(detail="Condition rule not found")
    return rule


@put("/trigger-conditions/{condition_id:str}", sync_to_thread=False)
def update_condition(condition_id: str, data: dict) -> Any:
    if not update_trigger_condition(
        condition_id=condition_id,
        name=data.get("name"),
        description=data.get("description"),
        enabled=data.get("enabled"),
        logic=data.get("logic"),
        conditions=data.get("conditions"),
    ):
        raise NotFoundException(detail="Condition rule not found or no changes")
    return get_trigger_condition(condition_id)


@delete(
    "/trigger-conditions/{condition_id:str}",
    status_code=200,
    sync_to_thread=False,
)
def delete_condition(condition_id: str) -> dict[str, Any]:
    if not delete_trigger_condition(condition_id):
        raise NotFoundException(detail="Condition rule not found")
    return {"message": "Condition rule deleted"}


trigger_conditions_router = Router(
    path="/admin",
    route_handlers=[
        list_conditions,
        create_condition,
        get_condition,
        update_condition,
        delete_condition,
    ],
)


# ===========================================================================
# /admin/bots/memory/* (5)
# ===========================================================================


def _list_bots_with_memory() -> List[dict]:
    with get_connection() as conn:
        cursor = conn.execute(
            """SELECT m.bot_id,
                      COALESCE(t.name, m.bot_id) AS bot_name,
                      COUNT(m.key) AS entry_count,
                      SUM(LENGTH(m.value)) AS used_bytes
               FROM bot_memory m
               LEFT JOIN triggers t ON t.id = m.bot_id
               GROUP BY m.bot_id
               ORDER BY bot_name"""
        )
        return [dict(row) for row in cursor.fetchall()]


@get("/bots/memory", sync_to_thread=False)
def list_all_bot_memory() -> dict[str, Any]:
    bots = _list_bots_with_memory()
    return {"bots": bots, "total": len(bots)}


@get("/bots/{bot_id:str}/memory", sync_to_thread=False)
def get_single_bot_memory(bot_id: str) -> dict[str, Any]:
    entries = get_bot_memory(bot_id)
    used_bytes = sum(len(e["value"].encode("utf-8")) for e in entries)
    return {
        "bot_id": bot_id,
        "entries": entries,
        "used_bytes": used_bytes,
        "max_bytes": 65536,
    }


@put("/bots/{bot_id:str}/memory/{key:str}", sync_to_thread=False)
def upsert_bot_memory(bot_id: str, key: str, data: dict) -> Any:
    if not data or "value" not in data:
        raise ClientException(detail="value is required")
    return upsert_memory_entry(
        bot_id=bot_id,
        key=key,
        value=data["value"],
        expires_at=data.get("expiresAt"),
    )


@delete(
    "/bots/{bot_id:str}/memory/{key:str}",
    status_code=200,
    sync_to_thread=False,
)
def delete_bot_memory_entry(bot_id: str, key: str) -> dict[str, Any]:
    if not delete_memory_entry(bot_id, key):
        raise NotFoundException(detail="Memory entry not found")
    return {"message": "Memory entry deleted"}


@delete(
    "/bots/{bot_id:str}/memory",
    status_code=200,
    sync_to_thread=False,
)
def clear_bot_memory_all(bot_id: str) -> dict[str, Any]:
    deleted_count = clear_bot_memory(bot_id)
    return {"deleted_count": deleted_count, "message": "Bot memory cleared"}


bot_memory_router = Router(
    path="/admin",
    route_handlers=[
        list_all_bot_memory,
        get_single_bot_memory,
        upsert_bot_memory,
        delete_bot_memory_entry,
        clear_bot_memory_all,
    ],
)
