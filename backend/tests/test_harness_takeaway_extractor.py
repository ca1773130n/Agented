"""Tests for the positive-learning takeaway extractor."""

from __future__ import annotations

import json
from unittest.mock import patch

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


# ---------- skill auto-writer -----------------------------------------------

def _seed_project_with_local_path(project_id: str, local_path) -> None:
    """Plant a projects row with a local_path so the skill auto-writer
    targets the project's own .claude/skills tree."""
    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO projects (id, name, local_path) "
            "VALUES (?, 'Test', ?)",
            (project_id, str(local_path)),
        )
        conn.commit()


def test_apply_skill_materializes_skill_md_and_binds(isolated_db, tmp_path):
    """Skill auto-writer writes a SKILL.md package under the project's
    .claude/skills/<name>/ and registers it via add_project_skill."""
    _seed_project_with_local_path("proj-skill-a", tmp_path)
    _seed_execution("exec-skill", _make_assistant_stream(
        "I learned that to spin up the dev server you must run "
        "`just dev-backend` and `just dev-frontend` in separate terminals.",
    ))
    ids = _extract("exec-skill", "proj-skill-a")
    skill_tk = next(
        repo.get(i) for i in ids
        if (repo.get(i) or {}).get("suggested_target") == "skill"
    )

    result = extractor.apply_takeaway(skill_tk["id"])
    assert result["applied"] is True
    assert result["target"] == "skill"

    # SKILL.md exists at the expected location.
    skill_root = tmp_path / ".claude" / "skills"
    skill_dirs = list(skill_root.iterdir())
    assert skill_dirs, f"expected SKILL.md dir under {skill_root}"
    md_path = skill_dirs[0] / "SKILL.md"
    assert md_path.is_file()
    body = md_path.read_text()
    # Frontmatter + recipe body landed.
    assert "name: " in body
    assert "source: agented-takeaway" in body
    assert "just dev-backend" in body

    # And the project_skills binding was registered.
    from app.db.projects import get_project_skills
    bindings = get_project_skills("proj-skill-a")
    assert bindings
    assert any(b["skill_name"] == result["asset_id"] for b in bindings)


def test_apply_skill_falls_back_to_user_dir_when_no_local_path(
    isolated_db, monkeypatch, tmp_path,
):
    """Project with no local_path → skill lands under
    ``~/.claude/skills/agented-<project_id>/`` (sandboxed via HOME)."""
    monkeypatch.setenv("HOME", str(tmp_path))
    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO projects (id, name) VALUES (?, 'Test')",
            ("proj-skill-noloc",),
        )
        conn.commit()
    _seed_execution("exec-skill-noloc", _make_assistant_stream(
        "I learned that the deploy script must be run with sudo because "
        "it writes to /etc.",
    ))
    ids = _extract("exec-skill-noloc", "proj-skill-noloc")
    skill_tk = next(
        repo.get(i) for i in ids
        if (repo.get(i) or {}).get("suggested_target") == "skill"
    )
    result = extractor.apply_takeaway(skill_tk["id"])
    assert result["applied"] is True

    expected_root = tmp_path / ".claude" / "skills" / "agented-proj-skill-noloc"
    skill_dirs = list(expected_root.iterdir())
    assert skill_dirs
    assert (skill_dirs[0] / "SKILL.md").is_file()


def test_apply_skill_without_project_id_fails(isolated_db):
    """A skill takeaway with no project_id can't be materialized — no
    target directory to write to."""
    # Insert directly (bypass extractor) with project_id=None.
    [tk_id] = repo.insert_many([{
        "session_kind": "trigger_execution",
        "session_id": "exec-orphan",
        "project_id": None,
        "kind": "discovered_procedure",
        "content": "Some procedure",
        "confidence": 0.7,
        "suggested_target": "skill",
        "suggested_payload": {"title": "orphan-skill", "recipe": "do X"},
        "extractor_version": "heuristic-test",
    }])
    result = extractor.apply_takeaway(tk_id)
    assert result["applied"] is False


