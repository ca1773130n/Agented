"""Materialize tests (26-04 — the conservative IMPLEMENT step of the P4 loop).

Exercises ``CompetitorStrategyService.materialize`` against an ``isolated_db``
(migration 174 gives ``competitor_strategy``; the v04 GRD tables give projects /
milestones / phases / plans). The headline assertions:

* An approved + §5B-CLEARED strategy materializes into a real ``ProjectPlan``
  (``plan-`` id) with a populated ``tasks_json``, stamping
  ``competitor_strategy.plan_id`` + ``status='implementing'`` via the
  ``mark_implementing`` DAO gate — and mutates NO repo files. The
  ExecutionService / goal_loop_runner / ProjectSessionManager seams are spied on
  and asserted NOT called (zero repo mutation, zero session spawn).
* An UNCLEARED strategy raises ``LegalGateNotCleared`` and creates NO plan (plan
  count unchanged, ``plan_id`` still null, status still ``'approved'``) — the
  non-bypassable §5B gate, re-enforced on the materialize path.
* A not-approved (still ``'proposed'``) strategy raises ``ValueError``.
"""

import pytest

from app.database import get_connection
from app.db import competitor_strategies as dao
from app.db import grd as grd_db
from app.db.competitor_strategies import LEGAL_CHECKLIST_ITEMS, LegalGateNotCleared
from app.db.projects import create_project
from app.services.competitor_strategy_service import CompetitorStrategyService


def _seed_project_with_phase(*, name="ci-materialize-proj"):
    """Create a project + a milestone + one phase, set it as the current milestone.

    Returns ``(project_id, milestone_id, phase_id)``. ``current_milestone_id`` is
    stamped via raw SQL (no public setter on ``update_project`` for it).
    """
    project_id = create_project(name=name)
    milestone_id = grd_db.create_milestone(project_id, "v0.9.0", "Test milestone")
    phase_id = grd_db.add_project_phase(milestone_id, 1, "Phase 1")
    with get_connection() as conn:
        conn.execute(
            "UPDATE projects SET current_milestone_id = ? WHERE id = ?",
            (milestone_id, project_id),
        )
        conn.commit()
    return project_id, milestone_id, phase_id


def _seed_strategy(project_id, *, status="approved", cleared=False):
    """Insert a competitor_strategy, optionally approved + 7/7 legally cleared."""
    strat = dao.create_strategy(
        project_id,
        title="Respond to ACME's new feature",
        body="Ship our own behavior-only response: do X, then Y.",
        backend_kind="claude",
        model="claude-haiku-4-5-20251001",
    )
    sid = strat["id"]
    if cleared:
        for item in LEGAL_CHECKLIST_ITEMS:
            dao.record_legal_item(sid, item, True, project_id=project_id)
    if status == "approved":
        dao.set_status(sid, "approved", project_id=project_id)
    return sid


def _spy_no_repo_mutation(monkeypatch):
    """Spy the autonomy/execution seams; record any call. Returns the call list.

    These modules import lazily inside the runner, so we patch the symbols the
    MVP path would have to reach IF it (wrongly) tried to spawn a session. The
    MVP must touch NONE of them — materialize writes a PLAN ARTIFACT only.
    """
    calls = []

    import app.services.goal_loop_runner as glr

    monkeypatch.setattr(glr, "start_runner", lambda *a, **k: calls.append(("start_runner", a, k)))
    try:
        from app.services import project_session_manager as psm

        monkeypatch.setattr(
            psm.ProjectSessionManager,
            "create_session",
            lambda *a, **k: calls.append(("create_session", a, k)),
        )
    except (ImportError, AttributeError):  # pragma: no cover - manager optional in some test builds
        pass
    try:
        from app.services import execution_service as es

        monkeypatch.setattr(
            es.ExecutionService,
            "run_trigger",
            lambda *a, **k: calls.append(("run_trigger", a, k)),
        )
    except (ImportError, AttributeError):  # pragma: no cover
        pass
    return calls


def test_materialize_creates_plan_and_stamps_strategy(isolated_db, monkeypatch):
    project_id, milestone_id, phase_id = _seed_project_with_phase()
    sid = _seed_strategy(project_id, status="approved", cleared=True)
    calls = _spy_no_repo_mutation(monkeypatch)

    before = len(grd_db.get_plans_by_phase(phase_id))
    result = CompetitorStrategyService.materialize(project_id, sid)

    # A real ProjectPlan was created under the current phase.
    plans = grd_db.get_plans_by_phase(phase_id)
    assert len(plans) == before + 1
    plan = result["plan"]
    assert plan["id"].startswith("plan-")
    assert plan["phase_id"] == phase_id
    assert plan["tasks_json"]
    assert "competitor_strategy" in plan["tasks_json"]

    # The strategy got stamped + transitioned through the gate.
    strat = result["strategy"]
    assert strat["plan_id"] == plan["id"]
    assert strat["status"] == "implementing"

    # ZERO repo mutation / session spawn.
    assert calls == [], f"materialize must not spawn any execution/session: {calls}"


