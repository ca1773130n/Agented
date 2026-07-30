"""Auto-distill policy — the trigger that keeps super-agent L1 runbooks fresh.

Every test here is about SPEND. ``tesserae distill --all`` costs money, so the
gates (per-project opt-in, graph-digest change, minimum interval, coalescing,
dry-run budget) are the feature; the dispatch is incidental. No subprocess is
ever spawned: ``run_op_async`` is replaced with a recording spy.
"""

import json

import pytest

from app.services import tesserae_integration as ti


@pytest.fixture(autouse=True)
def _clear_auto_distill_state(isolated_db):
    """The policy memo is a module global — a leaked digest/timestamp from one
    test silently satisfies the next test's gate.

    ``isolated_db`` because the memo is only a CACHE of
    ``projects.tesserae_auto_distill_state``: clearing the dict without a fresh
    DB would just reload the previous test's row, and the real DB must never be
    written by a test run."""
    with ti._auto_distill_lock:
        ti._auto_distill_state.clear()
    yield
    with ti._auto_distill_lock:
        ti._auto_distill_state.clear()


def _restart() -> None:
    """Simulate a gunicorn restart: process memory is gone, the DB is not."""
    with ti._auto_distill_lock:
        ti._auto_distill_state.clear()


def _make_project_row(project_id: str) -> None:
    """The persisted record lives on the projects row, so the row must exist."""
    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name) VALUES (?, ?)", (project_id, f"P {project_id}")
        )
        conn.commit()


@pytest.fixture
def spy(monkeypatch):
    """Records run_op_async calls instead of dispatching a real op."""
    calls: list[tuple] = []

    def _fake(project_id, op, **kwargs):
        calls.append((project_id, op, kwargs))
        return "job-fake"

    monkeypatch.setattr(ti, "run_op_async", _fake)
    return calls


