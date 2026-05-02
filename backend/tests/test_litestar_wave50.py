"""Smoke tests for the wave 50 batch (bot_templates, quality_ratings)."""

from litestar.testing import create_test_client

from app.db.rbac import create_user_role
from app_litestar.auth import provide_caller
from app_litestar.routes.bot_templates import bot_templates_router
from app_litestar.routes.health import health_router
from app_litestar.routes.quality_ratings import quality_ratings_router


def _client():
    return create_test_client(
        route_handlers=[health_router, bot_templates_router, quality_ratings_router],
        dependencies={"caller": provide_caller},
    )


class TestBotTemplates:
    def test_list_in_bootstrap_mode(self, isolated_db):
        with _client() as c:
            resp = c.get("/admin/bot-templates/")
        assert resp.status_code == 200
        assert "templates" in resp.json()

    def test_unknown_template_returns_404(self, isolated_db):
        create_user_role("admin-key-bt", "Admin", "admin")
        with _client() as c:
            resp = c.get(
                "/admin/bot-templates/missing-id",
                headers={"X-API-Key": "admin-key-bt"},
            )
        assert resp.status_code == 404


class TestQualityRatings:
    def test_list_entries(self, isolated_db):
        with _client() as c:
            resp = c.get("/admin/quality/entries")
        assert resp.status_code == 200
        body = resp.json()
        assert "entries" in body and "total" in body

    def test_invalid_limit_returns_400(self, isolated_db):
        with _client() as c:
            resp = c.get("/admin/quality/entries?limit=500")
        assert resp.status_code == 400

    def test_invalid_rating_returns_400(self, isolated_db):
        with _client() as c:
            resp = c.post(
                "/admin/quality/entries/exec-x",
                json={"rating": 99, "feedback": ""},
            )
        assert resp.status_code == 400

    def test_stats(self, isolated_db):
        with _client() as c:
            resp = c.get("/admin/quality/stats")
        assert resp.status_code == 200
        assert "bots" in resp.json()
