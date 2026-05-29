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
        lines.append(
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {"type": "text", "text": t},
                        ]
                    },
                }
            )
        )
    return "\n".join(lines)


def _seed_execution(execution_id: str, stream: str, *, status: str = "completed") -> None:
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
        "trigger_execution",
        execution_id,
        project_id=project_id,
    )


# ---------- pattern detection -----------------------------------------------


def test_extracts_user_preference_from_remember_phrase(isolated_db):
    _seed_execution(
        "exec-pref",
        _make_assistant_stream(
            "Got it, I'll remember that you prefer snake_case for all "
            "Python variables going forward.",
        ),
    )
    ids = _extract("exec-pref", "proj-tk-a")
    assert ids
    prefs = [r for r in repo.list_for_project("proj-tk-a") if r["kind"] == "user_preference"]
    assert prefs
    assert any("snake_case" in r["content"] for r in prefs)
    assert prefs[0]["suggested_target"] == "memory"


def test_extracts_domain_fact_path(isolated_db):
    _seed_execution(
        "exec-fact",
        _make_assistant_stream(
            "The deploy script lives at `scripts/deploy.sh` in this repo.",
        ),
    )
    _extract("exec-fact", "proj-tk-b")
    facts = [r for r in repo.list_for_project("proj-tk-b") if r["kind"] == "domain_fact"]
    assert facts
    assert any("deploy.sh" in r["content"] for r in facts)
    assert facts[0]["suggested_target"] == "knowledge_graph"


def test_extracts_discovered_procedure(isolated_db):
    _seed_execution(
        "exec-proc",
        _make_assistant_stream(
            "I learned that to deploy this service you must first run migrations.",
        ),
    )
    _extract("exec-proc", "proj-tk-c")
    procs = [r for r in repo.list_for_project("proj-tk-c") if r["kind"] == "discovered_procedure"]
    assert procs
    assert procs[0]["suggested_target"] == "skill"


def test_extractor_deduplicates_within_session(isolated_db):
    _seed_execution(
        "exec-dup",
        _make_assistant_stream(
            "I'll remember that you prefer snake_case for Python variables.",
            "Just noting again: I'll remember that you prefer snake_case for Python variables.",
        ),
    )
    _extract("exec-dup", "proj-tk-d")
    prefs = [
        r
        for r in repo.list_for_project("proj-tk-d")
        if r["kind"] == "user_preference" and "snake_case" in r["content"]
    ]
    assert len(prefs) == 1


def test_empty_session_produces_no_takeaways(isolated_db):
    _seed_execution("exec-empty", "")
    assert _extract("exec-empty", "proj-tk-e") == []


def test_unknown_session_kind_is_noop(isolated_db):
    assert extractor.extract_for_session("totally-fake-kind", "xxx") == []


# ---------- apply / dismiss --------------------------------------------------


def test_apply_takeaway_to_memory(isolated_db):
    _seed_execution(
        "exec-apply",
        _make_assistant_stream(
            "Got it, I'll remember that you prefer kebab-case URL paths.",
        ),
    )
    ids = _extract("exec-apply", "proj-tk-apply")
    assert ids
    memory_tk = next(
        repo.get(i) for i in ids if (repo.get(i) or {}).get("suggested_target") == "memory"
    )
    result = extractor.apply_takeaway(memory_tk["id"])
    assert result["applied"] is True
    assert result["target"] == "memory"
    refreshed = repo.get(memory_tk["id"])
    assert refreshed["applied"] is True
    assert refreshed["applied_target"] == "memory"


def test_dismiss_takeaway(isolated_db):
    _seed_execution(
        "exec-dismiss",
        _make_assistant_stream(
            "I'll remember that you prefer something irrelevant for now.",
        ),
    )
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
    _seed_execution(
        "exec-twice",
        _make_assistant_stream(
            "Got it, I'll remember that you prefer Vue 3 composition API.",
        ),
    )
    ids = _extract("exec-twice", "proj-tk-twice")
    tk = next(repo.get(i) for i in ids if (repo.get(i) or {}).get("suggested_target") == "memory")
    assert extractor.apply_takeaway(tk["id"])["applied"] is True
    second = extractor.apply_takeaway(tk["id"])
    assert second["applied"] is False
    assert "already applied" in second["reason"]