def _write_graph(root, body: str) -> None:
    tess = root / ".tesserae"
    tess.mkdir(parents=True, exist_ok=True)
    (tess / "graph.json").write_text(json.dumps({"nodes": [], "marker": body}))


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A tesserae-enabled, distill-OPTED-IN project with a compiled graph."""
    root = tmp_path / "proj"
    root.mkdir()
    _write_graph(root, "A")
    monkeypatch.setattr(ti, "get_tesserae_root", lambda pid: root)
    monkeypatch.setattr(ti, "get_distill_enabled", lambda pid: True)
    return root


# ---------------------------------------------------------------------------
# The money gate
# ---------------------------------------------------------------------------


def test_no_dispatch_when_distill_disabled(project, spy, monkeypatch):
    """THE load-bearing gate: a project that has not opted in never spends.

    Everything else is satisfied here — tesserae enabled, graph present, graph
    never seen before, no prior dispatch — so the opt-in is the only thing
    standing between this call and an LLM bill. Deleting the
    ``get_distill_enabled`` check in ``_maybe_schedule_auto_distill`` makes this
    test fail (verified both directions).
    """
    monkeypatch.setattr(ti, "get_distill_enabled", lambda pid: False)
    ti._maybe_schedule_auto_distill("proj-1", project)
    assert spy == []


def test_dispatch_when_distill_enabled(project, spy):
    """Control for the test above: identical state, opt-in ON ⇒ one dispatch."""
    ti._maybe_schedule_auto_distill("proj-1", project)
    assert len(spy) == 1


# ---------------------------------------------------------------------------
# Trigger correctness
# ---------------------------------------------------------------------------


def test_no_dispatch_when_compile_failed(project, spy, monkeypatch):
    """compile_workspace only consults the policy on a successful compile."""
    failed = ti.TesseraeOpResult(
        op="compile", ok=False, reason="boom", started_at="t", finished_at="t"
    )
    monkeypatch.setattr(ti, "_run_tesserae", lambda *a, **k: failed)
    res = ti.compile_workspace("proj-1")
    assert res.ok is False
    assert spy == []


def test_no_dispatch_when_graph_missing(tmp_path, spy, monkeypatch):
    """No compiled graph ⇒ nothing to distill from; refuse rather than guess."""
    root = tmp_path / "empty"
    (root / ".tesserae").mkdir(parents=True)
    monkeypatch.setattr(ti, "get_distill_enabled", lambda pid: True)
    ti._maybe_schedule_auto_distill("proj-1", root)
    assert spy == []


def _age_past_window(project_id: str) -> None:
    """Backdate the last dispatch so the min-interval gate is satisfied and the
    NEXT gate under test is the only thing that can block."""
    with ti._auto_distill_lock:
        ti._auto_distill_state[project_id]["at_monotonic"] -= (
            ti._TESSERAE_AUTO_DISTILL_MIN_INTERVAL_SECONDS + 1
        )


def test_dispatch_once_per_graph_digest(project, spy):
    """An unchanged graph cannot stale a runbook, so a repeat compile that
    produced identical bytes must not spend again.

    The window is aged out first, ON PURPOSE: without that, the min-interval
    gate blocks the second call and this test passes even with the digest check
    deleted (it did — caught by mutation). Aged, the digest is the only gate
    left, and ``test_dispatch_after_min_interval_elapses`` is the paired control
    showing the same aging DOES dispatch when the bytes differ.
    """
    ti._maybe_schedule_auto_distill("proj-1", project)
    assert len(spy) == 1
    _age_past_window("proj-1")
    _write_graph(project, "A")  # byte-identical rewrite
    ti._maybe_schedule_auto_distill("proj-1", project)
    assert len(spy) == 1, "identical graph bytes must never buy a second distill"


def test_min_interval_blocks_changed_graph(project, spy):
    """Rate limit: a genuinely CHANGED graph inside the 6 h window is deferred.

    This is the gate that bounds spend when a project compiles constantly —
    without it, the digest check alone would fire on every compile.
    """
    ti._maybe_schedule_auto_distill("proj-1", project)
    assert len(spy) == 1
    _write_graph(project, "B")  # different bytes → digest moved
    ti._maybe_schedule_auto_distill("proj-1", project)
    assert len(spy) == 1, "changed graph inside the min interval must not dispatch"


def test_dispatch_after_min_interval_elapses(project, spy, monkeypatch):
    """Control for the rate limit: once the window passes, a changed graph fires."""
    ti._maybe_schedule_auto_distill("proj-1", project)
    _age_past_window("proj-1")
    _write_graph(project, "B")
    ti._maybe_schedule_auto_distill("proj-1", project)
    assert len(spy) == 2


def test_per_project_state_is_independent(project, spy):
    """One project's dispatch must not consume another's window."""
    ti._maybe_schedule_auto_distill("proj-1", project)
    ti._maybe_schedule_auto_distill("proj-2", project)
    assert [c[0] for c in spy] == ["proj-1", "proj-2"]


# ---------------------------------------------------------------------------
# What gets dispatched
# ---------------------------------------------------------------------------


def test_dispatch_kwargs(project, spy):
    """Coalescing + the spend budget are part of the dispatch contract."""
    ti._maybe_schedule_auto_distill("proj-1", project)
    project_id, op, kwargs = spy[0]
    assert (project_id, op) == ("proj-1", "agent-distill")
    assert kwargs["coalesce"] is True
    assert kwargs["max_estimated_llm_calls"] == ti._TESSERAE_AUTO_DISTILL_MAX_ESTIMATED_LLM_CALLS


def test_coalesce_prevents_overlapping_subprocesses(monkeypatch):
    """Prove the coalescing the policy relies on, in run_op_async itself: while
    an agent-distill job is running for a project, a second request returns the
    RUNNING job id instead of spawning another subprocess."""
    import threading

    release = threading.Event()
    started = threading.Event()
    runs: list[int] = []

    def _slow(project_id, **kwargs):
        runs.append(1)
        started.set()
        release.wait(5)
        return ti.TesseraeOpResult(
            op="agent-distill", ok=True, reason="", started_at="t", finished_at="t"
        )

    monkeypatch.setitem(ti._OP_DISPATCH, "agent-distill", _slow)
    first = ti.run_op_async("proj-1", "agent-distill", coalesce=True)
    assert started.wait(5)
    second = ti.run_op_async("proj-1", "agent-distill", coalesce=True)
    assert second == first
    assert len(runs) == 1
    release.set()


def test_dispatch_failure_does_not_break_compile(project, monkeypatch):
    """The policy is best-effort: run_op_async blowing up must not fail the
    compile that triggered it. Guarded by the try/except INSIDE
    ``_maybe_schedule_auto_distill``."""
    ok = ti.TesseraeOpResult(op="compile", ok=True, reason="", started_at="t", finished_at="t")
    monkeypatch.setattr(ti, "_run_tesserae", lambda *a, **k: ok)

    def _boom(*a, **k):
        raise RuntimeError("dispatch exploded")

    monkeypatch.setattr(ti, "run_op_async", _boom)
    assert ti.compile_workspace("proj-1").ok is True


def test_policy_failure_does_not_break_compile(project, monkeypatch):
    """The OUTER guard in ``compile_workspace``: the policy's own pre-dispatch
    work (digest, locking) sits outside the inner try, so a raise there would
    propagate and fail an otherwise-successful compile.

    Removing the outer try/except makes this test fail; it does NOT make
    ``test_dispatch_failure_does_not_break_compile`` fail, because the inner
    guard already absorbs that one (caught by mutation). ``_graph_digest`` is
    the probe because it is reached ONLY through the policy — patching
    ``get_distill_enabled`` would also break the compile's own --distill flag
    lookup and prove nothing about this guard.
    """
    ok = ti.TesseraeOpResult(op="compile", ok=True, reason="", started_at="t", finished_at="t")
    monkeypatch.setattr(ti, "_run_tesserae", lambda *a, **k: ok)

    def _boom(*a, **k):
        raise RuntimeError("digest exploded")

    monkeypatch.setattr(ti, "_graph_digest", _boom)
    assert ti.compile_workspace("proj-1").ok is True


def test_successful_compile_dispatches_through_compile_workspace(project, spy, monkeypatch):
    """End-to-end through the real call site, not just the policy function."""
    ok = ti.TesseraeOpResult(op="compile", ok=True, reason="", started_at="t", finished_at="t")
    monkeypatch.setattr(ti, "_run_tesserae", lambda *a, **k: ok)
    ti.compile_workspace("proj-1")
    assert [(c[0], c[1]) for c in spy] == [("proj-1", "agent-distill")]


# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------


def test_auto_distill_state_reports_dispatch(project, spy):
    """An operator must be able to see that it fired, and why."""
    assert ti.auto_distill_state("proj-1") == {}
    ti._maybe_schedule_auto_distill("proj-1", project)
    st = ti.auto_distill_state("proj-1")
    assert st["reason"] == "graph_changed"
    assert st["at"]


def test_auto_distill_state_records_outcome_and_cost(project, spy, monkeypatch):
    """The op writes the measured provider-call count (and any refusal) back, so
    spend is auditable after the fact — not merely 'it fired'."""
    ti._maybe_schedule_auto_distill("proj-1", project)
    monkeypatch.setattr(
        "app.services.super_agent_memory.distill_super_agents",
        lambda pid, **kw: {"ok": True, "llm_calls": 7},
    )
    ti._agent_distill_op("proj-1", max_estimated_llm_calls=60)
    st = ti.auto_distill_state("proj-1")
    assert st["llm_calls"] == 7
    assert st["reason"] == "ok"


def test_timed_out_run_is_audited_as_a_floor_not_a_total(project, spy, monkeypatch):
    """A killed run's cost is what the finished agents printed PLUS an unknown
    amount from the agent we killed mid-flight. The audit trail must carry that
    as a floor, or the operator reads 17 as the bill.

    Both directions: `test_auto_distill_state_records_outcome_and_cost` is the
    paired control — a completed run reports the same shape with
    `llm_calls_partial` false. Dropping the flag from `auto_distill_state` or
    from the op's write-back fails this test and not that one.
    """
    ti._maybe_schedule_auto_distill("proj-1", project)
    monkeypatch.setattr(
        "app.services.super_agent_memory.distill_super_agents",
        lambda pid, **kw: {
            "ok": False,
            "reason": "timeout_after_1800s",
            "llm_calls": 17,
            "llm_calls_partial": True,
        },
    )
    ti._agent_distill_op("proj-1", max_estimated_llm_calls=60)
    st = ti.auto_distill_state("proj-1")
    assert st["llm_calls"] == 17
    assert st["llm_calls_partial"] is True
    assert st["reason"] == "timeout_after_1800s"


def test_refusal_is_audited_as_a_real_zero(project, spy, monkeypatch):
    """The other half of the same rule: a refusal never spawned tesserae, so it
    genuinely cost nothing and must read as an exact 0 — not as the "—" that a
    missing count would render, which is the UI's spelling of "unknown"."""
    ti._maybe_schedule_auto_distill("proj-1", project)
    monkeypatch.setattr(
        "app.services.super_agent_memory.distill_super_agents",
        lambda pid, **kw: {"ok": False, "reason": "estimate_over_budget_999", "llm_calls": 0},
    )
    ti._agent_distill_op("proj-1", max_estimated_llm_calls=60)
    st = ti.auto_distill_state("proj-1")
    assert st["llm_calls"] == 0 and st["llm_calls_partial"] is False