# ---------- LLM extraction --------------------------------------------------

def _long_subtle_stream() -> str:
    """A transcript with NO heuristic-matching phrases — only the LLM
    should surface anything. Long enough to clear the min-bytes gate."""
    filler = "Analysing the codebase. " * 80  # ~2KB filler
    return _make_assistant_stream(
        filler + " Note for context: the project's CI uses pytest-xdist "
        "and we should batch slow tests with the @pytest.mark.slow marker.",
    )


def test_llm_disabled_by_default(isolated_db, monkeypatch):
    """Without AGENTED_TAKEAWAY_LLM=1 the LLM path never runs."""
    monkeypatch.delenv("AGENTED_TAKEAWAY_LLM", raising=False)
    _seed_execution("exec-llm-off", _long_subtle_stream())

    with patch.object(
        extractor, "_run_codex_for_extraction",
    ) as mock_codex:
        _extract("exec-llm-off", "proj-tk-llm-off")
    mock_codex.assert_not_called()


def test_llm_enabled_with_short_transcript_skips_codex(isolated_db, monkeypatch):
    """Short transcripts don't justify the LLM cost — heuristic-only."""
    monkeypatch.setenv("AGENTED_TAKEAWAY_LLM", "1")
    _seed_execution("exec-llm-short", _make_assistant_stream("brief"))

    with patch.object(
        extractor, "_run_codex_for_extraction",
    ) as mock_codex:
        _extract("exec-llm-short", "proj-tk-llm-short")
    mock_codex.assert_not_called()


def test_llm_extracts_takeaways_from_long_transcript(isolated_db, monkeypatch):
    """LLM surfaces what heuristic missed: subtle multi-line context."""
    monkeypatch.setenv("AGENTED_TAKEAWAY_LLM", "1")
    monkeypatch.setenv("AGENTED_TAKEAWAY_LLM_MIN_BYTES", "100")
    _seed_execution("exec-llm-on", _long_subtle_stream())

    llm_payload = [
        {
            "kind": "domain_fact",
            "content": "CI uses pytest-xdist; slow tests need @pytest.mark.slow",
            "confidence": 0.85,
            "suggested_target": "knowledge_graph",
            "rationale": "transcript mentioned pytest-xdist + slow marker",
        },
        {
            "kind": "user_preference",
            "content": "Batch slow tests with @pytest.mark.slow",
            "confidence": 0.75,
            "suggested_target": "memory",
            "rationale": "stated as a convention",
        },
    ]
    with patch.object(
        extractor, "_run_codex_for_extraction",
        return_value=json.dumps(llm_payload),
    ):
        ids = _extract("exec-llm-on", "proj-tk-llm-on")

    rows = [r for r in (repo.get(i) for i in ids) if r is not None]
    llm_rows = [r for r in rows if r["extractor_version"].startswith("llm")]
    assert len(llm_rows) == 2
    facts = [r for r in llm_rows if r["kind"] == "domain_fact"]
    assert facts and "pytest-xdist" in facts[0]["content"]
    # Rationale lands in the evidence blob.
    assert facts[0]["evidence"].get("rationale")


def test_llm_handles_codex_preamble(isolated_db, monkeypatch):
    """Real Codex sometimes prints a preamble before the JSON. The
    extractor must slice from first ``[`` to last ``]``."""
    monkeypatch.setenv("AGENTED_TAKEAWAY_LLM", "1")
    monkeypatch.setenv("AGENTED_TAKEAWAY_LLM_MIN_BYTES", "100")
    _seed_execution("exec-llm-preamble", _long_subtle_stream())

    noisy = (
        "Reading prompt...\nOK, here's the JSON:\n"
        + json.dumps([{
            "kind": "domain_fact", "content": "x is at /path/to/x",
            "confidence": 0.7, "suggested_target": "knowledge_graph",
            "rationale": "explicit reference",
        }])
        + "\n\n(end of output)\n"
    )
    with patch.object(
        extractor, "_run_codex_for_extraction", return_value=noisy,
    ):
        ids = _extract("exec-llm-preamble", "proj-tk-llm-preamble")

    rows = [r for r in (repo.get(i) for i in ids) if r is not None]
    llm_rows = [r for r in rows if r["extractor_version"].startswith("llm")]
    assert len(llm_rows) == 1
    assert "x is at" in llm_rows[0]["content"]


