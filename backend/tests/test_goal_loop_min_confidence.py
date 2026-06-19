from app.models.loop_spec import QualityGate
from app.services.goal_loop_runner import _met_terminates


def test_high_confidence_met_terminates():
    assert (
        _met_terminates(
            met=True, confidence=0.9, gate=QualityGate(kind="llm_judge", min_confidence=0.7)
        )
        is True
    )


def test_low_confidence_met_does_not_terminate():
    assert (
        _met_terminates(
            met=True, confidence=0.5, gate=QualityGate(kind="llm_judge", min_confidence=0.7)
        )
        is False
    )


def test_not_met_never_terminates():
    assert (
        _met_terminates(
            met=False, confidence=1.0, gate=QualityGate(kind="llm_judge", min_confidence=0.0)
        )
        is False
    )


def test_no_gate_falls_back_to_met():
    assert _met_terminates(met=True, confidence=0.1, gate=None) is True
