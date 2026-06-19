from app.services import goal_loop_runner as glr
from app.models.loop_spec import LoopSpec


def test_runner_state_exposes_parsed_spec():
    spec = LoopSpec.from_legacy_config({"goal": "g", "max_iterations": 7}, execution_type="goal_loop")
    state = glr._RunnerState(session_id="s", config={"goal": "g", "max_iterations": 7},
                             started_at=0.0, spec=spec)
    assert state.spec.exit.max_iterations == 7
    assert state.total_tokens == 0


def test_start_runner_parses_legacy_dict_into_spec(monkeypatch):
    captured = {}
    monkeypatch.setattr(glr.threading, "Thread",
                        lambda **kw: type("T", (), {"start": lambda self: captured.update(kw=kw)})())
    glr.start_runner("sess-spec", {"goal": "g", "max_iterations": 3}, cwd="/tmp")
    state = glr._runners["sess-spec"]
    assert state.spec.exit.max_iterations == 3
    glr._runners.pop("sess-spec", None)
