"""Tests for the per-project corpus-health gate (answer-eval run-6 finding).

corpus_health counts durable, project-scoped retrievable items (kg signals,
takeaways, project execution logs; generative Tesserae excluded) and decides
whether the live RAG pipeline should run for a project.
"""

from __future__ import annotations


def _seed_signals(project_id: str, n: int) -> None:
    from app.db import harness_kg_signals

    for i in range(n):
        harness_kg_signals.record_signal(
            signal_id=f"sig-{project_id}-{i}",
            project_id=project_id,
            question=f"Question {i}?",
            content=f"content body {i}",
            round_id="r1",
            already_forged=False,
            weight=1.0,
            now="2026-01-01T00:00:00",
        )


def test_corpus_health_counts_durable_kg_signals():
    from app.services.answer_pipeline_service import corpus_health

    _seed_signals("proj-ch", 5)
    h = corpus_health("proj-ch")
    assert h["kg_signals"] == 5
    assert h["takeaways"] == 0
    assert h["executions"] == 0
    assert h["total"] == 5


def test_corpus_health_thin_below_threshold_is_unhealthy():
    from app.services.answer_pipeline_service import corpus_health

    _seed_signals("proj-thin", 6)  # the run-6 net-negative corpus size
    h = corpus_health("proj-thin", min_items=8)
    assert h["total"] == 6
    assert h["min_items"] == 8
    assert h["healthy"] is False


def test_corpus_health_at_threshold_is_healthy():
    from app.services.answer_pipeline_service import corpus_health

    _seed_signals("proj-rich", 8)
    h = corpus_health("proj-rich", min_items=8)
    assert h["total"] == 8
    assert h["healthy"] is True


def test_corpus_health_threshold_from_env(monkeypatch):
    from app.services.answer_pipeline_service import corpus_health

    _seed_signals("proj-env", 6)
    monkeypatch.setenv("AGENTED_RAG_MIN_CORPUS", "5")
    assert corpus_health("proj-env")["healthy"] is True  # 6 >= 5
    monkeypatch.setenv("AGENTED_RAG_MIN_CORPUS", "10")
    assert corpus_health("proj-env")["healthy"] is False  # 6 < 10


def test_corpus_health_empty_project_is_unhealthy():
    from app.services.answer_pipeline_service import corpus_health

    h = corpus_health("proj-does-not-exist")
    assert h["total"] == 0
    assert h["healthy"] is False
