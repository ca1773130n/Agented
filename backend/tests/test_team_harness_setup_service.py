"""Phase 21 (21-02) skeleton tests for TeamHarnessSetupService.

Covers the cross-cutting orchestration contract: import smoke (EVAL S3),
the none->running->ready/failed state machine, the failed-step + retryable
behaviour (P6), and the re-run-skips-ok idempotency floor (P1).

These tests are EXTENDED by 21-03..06 as the real step bodies land (driver,
no_destructive, bundle_selection, renderer_compile, autonomy_policy). The
``-k`` keywords used here ("failed_step", "idempotent") match the EVAL P1/P6
commands so later plans add to the same file.
"""

from app.db.projects import create_project, get_harness_setup_status, get_harness_setup_steps
from app.services import team_harness_setup_service as svc
from app.services.team_harness_setup_service import (
    HARNESS_SETUP_STEP_KEYS,
    StepResult,
    TeamHarnessSetupService,
)


def _all_ok_funcs():
    """Build a dispatch table where every step returns StepResult ok."""
    return {key: (lambda pid, row, k=key: StepResult(k, "ok")) for key in HARNESS_SETUP_STEP_KEYS}


def test_import_smoke_six_step_keys():
    """EVAL S3: module imports cleanly and the six ordered keys match."""
    assert len(HARNESS_SETUP_STEP_KEYS) == 6
    assert HARNESS_SETUP_STEP_KEYS == [
        "grd_init",
        "team_topology",
        "bundle_binding",
        "tesserae_enable",
        "default_policies",
        "materialize_compile",
    ]


def test_state_machine_fresh_run_ready(isolated_db, monkeypatch):
    """Fresh run with all-ok steps ends 'ready' with 6 ok rows."""
    pid = create_project(name="harness-fresh-ready")
    monkeypatch.setattr(TeamHarnessSetupService, "_STEP_FUNCS", _all_ok_funcs())

    final = TeamHarnessSetupService.setup(pid)

    assert final == "ready"
    assert get_harness_setup_status(pid) == "ready"
    rows = get_harness_setup_steps(pid)
    assert len(rows) == 6
    assert all(r["status"] == "ok" for r in rows)
    assert {r["step_key"] for r in rows} == set(HARNESS_SETUP_STEP_KEYS)


def test_failed_step_sets_failed_and_stops(isolated_db, monkeypatch):
    """failed_step: 2nd step raises -> status 'failed', failed row with detail,
    later steps have NO rows (still retryable)."""
    pid = create_project(name="harness-failed-step")

    def boom(project_id, existing_row):
        raise RuntimeError("topology blew up")

    funcs = _all_ok_funcs()
    funcs["team_topology"] = boom
    monkeypatch.setattr(TeamHarnessSetupService, "_STEP_FUNCS", funcs)

    final = TeamHarnessSetupService.setup(pid)

    assert final == "failed"
    assert get_harness_setup_status(pid) == "failed"
    rows = {r["step_key"]: r for r in get_harness_setup_steps(pid)}
    # Step a (before the failure) recorded ok.
    assert rows["grd_init"]["status"] == "ok"
    # Failed step recorded with non-empty detail.
    assert rows["team_topology"]["status"] == "failed"
    assert rows["team_topology"]["detail"]
    assert "topology blew up" in rows["team_topology"]["detail"]
    # Steps AFTER the failure are unrecorded -> retryable.
    for later in ("bundle_binding", "tesserae_enable", "default_policies", "materialize_compile"):
        assert later not in rows


