# backend/tests/test_loop_spec_quality_gate.py
from app.models.loop_spec import LoopSpec


def test_check_cmd_maps_to_test_pass_gate_and_sandbox_default_isolated():
    spec = LoopSpec.from_legacy_config(
        {"goal": "g", "check_cmd": "pytest -q"}, execution_type="goal_loop"
    )
    assert spec.exit.quality_gate is not None
    assert spec.exit.quality_gate.kind == "test_pass"
    assert spec.state.sandbox == "isolated"  # default ON


def test_metric_spec_maps_to_metric_gate():
    spec = LoopSpec.from_legacy_config(
        {"goal": "g", "metric_spec": {"name": "f1", "target": 0.8}}, execution_type="goal_loop"
    )
    assert spec.exit.quality_gate.kind == "metric"
    assert spec.exit.quality_gate.metric_name == "f1"
    assert spec.exit.quality_gate.threshold == 0.8


def test_goal_loop_default_is_llm_judge_gate():
    spec = LoopSpec.from_legacy_config({"goal": "g"}, execution_type="goal_loop")
    assert spec.exit.quality_gate.kind == "llm_judge"


def test_explicit_quality_gate_and_sandbox_inherit_parse():
    spec = LoopSpec.from_legacy_config(
        {
            "goal": "g",
            "quality_gate": {
                "kind": "llm_judge",
                "rubric": "be strict",
                "judge_version": "v2",
                "min_confidence": 0.7,
            },
            "sandbox": "inherit",
        },
        execution_type="goal_loop",
    )
    qg = spec.exit.quality_gate
    assert qg.rubric == "be strict" and qg.judge_version == "v2" and qg.min_confidence == 0.7
    assert spec.state.sandbox == "inherit"


def test_ralph_default_sandbox_isolated_no_gate_when_no_check():
    spec = LoopSpec.from_legacy_config({"task_description": "do"}, execution_type="ralph")
    assert spec.state.sandbox == "isolated"
    assert spec.exit.quality_gate is None  # ralph has no check_cmd → no eval gate