# ---------- autoapply env-var gate ------------------------------------------


def test_autoapply_disabled_by_default(isolated_db, monkeypatch):
    monkeypatch.delenv("AGENTED_TAKEAWAY_AUTOAPPLY", raising=False)
    _seed_execution(
        "exec-auto-off",
        _make_assistant_stream(
            "Got it, I'll remember that you prefer descriptive variable names.",
        ),
    )
    ids = _extract("exec-auto-off", "proj-tk-auto-off")
    rows = [r for r in (repo.get(i) for i in ids) if r is not None]
    assert all(not r["applied"] for r in rows)


def test_autoapply_enabled_applies_high_confidence(isolated_db, monkeypatch):
    monkeypatch.setenv("AGENTED_TAKEAWAY_AUTOAPPLY", "1")
    _seed_execution(
        "exec-auto-on",
        _make_assistant_stream(
            "Got it, I'll remember that you prefer pytest fixtures over setUp.",
        ),
    )
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
            "INSERT OR IGNORE INTO projects (id, name, local_path) VALUES (?, 'Test', ?)",
            (project_id, str(local_path)),
        )
        conn.commit()


def test_apply_skill_materializes_skill_md_and_binds(isolated_db, tmp_path):
    """Skill auto-writer writes a SKILL.md package under the project's
    .claude/skills/<name>/ and registers it via add_project_skill."""
    _seed_project_with_local_path("proj-skill-a", tmp_path)
    _seed_execution(
        "exec-skill",
        _make_assistant_stream(
            "I learned that to spin up the dev server you must run "
            "`just dev-backend` and `just dev-frontend` in separate terminals.",
        ),
    )
    ids = _extract("exec-skill", "proj-skill-a")
    skill_tk = next(
        repo.get(i) for i in ids if (repo.get(i) or {}).get("suggested_target") == "skill"
    )

    result = extractor.apply_takeaway(skill_tk["id"])
    assert result["applied"] is True
    assert result["target"] == "skill"

    # SKILL.md exists under .claude/skills/.agented-takeaways/ — the
    # dedicated subdir keeps auto-generated takeaway skills separable
    # from operator-curated ones (single gitignore line).
    skill_root = tmp_path / ".claude" / "skills" / ".agented-takeaways"
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
    isolated_db,
    monkeypatch,
    tmp_path,
):
    """Project with no local_path → skill lands under
    ``~/.claude/skills/.agented-takeaways/<project_id>/`` (sandboxed
    via HOME)."""
    monkeypatch.setenv("HOME", str(tmp_path))
    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO projects (id, name) VALUES (?, 'Test')",
            ("proj-skill-noloc",),
        )
        conn.commit()
    _seed_execution(
        "exec-skill-noloc",
        _make_assistant_stream(
            "I learned that the deploy script must be run with sudo because it writes to /etc.",
        ),
    )
    ids = _extract("exec-skill-noloc", "proj-skill-noloc")
    skill_tk = next(
        repo.get(i) for i in ids if (repo.get(i) or {}).get("suggested_target") == "skill"
    )
    result = extractor.apply_takeaway(skill_tk["id"])
    assert result["applied"] is True

    expected_root = tmp_path / ".claude" / "skills" / ".agented-takeaways" / "proj-skill-noloc"
    skill_dirs = list(expected_root.iterdir())
    assert skill_dirs
    assert (skill_dirs[0] / "SKILL.md").is_file()