def test_rerun_skips_ok_steps_idempotent(isolated_db, monkeypatch):
    """idempotent: a successful run, then a re-run skips already-ok steps
    (their body does not execute) while a never-run/failed step would run."""
    pid = create_project(name="harness-idempotent")

    calls: dict[str, int] = {}

    def counting(project_id, existing_row, key):
        calls[key] = calls.get(key, 0) + 1
        return StepResult(key, "ok")

    funcs = {
        key: (lambda pid, row, k=key: counting(pid, row, k)) for key in HARNESS_SETUP_STEP_KEYS
    }
    monkeypatch.setattr(TeamHarnessSetupService, "_STEP_FUNCS", funcs)

    # First run: every step body executes once.
    assert TeamHarnessSetupService.setup(pid) == "ready"
    assert all(calls[k] == 1 for k in HARNESS_SETUP_STEP_KEYS)

    # Second run: all rows already 'ok' -> no body re-executes.
    assert TeamHarnessSetupService.setup(pid) == "ready"
    assert all(calls[k] == 1 for k in HARNESS_SETUP_STEP_KEYS)


def test_rerun_reattempts_failed_step_idempotent(isolated_db, monkeypatch):
    """idempotent: after a failure, a re-run skips the already-ok prefix and
    re-attempts the failed step (now succeeding) -> 'ready'."""
    pid = create_project(name="harness-retry-failed")

    state = {"fail": True}
    calls: dict[str, int] = {}

    def maybe_fail(project_id, existing_row):
        calls["team_topology"] = calls.get("team_topology", 0) + 1
        if state["fail"]:
            raise RuntimeError("transient")
        return StepResult("team_topology", "ok")

    def grd(project_id, existing_row):
        calls["grd_init"] = calls.get("grd_init", 0) + 1
        return StepResult("grd_init", "ok")

    funcs = _all_ok_funcs()
    funcs["grd_init"] = grd
    funcs["team_topology"] = maybe_fail
    monkeypatch.setattr(TeamHarnessSetupService, "_STEP_FUNCS", funcs)

    assert TeamHarnessSetupService.setup(pid) == "failed"
    assert calls["grd_init"] == 1
    assert calls["team_topology"] == 1

    # Retry: grd_init already ok -> skipped; team_topology re-attempted.
    state["fail"] = False
    assert TeamHarnessSetupService.setup(pid) == "ready"
    assert calls["grd_init"] == 1  # skipped, not re-run
    assert calls["team_topology"] == 2  # re-attempted


def test_placeholder_dispatch_runs_ready(isolated_db, monkeypatch):
    """The shipped dispatch runs none->running->ready with 6 ok rows.

    21-03 replaced the grd_init/team_topology placeholders with real bodies
    that require project state (local_path / owner_team_id). This test asserts
    the orchestration shape over a no-op dispatch, so we pin the table to
    no-op funcs (the real bodies have dedicated tests below)."""
    pid = create_project(name="harness-placeholder")
    monkeypatch.setattr(TeamHarnessSetupService, "_STEP_FUNCS", _all_ok_funcs())
    assert svc.TeamHarnessSetupService.setup(pid) == "ready"
    assert len(get_harness_setup_steps(pid)) == 6


# ===========================================================================
# 21-03: step a (grd_init reconcile) + step b (team_topology, driver=grd)
# ===========================================================================

import os  # noqa: E402

from app.db.project_sa_instances import (  # noqa: E402
    get_instance_driver,
    get_project_sa_instances_for_project,
)
from app.db.super_agents import create_super_agent  # noqa: E402
from app.db.teams import add_team_member, create_team  # noqa: E402


def _project_with_team(name, sa_count=2, local_path=None):
    """Seed a team + super-agents and a project owning that team.

    Mirrors tests/test_instance_service.py setup. Returns (project_id, team_id).
    """
    team_id = create_team(name=f"{name}-team")
    for i in range(sa_count):
        sa_id = create_super_agent(name=f"{name}-SA{i}", backend_type="claude")
        add_team_member(team_id=team_id, super_agent_id=sa_id, name=f"SA{i}")
    pid = create_project(name=name, owner_team_id=team_id, local_path=local_path)
    return pid, team_id


def _patch_instance_side_effects(monkeypatch):
    """Stub worktree + session creation so create_team_instances stays unit-pure."""
    from app.services.instance_service import InstanceService

    monkeypatch.setattr(
        InstanceService, "_create_worktree_for_instance", classmethod(lambda cls, *a, **k: None)
    )
    monkeypatch.setattr(
        InstanceService, "_create_initial_session", classmethod(lambda cls, *a, **k: None)
    )


