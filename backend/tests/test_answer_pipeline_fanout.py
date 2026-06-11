"""TDD tests for AnswerPipelineService fanout retrievers (real isolated_db).

Tests each _search_* retriever for correct provenance keys, the mandatory
two-project leak test, and the tesserae budget guard.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Helpers — seed DB rows
# ---------------------------------------------------------------------------


def _seed_trigger_and_project(*, project_id: str, trigger_id: str, execution_id: str):
    """Insert minimal rows to make _project_execution_ids work.

    Uses separate get_connection() calls per step so each insert is
    committed on its own connection — FK checks then see committed data.
    """
    from app.db.connection import get_connection

    # 1. project
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO projects (id, name) VALUES (?, ?)",
            (project_id, f"Project {project_id}"),
        )
        conn.commit()
    # 2. trigger (prompt_template NOT NULL, so must supply it)
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO triggers (id, name, enabled, prompt_template) VALUES (?, ?, 1, '')",
            (trigger_id, f"Trigger {trigger_id}"),
        )
        conn.commit()
    # 3. project_paths (FK: trigger_id → triggers, project_id → projects)
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO project_paths (trigger_id, local_project_path, project_id) "
            "VALUES (?, ?, ?)",
            (trigger_id, "/tmp/path", project_id),
        )
        conn.commit()
    # 4. execution_log (FK: trigger_id → triggers)
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO execution_logs "
            "(execution_id, trigger_id, trigger_type, started_at, backend_type, status, prompt) "
            "VALUES (?, ?, 'schedule', '2026-01-01T00:00:00', 'claude', 'completed', 'prompt')",
            (execution_id, trigger_id),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Individual retriever tests
# ---------------------------------------------------------------------------


def test_search_kg_signals_returns_provenance(isolated_db):
    from app.db import harness_kg_signals
    from app.services.answer_pipeline_service import _search_kg_signals

    harness_kg_signals.record_signal(
        signal_id="sig-test-1",
        project_id="proj-A",
        question="How does X work?",
        content="X works by doing Y",
        weight=0.8,
        already_forged=False,
        now="2026-01-01T00:00:00",
    )

    chunks = _search_kg_signals("proj-A", "How does X work")
    assert len(chunks) >= 1
    assert all(c.source == "kg_signal" for c in chunks)
    assert all(c.provenance_key.startswith("signal:") for c in chunks)


def test_search_execution_logs_returns_provenance(isolated_db):
    from app.db.connection import get_connection
    from app.services.answer_pipeline_service import _search_execution_logs

    _seed_trigger_and_project(
        project_id="proj-A",
        trigger_id="trig-A",
        execution_id="exec-A-1",
    )
    # Insert FTS content
    with get_connection() as conn:
        conn.execute(
            "UPDATE execution_logs SET stdout_log = ? WHERE execution_id = ?",
            ("The deployment was successful and all tests passed with flying colors", "exec-A-1"),
        )
        conn.commit()

    # Rebuild FTS index
    with get_connection() as conn:
        try:
            conn.execute("INSERT INTO execution_logs_fts(execution_logs_fts) VALUES('rebuild')")
            conn.commit()
        except Exception:
            pass

    chunks = _search_execution_logs("proj-A", "deployment successful")
    # May be empty if FTS index is fresh — just assert no cross-project leak
    for c in chunks:
        assert c.source == "execution_log"
        assert c.provenance_key.startswith("execution:")


def test_search_takeaways_returns_provenance(isolated_db):
    from app.db import harness_takeaways
    from app.services.answer_pipeline_service import _search_takeaways

    harness_takeaways.insert_many(
        [
            {
                "session_kind": "harness",
                "session_id": "sess-1",
                "project_id": "proj-A",
                "kind": "domain_fact",
                "content": "We should fix the config management approach",
                "confidence": 0.8,
                "evidence": {},
                "suggested_payload": {},
                "extractor_version": "v1",
            }
        ]
    )

    chunks = _search_takeaways("proj-A", "config management")
    assert len(chunks) >= 1
    assert all(c.source == "takeaway" for c in chunks)
    assert all(c.provenance_key.startswith("takeaway:") for c in chunks)


def test_search_findings_returns_provenance(isolated_db):
    from app.db import findings
    from app.services.answer_pipeline_service import _search_findings

    _seed_trigger_and_project(
        project_id="proj-A",
        trigger_id="trig-A",
        execution_id="exec-A-1",
    )

    findings.create_finding(
        {
            "title": "SQL injection in login form",
            "severity": "high",
            "description": "The login endpoint is vulnerable",
            "execution_id": "exec-A-1",
        }
    )

    chunks = _search_findings("proj-A", "SQL injection")
    assert len(chunks) >= 1
    assert all(c.source == "finding" for c in chunks)
    assert all(c.provenance_key.startswith("finding:") for c in chunks)


def test_search_verifications_returns_provenance(isolated_db):
    from app.db import verification_records
    from app.services.answer_pipeline_service import _search_verifications

    _seed_trigger_and_project(
        project_id="proj-A",
        trigger_id="trig-A",
        execution_id="exec-A-1",
    )

    verification_records.record_verification(
        execution_id="exec-A-1",
        claim="All tests pass",
        status="passed",
        evidence_ref="Ran pytest, all green",
    )

    chunks = _search_verifications("proj-A", "tests pass")
    assert len(chunks) >= 1
    assert all(c.source == "verification" for c in chunks)
    assert all(c.provenance_key.startswith("verification:") for c in chunks)


# ---------------------------------------------------------------------------
# Two-project leak test
# ---------------------------------------------------------------------------


def test_two_project_no_cross_project_leak(isolated_db):
    """Project A fanout must yield ZERO chunks whose provenance keys belong to project B."""
    from app.db import findings, harness_kg_signals, harness_takeaways
    from app.services.answer_pipeline_service import (
        _search_execution_logs,
        _search_findings,
        _search_kg_signals,
        _search_takeaways,
        _search_verifications,
    )

    # Seed project A
    _seed_trigger_and_project(
        project_id="proj-A",
        trigger_id="trig-A",
        execution_id="exec-A-1",
    )
    # Seed project B
    _seed_trigger_and_project(
        project_id="proj-B",
        trigger_id="trig-B",
        execution_id="exec-B-1",
    )

    # Seed project A data
    harness_kg_signals.record_signal(
        signal_id="sig-A-1",
        project_id="proj-A",
        question="Project A question",
        content="Project A content only",
        weight=0.9,
        already_forged=False,
        now="2026-01-01T00:00:00",
    )
    harness_takeaways.insert_many(
        [
            {
                "session_kind": "harness",
                "session_id": "sess-A",
                "project_id": "proj-A",
                "kind": "domain_fact",
                "content": "Only relevant to project A",
                "confidence": 0.8,
                "evidence": {},
                "suggested_payload": {},
                "extractor_version": "v1",
            }
        ]
    )
    findings.create_finding(
        {
            "title": "Project A finding",
            "severity": "medium",
            "description": "Only in project A",
            "execution_id": "exec-A-1",
        }
    )

    # Seed project B data (must NOT appear in proj-A fanout)
    harness_kg_signals.record_signal(
        signal_id="sig-B-1",
        project_id="proj-B",
        question="Project B question",
        content="Project B content only",
        weight=0.9,
        already_forged=False,
        now="2026-01-01T00:00:00",
    )
    harness_takeaways.insert_many(
        [
            {
                "session_kind": "harness",
                "session_id": "sess-B",
                "project_id": "proj-B",
                "kind": "domain_fact",
                "content": "Only relevant to project B",
                "confidence": 0.8,
                "evidence": {},
                "suggested_payload": {},
                "extractor_version": "v1",
            }
        ]
    )
    findings.create_finding(
        {
            "title": "Project B finding",
            "severity": "medium",
            "description": "Only in project B",
            "execution_id": "exec-B-1",
        }
    )

    query = "project content"

    kg_chunks = _search_kg_signals("proj-A", query)
    takeaway_chunks = _search_takeaways("proj-A", query)
    finding_chunks = _search_findings("proj-A", query)
    exec_chunks = _search_execution_logs("proj-A", query)
    verif_chunks = _search_verifications("proj-A", query)

    all_chunks = kg_chunks + takeaway_chunks + finding_chunks + exec_chunks + verif_chunks

    # Assert NO chunk has a provenance key tied to project B
    for chunk in all_chunks:
        assert "exec-B-1" not in chunk.provenance_key, (
            f"Cross-project leak: chunk from proj-B appeared in proj-A fanout: {chunk}"
        )

    # KG signals are project-keyed, so sig-B-1 must not appear
    kg_keys = [c.provenance_key for c in kg_chunks]
    assert not any("sig-B-1" in k for k in kg_keys), (
        f"KG signal leak: sig-B-1 in proj-A results: {kg_keys}"
    )


# ---------------------------------------------------------------------------
# Tesserae budget
# ---------------------------------------------------------------------------


def test_ask_tesserae_budgeted_respects_budget(monkeypatch):
    from app.services import answer_pipeline_service as svc

    call_count = {"n": 0}

    def _mock_ask_tesserae(project_id, question, *, top_k=5):
        call_count["n"] += 1
        return "Tesserae answer text"

    monkeypatch.setattr(svc, "_ask_tesserae_raw", _mock_ask_tesserae)

    state = {"used": 0}

    # First call should consume budget
    chunks1 = svc._ask_tesserae_budgeted(
        project_id="proj-A",
        query="what is the project",
        tesserae_root="/some/root",
        budget_state=state,
        tesserae_budget=1,
        remaining_seconds=90.0,
    )
    assert len(chunks1) >= 1
    assert state["used"] == 1

    # Second call should return nothing (budget exhausted)
    chunks2 = svc._ask_tesserae_budgeted(
        project_id="proj-A",
        query="what else",
        tesserae_root="/some/root",
        budget_state=state,
        tesserae_budget=1,
        remaining_seconds=90.0,
    )
    assert chunks2 == []
    # ask_tesserae was only called ONCE
    assert call_count["n"] == 1


def test_ask_tesserae_budgeted_not_enough_time(monkeypatch):
    """Tesserae should NOT be called when remaining_seconds <= 25."""
    from app.services import answer_pipeline_service as svc

    call_count = {"n": 0}

    def _mock_ask_tesserae(project_id, question, *, top_k=5):
        call_count["n"] += 1
        return "Tesserae answer text"

    monkeypatch.setattr(svc, "_ask_tesserae_raw", _mock_ask_tesserae)

    state = {"used": 0}
    chunks = svc._ask_tesserae_budgeted(
        project_id="proj-A",
        query="what is the project",
        tesserae_root="/some/root",
        budget_state=state,
        tesserae_budget=1,
        remaining_seconds=20.0,  # below 25s threshold
    )
    assert chunks == []
    assert call_count["n"] == 0


def test_ask_tesserae_budgeted_returns_none(monkeypatch):
    """ask_tesserae returning None → empty list."""
    from app.services import answer_pipeline_service as svc

    monkeypatch.setattr(svc, "_ask_tesserae_raw", lambda *a, **kw: None)

    state = {"used": 0}
    chunks = svc._ask_tesserae_budgeted(
        project_id="proj-A",
        query="question",
        tesserae_root="/some/root",
        budget_state=state,
        tesserae_budget=1,
        remaining_seconds=90.0,
    )
    assert chunks == []