def test_apply_skill_without_project_id_fails(isolated_db):
    """A skill takeaway with no project_id can't be materialized — no
    target directory to write to."""
    # Insert directly (bypass extractor) with project_id=None.
    [tk_id] = repo.insert_many(
        [
            {
                "session_kind": "trigger_execution",
                "session_id": "exec-orphan",
                "project_id": None,
                "kind": "discovered_procedure",
                "content": "Some procedure",
                "confidence": 0.7,
                "suggested_target": "skill",
                "suggested_payload": {"title": "orphan-skill", "recipe": "do X"},
                "extractor_version": "heuristic-test",
            }
        ]
    )
    result = extractor.apply_takeaway(tk_id)
    assert result["applied"] is False


# ---------- claude_md auto-writer -------------------------------------------


def _plant_claude_md_takeaway(
    project_id: str,
    content: str = "Use the existing test fixtures instead of inventing new ones.",
) -> str:
    """Insert a claude_md-targeted takeaway directly (extractor doesn't
    surface claude_md from heuristic patterns)."""
    [tk_id] = repo.insert_many(
        [
            {
                "session_kind": "trigger_execution",
                "session_id": f"exec-cm-{project_id}",
                "project_id": project_id,
                "kind": "user_preference",
                "content": content,
                "confidence": 0.9,
                "suggested_target": "claude_md",
                "suggested_payload": {},
                "extractor_version": "test-claude-md",
            }
        ]
    )
    return tk_id


def test_apply_claude_md_appends_managed_section_preserving_user_content(
    isolated_db,
    tmp_path,
):
    """An existing CLAUDE.md gets a new marker-bracketed section appended;
    operator-authored content stays untouched."""
    _seed_project_with_local_path("proj-cm-a", tmp_path)
    cm = tmp_path / "CLAUDE.md"
    cm.write_text("# My Project\n\nOperator-authored content stays here.\n")

    tk_id = _plant_claude_md_takeaway("proj-cm-a")
    result = extractor.apply_takeaway(tk_id)
    assert result["applied"] is True
    assert result["target"] == "claude_md"

    body = cm.read_text()
    # Original content survives verbatim.
    assert "# My Project" in body
    assert "Operator-authored content stays here." in body
    # Managed section landed AFTER it.
    assert "<!-- Agented Takeaways: project proj-cm-a" in body
    assert "<!-- End Agented Takeaways -->" in body
    # Takeaway bullet present with id marker.
    assert f"tk:{tk_id}" in body
    assert "test fixtures" in body
    # The two regions are in the right order.
    assert body.index("Operator-authored") < body.index("Agented Takeaways")


def test_apply_claude_md_creates_file_when_missing(isolated_db, tmp_path):
    _seed_project_with_local_path("proj-cm-b", tmp_path)
    cm = tmp_path / "CLAUDE.md"
    assert not cm.exists()

    tk_id = _plant_claude_md_takeaway("proj-cm-b")
    result = extractor.apply_takeaway(tk_id)
    assert result["applied"] is True
    assert cm.is_file()
    body = cm.read_text()
    assert "Agented Takeaways: project proj-cm-b" in body
    assert f"tk:{tk_id}" in body


def test_apply_claude_md_is_idempotent_on_reapply(isolated_db, tmp_path):
    """A second apply of the same takeaway must not double-write the bullet."""
    _seed_project_with_local_path("proj-cm-c", tmp_path)
    tk_id = _plant_claude_md_takeaway("proj-cm-c")
    extractor.apply_takeaway(tk_id)

    # Force-reset the applied flag so we can re-run apply through the
    # public entry point.
    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute(
            "UPDATE session_takeaways SET applied = 0, applied_at = NULL WHERE id = ?",
            (tk_id,),
        )
        conn.commit()

    extractor.apply_takeaway(tk_id)
    body = (tmp_path / "CLAUDE.md").read_text()
    # Bullet appears exactly once.
    assert body.count(f"tk:{tk_id}") == 1


