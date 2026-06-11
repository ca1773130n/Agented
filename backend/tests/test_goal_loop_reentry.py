"""Goal-loop re-entry from persisted iteration knowledge (Phase 4, Unit C)."""

from unittest.mock import patch

from app.services import goal_loop_runner


def _make_failed_goal_session(session_id="gls-1", project_id="proj-1"):
    """Insert a minimal failed goal-loop project_sessions row + config +
    iteration history. Use the real DB helpers found in Step 1 (create the
    project row first if project_sessions FKs projects)."""
    from app.db.connection import get_connection
    from app.db.goal_loop import set_goal_loop_config

    with get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO projects (id, name) VALUES (?, ?)", (project_id, "P"))
        conn.execute(
            "INSERT INTO project_sessions (id, project_id, status, execution_type) "
            "VALUES (?, ?, 'failed', 'goal_loop')",
            (session_id, project_id),
        )
        conn.executemany(
            "INSERT INTO goal_loop_iterations "
            "(session_id, iteration, judge_source, verdict) "
            "VALUES (?, ?, ?, ?)",
            [
                (session_id, 1, "judge", "not_achieved"),
                (session_id, 2, "judge", "not_achieved"),
            ],
        )
        conn.commit()
    set_goal_loop_config(session_id, {"goal": "make tests pass", "max_iterations": 10})


def test_resume_goal_loop_spawns_fresh_session_with_context():
    _make_failed_goal_session()
    with patch.object(goal_loop_runner, "_spawn_resumed_session", return_value="gls-2") as spawn:
        result = goal_loop_runner.resume_goal_loop("gls-1")
    assert result["session_id"] == "gls-2"
    cfg = spawn.call_args.args[1]  # (origin_session_id, goal_config, ...)
    assert "resume_context" in cfg
    assert "iteration 2" in cfg["resume_context"]  # resumed AFTER iteration N
    assert cfg["goal"] == "make tests pass"


def test_resume_rejects_non_goal_or_active_sessions():
    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO projects (id, name) VALUES ('proj-1', 'P')")
        conn.execute(
            "INSERT INTO project_sessions (id, project_id, status, execution_type) "
            "VALUES ('s-active', 'proj-1', 'active', 'goal_loop'), "
            "       ('s-direct', 'proj-1', 'failed', 'direct'), "
            "       ('s-ralph', 'proj-1', 'failed', 'ralph_loop')",
        )
        conn.commit()
    assert goal_loop_runner.resume_goal_loop("s-active").get("error") == "not_eligible"
    assert goal_loop_runner.resume_goal_loop("s-direct").get("error") == "not_eligible"
    # ralph_loop excluded: no durable config/iterations to resume from.
    assert goal_loop_runner.resume_goal_loop("s-ralph").get("error") == "not_eligible"
    assert goal_loop_runner.resume_goal_loop("nope").get("error") == "not_found"


def test_resume_no_fan_out():
    _make_failed_goal_session("gls-3")
    from app.db.connection import get_connection

    with get_connection() as conn:  # an existing resumed child blocks a second resume
        conn.execute(
            "INSERT INTO project_sessions (id, project_id, status, execution_type, resumed_from) "
            "VALUES ('gls-3b', 'proj-1', 'active', 'goal_loop', 'gls-3')"
        )
        conn.commit()
    assert goal_loop_runner.resume_goal_loop("gls-3").get("error") == "already_resumed"


def test_resume_concurrent_double_call_single_spawn():
    """Two concurrent resume calls: exactly one spawns; the other is rejected
    by the in-flight guard (the DB resumed_from child appears too late)."""
    import threading

    _make_failed_goal_session("gls-race")
    release = threading.Event()
    results = []

    def _blocking_spawn(*args, **kwargs):
        release.wait(timeout=5)
        return "gls-race-child"

    def _call():
        results.append(goal_loop_runner.resume_goal_loop("gls-race"))

    with patch.object(goal_loop_runner, "_spawn_resumed_session", side_effect=_blocking_spawn):
        t1 = threading.Thread(target=_call)
        t2 = threading.Thread(target=_call)
        t1.start()
        t2.start()
        import time

        time.sleep(0.1)  # let both threads pass validation and hit the claim
        release.set()
        t1.join(timeout=5)
        t2.join(timeout=5)
    outcomes = sorted(("ok" if "session_id" in r else r.get("error", "unknown")) for r in results)
    assert outcomes == ["already_resumed", "ok"]


def test_resume_requires_config():
    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO projects (id, name) VALUES ('proj-1', 'P')")
        conn.execute(
            "INSERT INTO project_sessions (id, project_id, status, execution_type) "
            "VALUES ('gls-nocfg', 'proj-1', 'failed', 'goal_loop')"
        )
        conn.commit()
    assert goal_loop_runner.resume_goal_loop("gls-nocfg").get("error") == "config_missing"


def test_resume_loop_route_404_when_not_found():
    from litestar.testing import create_test_client

    from app_litestar.auth import provide_caller
    from app_litestar.routes.grd_routes import grd_router  # confirm symbol via grep

    with create_test_client(
        route_handlers=[grd_router], dependencies={"caller": provide_caller}
    ) as client:
        resp = client.post("/api/projects/proj-1/sessions/nope/resume-loop")
    assert resp.status_code == 404


def test_resume_preserves_yolo_mode():
    """A yolo goal-loop must respawn as yolo: create_session(yolo_mode=False)
    would activate the permission-hook overlay and block the unattended loop
    (codex PR review P2). The original handler expresses yolo solely via the
    create_session flag — mirror that."""
    from unittest.mock import patch

    from app.db.connection import get_connection

    _make_failed_goal_session("gls-yolo")
    with get_connection() as conn:
        conn.execute("UPDATE project_sessions SET yolo_mode = 1 WHERE id = 'gls-yolo'")
        conn.commit()

    with (
        patch(
            "app.services.project_session_manager.ProjectSessionManager.create_session",
            return_value="gls-yolo-child",
        ) as create,
        patch.object(goal_loop_runner, "start_runner"),
        patch("app.db.goal_loop.set_goal_loop_config"),
    ):
        result = goal_loop_runner.resume_goal_loop("gls-yolo")
    assert result.get("session_id") == "gls-yolo-child"
    assert create.call_args.kwargs.get("yolo_mode") is True
