"""Bookmark service for execution pinning with deep-links and tags.

Provides bookmark CRUD and deep-link resolution for bot profile pages.
"""

import logging
from typing import Optional

from app.db.bookmarks import (
    create_bookmark as db_create_bookmark,
)
from app.db.bookmarks import (
    delete_bookmark as db_delete_bookmark,
)
from app.db.bookmarks import (
    get_bookmark as db_get_bookmark,
)
from app.db.bookmarks import (
    list_bookmarks_for_execution,
    list_bookmarks_for_trigger,
)
from app.db.bookmarks import (
    search_bookmarks as db_search_bookmarks,
)
from app.db.bookmarks import (
    update_bookmark as db_update_bookmark,
)

logger = logging.getLogger(__name__)


def create_bookmark(
    execution_id: str,
    trigger_id: str,
    title: str,
    notes: str = "",
    tags: list[str] = None,
    line_number: Optional[int] = None,
    created_by: str = "system",
) -> Optional[str]:
    """Create a bookmark with auto-generated deep-link.

    Args:
        execution_id: The execution ID to bookmark.
        trigger_id: The trigger ID associated with the execution.
        title: Bookmark title.
        notes: Optional notes.
        tags: List of tag strings.
        line_number: Optional line number for deep-link anchor.
        created_by: Who created this bookmark.

    Returns:
        The new bookmark ID, or None on failure.
    """
    if tags is None:
        tags = []

    # Generate deep-link URL
    deep_link = f"/executions/{execution_id}"
    if line_number is not None:
        deep_link = f"{deep_link}#line-{line_number}"

    # Convert tags list to comma-separated string for storage
    tags_str = ",".join(tags)

    return db_create_bookmark(
        execution_id=execution_id,
        trigger_id=trigger_id,
        title=title,
        notes=notes,
        tags=tags_str,
        line_number=line_number,
        deep_link=deep_link,
        created_by=created_by,
    )


def get_bookmarks_for_bot(trigger_id: str) -> list[dict]:
    """Get all bookmarks for a trigger (for bot profile page).

    Args:
        trigger_id: The trigger ID to list bookmarks for.

    Returns:
        List of bookmark dicts with tags parsed as lists.
    """
    bookmarks = list_bookmarks_for_trigger(trigger_id)
    return [_parse_tags(b) for b in bookmarks]


def get_bookmarks_for_execution(execution_id: str) -> list[dict]:
    """Get all bookmarks for an execution.

    Args:
        execution_id: The execution ID.

    Returns:
        List of bookmark dicts with tags parsed as lists.
    """
    bookmarks = list_bookmarks_for_execution(execution_id)
    return [_parse_tags(b) for b in bookmarks]


def resolve_deep_link(bookmark_id: str) -> Optional[str]:
    """Resolve the deep-link URL for a bookmark.

    Args:
        bookmark_id: The bookmark ID.

    Returns:
        The deep-link URL string, or None if bookmark not found.
    """
    bookmark = db_get_bookmark(bookmark_id)
    if not bookmark:
        return None
    return bookmark["deep_link"]


def get_bookmark(bookmark_id: str) -> Optional[dict]:
    """Get a bookmark by ID with parsed tags.

    Args:
        bookmark_id: The bookmark ID.

    Returns:
        Bookmark dict with tags as list, or None.
    """
    bookmark = db_get_bookmark(bookmark_id)
    if not bookmark:
        return None
    return _parse_tags(bookmark)


def update_bookmark(
    bookmark_id: str,
    title: Optional[str] = None,
    notes: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> bool:
    """Update a bookmark's title, notes, or tags.

    Args:
        bookmark_id: The bookmark ID.
        title: New title (if provided).
        notes: New notes (if provided).
        tags: New tags list (if provided).

    Returns:
        True if updated.
    """
    tags_str = ",".join(tags) if tags is not None else None
    return db_update_bookmark(
        bookmark_id=bookmark_id,
        title=title,
        notes=notes,
        tags=tags_str,
    )


def delete_bookmark(bookmark_id: str) -> bool:
    """Delete a bookmark by ID.

    Args:
        bookmark_id: The bookmark ID.

    Returns:
        True if deleted.
    """
    return db_delete_bookmark(bookmark_id)


def search_bookmarks(query: Optional[str] = None, tags: Optional[list[str]] = None) -> list[dict]:
    """Search bookmarks by query text and/or tags.

    Args:
        query: Text search on title/notes.
        tags: List of tags to filter by.

    Returns:
        List of matching bookmarks with tags parsed as lists.
    """
    tags_str = ",".join(tags) if tags else None
    bookmarks = db_search_bookmarks(query=query, tags=tags_str)
    return [_parse_tags(b) for b in bookmarks]


def _parse_tags(bookmark: dict) -> dict:
    """Parse the comma-separated tags string into a list."""
    bookmark = dict(bookmark)
    tags_str = bookmark.get("tags", "")
    bookmark["tags"] = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []
    return bookmark
