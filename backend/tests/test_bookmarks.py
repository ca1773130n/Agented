"""Tests for execution bookmarking with deep-links and tagging."""

from app.services.bookmark_service import (
    create_bookmark,
    delete_bookmark,
    get_bookmark,
    get_bookmarks_for_bot,
    get_bookmarks_for_execution,
    resolve_deep_link,
    search_bookmarks,
    update_bookmark,
)


def _create_test_bookmark(isolated_db, **kwargs):
    """Helper to create a bookmark with defaults."""
    defaults = {
        "execution_id": "exec-trig-test1-20260101T120000-abc1",
        "trigger_id": "trig-test01",
        "title": "Test Bookmark",
        "notes": "Some notes about this execution",
        "tags": ["security", "critical"],
    }
    defaults.update(kwargs)
    return create_bookmark(**defaults)


def test_create_bookmark(isolated_db):
    """Test creating a bookmark returns a valid ID."""
    bookmark_id = _create_test_bookmark(isolated_db)
    assert bookmark_id is not None
    assert bookmark_id.startswith("bm-")


def test_get_bookmark(isolated_db):
    """Test getting a bookmark by ID returns correct fields."""
    bookmark_id = _create_test_bookmark(isolated_db)
    bookmark = get_bookmark(bookmark_id)

    assert bookmark is not None
    assert bookmark["id"] == bookmark_id
    assert bookmark["execution_id"] == "exec-trig-test1-20260101T120000-abc1"
    assert bookmark["trigger_id"] == "trig-test01"
    assert bookmark["title"] == "Test Bookmark"
    assert bookmark["notes"] == "Some notes about this execution"
    assert bookmark["tags"] == ["security", "critical"]
    assert bookmark["created_by"] == "system"


def test_get_nonexistent_bookmark(isolated_db):
    """Test getting a nonexistent bookmark returns None."""
    bookmark = get_bookmark("bm-nonexist")
    assert bookmark is None


def test_deep_link_without_line_number(isolated_db):
    """Test deep-link generation without line number."""
    bookmark_id = _create_test_bookmark(isolated_db)
    bookmark = get_bookmark(bookmark_id)

    assert bookmark["deep_link"] == "/executions/exec-trig-test1-20260101T120000-abc1"
    assert bookmark["line_number"] is None


def test_deep_link_with_line_number(isolated_db):
    """Test deep-link generation with line number."""
    bookmark_id = _create_test_bookmark(isolated_db, line_number=42)
    bookmark = get_bookmark(bookmark_id)

    assert bookmark["deep_link"] == "/executions/exec-trig-test1-20260101T120000-abc1#line-42"
    assert bookmark["line_number"] == 42


def test_resolve_deep_link_without_line_number(isolated_db):
    """Test resolve_deep_link returns correct URL without line number."""
    bookmark_id = _create_test_bookmark(isolated_db)
    url = resolve_deep_link(bookmark_id)
    assert url == "/executions/exec-trig-test1-20260101T120000-abc1"


def test_resolve_deep_link_with_line_number(isolated_db):
    """Test resolve_deep_link returns correct URL with line number."""
    bookmark_id = _create_test_bookmark(isolated_db, line_number=99)
    url = resolve_deep_link(bookmark_id)
    assert url == "/executions/exec-trig-test1-20260101T120000-abc1#line-99"


def test_resolve_deep_link_nonexistent(isolated_db):
    """Test resolve_deep_link returns None for nonexistent bookmark."""
    url = resolve_deep_link("bm-nonexist")
    assert url is None


def test_list_by_trigger_id(isolated_db):
    """Test listing bookmarks by trigger_id returns correct bookmarks."""
    _create_test_bookmark(isolated_db, trigger_id="trig-alpha", title="Alpha 1")
    _create_test_bookmark(isolated_db, trigger_id="trig-alpha", title="Alpha 2")
    _create_test_bookmark(isolated_db, trigger_id="trig-beta", title="Beta 1")

    alpha_bookmarks = get_bookmarks_for_bot("trig-alpha")
    assert len(alpha_bookmarks) == 2
    titles = {b["title"] for b in alpha_bookmarks}
    assert titles == {"Alpha 1", "Alpha 2"}

    beta_bookmarks = get_bookmarks_for_bot("trig-beta")
    assert len(beta_bookmarks) == 1
    assert beta_bookmarks[0]["title"] == "Beta 1"


