from unittest.mock import patch

from app_litestar.routes import grd_routes as gr

# Litestar 2.x wraps @post handlers in an HTTPRouteHandler that is not
# directly callable with positional args — call the underlying function
# via ``.fn`` (per the plan's note on the decorated-handler gotcha).


def test_intervene_route_calls_runner():
    with (
        patch.object(gr, "_ensure_project", lambda pid: {"id": pid}),
        patch("app.services.goal_loop_runner.intervene_runner", return_value=True) as m,
    ):
        out = gr.loop_intervene.fn("p", "sess", {"message": "do X"})
    m.assert_called_once_with("sess", "do X")
    assert out["ok"] is True


def test_gate_decision_route_calls_runner():
    with (
        patch.object(gr, "_ensure_project", lambda pid: {"id": pid}),
        patch("app.services.goal_loop_runner.submit_gate_decision", return_value=True) as m,
    ):
        out = gr.loop_gate_decision.fn("p", "sess", {"decision": "continue"})
    m.assert_called_once_with("sess", "continue", None)
    assert out["ok"] is True


def test_gate_decision_rejects_bad_decision():
    import pytest
    from litestar.exceptions import ClientException

    with patch.object(gr, "_ensure_project", lambda pid: {"id": pid}):
        with pytest.raises(ClientException):
            gr.loop_gate_decision.fn("p", "sess", {"decision": "nope"})


def test_stop_route_signals_runner_so_reset_children_actually_stop():
    """The generic /stop route must call stop_runner (keyed by the stable id)
    BEFORE ProjectSessionManager.stop_session — otherwise a context_policy=reset
    loop, whose live child has a different id, keeps iterating after the route
    only kills the original (already-dead) process."""
    calls = []
    with (
        patch(
            "app.services.goal_loop_runner.stop_runner",
            side_effect=lambda sid: calls.append(("runner", sid)),
        ),
        patch.object(
            gr.ProjectSessionManager,
            "stop_session",
            side_effect=lambda sid: calls.append(("psm", sid)) or True,
        ),
    ):
        out = gr.stop_session.fn("p", "sess")
    assert ("runner", "sess") in calls
    # stop_runner is signalled before (or with) the PSM kill.
    assert calls.index(("runner", "sess")) < calls.index(("psm", "sess"))
    assert out["session_id"] == "sess"