def test_operator_op_does_not_touch_auto_state(project, spy, monkeypatch):
    """A manual distill is not automatic spend and must not be reported as such."""
    ti._maybe_schedule_auto_distill("proj-1", project)
    monkeypatch.setattr(
        "app.services.super_agent_memory.distill_super_agents",
        lambda pid, **kw: {"ok": True, "llm_calls": 99},
    )
    ti._agent_distill_op("proj-1")
    assert ti.auto_distill_state("proj-1")["llm_calls"] is None


# ---------------------------------------------------------------------------
# Durability (F5 + F8): the record outlives the process, because both the audit
# trail AND the 6 h spend floor are read off it.
# ---------------------------------------------------------------------------


def test_min_interval_survives_a_restart(project, spy, monkeypatch):
    """THE spend leak this persistence exists for: the floor was in-memory only,
    so a restart erased ``prev``, the interval check was skipped as a "first
    dispatch", and the next successful compile opened a fresh window.

    Aged nothing here — the record is fresh, so the ONLY thing that can block the
    second dispatch is the persisted timestamp being found again.
    ``test_min_interval_floor_expires_across_a_restart`` is the paired control
    (same restart, aged row ⇒ it DOES dispatch), so this cannot be passed by a
    mutation that just blocks everything after a restart.
    """
    _make_project_row("proj-1")
    ti._maybe_schedule_auto_distill("proj-1", project)
    assert len(spy) == 1
    _restart()
    _write_graph(project, "B")  # genuinely changed graph
    ti._maybe_schedule_auto_distill("proj-1", project)
    assert len(spy) == 1, "the 6 h floor must not reset when the process does"


