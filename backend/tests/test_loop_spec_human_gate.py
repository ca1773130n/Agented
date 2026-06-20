from app.models.loop_spec import LoopGate, LoopSpec


def test_human_gate_defaults_off():
    spec = LoopSpec.from_legacy_config({"goal": "g"}, execution_type="goal_loop")
    assert spec.state.human_gate is None


def test_human_gate_every_n_parses():
    spec = LoopSpec.from_legacy_config(
        {"goal": "g", "human_gate": {"mode": "every_n", "n": 3}}, execution_type="goal_loop"
    )
    assert spec.state.human_gate == LoopGate(mode="every_n", n=3)


def test_human_gate_on_exit_parses_for_ralph():
    spec = LoopSpec.from_legacy_config(
        {"task_description": "t", "human_gate": {"mode": "on_exit"}}, execution_type="ralph"
    )
    assert spec.state.human_gate.mode == "on_exit"
    assert spec.state.human_gate.n == 1  # default
