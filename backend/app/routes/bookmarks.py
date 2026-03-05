"""Bookmark management API endpoints."""

from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag

from app.models.common import error_response

from ..models.bookmark import (
    BookmarkCreate,
    BookmarkPath,
    BookmarkUpdate,
    TriggerBookmarkPath,
)
from ..services.bookmark_service import (
    create_bookmark,
    delete_bookmark,
    get_bookmark,
    get_bookmarks_for_bot,
    search_bookmarks,
    update_bookmark,
)

tag = Tag(name="bookmarks", description="Execution bookmark management")
bookmarks_bp = APIBlueprint("bookmarks", __name__, url_prefix="/admin", abp_tags=[tag])


@bookmarks_bp.post("/bookmarks")
def create_bookmark_route(body: BookmarkCreate):
    """Create a new execution bookmark with optional deep-link."""
    bookmark_id = create_bookmark(
        execution_id=body.execution_id,
        trigger_id=body.trigger_id,
        title=body.title,
        notes=body.notes,
        tags=body.tags,
        line_number=body.line_number,
    )
    if not bookmark_id:
        return error_response(
            "INTERNAL_SERVER_ERROR", "Failed to create bookmark", HTTPStatus.INTERNAL_SERVER_ERROR
        )

    bookmark = get_bookmark(bookmark_id)
    return bookmark, HTTPStatus.CREATED


@bookmarks_bp.get("/bookmarks")
def list_bookmarks_route():
    """List bookmarks with optional filtering by trigger_id, tags, or query."""
    trigger_id = request.args.get("trigger_id")
    tags_param = request.args.get("tags")
    query = request.args.get("query")

    if trigger_id:
        bookmarks = get_bookmarks_for_bot(trigger_id)
    else:
        tags_list = [t.strip() for t in tags_param.split(",") if t.strip()] if tags_param else None
        bookmarks = search_bookmarks(query=query, tags=tags_list)

    return {"bookmarks": bookmarks, "total": len(bookmarks)}, HTTPStatus.OK


@bookmarks_bp.get("/bookmarks/<bookmark_id>")
def get_bookmark_route(path: BookmarkPath):
    """Get a single bookmark by ID."""
    bookmark = get_bookmark(path.bookmark_id)
    if not bookmark:
        return error_response("NOT_FOUND", "Bookmark not found", HTTPStatus.NOT_FOUND)
    return bookmark, HTTPStatus.OK


@bookmarks_bp.put("/bookmarks/<bookmark_id>")
def update_bookmark_route(path: BookmarkPath, body: BookmarkUpdate):
    """Update a bookmark's title, notes, or tags."""
    existing = get_bookmark(path.bookmark_id)
    if not existing:
        return error_response("NOT_FOUND", "Bookmark not found", HTTPStatus.NOT_FOUND)

    updated = update_bookmark(
        bookmark_id=path.bookmark_id,
        title=body.title,
        notes=body.notes,
        tags=body.tags,
    )
    if not updated:
        return error_response("BAD_REQUEST", "No changes applied", HTTPStatus.BAD_REQUEST)

    bookmark = get_bookmark(path.bookmark_id)
    return bookmark, HTTPStatus.OK


@bookmarks_bp.delete("/bookmarks/<bookmark_id>")
def delete_bookmark_route(path: BookmarkPath):
    """Delete a bookmark by ID."""
    deleted = delete_bookmark(path.bookmark_id)
    if not deleted:
        return error_response("NOT_FOUND", "Bookmark not found", HTTPStatus.NOT_FOUND)
    return {"message": "Bookmark deleted"}, HTTPStatus.OK


@bookmarks_bp.get("/triggers/<trigger_id>/bookmarks")
def list_trigger_bookmarks_route(path: TriggerBookmarkPath):
    """List all bookmarks for a specific trigger (for bot profile page)."""
    bookmarks = get_bookmarks_for_bot(path.trigger_id)
    return {"bookmarks": bookmarks, "total": len(bookmarks)}, HTTPStatus.OK
