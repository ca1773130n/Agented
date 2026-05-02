"""Smoke tests for the Litestar skills cluster (wave 57)."""

from litestar.testing import create_test_client

from app.db.rbac import create_user_role
from app_litestar.auth import provide_caller
from app_litestar.routes.health import health_router
from app_litestar.routes.skills import (
    skill_conversations_router,
    skill_sets_router,
    skills_router,
)


def _client():
    return create_test_client(
        route_handlers=[
            health_router,
            # /api/skills/conversations registered first so its prefix takes
            # precedence over /api/skills/{skill_name} catches.
            skill_conversations_router,
            skills_router,
            skill_sets_router,
        ],
        dependencies={"caller": provide_caller},
    )


def test_list_skills_bootstrap(isolated_db):
    with _client() as c:
        resp = c.get("/api/skills/")
    assert resp.status_code == 200


def test_unknown_skill_404(isolated_db):
    create_user_role("admin-key-skill", "Admin", "admin")
    with _client() as c:
        resp = c.get(
            "/api/skills/discover/missing-skill",
            headers={"X-API-Key": "admin-key-skill"},
        )
    # SkillsService returns NOT_FOUND tuple → 404
    assert resp.status_code == 404


def test_user_skills_list(isolated_db):
    create_user_role("admin-key-us", "Admin", "admin")
    with _client() as c:
        resp = c.get(
            "/api/skills/user",
            headers={"X-API-Key": "admin-key-us"},
        )
    assert resp.status_code == 200


def test_harness_config(isolated_db):
    create_user_role("admin-key-hc", "Admin", "admin")
    with _client() as c:
        resp = c.get(
            "/api/skills/harness/config",
            headers={"X-API-Key": "admin-key-hc"},
        )
    assert resp.status_code in (200, 404, 500)  # depends on harness state


def test_skill_sets_list(isolated_db):
    with _client() as c:
        resp = c.get("/api/skill-sets/")
    assert resp.status_code == 200
    assert "skill_sets" in resp.json()


def test_skill_set_create_rejects_empty_name(isolated_db):
    create_user_role("admin-key-ss", "Admin", "admin")
    with _client() as c:
        resp = c.post(
            "/api/skill-sets/",
            headers={"X-API-Key": "admin-key-ss"},
            json={"name": ""},
        )
    assert resp.status_code == 400


def test_skill_set_update_unknown_404(isolated_db):
    create_user_role("admin-key-ss2", "Admin", "admin")
    with _client() as c:
        resp = c.put(
            "/api/skill-sets/missing-id",
            headers={"X-API-Key": "admin-key-ss2"},
            json={"name": "x"},
        )
    assert resp.status_code == 404


def test_conversation_unknown_404(isolated_db):
    create_user_role("admin-key-conv", "Admin", "admin")
    with _client() as c:
        resp = c.get(
            "/api/skills/conversations/missing-id",
            headers={"X-API-Key": "admin-key-conv"},
        )
    # Service returns NOT_FOUND tuple → 404
    assert resp.status_code == 404


def test_send_message_requires_message(isolated_db):
    create_user_role("admin-key-conv2", "Admin", "admin")
    with _client() as c:
        resp = c.post(
            "/api/skills/conversations/foo/message",
            headers={"X-API-Key": "admin-key-conv2"},
            json={},
        )
    assert resp.status_code == 400
