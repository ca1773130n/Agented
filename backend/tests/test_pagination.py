"""Tests verifying pagination on previously unpaginated endpoints.

Seeds 25 triggers via isolated_db fixture and verifies:
- Default request returns all items with total_count
- limit=10&offset=0 returns 10 items with correct total_count
- limit=10&offset=10 returns 10 items (items 11-20) with correct total_count
- limit=10&offset=20 returns remaining items with correct total_count
- offset beyond total returns 0 items with correct total_count
- At least 3 previously unpaginated endpoints accept pagination params
"""

import pytest

from app import create_app
from app.db.triggers import count_all_triggers, get_all_triggers


@pytest.fixture
def client(isolated_db):
    """Create a Flask test client with isolated DB."""
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def seed_triggers(isolated_db):
    """Seed 25 custom triggers into the DB for pagination tests.

    Returns (trigger_ids, total_count) where total_count includes predefined triggers.
    """
    from app.db.triggers import add_trigger

    # Count predefined triggers already in DB
    predefined_count = count_all_triggers()

    trigger_ids = []
    for i in range(25):
        tid = add_trigger(
            name=f"Test Trigger {i:03d}",
            prompt_template=f"Test prompt {i}",
            backend_type="claude",
            trigger_source="webhook",
        )
        trigger_ids.append(tid)

    total = predefined_count + 25
    return trigger_ids, total


class TestTriggerPagination:
    """Test pagination on the triggers list endpoint (GET /admin/triggers/)."""

    def test_default_returns_all_with_total_count(self, client, seed_triggers):
        """Default request (no limit/offset) returns all items with total_count."""
        _, total = seed_triggers
        resp = client.get("/admin/triggers/")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "triggers" in data
        assert "total_count" in data
        assert data["total_count"] == total
        assert len(data["triggers"]) == total

    def test_limit_10_offset_0(self, client, seed_triggers):
        """limit=10&offset=0 returns 10 items with correct total_count."""
        _, total = seed_triggers
        resp = client.get("/admin/triggers/?limit=10&offset=0")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["triggers"]) == 10
        assert data["total_count"] == total

    def test_limit_10_offset_10(self, client, seed_triggers):
        """limit=10&offset=10 returns items 11-20 with correct total_count."""
        _, total = seed_triggers
        resp = client.get("/admin/triggers/?limit=10&offset=10")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["triggers"]) == 10
        assert data["total_count"] == total

    def test_limit_10_offset_past_20(self, client, seed_triggers):
        """limit=10&offset=20 returns min(10, remaining) items with correct total_count."""
        _, total = seed_triggers
        resp = client.get("/admin/triggers/?limit=10&offset=20")
        assert resp.status_code == 200
        data = resp.get_json()
        remaining = total - 20
        assert len(data["triggers"]) == min(10, remaining)
        assert data["total_count"] == total

    def test_offset_beyond_total(self, client, seed_triggers):
        """Offset beyond total returns 0 items with correct total_count."""
        _, total = seed_triggers
        resp = client.get(f"/admin/triggers/?limit=10&offset={total + 10}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["triggers"]) == 0
        assert data["total_count"] == total


class TestDBLevelPagination:
    """Test that pagination is implemented at the SQL level."""

    def test_get_all_triggers_with_limit_offset(self, seed_triggers):
        """Verify get_all_triggers uses SQL LIMIT/OFFSET."""
        _, total = seed_triggers
        all_triggers = get_all_triggers()
        assert len(all_triggers) == total

        page1 = get_all_triggers(limit=10, offset=0)
        assert len(page1) == 10

        page2 = get_all_triggers(limit=10, offset=10)
        assert len(page2) == 10

        page3 = get_all_triggers(limit=10, offset=20)
        assert len(page3) == min(10, total - 20)

        over = get_all_triggers(limit=10, offset=total + 5)
        assert len(over) == 0

        # Collect all pages to verify distinct items
        all_items = list(page1) + list(page2) + list(page3)
        all_ids = [t["id"] for t in all_items]
        assert len(set(all_ids)) == len(all_ids)

    def test_count_all_triggers(self, seed_triggers):
        """Verify count_all_triggers returns correct total."""
        _, total = seed_triggers
        assert count_all_triggers() == total


class TestMultipleEndpointsPagination:
    """Verify that at least 3 previously unpaginated endpoints accept pagination params."""

    def test_sketches_accepts_pagination(self, client, isolated_db):
        """GET /admin/sketches/ accepts limit/offset params."""
        resp = client.get("/admin/sketches/?limit=5&offset=0")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "sketches" in data
        assert "total_count" in data

    def test_super_agents_accepts_pagination(self, client, isolated_db):
        """GET /admin/super-agents/ accepts limit/offset params."""
        resp = client.get("/admin/super-agents/?limit=5&offset=0")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "super_agents" in data
        assert "total_count" in data

    def test_executions_accepts_pagination(self, client, isolated_db):
        """GET /admin/executions accepts limit/offset params."""
        resp = client.get("/admin/executions?limit=5&offset=0")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "executions" in data
        assert "total_count" in data

    def test_budget_limits_accepts_pagination(self, client, isolated_db):
        """GET /admin/budgets/limits accepts limit/offset params."""
        resp = client.get("/admin/budgets/limits?limit=5&offset=0")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "limits" in data
        assert "total_count" in data