def test_apply_claude_md_multiple_takeaways_share_one_section(
    isolated_db,
    tmp_path,
):
    """Multiple takeaways for the same project end up as bullets inside
    the SAME marker-bracketed section, not duplicated section blocks."""
    _seed_project_with_local_path("proj-cm-d", tmp_path)
    tk1 = _plant_claude_md_takeaway("proj-cm-d", content="prefer pytest")
    tk2 = _plant_claude_md_takeaway("proj-cm-d", content="never edit migrations")
    extractor.apply_takeaway(tk1)
    extractor.apply_takeaway(tk2)

    body = (tmp_path / "CLAUDE.md").read_text()
    assert body.count("<!-- Agented Takeaways: project proj-cm-d") == 1
    assert body.count("<!-- End Agented Takeaways -->") == 1
    assert f"tk:{tk1}" in body
    assert f"tk:{tk2}" in body


def test_apply_claude_md_without_project_id_fails(isolated_db):
    """No project_id → no target file path. Returns failed without writing."""
    [tk_id] = repo.insert_many(
        [
            {
                "session_kind": "trigger_execution",
                "session_id": "exec-cm-orphan",
                "project_id": None,
                "kind": "user_preference",
                "content": "something",
                "confidence": 0.9,
                "suggested_target": "claude_md",
                "suggested_payload": {},
                "extractor_version": "test",
            }
        ]
    )
    result = extractor.apply_takeaway(tk_id)
    assert result["applied"] is False


def test_apply_claude_md_falls_back_to_user_dir(
    isolated_db,
    monkeypatch,
    tmp_path,
):
    """Project with no local_path → writes to ``$HOME/.claude/CLAUDE.md``."""
    monkeypatch.setenv("HOME", str(tmp_path))
    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO projects (id, name) VALUES (?, 'Test')",
            ("proj-cm-noloc",),
        )
        conn.commit()
    tk_id = _plant_claude_md_takeaway("proj-cm-noloc")
    result = extractor.apply_takeaway(tk_id)
    assert result["applied"] is True

    cm = tmp_path / ".claude" / "CLAUDE.md"
    assert cm.is_file()
    body = cm.read_text()
    assert "Agented Takeaways: project proj-cm-noloc" in body


# ---------- LLM extraction --------------------------------------------------


def _long_subtle_stream() -> str:
    """A transcript with NO heuristic-matching phrases — only the LLM
    should surface anything. Long enough to clear the min-bytes gate."""
    filler = "Analysing the codebase. " * 80  # ~2KB filler
    return _make_assistant_stream(
        filler + " Note for context: the project's CI uses pytest-xdist "
        "and we should batch slow tests with the @pytest.mark.slow marker.",
    )


def test_llm_explicit_disable_skips_codex(isolated_db, monkeypatch):
    """Setting ``AGENTED_TAKEAWAY_LLM=0`` disables the LLM path. The
    default is ON (flipped 2026-05-25 after dogfood); this test locks
    the opt-out so CI / tests that don't want Codex calls can disable
    it explicitly."""
    monkeypatch.setenv("AGENTED_TAKEAWAY_LLM", "0")
    _seed_execution("exec-llm-off", _long_subtle_stream())

    with patch.object(
        extractor,
        "_run_llm_for_extraction",
    ) as mock_codex:
        _extract("exec-llm-off", "proj-tk-llm-off")
    mock_codex.assert_not_called()


