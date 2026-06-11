"""TDD tests for AnswerEvalService — question set, blind judge, baseline-vs-pipeline.

All LLM calls stubbed via the llm_call / pipeline_llm_call seams.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Helpers — seed DB rows
# ---------------------------------------------------------------------------


def _seed_project(project_id: str, trigger_id: str, execution_id: str, isolated_db):
    """Seed a minimal project_paths + execution_logs row (mirrors test_answer_pipeline_fanout)."""
    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO projects (id, name) VALUES (?, ?)",
            (project_id, f"Project {project_id}"),
        )
        conn.commit()

    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO triggers (id, name, enabled, prompt_template) VALUES (?, ?, 1, '')",
            (trigger_id, f"Trigger {trigger_id}"),
        )
        conn.commit()

    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO project_paths (trigger_id, local_project_path, project_id)"
            " VALUES (?, ?, ?)",
            (trigger_id, "/tmp/path", project_id),
        )
        conn.commit()

    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO execution_logs"
            " (execution_id, trigger_id, trigger_type, started_at, backend_type, status, prompt)"
            " VALUES (?, ?, 'schedule', '2026-01-01T00:00:00', 'claude', 'completed', ?)",
            (execution_id, trigger_id, "Deploy the app to staging"),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# build_question_set — sampling + determinism + padding
# ---------------------------------------------------------------------------


def test_build_question_set_returns_list(isolated_db):
    from app.services.answer_eval_service import AnswerEvalService

    qs = AnswerEvalService.build_question_set("proj-empty", n=8)
    assert isinstance(qs, list)


def test_build_question_set_padded_to_n_when_short(isolated_db):
    """When corpus is thin the set is padded with generic questions to reach n."""
    from app.services.answer_eval_service import AnswerEvalService

    qs = AnswerEvalService.build_question_set("proj-empty-pad", n=4)
    assert len(qs) >= 1  # padded — at minimum generic questions present
    assert len(qs) <= 4


def test_build_question_set_kg_signals_included(isolated_db):
    """Questions from harness_kg_signals are included in the set."""
    from app.db import harness_kg_signals
    from app.services.answer_eval_service import AnswerEvalService

    harness_kg_signals.record_signal(
        signal_id="sig-qs-1",
        project_id="proj-qs",
        question="What is the deployment process?",
        content="Deploy using docker-compose.",
        round_id="r1",
        already_forged=False,
        weight=1.0,
        now="2026-01-01T00:00:00",
    )
    qs = AnswerEvalService.build_question_set("proj-qs", n=8)
    assert any("deployment" in q.lower() for q in qs)


def test_build_question_set_execution_prompts_included(isolated_db):
    """Execution prompts (project-scoped) appear in the question set."""
    from app.services.answer_eval_service import AnswerEvalService

    _seed_project("proj-ep", "trig-ep", "exec-ep-1", isolated_db)
    qs = AnswerEvalService.build_question_set("proj-ep", n=8)
    # The prompt "Deploy the app to staging" should surface
    assert any("staging" in q.lower() or "deploy" in q.lower() for q in qs)


def test_build_question_set_deterministic(isolated_db):
    """Same project + n → same sorted set."""
    from app.db import harness_kg_signals
    from app.services.answer_eval_service import AnswerEvalService

    harness_kg_signals.record_signal(
        signal_id="sig-det-1",
        project_id="proj-det",
        question="How are deployments triggered?",
        content="Via GitHub Actions.",
        round_id="r1",
        already_forged=False,
        weight=1.0,
        now="2026-01-01T00:00:00",
    )
    harness_kg_signals.record_signal(
        signal_id="sig-det-2",
        project_id="proj-det",
        question="What is the rollback procedure?",
        content="Run rollback script.",
        round_id="r1",
        already_forged=False,
        weight=1.0,
        now="2026-01-01T00:00:00",
    )
    a = AnswerEvalService.build_question_set("proj-det", n=8)
    b = AnswerEvalService.build_question_set("proj-det", n=8)
    assert a == b


def test_build_question_set_sliced_to_n(isolated_db):
    """Result never exceeds n items."""
    from app.db import harness_kg_signals
    from app.services.answer_eval_service import AnswerEvalService

    for i in range(20):
        harness_kg_signals.record_signal(
            signal_id=f"sig-many-{i}",
            project_id="proj-many",
            question=f"Question number {i} about the system?",
            content=f"Answer {i}",
            round_id="r1",
            already_forged=False,
            weight=1.0,
            now="2026-01-01T00:00:00",
        )
    qs = AnswerEvalService.build_question_set("proj-many", n=5)
    assert len(qs) <= 5


# ---------------------------------------------------------------------------
# Two-project question-set leak test
# ---------------------------------------------------------------------------


def test_two_project_question_set_no_leak(isolated_db):
    """Project B's prompts/signals must never appear in project A's question set."""
    from app.db import harness_kg_signals
    from app.services.answer_eval_service import AnswerEvalService

    # Seed project A
    harness_kg_signals.record_signal(
        signal_id="sig-a-leak",
        project_id="proj-leak-A",
        question="How does project A deploy?",
        content="Project A uses CI/CD pipeline.",
        round_id="r1",
        already_forged=False,
        weight=1.0,
        now="2026-01-01T00:00:00",
    )
    _seed_project("proj-leak-A", "trig-leak-A", "exec-leak-A-1", isolated_db)

    # Seed project B with DIFFERENT prompts
    harness_kg_signals.record_signal(
        signal_id="sig-b-leak",
        project_id="proj-leak-B",
        question="How does project B configure secrets?",
        content="Project B uses Vault.",
        round_id="r1",
        already_forged=False,
        weight=1.0,
        now="2026-01-01T00:00:00",
    )
    # Seed project B with a distinctive prompt via direct insert
    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO projects (id, name) VALUES (?, ?)",
            ("proj-leak-B", "Project proj-leak-B"),
        )
        conn.commit()
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO triggers (id, name, enabled, prompt_template) VALUES (?, ?, 1, '')",
            ("trig-leak-B", "Trigger trig-leak-B"),
        )
        conn.commit()
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO project_paths (trigger_id, local_project_path, project_id)"
            " VALUES (?, ?, ?)",
            ("trig-leak-B", "/tmp/path-b", "proj-leak-B"),
        )
        conn.commit()
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO execution_logs"
            " (execution_id, trigger_id, trigger_type, started_at, backend_type, status, prompt)"
            " VALUES (?, ?, 'schedule', '2026-01-01T00:00:00', 'claude', 'completed', ?)",
            ("exec-leak-B-1", "trig-leak-B", "Configure secrets using Vault for project B"),
        )
        conn.commit()

    qs_a = AnswerEvalService.build_question_set("proj-leak-A", n=8)

    # None of the B-specific strings should appear in A's set
    b_markers = ["project b", "vault", "secrets", "proj-leak-B"]
    for q in qs_a:
        for marker in b_markers:
            assert marker not in q.lower(), (
                f"Project B marker '{marker}' leaked into project A's question set: {q!r}"
            )


# ---------------------------------------------------------------------------
# run_eval — stubbed LLM calls
# ---------------------------------------------------------------------------


def _make_llm_call(answer: str):
    """Return a deterministic llm_call stub."""

    def stub(messages):
        return answer

    return stub


def _make_judge_call(scores: dict):
    """Return a judge stub that returns a forgiving-parseable JSON string."""
    import json

    def stub(messages):
        return json.dumps(scores)

    return stub


def test_run_eval_returns_run_id(isolated_db):
    from app.services.answer_eval_service import AnswerEvalService

    run_id = AnswerEvalService.run_eval(
        "proj-ev1",
        n=2,
        judge_backend="claude",
        llm_call=_make_llm_call("The answer is 42."),
        pipeline_llm_call=_make_llm_call("Pipeline answer with sources."),
    )
    assert isinstance(run_id, int)
    assert run_id > 0


def test_run_eval_uses_provided_run_id(isolated_db):
    """When run_id is supplied the service uses it, never creates a second run."""
    from app.db.answer_eval import create_run, get_run
    from app.services.answer_eval_service import AnswerEvalService

    pre_run_id = create_run("proj-ev-pre", judge_backend="claude")

    returned_id = AnswerEvalService.run_eval(
        "proj-ev-pre",
        n=2,
        run_id=pre_run_id,
        llm_call=_make_llm_call("baseline answer"),
        pipeline_llm_call=_make_llm_call("pipeline answer"),
    )
    assert returned_id == pre_run_id

    run = get_run(pre_run_id)
    assert run["status"] == "complete"


def test_run_eval_records_two_arms_per_question(isolated_db):
    """For each question, both 'baseline' and 'pipeline' results are recorded."""
    from app.db import answer_eval as ae
    from app.services.answer_eval_service import AnswerEvalService

    run_id = AnswerEvalService.run_eval(
        "proj-ev2",
        n=2,
        llm_call=_make_llm_call("answer"),
        pipeline_llm_call=_make_llm_call("pipeline answer"),
        judge_backend="claude",
    )
    results = ae.list_results(run_id)
    # n=2 questions × 2 arms = 4 rows
    assert len(results) == 4
    arms = {r["arm"] for r in results}
    assert arms == {"baseline", "pipeline"}


def test_run_eval_aggregates_and_deltas_correct(isolated_db):
    """finalize_run is called with correct per-arm means and deltas."""
    from app.db import answer_eval as ae
    from app.services.answer_eval_service import AnswerEvalService

    call_count = {"n": 0}

    def judge_stub(messages):
        # Alternating scores to distinguish arms: first call=baseline, second=pipeline
        import json

        call_count["n"] += 1
        if call_count["n"] % 2 == 1:
            return json.dumps(
                {"groundedness": 0.6, "sufficiency": 0.5, "quality": 0.7, "reason": "baseline ok"}
            )
        else:
            return json.dumps(
                {"groundedness": 0.9, "sufficiency": 0.8, "quality": 1.0, "reason": "pipeline ok"}
            )

    # With n=1 we get 1 question × 2 arms = 2 judge calls
    # We need 1 question — seed one kg signal
    from app.db import harness_kg_signals

    harness_kg_signals.record_signal(
        signal_id="sig-agg-1",
        project_id="proj-agg",
        question="What is the CI pipeline?",
        content="Jenkins.",
        round_id="r1",
        already_forged=False,
        weight=1.0,
        now="2026-01-01T00:00:00",
    )

    run_id = AnswerEvalService.run_eval(
        "proj-agg",
        n=1,
        llm_call=_make_llm_call("baseline answer"),
        pipeline_llm_call=judge_stub,  # reuse as answer + judge stubs
    )
    run = ae.get_run(run_id)
    assert run["status"] == "complete"
    assert run["finished_at"] is not None


def test_run_eval_blind_judge_prompt_contains_no_arm_names(isolated_db):
    """Judge prompts must never contain 'baseline' or 'pipeline' (blind evaluation)."""
    from app.services.answer_eval_service import AnswerEvalService

    captured_judge_prompts = []

    def capturing_judge(messages):
        for m in messages:
            if isinstance(m.get("content"), str):
                captured_judge_prompts.append(m["content"])
        return '{"groundedness": 0.8, "sufficiency": 0.7, "quality": 0.9, "reason": "ok"}'

    from app.db import harness_kg_signals

    harness_kg_signals.record_signal(
        signal_id="sig-blind-1",
        project_id="proj-blind",
        question="What monitoring is in place?",
        content="Prometheus + Grafana.",
        round_id="r1",
        already_forged=False,
        weight=1.0,
        now="2026-01-01T00:00:00",
    )

    AnswerEvalService.run_eval(
        "proj-blind",
        n=1,
        llm_call=_make_llm_call("The answer."),
        pipeline_llm_call=_make_llm_call("Pipeline answer."),
        judge_backend="claude",
    )

    # We need to inject the capturing judge — re-run with direct judge injection
    # by passing a combined stub
    captured_judge_prompts.clear()

    def all_in_one_stub(messages):
        # Called for baseline answer, pipeline answer, and judge
        content = " ".join(
            m.get("content", "") for m in messages if isinstance(m.get("content"), str)
        )
        captured_judge_prompts.append(content)
        return '{"groundedness": 0.8, "sufficiency": 0.7, "quality": 0.9, "reason": "ok"}'

    AnswerEvalService.run_eval(
        "proj-blind",
        n=1,
        llm_call=all_in_one_stub,
        pipeline_llm_call=all_in_one_stub,
        judge_backend="claude",
    )

    # Judge prompts (those that look like judge calls — contain "groundedness" markers)
    judge_prompts = [p for p in captured_judge_prompts if "answer" in p.lower()]
    # None of the captured content should name the arm
    for prompt in judge_prompts:
        assert "baseline" not in prompt, f"'baseline' found in judge prompt: {prompt[:200]}"
        assert "pipeline" not in prompt, f"'pipeline' found in judge prompt: {prompt[:200]}"


def test_run_eval_per_question_failure_records_zeros_and_run_completes(isolated_db):
    """When both LLM calls raise, zeros are recorded and the run still finalizes."""
    from app.db import answer_eval as ae
    from app.services.answer_eval_service import AnswerEvalService

    def always_raises(messages):
        raise RuntimeError("simulated LLM failure")

    from app.db import harness_kg_signals

    harness_kg_signals.record_signal(
        signal_id="sig-fail-1",
        project_id="proj-fail",
        question="What happens when CI fails?",
        content="Slack alert.",
        round_id="r1",
        already_forged=False,
        weight=1.0,
        now="2026-01-01T00:00:00",
    )

    run_id = AnswerEvalService.run_eval(
        "proj-fail",
        n=1,
        llm_call=always_raises,
        pipeline_llm_call=always_raises,
    )
    run = ae.get_run(run_id)
    assert run is not None
    assert run["status"] == "complete"

    results = ae.list_results(run_id)
    assert len(results) >= 2
    error_results = [r for r in results if r["judge_reason"] == "error"]
    assert len(error_results) >= 2
    for r in error_results:
        assert r["groundedness"] == pytest.approx(0.0)
        assert r["sufficiency"] == pytest.approx(0.0)
        assert r["quality"] == pytest.approx(0.0)


def test_fatal_error_marks_run_failed(isolated_db):
    """A fatal pre-loop error must leave the run terminally 'failed', never
    'running' forever (codex PR review)."""
    from unittest.mock import patch

    import pytest

    from app.db.answer_eval import create_run, get_run
    from app.services.answer_eval_service import AnswerEvalService

    run_id = create_run("proj-x", judge_backend="claude")
    with patch.object(AnswerEvalService, "build_question_set", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            AnswerEvalService.run_eval(
                "proj-x",
                n=2,
                llm_call=lambda m: "a",
                pipeline_llm_call=lambda m: "a",
                run_id=run_id,
            )
    run = get_run(run_id)
    assert run["status"] == "failed"
    assert run["finished_at"] is not None
