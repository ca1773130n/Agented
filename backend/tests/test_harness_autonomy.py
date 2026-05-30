from app.models.autonomy_policy import AutonomyPolicy, AutonomyDecision, GateResult


def test_policy_defaults_are_safe():
    p = AutonomyPolicy()
    assert p.enabled is False  # review-mode default
    assert 0.0 <= p.confidence_threshold <= 1.0
    assert p.confidence_threshold == 0.85
    assert p.max_ops_per_round == 5
    assert p.block_deletes is True  # safe default
    assert p.cooldown_seconds == 3600


def test_policy_bounds_enforced():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AutonomyPolicy(confidence_threshold=1.5)


def test_decision_shape():
    d = AutonomyDecision(
        eligible=False, gates=[GateResult(name="confidence", passed=False, detail="0.4 < 0.85")]
    )
    assert d.eligible is False
    assert d.gates[0].name == "confidence"
    assert AutonomyDecision.model_validate_json(d.model_dump_json()).eligible is False
