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


def test_advance_iteration_spawns_a_fresh_process(monkeypatch, isolated_db):
    """``context_policy=reset`` must START A NEW claude OS process (clean context
    window) — NOT write a prompt into the same long-lived process. Assert the
    fresh-spawn recipe (``create_session`` with a new session) is what runs, and
    that no continue-prompt is squirted into the origin process via ``send_input``.
    """
    _make_active_goal_session()
    created = {}
    monkeypatch.setattr(
        glr.ProjectSessionManager,
        "create_session",
        lambda **kw: created.update(kw) or "gls-reset-child",
    )
    sent_to = []
    monkeypatch.setattr(
        glr.ProjectSessionManager,
        "send_input",
        lambda session_id, payload: sent_to.append(session_id) or True,
    )
    stopped = []
    monkeypatch.setattr(
        glr.ProjectSessionManager, "stop_session", lambda sid, *a, **k: stopped.append(sid) or True
    )

    new_sid = glr._advance_iteration(session_id="gls-reset", cwd="/tmp", goal="make tests pass")

    # A genuinely fresh, no-PTY, stream-json claude process was created.
    assert new_sid == "gls-reset-child"
    assert created, "create_session must be called to spawn a fresh context window"
    assert created.get("use_pty") is False
    assert created.get("stream_json") is True
    assert created.get("execution_type") == "goal_loop"
    assert created["cmd"][0] == "claude"
    # The carried-context process is torn down (its conversation history is what
    # we discard), and the kickoff prompt is delivered ONLY to the fresh child —
    # never re-injected into the origin's retained context window.
    assert "gls-reset" in stopped, "the carried-context origin process must be stopped"
    assert sent_to == ["gls-reset-child"], "seed prompt must go to the fresh child only"


def test_advance_iteration_falls_back_to_continue_when_row_missing(monkeypatch, isolated_db):
    """If the origin session row is gone we cannot spawn a faithful fresh child;
    degrade to a continue prompt rather than crashing the loop."""
    monkeypatch.setattr(
        glr.ProjectSessionManager,
        "create_session",
        lambda **kw: (_ for _ in ()).throw(AssertionError("must not spawn without origin row")),
    )
    calls = {"continue": 0}
    monkeypatch.setattr(
        glr, "_send_continue", lambda *a, **k: calls.__setitem__("continue", calls["continue"] + 1)
    )
    new_sid = glr._advance_iteration(session_id="missing-sess", cwd="/tmp", goal="g")
    assert new_sid is None
    assert calls["continue"] == 1


def test_carry_uses_send_continue(monkeypatch):
    calls = {"continue": 0, "reset": 0}
    monkeypatch.setattr(
        glr, "_send_continue", lambda *a, **k: calls.__setitem__("continue", calls["continue"] + 1)
    )
    monkeypatch.setattr(
        glr,
        "_advance_iteration",
        lambda *a, **k: calls.__setitem__("reset", calls["reset"] + 1),
        raising=False,
    )
    glr._next_iteration(policy="carry", session_id="s", cwd="/tmp", goal="g")
    assert calls["continue"] == 1 and calls["reset"] == 0


def test_reset_spawns_fresh_session(monkeypatch):
    calls = {"continue": 0, "reset": 0}
    monkeypatch.setattr(
        glr, "_send_continue", lambda *a, **k: calls.__setitem__("continue", calls["continue"] + 1)
    )
    monkeypatch.setattr(
        glr, "_advance_iteration", lambda *a, **k: calls.__setitem__("reset", calls["reset"] + 1)
    )
    glr._next_iteration(policy="reset", session_id="s", cwd="/tmp", goal="g")
    assert calls["reset"] == 1 and calls["continue"] == 0
