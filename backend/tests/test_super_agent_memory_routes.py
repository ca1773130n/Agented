"""Route-level guards for the super-agent memory endpoints — the IDOR fix
(codex High): a caller must pass the project access check before reading a
project's agent memory or triggering its distill, not merely prove the SA exists."""

import pytest
from litestar.exceptions import NotFoundException

from app_litestar.auth import Caller
from app_litestar.routes import super_agents_cluster as sac


def _caller():
    return Caller(api_key="k", role="user", user_id="u1")


def test_memory_route_denies_when_project_access_denied(monkeypatch):
    # SA exists, but the caller can't access the project → 404 (IDOR guard).
    monkeypatch.setattr(sac, "get_super_agent", lambda sid: {"id": sid})
    monkeypatch.setattr(
        "app.db.owned_entities.can_access", lambda table, eid, uid, role: False
    )
    with pytest.raises(NotFoundException):
        sac.super_agent_memory_endpoint.fn("super-x", "victim-project", _caller())


def test_distill_route_denies_when_project_access_denied(monkeypatch):
    monkeypatch.setattr(sac, "get_super_agent", lambda sid: {"id": sid})
    monkeypatch.setattr(
        "app.db.owned_entities.can_access", lambda table, eid, uid, role: False
    )
    with pytest.raises(NotFoundException):
        sac.super_agent_memory_distill_endpoint.fn("super-x", "victim-project", _caller())


def test_memory_route_allows_when_project_access_granted(monkeypatch):
    monkeypatch.setattr(sac, "get_super_agent", lambda sid: {"id": sid})
    monkeypatch.setattr(
        "app.db.owned_entities.can_access", lambda table, eid, uid, role: True
    )
    from app.services import super_agent_memory as sam

    monkeypatch.setattr(
        sam, "read_agent_memory", lambda pid, sid: {"key": "k", "notes": [], "text": ""}
    )
    monkeypatch.setattr(sam, "agent_org", lambda pid: [])
    out = sac.super_agent_memory_endpoint.fn("super-x", "my-project", _caller())
    assert out == {"memory": {"key": "k", "notes": [], "text": ""}, "org": []}