def test_llm_codex_failure_does_not_block_heuristic(isolated_db, monkeypatch):
    """If Codex errors, the heuristic results still flow through."""
    monkeypatch.setenv("AGENTED_TAKEAWAY_LLM", "1")
    monkeypatch.setenv("AGENTED_TAKEAWAY_LLM_MIN_BYTES", "100")
    # Stream that has BOTH a heuristic match AND enough length for LLM.
    stream = _make_assistant_stream(
        "Got it, I'll remember that you prefer ESLint over Prettier.",
        "x" * 3000,
    )
    _seed_execution("exec-llm-error", stream)

    def _exploding(*_args, **_kwargs):
        raise RuntimeError("codex CLI exited 1: boom")

    with patch.object(
        extractor, "_run_codex_for_extraction", _exploding,
    ):
        ids = _extract("exec-llm-error", "proj-tk-llm-error")

    # Heuristic still surfaced the "I'll remember" preference.
    rows = [r for r in (repo.get(i) for i in ids) if r is not None]
    assert any(r["kind"] == "user_preference" for r in rows)


def test_llm_malformed_output_is_dropped_silently(isolated_db, monkeypatch):
    """A Codex run that returns non-JSON gibberish must not crash —
    the heuristic results still land."""
    monkeypatch.setenv("AGENTED_TAKEAWAY_LLM", "1")
    monkeypatch.setenv("AGENTED_TAKEAWAY_LLM_MIN_BYTES", "100")
    stream = _make_assistant_stream(
        "Got it, I'll remember that you prefer Vue's <script setup>.",
        "x" * 3000,
    )
    _seed_execution("exec-llm-bad", stream)

    with patch.object(
        extractor, "_run_codex_for_extraction",
        return_value="this is not json at all",
    ):
        ids = _extract("exec-llm-bad", "proj-tk-llm-bad")
    rows = [r for r in (repo.get(i) for i in ids) if r is not None]
    # No LLM rows, but the heuristic preference is still there.
    assert all(not r["extractor_version"].startswith("llm") for r in rows)
    assert any(r["kind"] == "user_preference" for r in rows)


def test_llm_dedups_when_overlapping_with_heuristic(isolated_db, monkeypatch):
    """If LLM and heuristic surface the same content, only ONE row lands."""
    monkeypatch.setenv("AGENTED_TAKEAWAY_LLM", "1")
    monkeypatch.setenv("AGENTED_TAKEAWAY_LLM_MIN_BYTES", "100")
    stream = _make_assistant_stream(
        "Got it, I'll remember that you prefer flake8 over pylint.",
        "x" * 3000,
    )
    _seed_execution("exec-llm-dedup", stream)

    # LLM proposes the SAME preference content the heuristic already caught.
    overlap = json.dumps([{
        "kind": "user_preference",
        "content": "flake8 over pylint",
        "confidence": 0.8,
        "suggested_target": "memory",
        "rationale": "explicit preference statement",
    }])
    with patch.object(
        extractor, "_run_codex_for_extraction", return_value=overlap,
    ):
        ids = _extract("exec-llm-dedup", "proj-tk-llm-dedup")

    rows = [r for r in (repo.get(i) for i in ids) if r is not None]
    flake8_rows = [r for r in rows if "flake8" in r["content"].lower()]
    # Heuristic wins ties (cheaper, deterministic).
    assert len(flake8_rows) == 1
    assert flake8_rows[0]["extractor_version"].startswith("heuristic")
