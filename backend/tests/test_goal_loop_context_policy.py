# backend/tests/test_goal_loop_context_policy.py
from app.services import goal_loop_runner as glr


def _make_active_goal_session(session_id="gls-reset", project_id="proj-reset"):
    """Insert a minimal active goal-loop project_sessions row + iteration history
    so ``_advance_iteration`` has an origin row to read and resume-context from."""
    from app.db.connection import get_connection
    from app.db.goal_loop import set_goal_loop_config

    with get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO projects (id, name) VALUES (?, ?)", (project_id, "P"))
        conn.execute(
            "INSERT INTO project_sessions (id, project_id, status, execution_type) "
            "VALUES (?, ?, 'active', 'goal_loop')",
            (session_id, project_id),
        )
        conn.executemany(
            "INSERT INTO goal_loop_iterations (session_id, iteration, judge_source, verdict) "
            "VALUES (?, ?, ?, ?)",
            [(session_id, 1, "judge", "not_met"), (session_id, 2, "judge", "not_met")],
        )
        conn.commit()
    set_goal_loop_config(session_id, {"goal": "make tests pass", "max_iterations": 10})


def test_advance_iteration_spawns_fresh_process_reads_stable_id_subscribes_before_seed(
    monkeypatch, isolated_db
):
    """``context_policy=reset`` must START A NEW claude process (clean context),
    reading resume-context + the origin row from the STABLE id, and SUBSCRIBE to
    the fresh child BEFORE seeding it (so a fast first turn can't be missed)."""
    _make_active_goal_session()
    created = {}
    monkeypatch.setattr(
        glr.ProjectSessionManager,
        "create_session",
        lambda **kw: created.update(kw) or "gls-reset-child",
    )
    order = []
    monkeypatch.setattr(
        glr.ProjectSessionManager,
        "subscribe_raw",
        lambda sid: order.append(("subscribe", sid)) or ["queue-obj"],
    )
    monkeypatch.setattr(
        glr.ProjectSessionManager,
        "send_input",
        lambda sid, payload: order.append(("send", sid)) or True,
    )
    stopped = []
    monkeypatch.setattr(
        glr.ProjectSessionManager, "stop_session", lambda sid, *a, **k: stopped.append(sid) or True
    )

    new_sid, new_queue = glr._advance_iteration(
        live_id="gls-reset", stable_id="gls-reset", cwd="/tmp", goal="make tests pass"
    )

    assert new_sid == "gls-reset-child"
    assert new_queue == ["queue-obj"]
    assert created.get("use_pty") is False and created.get("stream_json") is True
    assert created.get("execution_type") == "goal_loop"
    # subscribe to the fresh child happens BEFORE the seed prompt is sent to it.
    sub_idx = order.index(("subscribe", "gls-reset-child"))
    send_idx = order.index(("send", "gls-reset-child"))
    assert sub_idx < send_idx, "must subscribe to the fresh child before seeding it"
    assert "gls-reset" in stopped, "the carried-context live process must be stopped"


def test_advance_iteration_reads_stable_id_not_live_id(monkeypatch, isolated_db):
    """On the 2nd+ reset, live_id is a previous (empty) child; resume-context and
    the origin row must be read from the STABLE id, not the live child."""
    _make_active_goal_session(session_id="origin-x")
    seen = {}
    monkeypatch.setattr(glr, "_build_resume_context", lambda sid: seen.update(resume=sid) or "CTX")
    monkeypatch.setattr(glr.ProjectSessionManager, "create_session", lambda **kw: "child-2")
    monkeypatch.setattr(glr.ProjectSessionManager, "subscribe_raw", lambda sid: ["q"])
    monkeypatch.setattr(glr.ProjectSessionManager, "send_input", lambda sid, p: True)
    monkeypatch.setattr(glr.ProjectSessionManager, "stop_session", lambda sid, *a, **k: True)

    glr._advance_iteration(live_id="child-1", stable_id="origin-x", cwd="/tmp", goal="g")
    assert seen["resume"] == "origin-x", "resume-context must come from the stable id"


def test_advance_iteration_forwards_operator_note_into_seed(monkeypatch, isolated_db):
    """An operator note (carried on ``reason``) must reach the fresh child's seed —
    it would otherwise be lost on reset."""
    _make_active_goal_session(session_id="origin-n")
    monkeypatch.setattr(glr, "_build_resume_context", lambda sid: "")
    monkeypatch.setattr(glr.ProjectSessionManager, "create_session", lambda **kw: "child-n")
    monkeypatch.setattr(glr.ProjectSessionManager, "subscribe_raw", lambda sid: ["q"])
    monkeypatch.setattr(glr.ProjectSessionManager, "stop_session", lambda sid, *a, **k: True)
    seeded = {}
    monkeypatch.setattr(
        glr,
        "_send_initial",
        lambda sid, goal, **kw: seeded.update(resume_context=kw.get("resume_context")),
    )
    glr._advance_iteration(
        live_id="origin-n",
        stable_id="origin-n",
        cwd="/tmp",
        goal="g",
        reason="Operator note: focus on the parser",
    )
    assert "focus on the parser" in (seeded.get("resume_context") or "")


def test_advance_iteration_falls_back_to_continue_when_row_missing(monkeypatch, isolated_db):
    """If the origin (stable) session row is gone we cannot spawn a faithful fresh
    child; degrade to a continue prompt rather than crashing the loop."""
    monkeypatch.setattr(
        glr.ProjectSessionManager,
        "create_session",
        lambda **kw: (_ for _ in ()).throw(AssertionError("must not spawn without origin row")),
    )
    calls = {"continue": 0}
    monkeypatch.setattr(
        glr, "_send_continue", lambda *a, **k: calls.__setitem__("continue", calls["continue"] + 1)
    )
    new_sid, new_queue = glr._advance_iteration(
        live_id="missing-sess", stable_id="missing-sess", cwd="/tmp", goal="g"
    )
    assert new_sid is None and new_queue is None
    assert calls["continue"] == 1


def test_carry_uses_send_continue(monkeypatch):
    calls = {"continue": 0, "reset": 0}
    monkeypatch.setattr(
        glr, "_send_continue", lambda *a, **k: calls.__setitem__("continue", calls["continue"] + 1)
    )
    monkeypatch.setattr(
        glr,
        "_advance_iteration",
        lambda *a, **k: calls.__setitem__("reset", calls["reset"] + 1) or (None, None),
        raising=False,
    )
    out = glr._next_iteration(policy="carry", live_id="s", stable_id="s", cwd="/tmp", goal="g")
    assert calls["continue"] == 1 and calls["reset"] == 0
    assert out == (None, None)


def test_reset_spawns_fresh_session(monkeypatch):
    calls = {"continue": 0, "reset": 0}
    monkeypatch.setattr(
        glr, "_send_continue", lambda *a, **k: calls.__setitem__("continue", calls["continue"] + 1)
    )
    monkeypatch.setattr(
        glr,
        "_advance_iteration",
        lambda *a, **k: calls.__setitem__("reset", calls["reset"] + 1) or ("child", ["q"]),
    )
    out = glr._next_iteration(policy="reset", live_id="s", stable_id="s", cwd="/tmp", goal="g")
    assert calls["reset"] == 1 and calls["continue"] == 0
    assert out == ("child", ["q"])
