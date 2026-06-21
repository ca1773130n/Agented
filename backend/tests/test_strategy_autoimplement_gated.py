"""Auto-implement seam gating tests (26-05 — the TRIPLE-GATED auto-code wire).

``CompetitorStrategyService.start_autoimplement`` is the entry point into the
autonomy stack. It is the headline-safety seam: it must stay INERT (no session,
no repo touch) whenever ANY gate fails, and only spawns a goal-loop when ALL THREE
gates pass AND the strategy is materialized. These tests pin every gate state:

* ``AGENTED_STRATEGY_AUTOIMPLEMENT`` unset → ``disabled`` (the default) — NO session.
* flag set but strategy uncleared → ``legal_gate_not_cleared`` — NO session.
* flag set + cleared but no ``confirm_token`` → ``confirmation_required`` — NO session.
* flag set + cleared + confirm but NO ``plan_id`` → ``not_materialized`` — NO session.
* flag set + cleared + confirm + materialized → CALLS ``create_session`` ONCE with
  ``execution_type='goal_loop'``, a ``human_gate`` in the config, and ``cwd`` =
  the project worktree; returns ``status='started'`` + the new ``session_id``.
"""

from app.db import competitor_strategies as dao
from app.db import grd as grd_db
from app.db.competitor_strategies import LEGAL_CHECKLIST_ITEMS
from app.db.projects import create_project
from app.services.competitor_strategy_service import (
    AGENTED_STRATEGY_AUTOIMPLEMENT,
    CompetitorStrategyService,
)


def _seed_strategy(project_id, *, cleared=False):
    strat = dao.create_strategy(
        project_id,
        title="Auto-implement seam strategy",
        body="behavior-only response",
        backend_kind="claude",
        model="claude-haiku-4-5-20251001",
    )
    sid = strat["id"]
    if cleared:
        for item in LEGAL_CHECKLIST_ITEMS:
            dao.record_legal_item(sid, item, True, project_id=project_id)
    dao.set_status(sid, "approved", project_id=project_id)
    return sid


def _materialize_plan(project_id, sid):
    """Give a strategy a real ProjectPlan + stamp plan_id (the materialize precond).

    Builds a milestone+phase, adds a plan with a competitor-strategy ``tasks_json``,
    and stamps ``competitor_strategy.plan_id`` — the state ``materialize`` leaves
    behind, without driving the full materialize path.
    """
    from app.database import get_connection

    milestone_id = grd_db.create_milestone(project_id, "v0.9.0", "Test milestone")
    phase_id = grd_db.add_project_phase(milestone_id, 1, "Phase 1")
    plan_id = grd_db.add_project_plan(
        phase_id=phase_id,
        plan_number=1,
        title="Respond to ACME",
        description="behavior-only response",
        tasks_json='{"tasks": [{"id": 1, "title": "Do X", "description": "implement X"}]}',
    )
    with get_connection() as conn:
        conn.execute(
            "UPDATE competitor_strategy SET plan_id = ? WHERE id = ? AND project_id = ?",
            (plan_id, sid, project_id),
        )
        conn.commit()
    return plan_id


def _spy_session_seams(monkeypatch):
    """Spy the session-spawn seams; return the call list (empty unless wired path)."""
    calls = []
    import app.services.goal_loop_runner as glr

    monkeypatch.setattr(glr, "start_runner", lambda *a, **k: calls.append(("start_runner", a, k)))
    from app.services import project_session_manager as psm

    monkeypatch.setattr(
        psm.ProjectSessionManager,
        "create_session",
        lambda *a, **k: calls.append(("create_session", a, k)),
    )
    return calls


def test_autoimplement_disabled_by_default(isolated_db, monkeypatch):
    monkeypatch.delenv(AGENTED_STRATEGY_AUTOIMPLEMENT, raising=False)
    project_id = create_project(name="ai-off-proj")
    sid = _seed_strategy(project_id, cleared=True)

    result = CompetitorStrategyService.start_autoimplement(project_id, sid, confirm_token="yes")
    assert result["status"] == "disabled"


def test_autoimplement_flag_on_but_uncleared(isolated_db, monkeypatch):
    monkeypatch.setenv(AGENTED_STRATEGY_AUTOIMPLEMENT, "1")
    project_id = create_project(name="ai-uncleared-proj")
    sid = _seed_strategy(project_id, cleared=False)

    result = CompetitorStrategyService.start_autoimplement(project_id, sid, confirm_token="yes")
    assert result["status"] == "legal_gate_not_cleared"


