# backend/tests/services/test_goal_judge_llm_rubric.py
from app.services.goal_judge_service import _parse_judge_json


def test_parse_includes_confidence_when_present():
    assert _parse_judge_json('{"met": true, "reason": "ok", "confidence": 0.84}') == (
        True,
        "ok",
        0.84,
    )


def test_parse_defaults_confidence_when_absent():
    assert _parse_judge_json('{"met": false, "reason": "no"}') == (False, "no", 1.0)


def test_parse_none_on_garbage():
    assert _parse_judge_json("not json") is None
