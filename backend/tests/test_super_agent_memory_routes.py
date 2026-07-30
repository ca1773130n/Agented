"""Route-level guards for the super-agent memory endpoints — the IDOR fix
(codex High) and the enumeration-oracle fix: SA-missing / project-missing /
project-denied must all return an IDENTICAL 404 so an authed caller can't diff
responses to enumerate super-agent or project ids."""

import pytest
from litestar.exceptions import NotFoundException

from app_litestar.auth import Caller
from app_litestar.routes import super_agents_cluster as sac


def _caller():
    return Caller(api_key="k", role="user", user_id="u1")


def _patch(monkeypatch, *, sa=True, project=True, access=True):
    monkeypatch.setattr(sac, "get_super_agent", lambda sid: {"id": sid} if sa else None)
    monkeypatch.setattr("app.db.projects.get_project", lambda pid: {"id": pid} if project else None)
    monkeypatch.setattr("app.db.owned_entities.can_access", lambda table, eid, uid, role: access)


@pytest.mark.parametrize(
    "sa,project,access",
    [
        (False, True, True),  # super-agent doesn't exist
        (True, False, True),  # project doesn't exist (can_access-passes oracle)
        (True, True, False),  # project exists but access denied
    ],
)
def test_memory_route_uniform_404(monkeypatch, sa, project, access):
    _patch(monkeypatch, sa=sa, project=project, access=access)
    with pytest.raises(NotFoundException) as exc:
        sac.super_agent_memory_endpoint.fn("super-x", "proj", _caller())
    assert exc.value.detail == "Not found"  # identical detail in every case


def test_distill_route_uniform_404(monkeypatch):
    _patch(monkeypatch, access=False)
    with pytest.raises(NotFoundException) as exc:
        sac.super_agent_memory_distill_endpoint.fn("super-x", "proj", _caller())
    assert exc.value.detail == "Not found"


def test_distill_route_reports_a_stood_down_click_instead_of_a_job_id(monkeypatch):
    """``run_op_async`` returns "" when the only running distill is the AUTOMATIC
    one, which carries a provider-call budget this click does not. Handing that
    job back would answer an explicit, deliberately unpriced approval with a
    budget refusal — and the SPA would show "Distilling…" for a run this button
    never started."""
    _patch(monkeypatch)
    monkeypatch.setattr("app.services.tesserae_integration.run_op_async", lambda *a, **k: "")
    res = sac.super_agent_memory_distill_endpoint.fn("super-x", "proj", _caller())
    assert res == {"job_id": None, "reason": "auto_distill_running"}


def test_distill_route_returns_the_job_id_when_it_dispatched(monkeypatch):
    """Paired control for the test above."""
    _patch(monkeypatch)
    monkeypatch.setattr(
        "app.services.tesserae_integration.run_op_async", lambda *a, **k: "tess-agent-distill-1"
    )
    res = sac.super_agent_memory_distill_endpoint.fn("super-x", "proj", _caller())
    assert res == {"job_id": "tess-agent-distill-1", "reason": None}


def test_guard_runs_all_checks_even_when_first_fails(monkeypatch):
    # codex (timing oracle): the guard must NOT short-circuit — SA-missing,
    # project-missing, and project-denied must each do the SAME work (query count)
    # so latency can't distinguish them. Assert all three are invoked even when
    # the super-agent is already missing.
    calls = []
    monkeypatch.setattr(sac, "get_super_agent", lambda sid: calls.append("sa") or None)
    monkeypatch.setattr(
        "app.db.projects.get_project", lambda pid: calls.append("proj") or {"id": pid}
    )
    monkeypatch.setattr(
        "app.db.owned_entities.can_access",
        lambda t, e, u, r: calls.append("access") or True,
    )
    with pytest.raises(NotFoundException):
        sac.super_agent_memory_endpoint.fn("missing", "proj", _caller())
    assert calls == ["sa", "proj", "access"]  # all three, no short-circuit


def test_memory_route_allows_when_authorized(monkeypatch):
    _patch(monkeypatch)  # sa + project exist, access granted
    from app.services import super_agent_memory as sam

    monkeypatch.setattr(
        sam, "read_agent_memory", lambda pid, sid: {"key": "k", "notes": [], "text": ""}
    )
    monkeypatch.setattr(sam, "agent_org", lambda pid: [])
    out = sac.super_agent_memory_endpoint.fn("super-x", "my-project", _caller())
    assert out == {"memory": {"key": "k", "notes": [], "text": ""}, "org": []}
