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


def _drive_to_implementing(project_id, sid):
    """Promote an approved+cleared strategy to 'implementing' via the legal gate.

    The atomic claim (claim_for_autoimplement) requires status='implementing'
    (materialize's mark_implementing flips it), so wired-path tests must put the
    strategy in that state — exactly what running materialize would leave behind.
    """
    return dao.mark_implementing(sid, project_id=project_id)


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
    _drive_to_implementing(project_id, sid)

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

    # Finding #4: the launched subprocess command MUST carry
    # --dangerously-skip-permissions (the contract the autonomous in-worktree
    # code-mod assumes); the service passes an explicit cmd so it actually reaches
    # create_session rather than relying on the handler/manager to inject it.
    assert "--dangerously-skip-permissions" in kw["cmd"]
    assert kw["cmd"][0] == "claude"


# ---------------------------------------------------------------------------
# Finding #1 — atomic claim closes the TOCTOU window before any side effect
# ---------------------------------------------------------------------------


def test_autoimplement_gate_invalidated_after_materialize_no_session(isolated_db, monkeypatch):
    """A strategy whose §5B gate is invalidated cannot launch → no session, fail closed.

    Two layers cover this: the cheap pre-claim read-gate catches a clearance that
    was already NULL (returns legal_gate_not_cleared), and the ATOMIC CLAIM is the
    backstop for the narrow window where invalidation lands AFTER the cheap reads
    but BEFORE the claim. Either way the launch fails CLOSED — no session, no claim.
    """
    monkeypatch.setenv(AGENTED_STRATEGY_AUTOIMPLEMENT, "1")
    project_id = create_project(name="ai-invalidated-proj")
    sid = _seed_strategy(project_id, cleared=True)
    _materialize_plan(project_id, sid)
    _drive_to_implementing(project_id, sid)

    # Concurrent legal-reset slips in: clearance NULLed under the running gate.
    from app.database import get_connection

    with get_connection() as conn:
        conn.execute("UPDATE competitor_strategy SET legal_cleared_at = NULL WHERE id = ?", (sid,))
        conn.commit()

    calls = _spy_session_seams(monkeypatch)
    result = CompetitorStrategyService.start_autoimplement(
        project_id, sid, confirm_token="confirm-please"
    )

    # Fail closed via EITHER layer (cheap read-gate or the atomic claim backstop).
    assert result["status"] in ("legal_gate_not_cleared", "not_eligible")
    assert calls == [], f"invalidated gate must NOT spawn a session: {calls}"
    # No claim sentinel stamped (still NULL session_id → re-claimable once re-cleared).
    assert dao.get_strategy(sid, project_id=project_id)["session_id"] is None


def test_autoimplement_claim_backstop_after_cheap_gate(isolated_db, monkeypatch):
    """The ATOMIC CLAIM is the TOCTOU backstop: invalidation AFTER the cheap reads.

    Lets the cheap gates see a fully-cleared strategy, then NULLs legal_cleared_at
    in the instant the claim runs. The conditional UPDATE matches nothing →
    not_eligible, NO worktree, NO session.
    """
    monkeypatch.setenv(AGENTED_STRATEGY_AUTOIMPLEMENT, "1")
    project_id = create_project(name="ai-backstop-proj")
    sid = _seed_strategy(project_id, cleared=True)
    _materialize_plan(project_id, sid)
    _drive_to_implementing(project_id, sid)

    from app.database import get_connection

    # Race injector: the real claim runs AFTER a concurrent legal-reset NULLs
    # clearance — so the atomic conditional UPDATE matches 0 rows.
    real_claim = dao.claim_for_autoimplement

    def _claim_after_reset(strategy_id, pid):
        with get_connection() as conn:
            conn.execute(
                "UPDATE competitor_strategy SET legal_cleared_at = NULL WHERE id = ?",
                (strategy_id,),
            )
            conn.commit()
        return real_claim(strategy_id, pid)

    import app.services.competitor_strategy_service as svc

    monkeypatch.setattr(svc.competitor_strategies, "claim_for_autoimplement", _claim_after_reset)

    calls = _spy_session_seams(monkeypatch)
    wt = {"called": False}
    monkeypatch.setattr(
        CompetitorStrategyService,
        "_create_strategy_worktree",
        staticmethod(lambda base_dir, strategy_id: wt.__setitem__("called", True) or "/tmp/x"),
    )
    from app.services import project_workspace_service as pws

    monkeypatch.setattr(
        pws.ProjectWorkspaceService,
        "resolve_working_directory",
        staticmethod(lambda pid: "/tmp/ai-backstop-proj"),
    )

    result = CompetitorStrategyService.start_autoimplement(
        project_id, sid, confirm_token="confirm-please"
    )

    assert result["status"] == "not_eligible"
    assert wt["called"] is False, "claim backstop must run BEFORE any worktree"
    assert calls == [], "claim backstop must spawn NO session"
    assert dao.get_strategy(sid, project_id=project_id)["session_id"] is None