def test_autoimplement_flag_on_cleared_no_confirm(isolated_db, monkeypatch):
    monkeypatch.setenv(AGENTED_STRATEGY_AUTOIMPLEMENT, "1")
    project_id = create_project(name="ai-noconfirm-proj")
    sid = _seed_strategy(project_id, cleared=True)

    result = CompetitorStrategyService.start_autoimplement(project_id, sid)
    assert result["status"] == "confirmation_required"


def test_autoimplement_all_gates_pass_but_not_materialized(isolated_db, monkeypatch):
    """Flag on + cleared + confirm, but NO plan_id → not_materialized, NO session."""
    monkeypatch.setenv(AGENTED_STRATEGY_AUTOIMPLEMENT, "1")
    project_id = create_project(name="ai-unmaterialized-proj")
    sid = _seed_strategy(project_id, cleared=True)
    calls = _spy_session_seams(monkeypatch)

    result = CompetitorStrategyService.start_autoimplement(
        project_id, sid, confirm_token="confirm-please"
    )

    assert result["status"] == "not_materialized"
    # No plan to implement → still INERT.
    assert calls == [], f"un-materialized strategy must NOT spawn a session: {calls}"


def test_autoimplement_wired_path_spawns_goal_loop(isolated_db, monkeypatch):
    """All three gates + a materialized plan → ONE goal_loop session in the worktree."""
    monkeypatch.setenv(AGENTED_STRATEGY_AUTOIMPLEMENT, "1")
    project_id = create_project(name="ai-wired-proj")
    sid = _seed_strategy(project_id, cleared=True)
    _materialize_plan(project_id, sid)

    # Stub the worktree carve-out (no real git) — return a deterministic path so we
    # can assert the loop's cwd is the worktree, never main.
    fake_worktree = "/tmp/ai-wired-proj/.worktrees/strategy-xyz"
    monkeypatch.setattr(
        CompetitorStrategyService,
        "_create_strategy_worktree",
        staticmethod(lambda base_dir, strategy_id: fake_worktree),
    )
    # Resolve the project working dir without touching disk/git.
    from app.services import project_workspace_service as pws

    monkeypatch.setattr(
        pws.ProjectWorkspaceService,
        "resolve_working_directory",
        staticmethod(lambda pid: "/tmp/ai-wired-proj"),
    )

    # Spy create_session (return a fake session id), and neutralize the runner +
    # config-persist seams the handler reaches after it.
    captured = {}

    from app.services import project_session_manager as psm

    def _fake_create_session(*a, **k):
        captured["kwargs"] = k
        return "psess-wired1"

    monkeypatch.setattr(psm.ProjectSessionManager, "create_session", _fake_create_session)
    monkeypatch.setattr(
        psm.ProjectSessionManager,
        "get_session_info",
        staticmethod(lambda sid_: {"pid": 4242, "status": "active"}),
    )
    import app.services.goal_loop_runner as glr

    monkeypatch.setattr(glr, "start_runner", lambda *a, **k: None)
    import app.db as appdb

    # Capture the goal_loop_config the handler persists — the human_gate proof.
    monkeypatch.setattr(
        appdb,
        "set_goal_loop_config",
        lambda session_id_, cfg, *a, **k: captured.__setitem__("goal_loop_config", cfg),
    )

    result = CompetitorStrategyService.start_autoimplement(
        project_id, sid, confirm_token="confirm-please"
    )

    # Session launched, id surfaced + stamped on the strategy.
    assert result["status"] == "started"
    assert result["session_id"] == "psess-wired1"
    assert result["worktree_path"] == fake_worktree
    assert dao.get_strategy(sid, project_id=project_id)["session_id"] == "psess-wired1"

    # create_session was called ONCE with goal_loop + the worktree cwd.
    kw = captured["kwargs"]
    assert kw["execution_type"] == "goal_loop"
    assert kw["execution_mode"] == "autonomous"
    assert kw["cwd"] == fake_worktree
    assert kw["worktree_path"] == fake_worktree

    # The launched goal_loop_config carries a human_gate (operator approval pause)
    # and a non-empty goal derived from the materialized plan's tasks_json.
    cfg = captured["goal_loop_config"]
    assert cfg["human_gate"]["mode"] in ("on_exit", "every_n")
    assert "Do X" in cfg["goal"]
