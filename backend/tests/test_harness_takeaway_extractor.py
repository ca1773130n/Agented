"""Tests for the positive-learning takeaway extractor."""

from __future__ import annotations

import json

from app.db import harness_takeaways as repo
from app.services import harness_takeaway_extractor as extractor


def _make_assistant_stream(*texts: str) -> str:
    """Fake Claude JSONL stream — each text becomes one assistant turn."""
    lines = []
    for t in texts:
        lines.append(json.dumps({
            "type": "assistant", "message": {"content": [
                {"type": "text", "text": t},
            ]},
        }))
    return "\n".join(lines)


def _seed_execution(execution_id: str, stream: str, *,
                    status: str = "completed") -> None:
    """Plant an execution_logs row. ``trigger_id`` left NULL to dodge
    the triggers(id) FK."""
    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute(
            """INSERT INTO execution_logs
                   (execution_id, trigger_id, trigger_type, started_at,
                    backend_type, status, stdout_log)
               VALUES (?, NULL, 'manual', datetime('now'), 'claude', ?, ?)""",
            (execution_id, status, stream),
        )
        conn.commit()


def _extract(execution_id: str, project_id: str) -> list[str]:
    return extractor.extract_for_session(
        "trigger_execution", execution_id, project_id=project_id,
    )


# ---------- pattern detection -----------------------------------------------

def test_extracts_user_preference_from_remember_phrase(isolated_db):
    _seed_execution("exec-pref", _make_assistant_stream(
        "Got it, I'll remember that you prefer snake_case for all "
        "Python variables going forward.",
    ))
    ids = _extract("exec-pref", "proj-tk-a")
    assert ids
    prefs = [r for r in repo.list_for_project("proj-tk-a")
             if r["kind"] == "user_preference"]
    assert prefs
    assert any("snake_case" in r["content"] for r in prefs)
    assert prefs[0]["suggested_target"] == "memory"


def test_extracts_domain_fact_path(isolated_db):
    _seed_execution("exec-fact", _make_assistant_stream(
        "The deploy script lives at `scripts/deploy.sh` in this repo.",
    ))
    _extract("exec-fact", "proj-tk-b")
    facts = [r for r in repo.list_for_project("proj-tk-b")
             if r["kind"] == "domain_fact"]
    assert facts
    assert any("deploy.sh" in r["content"] for r in facts)
    assert facts[0]["suggested_target"] == "knowledge_graph"


def test_extracts_discovered_procedure(isolated_db):
    _seed_execution("exec-proc", _make_assistant_stream(
        "I learned that to deploy this service you must first run migrations.",
    ))
    _extract("exec-proc", "proj-tk-c")
    procs = [r for r in repo.list_for_project("proj-tk-c")
             if r["kind"] == "discovered_procedure"]
    assert procs
    assert procs[0]["suggested_target"] == "skill"


def test_extractor_deduplicates_within_session(isolated_db):
    _seed_execution("exec-dup", _make_assistant_stream(
        "I'll remember that you prefer snake_case for Python variables.",
        "Just noting again: I'll remember that you prefer snake_case for Python variables.",
    ))
    _extract("exec-dup", "proj-tk-d")
    prefs = [r for r in repo.list_for_project("proj-tk-d")
             if r["kind"] == "user_preference"
             and "snake_case" in r["content"]]
    assert len(prefs) == 1


def test_empty_session_produces_no_takeaways(isolated_db):
    _seed_execution("exec-empty", "")
    assert _extract("exec-empty", "proj-tk-e") == []


def test_unknown_session_kind_is_noop(isolated_db):
    assert extractor.extract_for_session("totally-fake-kind", "xxx") == []


# ---------- apply / dismiss --------------------------------------------------

def test_apply_takeaway_to_memory(isolated_db):
    _seed_execution("exec-apply", _make_assistant_stream(
        "Got it, I'll remember that you prefer kebab-case URL paths.",
    ))
    ids = _extract("exec-apply", "proj-tk-apply")
    assert ids
    memory_tk = next(
        repo.get(i) for i in ids
        if (repo.get(i) or {}).get("suggested_target") == "memory"
    )
    result = extractor.apply_takeaway(memory_tk["id"])
    assert result["applied"] is True
    assert result["target"] == "memory"
    refreshed = repo.get(memory_tk["id"])
    assert refreshed["applied"] is True
    assert refreshed["applied_target"] == "memory"


def test_dismiss_takeaway(isolated_db):
    _seed_execution("exec-dismiss", _make_assistant_stream(
        "I'll remember that you prefer something irrelevant for now.",
    ))
    ids = _extract("exec-dismiss", "proj-tk-dis")
    assert ids
    res = extractor.dismiss_takeaway(ids[0], reason="not useful")
    assert res["dismissed"] is True
    refreshed = repo.get(ids[0])
    assert refreshed["dismissed"] is True
    assert refreshed["dismissed_reason"] == "not useful"


def test_apply_unknown_returns_failed(isolated_db):
    res = extractor.apply_takeaway("tk-nope")
    assert res["applied"] is False
    assert "not found" in res["reason"]


def test_apply_already_applied_returns_failed(isolated_db):
    _seed_execution("exec-twice", _make_assistant_stream(
        "Got it, I'll remember that you prefer Vue 3 composition API.",
    ))
    ids = _extract("exec-twice", "proj-tk-twice")
    tk = next(
        repo.get(i) for i in ids
        if (repo.get(i) or {}).get("suggested_target") == "memory"
    )
    assert extractor.apply_takeaway(tk["id"])["applied"] is True
    second = extractor.apply_takeaway(tk["id"])
    assert second["applied"] is False
    assert "already applied" in second["reason"]


# ---------- autoapply env-var gate ------------------------------------------

def test_autoapply_disabled_by_default(isolated_db, monkeypatch):
    monkeypatch.delenv("AGENTED_TAKEAWAY_AUTOAPPLY", raising=False)
    _seed_execution("exec-auto-off", _make_assistant_stream(
        "Got it, I'll remember that you prefer descriptive variable names.",
    ))
    ids = _extract("exec-auto-off", "proj-tk-auto-off")
    rows = [r for r in (repo.get(i) for i in ids) if r is not None]
    assert all(not r["applied"] for r in rows)


def test_autoapply_enabled_applies_high_confidence(isolated_db, monkeypatch):
    monkeypatch.setenv("AGENTED_TAKEAWAY_AUTOAPPLY", "1")
    _seed_execution("exec-auto-on", _make_assistant_stream(
        "Got it, I'll remember that you prefer pytest fixtures over setUp.",
    ))
    ids = _extract("exec-auto-on", "proj-tk-auto-on")
    rows = [r for r in (repo.get(i) for i in ids) if r is not None]
    memory_rows = [r for r in rows if r["suggested_target"] == "memory"]
    assert memory_rows
    assert any(r["applied"] for r in memory_rows)