def test_list_by_execution_id(isolated_db):
    """Test listing bookmarks by execution_id."""
    exec_id = "exec-trig-test1-20260101T120000-abc1"
    _create_test_bookmark(isolated_db, execution_id=exec_id, title="First")
    _create_test_bookmark(isolated_db, execution_id=exec_id, title="Second", line_number=10)

    bookmarks = get_bookmarks_for_execution(exec_id)
    assert len(bookmarks) == 2


def test_tag_based_search(isolated_db):
    """Test searching bookmarks by tags."""
    _create_test_bookmark(isolated_db, title="Security Finding", tags=["security", "high"])
    _create_test_bookmark(isolated_db, title="Performance Issue", tags=["performance"])
    _create_test_bookmark(isolated_db, title="Bug Fix", tags=["bug", "security"])

    # Search by single tag
    results = search_bookmarks(tags=["security"])
    assert len(results) == 2
    titles = {b["title"] for b in results}
    assert "Security Finding" in titles
    assert "Bug Fix" in titles

    # Search by different tag
    results = search_bookmarks(tags=["performance"])
    assert len(results) == 1
    assert results[0]["title"] == "Performance Issue"


def test_text_search(isolated_db):
    """Test searching bookmarks by text query on title/notes."""
    _create_test_bookmark(
        isolated_db, title="Critical vulnerability", notes="Found SQL injection"
    )
    _create_test_bookmark(
        isolated_db, title="Minor issue", notes="CSS alignment problem"
    )

    results = search_bookmarks(query="SQL injection")
    assert len(results) == 1
    assert results[0]["title"] == "Critical vulnerability"

    results = search_bookmarks(query="Critical")
    assert len(results) == 1


def test_update_bookmark(isolated_db):
    """Test updating a bookmark's title, notes, and tags."""
    bookmark_id = _create_test_bookmark(isolated_db)

    updated = update_bookmark(
        bookmark_id, title="Updated Title", notes="Updated notes", tags=["new-tag"]
    )
    assert updated is True

    bookmark = get_bookmark(bookmark_id)
    assert bookmark["title"] == "Updated Title"
    assert bookmark["notes"] == "Updated notes"
    assert bookmark["tags"] == ["new-tag"]


def test_update_partial(isolated_db):
    """Test updating only some fields of a bookmark."""
    bookmark_id = _create_test_bookmark(isolated_db)

    update_bookmark(bookmark_id, title="New Title Only")

    bookmark = get_bookmark(bookmark_id)
    assert bookmark["title"] == "New Title Only"
    assert bookmark["notes"] == "Some notes about this execution"  # unchanged


def test_delete_bookmark(isolated_db):
    """Test deleting a bookmark."""
    bookmark_id = _create_test_bookmark(isolated_db)

    deleted = delete_bookmark(bookmark_id)
    assert deleted is True

    bookmark = get_bookmark(bookmark_id)
    assert bookmark is None


def test_delete_nonexistent_bookmark(isolated_db):
    """Test deleting a nonexistent bookmark returns False."""
    deleted = delete_bookmark("bm-nonexist")
    assert deleted is False


def test_bookmark_with_invalid_execution_id(isolated_db):
    """Test bookmark creation succeeds even with invalid execution_id."""
    bookmark_id = create_bookmark(
        execution_id="exec-invalid-doesnt-exist",
        trigger_id="trig-test01",
        title="Ghost Bookmark",
    )
    assert bookmark_id is not None
    bookmark = get_bookmark(bookmark_id)
    assert bookmark["execution_id"] == "exec-invalid-doesnt-exist"


def test_empty_tags(isolated_db):
    """Test creating and querying bookmarks with no tags."""
    bookmark_id = create_bookmark(
        execution_id="exec-trig-test1-20260101T120000-abc1",
        trigger_id="trig-test01",
        title="No Tags",
        tags=[],
    )
    bookmark = get_bookmark(bookmark_id)
    assert bookmark["tags"] == []
