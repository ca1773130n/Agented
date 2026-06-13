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


def test_placeholder_dispatch_runs_ready(isolated_db):
    """The shipped placeholder bodies run none->running->ready with 6 ok rows."""
    pid = create_project(name="harness-placeholder")
    assert svc.TeamHarnessSetupService.setup(pid) == "ready"
    assert len(get_harness_setup_steps(pid)) == 6