def test_materialize_uncleared_raises_and_creates_no_plan(isolated_db, monkeypatch):
    project_id, milestone_id, phase_id = _seed_project_with_phase(name="uncleared-proj")
    sid = _seed_strategy(project_id, status="approved", cleared=False)
    _spy_no_repo_mutation(monkeypatch)

    before = len(grd_db.get_plans_by_phase(phase_id))
    with pytest.raises(LegalGateNotCleared):
        CompetitorStrategyService.materialize(project_id, sid)

    # No plan created, no stamp, status untouched.
    assert len(grd_db.get_plans_by_phase(phase_id)) == before
    strat = dao.get_strategy(sid, project_id=project_id)
    assert strat["plan_id"] is None
    assert strat["status"] == "approved"


def test_materialize_not_approved_raises_valueerror(isolated_db):
    project_id, milestone_id, phase_id = _seed_project_with_phase(name="proposed-proj")
    # status='proposed' (not approved), even if legally cleared.
    sid = _seed_strategy(project_id, status="proposed", cleared=True)

    before = len(grd_db.get_plans_by_phase(phase_id))
    with pytest.raises(ValueError):
        CompetitorStrategyService.materialize(project_id, sid)
    assert len(grd_db.get_plans_by_phase(phase_id)) == before


def test_materialize_foreign_strategy_raises(isolated_db):
    """A strategy from project B cannot be materialized via project A's id."""
    proj_a, _, _ = _seed_project_with_phase(name="proj-a")
    proj_b, _, _ = _seed_project_with_phase(name="proj-b")
    sid_b = _seed_strategy(proj_b, status="approved", cleared=True)
    with pytest.raises(ValueError):
        CompetitorStrategyService.materialize(proj_a, sid_b)


def test_materialize_plan_creation_failure_reverts_to_approved(isolated_db, monkeypatch):
    """add_project_plan failing AFTER mark_implementing must NOT wedge the strategy.

    mark_implementing flips 'approved' -> 'implementing' BEFORE the plan is
    created. If plan creation then fails, the strategy must NOT be left stuck in
    'implementing' with no plan_id (an un-editable, un-re-materializable wedge):
    materialize reverts it back to 'approved', PRESERVES legal_cleared_at, and
    re-raises — so the operator can simply retry.
    """
    import app.services.competitor_strategy_service as svc

    project_id, milestone_id, phase_id = _seed_project_with_phase(name="materialize-revert-proj")
    sid = _seed_strategy(project_id, status="approved", cleared=True)
    cleared_before = dao.get_strategy(sid, project_id=project_id)["legal_cleared_at"]
    assert cleared_before is not None

    # Plan creation explodes (e.g. an IntegrityError) AFTER mark_implementing ran.
    def _boom(*a, **k):
        raise RuntimeError("plan insert exploded")

    monkeypatch.setattr(svc.grd_db, "add_project_plan", _boom)

    before = len(grd_db.get_plans_by_phase(phase_id))
    with pytest.raises(RuntimeError):
        CompetitorStrategyService.materialize(project_id, sid)

    # No plan persisted, no plan_id stamped.
    assert len(grd_db.get_plans_by_phase(phase_id)) == before
    strat = dao.get_strategy(sid, project_id=project_id)
    assert strat["plan_id"] is None
    # Reverted to 'approved' (not wedged in 'implementing') with clearance intact:
    # the strategy is immediately re-materializable.
    assert strat["status"] == "approved"
    assert strat["legal_cleared_at"] is not None


def test_materialize_plan_returns_none_reverts_to_approved(isolated_db, monkeypatch):
    """add_project_plan returning None (not raising) also reverts the strategy."""
    import app.services.competitor_strategy_service as svc

    project_id, milestone_id, phase_id = _seed_project_with_phase(name="materialize-none-proj")
    sid = _seed_strategy(project_id, status="approved", cleared=True)

    real_add_project_plan = svc.grd_db.add_project_plan
    monkeypatch.setattr(svc.grd_db, "add_project_plan", lambda *a, **k: None)

    with pytest.raises(ValueError):
        CompetitorStrategyService.materialize(project_id, sid)

    strat = dao.get_strategy(sid, project_id=project_id)
    assert strat["plan_id"] is None
    assert strat["status"] == "approved"
    assert strat["legal_cleared_at"] is not None

    # And it is genuinely re-materializable: restoring the REAL add_project_plan
    # (without unwinding the isolated_db patch) lets the operator retry, which now
    # succeeds and lands the plan + flips back to 'implementing'.
    monkeypatch.setattr(svc.grd_db, "add_project_plan", real_add_project_plan)
    out = CompetitorStrategyService.materialize(project_id, sid)
    assert out["plan"] is not None
    assert dao.get_strategy(sid, project_id=project_id)["status"] == "implementing"