def test_autoimplement_double_claim_second_no_session(isolated_db, monkeypatch):
    """A second concurrent launch cannot double-start: second claim returns None."""
    monkeypatch.setenv(AGENTED_STRATEGY_AUTOIMPLEMENT, "1")
    project_id = create_project(name="ai-double-proj")
    sid = _seed_strategy(project_id, cleared=True)
    _materialize_plan(project_id, sid)
    _drive_to_implementing(project_id, sid)

    # First claim succeeds (simulates an in-flight launch holding the claim).
    first = dao.claim_for_autoimplement(sid, project_id)
    assert first is not None
    assert first["session_id"] == dao.AUTOIMPLEMENT_CLAIM_SENTINEL

    # Second launch through the service must find nothing to claim → no session.
    calls = _spy_session_seams(monkeypatch)
    result = CompetitorStrategyService.start_autoimplement(
        project_id, sid, confirm_token="confirm-please"
    )
    assert result["status"] == "not_eligible"
    assert calls == [], f"double-claim must NOT spawn a second session: {calls}"


def test_claim_requires_implementing_cleared_and_plan(isolated_db):
    """claim_for_autoimplement requires status='implementing' + plan_id + cleared."""
    project_id = create_project(name="ai-claim-precond-proj")

    # approved + cleared but NOT implementing, no plan_id → not claimable.
    sid = _seed_strategy(project_id, cleared=True)
    assert dao.claim_for_autoimplement(sid, project_id) is None

    # materialized (plan_id) but still 'approved' (not implementing) → not claimable.
    _materialize_plan(project_id, sid)
    assert dao.claim_for_autoimplement(sid, project_id) is None

    # implementing + cleared + plan_id → claimable exactly once.
    _drive_to_implementing(project_id, sid)
    assert dao.claim_for_autoimplement(sid, project_id) is not None
    assert dao.claim_for_autoimplement(sid, project_id) is None  # second returns None


def test_legal_reset_blocked_while_implementing(isolated_db):
    """update_body / record_legal_item must refuse to reset clearance in-flight."""
    import pytest

    project_id = create_project(name="ai-reset-block-proj")
    sid = _seed_strategy(project_id, cleared=True)
    _materialize_plan(project_id, sid)
    _drive_to_implementing(project_id, sid)

    with pytest.raises(ValueError):
        dao.update_body(sid, body="edited under running loop", project_id=project_id)
    with pytest.raises(ValueError):
        dao.record_legal_item(sid, "no_copied_code", False, project_id=project_id)

    # Clearance untouched — the loop's gate is intact.
    assert dao.get_strategy(sid, project_id=project_id)["legal_cleared_at"] is not None


# ---------------------------------------------------------------------------
# Finding #2 — launch failure cleans up the worktree + un-claims the strategy
# ---------------------------------------------------------------------------


def test_autoimplement_launch_failure_cleans_up(isolated_db, monkeypatch):
    """A create_session that raises leaves NO worktree, NO branch, un-claimed."""
    monkeypatch.setenv(AGENTED_STRATEGY_AUTOIMPLEMENT, "1")
    project_id = create_project(name="ai-cleanup-proj")
    sid = _seed_strategy(project_id, cleared=True)
    _materialize_plan(project_id, sid)
    _drive_to_implementing(project_id, sid)

    from app.services import project_workspace_service as pws

    monkeypatch.setattr(
        pws.ProjectWorkspaceService,
        "resolve_working_directory",
        staticmethod(lambda pid: "/tmp/ai-cleanup-proj"),
    )
    monkeypatch.setattr(
        CompetitorStrategyService,
        "_create_strategy_worktree",
        staticmethod(lambda base_dir, strategy_id: "/tmp/ai-cleanup-proj/.worktrees/strategy-x"),
    )

    removed = {}
    monkeypatch.setattr(
        CompetitorStrategyService,
        "_remove_strategy_worktree",
        staticmethod(
            lambda base_dir, strategy_id: removed.__setitem__("called", (base_dir, strategy_id))
        ),
    )

    from app.services import project_session_manager as psm

    def _boom(*a, **k):
        raise RuntimeError("launch exploded")

    monkeypatch.setattr(psm.ProjectSessionManager, "create_session", _boom)

    import pytest

    with pytest.raises((RuntimeError, ValueError)):
        CompetitorStrategyService.start_autoimplement(
            project_id, sid, confirm_token="confirm-please"
        )

    # Worktree teardown was invoked, and the claim was reverted → re-claimable.
    assert removed.get("called") is not None
    row = dao.get_strategy(sid, project_id=project_id)
    assert row["session_id"] is None
    assert dao.claim_for_autoimplement(sid, project_id) is not None