def test_min_interval_floor_expires_across_a_restart(project, spy, monkeypatch):
    """Control: the persisted clock is a real clock, not a permanent block. Age
    the row past the window (via ``at_epoch``, the only clock that crosses a
    process boundary) and the same restart dispatches."""
    from app.db.connection import get_connection

    _make_project_row("proj-1")
    ti._maybe_schedule_auto_distill("proj-1", project)
    _restart()
    with get_connection() as conn:
        raw = conn.execute(
            "SELECT tesserae_auto_distill_state FROM projects WHERE id = ?", ("proj-1",)
        ).fetchone()["tesserae_auto_distill_state"]
        st = json.loads(raw)
        assert "at_monotonic" not in st, "a monotonic reading is meaningless in another process"
        st["at_epoch"] -= ti._TESSERAE_AUTO_DISTILL_MIN_INTERVAL_SECONDS + 1
        conn.execute(
            "UPDATE projects SET tesserae_auto_distill_state = ? WHERE id = ?",
            (json.dumps(st), "proj-1"),
        )
        conn.commit()
    _write_graph(project, "B")
    ti._maybe_schedule_auto_distill("proj-1", project)
    assert len(spy) == 2


def test_digest_gate_survives_a_restart(project, spy):
    """The other half of the persisted record: an unchanged graph must not buy a
    distill just because the process bounced."""
    _make_project_row("proj-1")
    ti._maybe_schedule_auto_distill("proj-1", project)
    _restart()
    ti._maybe_schedule_auto_distill("proj-1", project)
    assert len(spy) == 1


