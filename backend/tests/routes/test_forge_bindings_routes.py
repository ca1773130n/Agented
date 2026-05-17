"""Tests for ``/admin/projects/{id}/forge-bindings`` CRUD + preview."""

from __future__ import annotations

import pytest
from litestar.testing import create_test_client

from app.db import create_project, create_rule as db_create_rule
from app_litestar.auth import provide_caller
from app_litestar.routes.project_forge_bindings import forge_bindings_router


def _client():
    return create_test_client(
        route_handlers=[forge_bindings_router],
        dependencies={"caller": provide_caller},
    )


@pytest.fixture
def project_id(isolated_db):
    del isolated_db
    return create_project(name="bindings-test", description="fixture")


def test_list_returns_empty(project_id):
    with _client() as c:
        r = c.get(f"/admin/projects/{project_id}/forge-bindings")
    assert r.status_code == 200
    assert r.json() == {"bindings": []}


def test_add_then_list_then_remove(project_id):
    with _client() as c:
        r = c.post(
            f"/admin/projects/{project_id}/forge-bindings",
            json={"kind": "skill", "asset_id": "code-search"},
        )
        assert r.status_code == 201
        binding = r.json()["binding"]
        assert binding["kind"] == "skill"
        assert binding["asset_id"] == "code-search"

        r = c.get(f"/admin/projects/{project_id}/forge-bindings")
        assert len(r.json()["bindings"]) == 1

        r = c.delete(
            f"/admin/projects/{project_id}/forge-bindings/{binding['id']}"
        )
        assert r.status_code == 204

        r = c.get(f"/admin/projects/{project_id}/forge-bindings")
        assert r.json() == {"bindings": []}


def test_replace_overwrites_full_set(project_id):
    with _client() as c:
        c.post(
            f"/admin/projects/{project_id}/forge-bindings",
            json={"kind": "skill", "asset_id": "old-skill"},
        )
        r = c.put(
            f"/admin/projects/{project_id}/forge-bindings",
            json={
                "bindings": [
                    {"kind": "skill", "asset_id": "new-skill"},
                    {"kind": "rule", "asset_id": "42"},
                ]
            },
        )
    assert r.status_code == 200
    asset_ids = {b["asset_id"] for b in r.json()["bindings"]}
    assert asset_ids == {"new-skill", "42"}


def test_add_rejects_unknown_kind(project_id):
    with _client() as c:
        r = c.post(
            f"/admin/projects/{project_id}/forge-bindings",
            json={"kind": "unknown_kind", "asset_id": "x"},
        )
    assert r.status_code == 400


def test_preview_returns_compiled_bundle(project_id):
    rule_id = db_create_rule(
        name="be-terse",
        description="Be terse in all replies.",
        project_id=project_id,
    )
    with _client() as c:
        c.post(
            f"/admin/projects/{project_id}/forge-bindings",
            json={"kind": "rule", "asset_id": str(rule_id)},
        )
        r = c.post(
            f"/admin/projects/{project_id}/forge-context/preview",
            json={"attachments": [{"kind": "snippet", "text": "tip: be brief"}]},
        )
    assert r.status_code in (200, 201)
    bundle = r.json()["bundle"]
    assert "Be terse" in bundle["system_prompt_text"]
    assert "tip: be brief" in bundle["prompt_prepend"]


def test_remove_nonexistent_returns_404(project_id):
    with _client() as c:
        r = c.delete(f"/admin/projects/{project_id}/forge-bindings/999999")
    assert r.status_code == 404


def test_unknown_project_returns_404(isolated_db):
    del isolated_db
    with _client() as c:
        r = c.get("/admin/projects/missing/forge-bindings")
    assert r.status_code == 404
