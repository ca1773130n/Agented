"""PR-R (wave 83): unit tests for the retention service.

Covers CRUD + validation + the no-op cleanup contract. The cleanup test
asserts that ``enqueue_cleanup`` does NOT touch other tables — that's the
entire point of deferring destructive enforcement to a follow-up PR.
"""

from __future__ import annotations

import pytest
from litestar.exceptions import ClientException

from app.db import retention_policies as policies_db
from app.services.retention_service import RetentionService


def _valid_payload(**overrides):
    payload = {
        "category": "execution_logs",
        "scope": "team",
        "scope_name": "Backend Team",
        "retention_days": 30,
        "delete_on_expiry": True,
        "archive_on_expiry": False,
        "estimated_size_gb": 1.5,
    }
    payload.update(overrides)
    return payload


def test_create_then_list(isolated_db):
    """Round-trip: created policy is returned from list_policies()."""
    created = RetentionService.create_policy(_valid_payload())
    assert created["id"].startswith("ret-")
    assert created["category"] == "execution_logs"
    assert created["retention_days"] == 30
    assert created["enabled"] == 1

    listed = RetentionService.list_policies()
    assert len(listed) == 1
    assert listed[0]["id"] == created["id"]


def test_create_with_unknown_category_rejected(isolated_db):
    with pytest.raises(ClientException) as exc:
        RetentionService.create_policy(_valid_payload(category="nope"))
    assert "Unknown category" in exc.value.detail


def test_create_with_retention_days_zero_rejected(isolated_db):
    with pytest.raises(ClientException) as exc:
        RetentionService.create_policy(_valid_payload(retention_days=0))
    assert ">= 1" in exc.value.detail


def test_create_with_missing_category_rejected(isolated_db):
    with pytest.raises(ClientException):
        RetentionService.create_policy({"retention_days": 30})


def test_toggle_flips_enabled(isolated_db):
    created = RetentionService.create_policy(_valid_payload())
    assert created["enabled"] == 1

    assert RetentionService.set_enabled(created["id"], False) is True
    refetched = RetentionService.get_policy(created["id"])
    assert refetched is not None
    assert refetched["enabled"] == 0

    assert RetentionService.set_enabled(created["id"], True) is True
    refetched = RetentionService.get_policy(created["id"])
    assert refetched is not None
    assert refetched["enabled"] == 1


def test_toggle_unknown_id_returns_false(isolated_db):
    assert RetentionService.set_enabled("ret-bogus", True) is False


def test_delete_removes_row(isolated_db):
    created = RetentionService.create_policy(_valid_payload())
    assert RetentionService.delete_policy(created["id"]) is True
    assert RetentionService.get_policy(created["id"]) is None
    assert RetentionService.list_policies() == []


def test_delete_unknown_id_returns_false(isolated_db):
    assert RetentionService.delete_policy("ret-bogus") is False


def test_enqueue_cleanup_returns_message_no_data_deleted(isolated_db):
    """The cleanup endpoint must not touch any other table.

    The whole point of PR-R is "persistence ships, enforcement deferred."
    We seed a couple of policies, run cleanup, and assert (a) the response
    has a message, (b) the policies are still there afterward, and (c)
    nothing in some sibling tables vanished.
    """
    from app.db.connection import get_connection

    # Seed two policies.
    RetentionService.create_policy(_valid_payload(category="execution_logs"))
    RetentionService.create_policy(_valid_payload(category="audit_logs", retention_days=180))
    before_count = len(RetentionService.list_policies())
    assert before_count == 2

    # Snapshot a couple of unrelated tables to prove cleanup didn't touch them.
    with get_connection() as conn:
        agents_before = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
        triggers_before = conn.execute("SELECT COUNT(*) FROM triggers").fetchone()[0]

    result = RetentionService.enqueue_cleanup()

    assert "message" in result
    assert "queued" in result["message"].lower()
    assert result["active_policies"] == 2

    # Policies themselves untouched.
    assert len(RetentionService.list_policies()) == before_count

    # Sibling tables untouched.
    with get_connection() as conn:
        agents_after = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
        triggers_after = conn.execute("SELECT COUNT(*) FROM triggers").fetchone()[0]
    assert agents_after == agents_before
    assert triggers_after == triggers_before


def test_ensure_schema_idempotent(isolated_db):
    """Calling ensure_schema twice must not raise (CREATE TABLE IF NOT EXISTS)."""
    policies_db.ensure_schema()
    policies_db.ensure_schema()
    # Sanity: table still works.
    assert RetentionService.list_policies() == []