def test_audit_trail_survives_a_restart(project, spy, monkeypatch):
    """F8: the operator-visible record of automatic LLM spend used to vanish on
    restart, leaving `logger.info` in the gunicorn log as the only evidence that
    a project distilled automatically an hour ago."""
    _make_project_row("proj-1")
    ti._maybe_schedule_auto_distill("proj-1", project)
    monkeypatch.setattr(
        "app.services.super_agent_memory.distill_super_agents",
        lambda pid, **kw: {
            "ok": False,
            "reason": "timeout_after_1800s",
            "llm_calls": 17,
            "llm_calls_partial": True,
        },
    )
    ti._agent_distill_op("proj-1", max_estimated_llm_calls=60)
    _restart()
    st = ti.auto_distill_state("proj-1")
    assert st["reason"] == "timeout_after_1800s"
    assert st["llm_calls"] == 17 and st["llm_calls_partial"] is True
    assert st["at"]


def test_persist_failure_degrades_to_the_old_in_memory_behaviour(project, spy, monkeypatch):
    """Persisting is best-effort. A DB that will not answer must not lose the
    dispatch, and must not fail the compile that triggered it — it costs only
    restart-durability, which is exactly the pre-change behaviour."""

    def _boom(*a, **k):
        raise RuntimeError("db on fire")

    monkeypatch.setattr("app.db.connection.get_connection", _boom)
    ti._save_auto_distill_state("proj-1", {"digest": "x"})  # must not raise
    assert ti._load_auto_distill_state("proj-1") == {}
    ti._maybe_schedule_auto_distill("proj-1", project)
    assert len(spy) == 1, "a failed persist must not swallow the dispatch"
    assert ti.auto_distill_state("proj-1")["reason"] == "graph_changed", "in-memory still works"


def test_unreadable_persisted_clock_does_not_wedge_the_policy(project, spy):
    """A record with no usable clock reads as infinitely old: one extra PRICED
    dispatch, rather than a policy that can never fire again. Fail-closed here
    would be a permanent wedge, because only a dispatch rewrites the row."""
    assert ti._seconds_since_dispatch({"digest": "abc"}) == float("inf")
    assert ti._seconds_since_dispatch({"digest": "abc", "at_epoch": "not-a-number"}) == float("inf")
    assert ti._seconds_since_dispatch({}) == float("inf")


# ---------------------------------------------------------------------------
# Coalescing has to respect spend AUTHORISATION (F6)
# ---------------------------------------------------------------------------


def _hold_a_distill_job(monkeypatch, **kwargs):
    """Start a real (patched) agent-distill job and leave it running. Returns
    ``(job_id, release)``."""
    import threading

    release = threading.Event()
    started = threading.Event()

    def _slow(project_id, **kw):
        started.set()
        release.wait(5)
        return ti.TesseraeOpResult(
            op="agent-distill", ok=True, reason="", started_at="t", finished_at="t"
        )

    monkeypatch.setitem(ti._OP_DISPATCH, "agent-distill", _slow)
    job_id = ti.run_op_async("proj-1", "agent-distill", coalesce=True, **kwargs)
    assert started.wait(5)
    return job_id, release


def test_coalesce_refuses_to_serve_a_differently_authorised_job(monkeypatch):
    """An operator's unpriced distill is running. The automatic policy carries a
    budget the operator's run does not, so joining it would file the operator's
    spend as this policy's dispatch. ``""`` = nothing dispatched.

    Paired with ``test_coalesce_prevents_overlapping_subprocesses`` above, which
    proves the SAME-arguments case still joins instead of spawning a second
    subprocess — the invariant that makes refusing here the only safe answer.
    """
    first, release = _hold_a_distill_job(monkeypatch)
    assert first
    assert (
        ti.run_op_async("proj-1", "agent-distill", coalesce=True, max_estimated_llm_calls=60) == ""
    )
    release.set()