def test_llm_enabled_with_short_transcript_skips_codex(isolated_db, monkeypatch):
    """Short transcripts don't justify the LLM cost — heuristic-only."""
    monkeypatch.setenv("AGENTED_TAKEAWAY_LLM", "1")
    _seed_execution("exec-llm-short", _make_assistant_stream("brief"))

    with patch.object(
        extractor,
        "_run_llm_for_extraction",
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
        extractor,
        "_run_llm_for_extraction",
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
        + json.dumps(
            [
                {
                    "kind": "domain_fact",
                    "content": "x is at /path/to/x",
                    "confidence": 0.7,
                    "suggested_target": "knowledge_graph",
                    "rationale": "explicit reference",
                }
            ]
        )
        + "\n\n(end of output)\n"
    )
    with patch.object(
        extractor,
        "_run_llm_for_extraction",
        return_value=noisy,
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
        extractor,
        "_run_llm_for_extraction",
        _exploding,
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
        extractor,
        "_run_llm_for_extraction",
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
    overlap = json.dumps(
        [
            {
                "kind": "user_preference",
                "content": "flake8 over pylint",
                "confidence": 0.8,
                "suggested_target": "memory",
                "rationale": "explicit preference statement",
            }
        ]
    )
    with patch.object(
        extractor,
        "_run_llm_for_extraction",
        return_value=overlap,
    ):
        ids = _extract("exec-llm-dedup", "proj-tk-llm-dedup")

    rows = [r for r in (repo.get(i) for i in ids) if r is not None]
    flake8_rows = [r for r in rows if "flake8" in r["content"].lower()]
    # Heuristic wins ties (cheaper, deterministic).
    assert len(flake8_rows) == 1
    assert flake8_rows[0]["extractor_version"].startswith("heuristic")


# ---------- constraint pattern: dogfood regressions ------------------------
#
# These tests lock the dogfood findings from running the extractor against
# the live ``agented.db``. The original constraint regex captured non-greedy
# up to the first word boundary, producing junk like "browse the" (10 chars)
# instead of the full claim, and the "need to" / "required to" triggers
# matched agent-intent narrative.


def test_constraint_captures_full_claim_not_fragment(isolated_db):
    """Real example from the dogfood: ``I can't browse the web — I don't
    have web search or internet access in this environment``. The full
    claim should land as a single takeaway, not the 10-char fragment
    "browse the"."""
    _seed_execution(
        "exec-c1",
        _make_assistant_stream(
            "I can't browse the web - I don't have web search or internet "
            "access in this environment.",
        ),
    )
    _extract("exec-c1", "proj-c1")
    constraints = [r for r in repo.list_for_project("proj-c1") if r["kind"] == "constraint"]
    assert constraints, "expected at least one constraint"
    # The full sentence after "can't" should be in the content — not a
    # tiny word-boundary fragment.
    matched = [c for c in constraints if "browse the web" in c["content"]]
    assert matched, f"got: {[c['content'] for c in constraints]}"
    # And specifically NOT just the 10-char fragment.
    assert all(len(c["content"]) > 15 for c in constraints)


def test_constraint_skips_intent_narrative(isolated_db):
    """Real example from the dogfood: ``I need to see exactly how those
    branches are structured`` shouldn't be a constraint — it's agent
    intent narrative, not an environmental block. Achieved by dropping
    ``need to`` from the trigger verb set."""
    _seed_execution(
        "exec-c2",
        _make_assistant_stream(
            "I need to see exactly how those branches are structured in the template.",
            "I'll need to consider whether the parent re-renders matter.",
        ),
    )
    _extract("exec-c2", "proj-c2")
    constraints = [r for r in repo.list_for_project("proj-c2") if r["kind"] == "constraint"]
    assert constraints == [], f"intent narrative leaked: {[c['content'] for c in constraints]}"


def test_truncate_slug_avoids_mid_token_and_trailing_dash():
    """Dogfood regression: rule + skill names landed with trailing
    dashes (``...research-``) or mid-token cuts (``...into-m``) when
    ``_slugify(...)[:N]`` ran without word-boundary awareness."""
    from app.services.harness_takeaway_extractor import _truncate_slug

    # Trailing dash case: 50-char window ending right after a dash.
    long_slug = "when-a-user-requests-deep-web-competitor-research-check-deferred"
    out = _truncate_slug(long_slug, 50)
    assert not out.endswith("-")
    assert len(out) <= 50
    # Should cut at a word boundary, not mid-token.
    # The 50th char of ``when-a-user-requests-deep-web-competitor-research-``
    # is the trailing dash; we want to keep through ``...research`` (49 chars).
    assert out == "when-a-user-requests-deep-web-competitor-research"

    # Mid-token case: 60-char window cuts ``multi`` to ``m``.
    slug = "for-agented-competitor-research-segment-the-landscape-into-multi-harness"
    out = _truncate_slug(slug, 60)
    assert not out.endswith("-")
    # Should NOT contain the truncated ``into-m`` token.
    assert not out.endswith("into-m")
    # Should fall back to a clean boundary.
    assert "into" in out


def test_truncate_slug_short_slug_passes_through():
    from app.services.harness_takeaway_extractor import _truncate_slug

    assert _truncate_slug("short-slug", 60) == "short-slug"


def test_file_mention_pattern_surfaces_backticked_paths(isolated_db):
    """English-trigger-free domain_fact detector. Real conversations
    inline backticked paths without "lives at" / "located in", and the
    dogfood pass against agented.db showed the English-keyed pattern
    missed 124 of these mentions across 4 sessions. The new pattern
    should surface them as domain_fact takeaways keyed on the path."""
    _seed_execution(
        "exec-fm",
        _make_assistant_stream(
            "The fix is in `frontend/src/webmcp/generic-tools.ts` and the "
            "regression test is in `frontend/src/webmcp/__tests__/generic-tools.test.ts`.",
        ),
    )
    _extract("exec-fm", "proj-fm")
    facts = [r for r in repo.list_for_project("proj-fm") if r["kind"] == "domain_fact"]
    paths = {(r.get("evidence") or {}).get("path") for r in facts}
    assert "frontend/src/webmcp/generic-tools.ts" in paths
    assert "frontend/src/webmcp/__tests__/generic-tools.test.ts" in paths
    # All are knowledge_graph-targeted at 0.40 confidence (review-only).
    assert all(r["suggested_target"] == "knowledge_graph" for r in facts)
    assert all(r["confidence"] < 0.85 for r in facts)


def test_file_mention_pattern_dedupes_repeated_path(isolated_db):
    """A chatty conversation mentioning the same path 8 times shouldn't
    produce 8 takeaways. Dedup is keyed on the canonical path."""
    _seed_execution(
        "exec-fm-dup",
        _make_assistant_stream(
            "Editing `src/App.vue`. Then again in `src/App.vue`. And once "
            "more in `src/App.vue`. Finally `src/App.vue` works.",
        ),
    )
    _extract("exec-fm-dup", "proj-fm-dup")
    facts = [
        r
        for r in repo.list_for_project("proj-fm-dup")
        if r["kind"] == "domain_fact" and (r.get("evidence") or {}).get("path") == "src/App.vue"
    ]
    assert len(facts) == 1


def test_file_mention_pattern_skips_version_numbers(isolated_db):
    """Backticked tokens like ``1.0`` and ``3.11.2`` shouldn't be treated
    as filepaths."""
    _seed_execution(
        "exec-fm-ver",
        _make_assistant_stream(
            "Bumped to `3.11.2` and updated the schema version to `1.0`.",
        ),
    )
    _extract("exec-fm-ver", "proj-fm-ver")
    facts = [r for r in repo.list_for_project("proj-fm-ver") if r["kind"] == "domain_fact"]
    assert facts == []


def test_constraint_still_catches_environment_block(isolated_db):
    """Real example: ``cannot reach the server (ERR-NETWORK)`` IS an
    environmental constraint and should still surface after the
    tightening."""
    _seed_execution(
        "exec-c3",
        _make_assistant_stream(
            "The proxy cannot reach the server at all (sidecar :20001 "
            "restarted, network blip, CORS preflight denied).",
        ),
    )
    _extract("exec-c3", "proj-c3")
    constraints = [r for r in repo.list_for_project("proj-c3") if r["kind"] == "constraint"]
    assert constraints
    assert any("reach the server" in c["content"] for c in constraints)
