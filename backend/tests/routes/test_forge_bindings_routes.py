"""Tests for ``/admin/projects/{id}/forge-bindings`` CRUD + preview."""

from __future__ import annotations

import pytest
from litestar.testing import create_test_client

from app.db import create_project
from app.db import create_rule as db_create_rule
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


@pytest.fixture
def workspace_project(isolated_db, tmp_path):
    """A project whose local_path is a real (empty) directory, so
    materialization can resolve a working directory and write files."""
    del isolated_db
    return create_project(name="ws-test", description="fixture", local_path=str(tmp_path)), tmp_path


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

        r = c.delete(f"/admin/projects/{project_id}/forge-bindings/{binding['id']}")
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


# --- atomic forge/create + no-orphan compensation (P7) -------------------


_SUBAGENT_PAYLOAD = {
    "name": "atomic-helper",
    "description": "an atomic test subagent",
    "content": "---\nname: atomic-helper\n---\nBe helpful.\n",
}


def _subagents_named(name):
    from app.db.subagents import get_subagent_by_name

    return get_subagent_by_name(name)


def _bindings(project_id):
    from app.db import list_project_forge_bindings

    return list_project_forge_bindings(project_id)


def test_forge_create_success(workspace_project):
    project_id, tmp_path = workspace_project
    with _client() as c:
        r = c.post(
            f"/admin/projects/{project_id}/forge/create",
            json={
                "kind": "subagent",
                "payload": _SUBAGENT_PAYLOAD,
                "bind": True,
                "materialize": True,
            },
        )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["kind"] == "subagent"
    # row exists
    row = _subagents_named("atomic-helper")
    assert row is not None
    # binding exists
    bindings = _bindings(project_id)
    assert any(b["kind"] == "subagent" and b["asset_id"] == row["id"] for b in bindings)
    # repo file exists on disk
    agent_file = tmp_path / ".claude" / "agents" / "atomic-helper.md"
    assert agent_file.exists()
    assert any(".claude/agents/atomic-helper.md" in p for p in body["written"])


def test_forge_create_no_orphan_on_bind_failure(workspace_project, monkeypatch):
    project_id, tmp_path = workspace_project

    def _boom(*a, **k):
        raise RuntimeError("injected bind failure")

    # Patch the name as bound inside the create service module.
    monkeypatch.setattr("app.services.forge_create_service.add_project_forge_binding", _boom)
    with _client() as c:
        r = c.post(
            f"/admin/projects/{project_id}/forge/create",
            json={"kind": "subagent", "payload": _SUBAGENT_PAYLOAD},
        )
    assert r.status_code >= 500
    # NO orphan: no row, no binding, no repo file.
    assert _subagents_named("atomic-helper") is None
    assert _bindings(project_id) == []
    assert not (tmp_path / ".claude" / "agents" / "atomic-helper.md").exists()


def test_forge_create_no_orphan_on_materialize_failure(workspace_project, monkeypatch):
    project_id, tmp_path = workspace_project

    def _boom(*a, **k):
        raise RuntimeError("injected materialize failure")

    monkeypatch.setattr("app.services.forge_create_service.materialize_primitives", _boom)
    with _client() as c:
        r = c.post(
            f"/admin/projects/{project_id}/forge/create",
            json={"kind": "subagent", "payload": _SUBAGENT_PAYLOAD},
        )
    assert r.status_code >= 500
    # NO orphan: the row AND the binding (both completed before materialize)
    # must be rolled back; no repo file.
    assert _subagents_named("atomic-helper") is None
    assert _bindings(project_id) == []
    assert not (tmp_path / ".claude" / "agents" / "atomic-helper.md").exists()


def test_forge_create_bad_kind_returns_400(project_id):
    with _client() as c:
        r = c.post(
            f"/admin/projects/{project_id}/forge/create",
            json={"kind": "nonsense", "payload": {}},
        )
    assert r.status_code == 400


def test_bundle_bind_cross_kind_one_call(project_id):
    from app.db import create_command as db_create_command
    from app.db.forge_bundles import add_bundle_item, create_forge_bundle
    from app.db.subagents import create_subagent

    rule_id = db_create_rule(name="bundle-rule", project_id=project_id)
    cmd_id = db_create_command(name="bundle-cmd", content="echo hi", project_id=project_id)
    sub = create_subagent(name="bundle-sub", content="---\nname: bundle-sub\n---\nx\n")

    bundle = create_forge_bundle(name="cross-kind-bundle")
    add_bundle_item(bundle["id"], "rule", str(rule_id))
    add_bundle_item(bundle["id"], "command", str(cmd_id))
    add_bundle_item(bundle["id"], "subagent", sub["id"])

    with _client() as c:
        r = c.post(f"/admin/projects/{project_id}/forge/bundles/{bundle['id']}/bind")
    assert r.status_code == 200, r.text
    assert r.json()["bound"] == 3
    bound = {(b["kind"], b["asset_id"]) for b in _bindings(project_id)}
    assert ("rule", str(rule_id)) in bound
    assert ("command", str(cmd_id)) in bound
    assert ("subagent", sub["id"]) in bound
