from app.models.harness_evolution import CheckResult, EvalVerdict, ReplaySample


def test_check_result_fields():
    c = CheckResult(name="frontmatter", passed=True, detail="ok", confidence=0.9)
    assert c.passed is True
    assert 0.0 <= c.confidence <= 1.0


def test_eval_verdict_aggregates():
    v = EvalVerdict(
        passed=False,
        score=0.4,
        per_check=[
            CheckResult(name="static", passed=True, detail="", confidence=1.0),
            CheckResult(name="replay:tk1", passed=False, detail="regresses", confidence=0.8),
        ],
    )
    assert v.passed is False
    assert len(v.per_check) == 2
    assert EvalVerdict.model_validate_json(v.model_dump_json()).score == 0.4


def test_replay_sample_shape():
    s = ReplaySample(
        incident_kind="h2_invalid_tool_call",
        layer="h2",
        evidence={"error": "x"},
        trajectory_excerpt="...",
    )
    assert s.layer == "h2"
