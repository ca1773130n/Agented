"""Tests for execution quality ratings CRUD and API endpoints."""

import pytest

from app.db.quality_ratings import (
    get_bot_quality_stats,
    get_quality_entries,
    upsert_quality_rating,
)

# Predefined trigger IDs seeded by isolated_db fixture
TRIGGER_A = "bot-security"
TRIGGER_B = "bot-pr-review"


# ---- DB CRUD Tests ----


def test_upsert_quality_rating_insert(isolated_db, app):
    """upsert_quality_rating inserts a new row on first call."""
    from app.db.triggers import create_execution_log

    exec_id = "exec-test-001"
    create_execution_log(
        execution_id=exec_id,
        trigger_id=TRIGGER_A,
        trigger_type="webhook",
        started_at="2026-01-01T00:00:00",
        prompt="test",
        backend_type="claude",
        command="claude -p test",
    )
    result = upsert_quality_rating(
        execution_id=exec_id,
        trigger_id=TRIGGER_A,
        rating=4,
        feedback="Good job",
    )
    assert result["execution_id"] == exec_id
    assert result["rating"] == 4
    assert result["feedback"] == "Good job"
    assert result["trigger_id"] == TRIGGER_A


def test_upsert_quality_rating_update(isolated_db, app):
    """upsert_quality_rating updates existing row on conflict."""
    from app.db.triggers import create_execution_log

    exec_id = "exec-test-002"
    create_execution_log(
        execution_id=exec_id,
        trigger_id=TRIGGER_A,
        trigger_type="webhook",
        started_at="2026-01-01T00:00:00",
        prompt="test",
        backend_type="claude",
        command="claude -p test",
    )
    upsert_quality_rating(execution_id=exec_id, trigger_id=TRIGGER_A, rating=3, feedback="OK")
    result = upsert_quality_rating(
        execution_id=exec_id, trigger_id=TRIGGER_A, rating=5, feedback="Great!"
    )
    assert result["rating"] == 5
    assert result["feedback"] == "Great!"


def test_upsert_quality_rating_invalid_range(isolated_db, app):
    """upsert_quality_rating raises ValueError for out-of-range rating."""
    with pytest.raises(ValueError):
        upsert_quality_rating(
            execution_id="exec-bad", trigger_id=TRIGGER_A, rating=6, feedback=""
        )
    with pytest.raises(ValueError):
        upsert_quality_rating(
            execution_id="exec-bad", trigger_id=TRIGGER_A, rating=0, feedback=""
        )


def test_get_quality_entries_empty(isolated_db, app):
    """get_quality_entries returns empty list when no ratings exist."""
    entries = get_quality_entries()
    assert entries == []


def test_get_quality_entries_with_data(isolated_db, app):
    """get_quality_entries returns entries after insertions."""
    from app.db.triggers import create_execution_log

    for i in range(3):
        exec_id = f"exec-entry-{i}"
        create_execution_log(
            execution_id=exec_id,
            trigger_id=TRIGGER_A,
            trigger_type="webhook",
            started_at="2026-01-01T00:00:00",
            prompt="test",
            backend_type="claude",
            command="claude -p test",
        )
        upsert_quality_rating(execution_id=exec_id, trigger_id=TRIGGER_A, rating=i + 3)

    entries = get_quality_entries()
    assert len(entries) == 3
    # Should include output_preview and trigger_name from JOIN
    assert "output_preview" in entries[0]
    assert "trigger_name" in entries[0]


def test_get_quality_entries_filter_by_trigger(isolated_db, app):
    """get_quality_entries filters correctly by trigger_id."""
    from app.db.triggers import create_execution_log

    create_execution_log(
        execution_id="exec-a1",
        trigger_id=TRIGGER_A,
        trigger_type="webhook",
        started_at="2026-01-01T00:00:00",
        prompt="test",
        backend_type="claude",
        command="claude -p test",
    )
    create_execution_log(
        execution_id="exec-b1",
        trigger_id=TRIGGER_B,
        trigger_type="github",
        started_at="2026-01-01T00:00:00",
        prompt="test",
        backend_type="claude",
        command="claude -p test",
    )
    upsert_quality_rating(execution_id="exec-a1", trigger_id=TRIGGER_A, rating=4)
    upsert_quality_rating(execution_id="exec-b1", trigger_id=TRIGGER_B, rating=2)

    a_entries = get_quality_entries(trigger_id=TRIGGER_A)
    assert len(a_entries) == 1
    assert a_entries[0]["execution_id"] == "exec-a1"

    b_entries = get_quality_entries(trigger_id=TRIGGER_B)
    assert len(b_entries) == 1
    assert b_entries[0]["execution_id"] == "exec-b1"


def test_get_bot_quality_stats_empty(isolated_db, app):
    """get_bot_quality_stats returns empty list when no ratings exist."""
    stats = get_bot_quality_stats()
    assert stats == []


def test_get_bot_quality_stats_with_data(isolated_db, app):
    """get_bot_quality_stats returns aggregated stats per trigger."""
    from app.db.triggers import create_execution_log

    for i in range(5):
        exec_id = f"exec-stats-{i}"
        create_execution_log(
            execution_id=exec_id,
            trigger_id=TRIGGER_A,
            trigger_type="webhook",
            started_at="2026-01-01T00:00:00",
            prompt="test",
            backend_type="claude",
            command="claude -p test",
        )
        upsert_quality_rating(execution_id=exec_id, trigger_id=TRIGGER_A, rating=(i % 5) + 1)

    stats = get_bot_quality_stats()
    assert len(stats) == 1
    stat = stats[0]
    assert stat["trigger_id"] == TRIGGER_A
    assert stat["total_rated"] == 5
    assert isinstance(stat["avg_score"], float)
    assert "recent_scores" in stat
    assert stat["trend"] in ("up", "down", "stable")
    assert isinstance(stat["thumbs_up"], int)
    assert isinstance(stat["thumbs_down"], int)


# ---- API Endpoint Tests ----


def test_list_quality_entries_api(client, isolated_db):
    """GET /admin/quality/entries returns entries list."""
    resp = client.get("/admin/quality/entries")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "entries" in data
    assert "total" in data


def test_list_quality_entries_invalid_limit(client, isolated_db):
    """GET /admin/quality/entries with invalid limit returns 400."""
    resp = client.get("/admin/quality/entries?limit=abc")
    assert resp.status_code == 400


def test_submit_quality_rating_api(client, isolated_db, app):
    """POST /admin/quality/entries/<id> creates/updates a rating."""
    from app.db.triggers import create_execution_log

    with app.app_context():
        create_execution_log(
            execution_id="exec-api-001",
            trigger_id=TRIGGER_A,
            trigger_type="webhook",
            started_at="2026-01-01T00:00:00",
            prompt="test",
            backend_type="claude",
            command="claude -p test",
        )

    resp = client.post(
        "/admin/quality/entries/exec-api-001",
        json={"rating": 4, "feedback": "Nice work", "trigger_id": TRIGGER_A},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["rating"] == 4
    assert data["feedback"] == "Nice work"


def test_submit_quality_rating_api_invalid_rating(client, isolated_db):
    """POST /admin/quality/entries/<id> with rating out of range returns 422 (Pydantic validation)."""
    resp = client.post(
        "/admin/quality/entries/exec-any",
        json={"rating": 6},
    )
    # flask-openapi3 returns 422 for Pydantic validation failures (ge/le constraints)
    assert resp.status_code == 422


def test_get_quality_stats_api(client, isolated_db):
    """GET /admin/quality/stats returns bots list."""
    resp = client.get("/admin/quality/stats")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "bots" in data
