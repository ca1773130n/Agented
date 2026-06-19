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