def test_coalesce_refuses_in_the_other_direction_too(monkeypatch):
    """And the operator clicking Distill during an automatic run is not answered
    with that run's budgeted refusal."""
    first, release = _hold_a_distill_job(monkeypatch, max_estimated_llm_calls=60)
    assert first
    assert ti.run_op_async("proj-1", "agent-distill", coalesce=True) == ""
    release.set()


def test_op_kwargs_is_not_leaked_into_the_job_api(monkeypatch):
    """It is coalesce identity, not part of the polled job shape."""
    job_id, release = _hold_a_distill_job(monkeypatch, max_estimated_llm_calls=60)
    assert "op_kwargs" not in ti.get_op_job(job_id)
    release.set()


def test_stood_down_dispatch_is_not_audited_as_one(project, monkeypatch):
    """F6(b): when the dispatch is refused because the operator's run holds the
    slot, ``_agent_distill_op`` never runs for this policy — so without this the
    record stays `{reason: graph_changed, llm_calls: None}` FOREVER, asserting an
    automatic dispatch, cost unknown, that never happened. Now durably, too."""
    _make_project_row("proj-1")
    monkeypatch.setattr(ti, "run_op_async", lambda *a, **k: "")
    ti._maybe_schedule_auto_distill("proj-1", project)
    _restart()
    st = ti.auto_distill_state("proj-1")
    assert st["reason"] == "served_by_operator_distill"
    assert st["llm_calls"] == 0 and st["llm_calls_partial"] is False


# ---------------------------------------------------------------------------
# Prerequisite: the corpus clock must be parseable, or the pass this policy
# automates raises DistillError instead of producing a runbook.
# ---------------------------------------------------------------------------


def _tesserae_parse_iso(value: str):
    """Byte-for-byte copy of tesserae's agent_distill._parse_iso normalisation —
    the reason a trailing 'Z' on an already-offset stamp is fatal rather than
    merely redundant."""
    from datetime import datetime

    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def test_persisted_ended_at_is_parseable_by_tesserae(isolated_db):
    """``end_session`` writes the ``ended_at`` COLUMN that
    ``_normalize_super_agent_session`` exports and tesserae's ``_corpus_clock``
    reduces to the distill corpus clock.

    ``isoformat()`` on an aware datetime already ends in '+00:00'; the old
    ``+ "Z"`` made '…+00:00Z', which _parse_iso rewrites to '…+00:00+00:00' →
    ValueError → None → DistillError. Restoring the '+ "Z"' fails this test.
    """
    from app.db.connection import get_connection
    from app.services.super_agent_session_service import SuperAgentSessionService

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO super_agents (id, name, backend_type) VALUES (?,?,?)",
            ("super-clock", "Clock", "claude"),
        )
        conn.commit()

    session_id, err = SuperAgentSessionService.create_session("super-clock")
    assert err is None and session_id
    ok, err = SuperAgentSessionService.end_session(session_id)
    assert ok, err

    with get_connection() as conn:
        ended_at = conn.execute(
            "SELECT ended_at FROM super_agent_sessions WHERE id = ?", (session_id,)
        ).fetchone()["ended_at"]

    assert not ended_at.endswith("+00:00Z")
    parsed = _tesserae_parse_iso(ended_at)  # raises ValueError on the old format
    assert parsed.tzinfo is not None


def test_compile_writes_the_agent_registry_BEFORE_running_tesserae(
    isolated_db, tmp_path, monkeypatch
):
    """Ordering bug, and the reason a first real run silently produced nothing.

    Tesserae mints the `Agent` nodes and `performed_by` edges DURING the compile,
    by reading `.tesserae/agents/registry.json` off disk. Agented's only other
    writer of that file is `distill_super_agents`, which runs AFTER a compile —
    so on a virgin project the compile resolved every session to the fallback
    `claude:unknown:default`, and the distill that followed declared the real
    agents against a graph that had never heard of them: every one `no-sessions`,
    priced at 0, `nothing_to_distill` — while the 6 h window and the graph digest
    were consumed anyway.

    Asserting the call ORDER is the whole point; asserting only that the registry
    was written would pass even if it happened after the compile, which is the
    bug.
    """
    from app.services import tesserae_integration as ti

    root = tmp_path / "ws"
    (root / ".tesserae").mkdir(parents=True)
    monkeypatch.setattr(ti, "get_tesserae_root", lambda pid: root)
    monkeypatch.setattr(ti, "get_distill_enabled", lambda pid: False)

    calls: list[str] = []
    monkeypatch.setattr(
        "app.services.super_agent_memory.sync_agent_registry",
        lambda pid: calls.append("registry") or (root / ".tesserae" / "agents"),
    )

    def _fake_run(op, args, **kw):
        calls.append("tesserae")
        return ti.TesseraeOpResult(op=op, ok=True, reason=None, started_at="t0", finished_at="t1")

    monkeypatch.setattr(ti, "_run_tesserae", _fake_run)
    monkeypatch.setattr(ti, "_maybe_schedule_auto_distill", lambda *a, **k: None)

    ti.compile_workspace("proj-1")
    assert calls == ["registry", "tesserae"], (
        "the registry must be refreshed BEFORE the compile that reads it"
    )


