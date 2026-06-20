# backend/tests/test_autoresearch_kernel.py
"""TDD tests for the autoresearch-core kernel integration (Tasks 2-4).

All DB tests use the `isolated_db` fixture (autouse=True in conftest.py) —
SQLite, no server required.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Task 2: GoalJudgeService kernel verdict tests
# ---------------------------------------------------------------------------
from app.services.goal_judge_service import GoalJudgeService, JudgeVerdict

_SPEC = {"metric_key": "acc", "comparator": ">=", "target": 0.8}


def _judge(text, **kw):
    return GoalJudgeService.judge("goal", text, metric_spec=_SPEC, **kw)


def test_kernel_supported(monkeypatch):
    monkeypatch.setattr("app.services.goal_judge_service.AUTORESEARCH_KERNEL_ENABLED", True)
    v = _judge('work...\n__RESULT__ {"acc": 0.9}\n')
    assert v.source == "kernel" and v.met is True and v.kernel_record.verdict == "supported"


def test_kernel_refuted(monkeypatch):
    monkeypatch.setattr("app.services.goal_judge_service.AUTORESEARCH_KERNEL_ENABLED", True)
    v = _judge('__RESULT__ {"acc": 0.5}')
    assert v.source == "kernel" and v.met is False and v.kernel_record.verdict == "refuted"


def test_kernel_inconclusive_without_result(monkeypatch):
    monkeypatch.setattr("app.services.goal_judge_service.AUTORESEARCH_KERNEL_ENABLED", True)
    v = _judge("no result line yet")
    assert v.source == "kernel" and v.met is False and v.kernel_record.verdict == "inconclusive"


def test_flag_off_ignores_metric_spec(monkeypatch):
    monkeypatch.setattr("app.services.goal_judge_service.AUTORESEARCH_KERNEL_ENABLED", False)
    v = GoalJudgeService.judge("goal", "x", metric_spec=_SPEC, check_cmd="true")
    assert v.source == "deterministic"  # check_cmd path, kernel skipped


def test_kernel_empty_dict_spec_does_not_reach_shell(monkeypatch):
    # BLOCKING regression (Codex): metric_spec={} is falsy; with `is not None` gating it
    # must stay in the kernel (invalid-spec verdict), never fall through to check_cmd (shell).
    monkeypatch.setattr("app.services.goal_judge_service.AUTORESEARCH_KERNEL_ENABLED", True)
    called = {"n": 0}
    monkeypatch.setattr(
        GoalJudgeService,
        "_run_deterministic",
        classmethod(lambda cls, *a, **k: called.__setitem__("n", 1)),
    )
    v = GoalJudgeService.judge("goal", "x", metric_spec={}, check_cmd="true")
    assert v.source == "kernel" and v.met is False and called["n"] == 0


def test_result_instruction_tolerates_non_dict():
    from app.services import goal_loop_runner as glr

    assert "<metric>" in glr._result_instruction("not-a-dict")
    assert "<metric>" in glr._result_instruction(None)


def test_kernel_wins_over_check_cmd(monkeypatch):
    # flag on + metric_spec → kernel decides; check_cmd (shell) is NEVER invoked.
    monkeypatch.setattr("app.services.goal_judge_service.AUTORESEARCH_KERNEL_ENABLED", True)
    called = {"n": 0}
    monkeypatch.setattr(
        GoalJudgeService,
        "_run_deterministic",
        classmethod(lambda cls, *a, **k: called.__setitem__("n", 1)),
    )
    v = _judge('__RESULT__ {"acc": 0.9}', check_cmd="false")
    assert v.source == "kernel" and called["n"] == 0


def test_kernel_invalid_spec_stays_in_kernel(monkeypatch):
    monkeypatch.setattr("app.services.goal_judge_service.AUTORESEARCH_KERNEL_ENABLED", True)
    v = GoalJudgeService.judge("g", "x", metric_spec={"bad": 1}, check_cmd="true")
    assert v.source == "kernel" and v.met is False  # config error → did NOT reach check_cmd


# ---------------------------------------------------------------------------
# Task 3: Runner plumbing tests
# ---------------------------------------------------------------------------

from app.db.goal_loop import list_goal_loop_dead_ends
from app.services import goal_loop_runner as glr


def test_kernel_dead_end_promotion_helper(isolated_db, monkeypatch):
    # The runner promotes a dead-end when a kernel verdict is a deterministic refutation.
    monkeypatch.setattr("app.services.goal_loop_runner.AUTORESEARCH_KERNEL_ENABLED", True)
    from autoresearch_core import DeterministicVerdict, ExperimentResult, MetricSpec

    rec = DeterministicVerdict().evaluate(
        MetricSpec("acc", ">=", 0.8), ExperimentResult(metrics={"acc": 0.5}, exit_code=0)
    )
    verdict = JudgeVerdict(met=False, source="kernel", reason=rec.detail, kernel_record=rec)
    glr._maybe_promote_kernel_dead_end("sess1", 1, "cache the tokenizer", verdict, "turn text")
    rows = list_goal_loop_dead_ends("sess1")
    assert len(rows) == 1 and rows[0]["approach"] == "cache the tokenizer"
    # idempotent — same approach_hash dedupes
    glr._maybe_promote_kernel_dead_end("sess1", 2, "cache the tokenizer", verdict, "turn text")
    assert len(list_goal_loop_dead_ends("sess1")) == 1


def test_prompt_result_block_gated():
    # __RESULT__ instruction only present when result_block is passed
    assert "__RESULT__" not in glr._initial_prompt("g", ouroboros=True)
    assert "__RESULT__" in glr._initial_prompt(
        "g",
        ouroboros=True,
        result_block=glr._result_instruction({"metric_key": "acc"}),
    )


# ---------------------------------------------------------------------------
# Task 4: Flag-off regression tests
# ---------------------------------------------------------------------------


def test_flag_off_no_kernel_behavior(isolated_db, monkeypatch):
    monkeypatch.setattr("app.services.goal_loop_runner.AUTORESEARCH_KERNEL_ENABLED", False)
    v = JudgeVerdict(met=False, source="kernel", reason="r", kernel_record=None)
    glr._maybe_promote_kernel_dead_end("s2", 1, "approach", v, "t")
    assert list_goal_loop_dead_ends("s2") == []


def test_flag_off_prompts_have_no_result_block():
    # result_block defaults to "" → prompts byte-identical to pre-integration
    assert "__RESULT__" not in glr._initial_prompt("g", ouroboros=True)
    assert "__RESULT__" not in glr._continue_prompt("g", "r", ouroboros=True)