# ---------------------------------------------------------------------------
# Finding #3 — worktree reuse rejects symlinks / stale dirs (cwd never escapes)
# ---------------------------------------------------------------------------


def test_worktree_reuse_rejects_symlink(isolated_db, tmp_path, monkeypatch):
    """A symlink at .worktrees/strategy-{sid} is rejected, not reused as cwd."""
    import os
    import subprocess

    base = tmp_path / "repo"
    base.mkdir()
    subprocess.run(["git", "init", str(base)], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(base), "config", "user.email", "t@t.t"], check=True)
    subprocess.run(["git", "-C", str(base), "config", "user.name", "t"], check=True)
    (base / "f.txt").write_text("x")
    subprocess.run(["git", "-C", str(base), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(base), "commit", "-m", "init"], capture_output=True, check=True
    )

    worktrees = base / ".worktrees"
    worktrees.mkdir()
    # A SYMLINK pointing back at main — the exact escape the validation must reject.
    link = worktrees / "strategy-evil"
    os.symlink(str(base), str(link))

    removed = {"n": 0}
    orig_remove = CompetitorStrategyService._remove_strategy_worktree

    def _spy_remove(base_dir, strategy_id):
        removed["n"] += 1
        orig_remove(base_dir, strategy_id)

    monkeypatch.setattr(
        CompetitorStrategyService, "_remove_strategy_worktree", staticmethod(_spy_remove)
    )

    result = CompetitorStrategyService._create_strategy_worktree(str(base), "evil")

    # The symlink was detected + torn down (cwd must NEVER escape to main). Whatever
    # path is returned must NOT resolve to the main checkout, and the original
    # symlink must no longer exist (a real worktree or nothing replaces it).
    assert removed["n"] >= 1, "symlink reuse must trigger teardown"
    assert not os.path.islink(str(link)), "the escaping symlink must be removed"
    if result is not None:
        assert os.path.realpath(result) != os.path.realpath(str(base)), (
            "cwd must never resolve to the main checkout"
        )


# ---------------------------------------------------------------------------
# Finding #5 — goal fails CLOSED on missing/empty tasks_json (no session)
# ---------------------------------------------------------------------------


def test_autoimplement_empty_tasks_json_fails_closed(isolated_db, monkeypatch):
    """Invalid/empty tasks_json → ValueError, NO claim, NO worktree, NO session."""
    import pytest

    from app.database import get_connection

    monkeypatch.setenv(AGENTED_STRATEGY_AUTOIMPLEMENT, "1")
    project_id = create_project(name="ai-emptytasks-proj")
    sid = _seed_strategy(project_id, cleared=True)
    _materialize_plan(project_id, sid)
    _drive_to_implementing(project_id, sid)

    # Corrupt the plan's tasks_json to an empty-tasks blob (post-materialize tamper).
    plan_id = dao.get_strategy(sid, project_id=project_id)["plan_id"]
    with get_connection() as conn:
        conn.execute(
            "UPDATE project_plans SET tasks_json = ? WHERE id = ?",
            ('{"tasks": []}', plan_id),
        )
        conn.commit()

    calls = _spy_session_seams(monkeypatch)
    wt = {"called": False}
    monkeypatch.setattr(
        CompetitorStrategyService,
        "_create_strategy_worktree",
        staticmethod(lambda base_dir, strategy_id: wt.__setitem__("called", True) or "/tmp/x"),
    )

    with pytest.raises(ValueError):
        CompetitorStrategyService.start_autoimplement(
            project_id, sid, confirm_token="confirm-please"
        )

    assert calls == [], "empty tasks_json must NOT spawn a session"
    assert wt["called"] is False, "empty tasks_json must NOT create a worktree"
    # Goal builds before the claim → strategy left un-claimed (session_id NULL).
    assert dao.get_strategy(sid, project_id=project_id)["session_id"] is None


def test_build_goal_rejects_unparseable_tasks_json(isolated_db):
    """_build_autoimplement_goal raises on missing/unparseable/empty tasks_json."""
    import pytest

    for bad in (None, "", "not json", '{"tasks": []}', "{}", '{"tasks": [1, 2]}'):
        with pytest.raises(ValueError):
            CompetitorStrategyService._build_autoimplement_goal({"tasks_json": bad})