# --- step a: grd_init reconcile --------------------------------------------


def test_grd_init_skips_when_planning_exists(isolated_db, monkeypatch, tmp_path):
    """grd_init: existing .planning/ -> skipped, no init triggered (no re-init)."""
    (tmp_path / ".planning").mkdir()
    pid = create_project(name="grd-init-present", local_path=str(tmp_path))

    triggered = {"n": 0}
    import app.services.grd_planning_service as gps

    monkeypatch.setattr(
        gps.GrdPlanningService,
        "auto_init_project",
        classmethod(lambda cls, *a, **k: triggered.__setitem__("n", triggered["n"] + 1)),
    )

    result = svc._step_grd_init(pid, None)
    assert result.status == "skipped"
    assert result.fingerprint is not None
    assert triggered["n"] == 0  # never re-init a populated project


def test_grd_init_triggers_when_planning_absent(isolated_db, monkeypatch, tmp_path):
    """grd_init: no .planning/ -> triggers auto_init_project, returns ok."""
    pid = create_project(name="grd-init-absent", local_path=str(tmp_path))

    triggered = {"n": 0}
    import app.services.grd_planning_service as gps

    monkeypatch.setattr(
        gps.GrdPlanningService,
        "auto_init_project",
        classmethod(lambda cls, *a, **k: triggered.__setitem__("n", triggered["n"] + 1)),
    )

    result = svc._step_grd_init(pid, None)
    assert result.status == "ok"
    assert triggered["n"] == 1


def test_grd_init_idempotent_skips_on_rerun(isolated_db, monkeypatch, tmp_path):
    """idempotent: once .planning/ exists, a re-run skips (never destructive)."""
    pid = create_project(name="grd-init-rerun", local_path=str(tmp_path))

    triggered = {"n": 0}
    import app.services.grd_planning_service as gps

    def _fake_init(cls, project_id, local_path):
        triggered["n"] += 1
        os.makedirs(os.path.join(local_path, ".planning"), exist_ok=True)

    monkeypatch.setattr(gps.GrdPlanningService, "auto_init_project", classmethod(_fake_init))

    first = svc._step_grd_init(pid, None)
    assert first.status == "ok"
    assert triggered["n"] == 1

    second = svc._step_grd_init(pid, None)
    assert second.status == "skipped"
    assert triggered["n"] == 1  # no second init


# --- step b: team topology + driver=grd ------------------------------------


def test_team_topology_sets_driver_grd(isolated_db, monkeypatch):
    """driver: after step b, every SA instance has get_instance_driver == 'grd'."""
    _patch_instance_side_effects(monkeypatch)
    pid, _team = _project_with_team("topo-driver", sa_count=2)

    result = svc._step_team_topology(pid, None)
    assert result.status == "ok"

    instances = get_project_sa_instances_for_project(pid)
    assert len(instances) == 2
    for inst in instances:
        assert get_instance_driver(inst["id"]) == "grd"


def test_team_topology_idempotent_no_duplicate(isolated_db, monkeypatch):
    """idempotent: run step b twice -> instance count unchanged (existence-check)."""
    _patch_instance_side_effects(monkeypatch)
    pid, _team = _project_with_team("topo-idem", sa_count=2)

    first = svc._step_team_topology(pid, None)
    assert first.status == "ok"
    count_after_first = len(get_project_sa_instances_for_project(pid))
    assert count_after_first == 2

    second = svc._step_team_topology(pid, None)
    assert second.status == "skipped"
    count_after_second = len(get_project_sa_instances_for_project(pid))
    assert count_after_second == count_after_first  # no duplicates

    # Driver still reconciled to grd on the skip path.
    for inst in get_project_sa_instances_for_project(pid):
        assert get_instance_driver(inst["id"]) == "grd"
