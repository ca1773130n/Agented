# backend/tests/services/test_goal_judge_sandbox.py
from app.services.goal_judge_service import GoalJudgeService, JudgeVerdict
from app.models.loop_spec import QualityGate


def test_verdict_has_confidence_and_version_defaults():
    v = JudgeVerdict(met=True, source="deterministic", reason="ok")
    assert v.confidence == 1.0 and v.judge_version is None


def test_deterministic_pass_is_confidence_1(tmp_path):
    (tmp_path / "ok").write_text("")
    v = GoalJudgeService.judge(
        "g",
        "",
        check_cmd="test -f ok",
        cwd=str(tmp_path),
        quality_gate=QualityGate(kind="test_pass"),
        sandbox="isolated",
    )
    assert v.met is True and v.confidence == 1.0 and v.source == "deterministic"


def test_deterministic_fail_is_confidence_0(tmp_path):
    v = GoalJudgeService.judge(
        "g",
        "",
        check_cmd="test -f nope",
        cwd=str(tmp_path),
        quality_gate=QualityGate(kind="test_pass"),
        sandbox="isolated",
    )
    assert v.met is False and v.confidence == 0.0


def test_inherit_sandbox_runs_in_place(tmp_path):
    (tmp_path / "ok").write_text("")
    v = GoalJudgeService.judge(
        "g",
        "",
        check_cmd="test -f ok",
        cwd=str(tmp_path),
        quality_gate=QualityGate(kind="test_pass"),
        sandbox="inherit",
    )
    assert v.met is True


def test_inherit_path_scrubs_parent_env(tmp_path):
    """sandbox=inherit must still scrub the env (secrets must not reach check_cmd)."""
    import os
    from app.services.goal_judge_service import GoalJudgeService
    from app.models.loop_spec import QualityGate
    os.environ["SECRET_TOKEN_JUDGE"] = "leak"
    try:
        v = GoalJudgeService.judge(
            "g", "", check_cmd='test -z "$SECRET_TOKEN_JUDGE"', cwd=str(tmp_path),
            quality_gate=QualityGate(kind="test_pass"), sandbox="inherit",
        )
        assert v.met is True  # secret absent in scrubbed env → test -z passes
    finally:
        os.environ.pop("SECRET_TOKEN_JUDGE", None)