def test_compile_survives_a_failing_registry_refresh(isolated_db, tmp_path, monkeypatch):
    """Attribution prep is best-effort: a registry we cannot write must never
    block a compile. Failing closed here would turn a cosmetic attribution
    problem into 'Compile is broken'."""
    from app.services import tesserae_integration as ti

    root = tmp_path / "ws"
    (root / ".tesserae").mkdir(parents=True)
    monkeypatch.setattr(ti, "get_tesserae_root", lambda pid: root)
    monkeypatch.setattr(ti, "get_distill_enabled", lambda pid: False)

    def _boom(pid):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr("app.services.super_agent_memory.sync_agent_registry", _boom)
    monkeypatch.setattr(
        ti,
        "_run_tesserae",
        lambda op, args, **kw: ti.TesseraeOpResult(
            op=op, ok=True, reason=None, started_at="t0", finished_at="t1"
        ),
    )
    monkeypatch.setattr(ti, "_maybe_schedule_auto_distill", lambda *a, **k: None)

    res = ti.compile_workspace("proj-1")
    assert res.ok is True


def test_chat_state_created_at_is_parseable():
    """Same bug class as above, second site: ``ChatStateService.init_session``.

    The stamp is aware, so ``isoformat()`` already carries '+00:00' and the old
    ``+ "Z"`` produced '…+00:00Z' — which ``datetime.fromisoformat`` rejects
    outright. Restoring the '+ "Z"' fails this test.
    """
    from datetime import datetime

    from app.services.chat_state_service import ChatStateService

    session_id = "chat-state-iso-guard"
    try:
        ChatStateService.init_session(session_id)
        created_at = ChatStateService._sessions[session_id]["created_at"]
    finally:
        ChatStateService.remove_session(session_id)

    assert not created_at.endswith("+00:00Z")
    assert datetime.fromisoformat(created_at).tzinfo is not None


def test_no_aware_datetime_gets_a_trailing_z_appended():
    """Bug-class pin: an AWARE datetime must never have '"Z"' appended.

    Scope note — this flags only the *aware* form. ``app.utils.timezone.utcnow``
    deliberately returns a NAIVE UTC datetime (a documented py3.12 shim), so the
    ``_utcnow().isoformat() + "Z"`` sites in ``db/secrets.py``,
    ``project_health_service`` and ``audit_log_service`` emit correct RFC3339 and
    are intentionally NOT matched here. Widening this regex to all
    ``isoformat() + "Z"`` would flag five correct call sites.
    """
    import re
    from pathlib import Path

    aware_then_z = re.compile(
        r"""now\(\s*(?:datetime\.)?(?:timezone\.utc|UTC|_dt\.UTC)\s*\)"""
        r"""[^\n]*?\.isoformat\(\)\s*\+\s*["']Z["']"""
    )

    app_root = Path(__file__).resolve().parent.parent / "app"
    offenders = [
        f"{path.relative_to(app_root.parent)}:{lineno}: {line.strip()}"
        for path in sorted(app_root.rglob("*.py"))
        for lineno, line in enumerate(path.read_text().splitlines(), start=1)
        if aware_then_z.search(line)
    ]

    assert offenders == [], "aware datetime with a trailing 'Z' appended:\n" + "\n".join(offenders)
