from app.models.loop_spec import LoopSpec


def test_from_legacy_goal_loop_config_roundtrips():
    legacy = {
        "goal": "make tests pass",
        "check_cmd": "pytest -q",
        "max_iterations": 20,
        "max_wall_seconds": 1800,
        "max_cost_usd": 5.0,
        "ouroboros": True,
        "judge_backend_kind": "claude",
        "judge_model_override": None,
        "metric_spec": None,
    }
    spec = LoopSpec.from_legacy_config(legacy, execution_type="goal_loop")
    assert spec.body.goal == "make tests pass"
    assert spec.body.kind == "eval_refine"
    assert spec.exit.max_iterations == 20
    assert spec.exit.max_wall_seconds == 1800
    assert spec.exit.max_cost_usd == 5.0
    assert spec.exit.max_tokens == 0          # new field defaults off
    assert spec.exit.convergence is True       # maps from ouroboros
    assert spec.exit.stagnation_no_progress_for == 0  # off by default
    assert spec.state.context_policy == "carry"
    assert spec.meta_execution_type == "goal_loop"


def test_from_legacy_ralph_config_maps_to_agent_task_reset():
    legacy = {
        "task_description": "build the thing",
        "max_iterations": 50,
        "no_progress_threshold": 3,
        "completion_promise": "COMPLETE",
    }
    spec = LoopSpec.from_legacy_config(legacy, execution_type="ralph")
    assert spec.body.kind == "agent_task"
    assert spec.body.goal == "build the thing"
    assert spec.exit.max_iterations == 50
    assert spec.exit.stagnation_no_progress_for == 3   # ralph's git no-progress
    assert spec.state.context_policy == "reset"        # ralph-purist fresh context
    assert spec.meta_execution_type == "ralph"


def test_new_fields_parse_when_present():
    spec = LoopSpec.from_legacy_config(
        {"goal": "g", "max_tokens": 500000, "context_policy": "reset",
         "stagnation_no_progress_for": 4},
        execution_type="goal_loop",
    )
    assert spec.exit.max_tokens == 500000
    assert spec.state.context_policy == "reset"
    assert spec.exit.stagnation_no_progress_for == 4
