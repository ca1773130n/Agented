"""Tests for the Forge-pivoted, project-scoped evolution loop."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.db import commands as commands_repo
from app.db import hooks as hooks_repo
from app.db import project_forge_bindings as bindings_repo
from app.db import rules as rules_repo
from app.db.connection import get_connection
from app.models.harness_evolution import CheckResult, EvalVerdict
from app.services import harness_evolver as evolver
from app.services.harness_evolver import (
    EvolutionPatch,
    PatchEntry,
    apply_patch,
    build_workspace,
    gather_inputs,
    parse_patch,
    validate_patch,
)


def _seed_project(project_id: str, name: str = "Test Project") -> None:
    """Insert a projects row so child rows (rules/hooks/commands) can hold a
    FK reference to it. Most Agented tests rely on the ``isolated_db`` fixture
    which doesn't auto-seed projects."""
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO projects (id, name) VALUES (?, ?)",
            (project_id, name),
        )
        conn.commit()


# --------------------------------------------------------------------------
# validate_patch — kind-specific shape checks
# --------------------------------------------------------------------------


def test_validate_accepts_clean_rule_hook_command_mcp():
    patch = EvolutionPatch(
        entries=[
            PatchEntry(
                op="create",
                kind="rule",
                name="r",
                payload={
                    "description": "Quote spaced cols.",
                },
            ),
            PatchEntry(
                op="create",
                kind="hook",
                name="h",
                payload={
                    "event": "PreToolUse",
                    "content": "#!/bin/sh\nexit 0",
                },
            ),
            PatchEntry(
                op="create",
                kind="command",
                name="c",
                payload={
                    "content": "Do the thing.",
                },
            ),
            PatchEntry(
                op="create",
                kind="mcp_server",
                name="m",
                payload={
                    "command": "node",
                },
            ),
        ]
    )
    assert validate_patch(patch) == []


def test_validate_rejects_unknown_kind():
    patch = EvolutionPatch(
        entries=[
            PatchEntry(op="create", kind="banana", name="x", payload={}),
        ]
    )
    problems = validate_patch(patch)
    assert problems and "not an auto-evolvable" in problems[0]


def test_validate_accepts_skill_create():
    """Skill create is now auto-evolvable — validate_patch must not reject it."""
    patch = EvolutionPatch(
        entries=[
            PatchEntry(op="create", kind="skill", name="s", payload={"description": "x"}),
        ]
    )
    problems = validate_patch(patch)
    assert not problems


def test_validate_hook_requires_known_event():
    patch = EvolutionPatch(
        entries=[
            PatchEntry(
                op="create",
                kind="hook",
                name="h",
                payload={
                    "event": "MadeUpEvent",
                    "content": "echo hi",
                },
            ),
        ]
    )
    problems = validate_patch(patch)
    assert problems and "unknown hook event" in problems[0]


def test_validate_hook_requires_content():
    patch = EvolutionPatch(
        entries=[
            PatchEntry(
                op="create",
                kind="hook",
                name="h",
                payload={
                    "event": "PreToolUse",
                },
            ),
        ]
    )
    problems = validate_patch(patch)
    assert any("hook.content is required" in p for p in problems)


def test_validate_mcp_server_requires_command_or_url():
    patch = EvolutionPatch(
        entries=[
            PatchEntry(
                op="create",
                kind="mcp_server",
                name="m",
                payload={
                    "description": "missing transport",
                },
            ),
        ]
    )
    problems = validate_patch(patch)
    assert any("mcp_server needs command" in p for p in problems)


def test_validate_update_requires_existing_asset_id():
    patch = EvolutionPatch(
        entries=[
            PatchEntry(
                op="update",
                kind="rule",
                name="r",
                payload={
                    "description": "x",
                },
            ),
        ]
    )
    problems = validate_patch(patch)
    assert any("missing existing_asset_id" in p for p in problems)


# --------------------------------------------------------------------------
# apply_patch — calls into the Forge repos + binds new assets to project
# --------------------------------------------------------------------------


def test_apply_create_rule_persists_and_binds(isolated_db):
    _seed_project("proj-test-a")
    patch = EvolutionPatch(
        entries=[
            PatchEntry(
                op="create",
                kind="rule",
                name="quote-cols",
                payload={
                    "description": "Quote spaced cols.",
                    "rule_type": "validation",
                },
            ),
        ]
    )
    applied, _journal = apply_patch(patch, "proj-test-a")
    assert len(applied) == 1
    assert applied[0]["kind"] == "rule"
    assert applied[0]["op"] == "create"
    new_id = applied[0]["asset_id"]

    persisted = rules_repo.get_rule(new_id)
    assert persisted is not None
    assert persisted["name"] == "quote-cols"
    assert persisted["project_id"] == "proj-test-a"

    bindings = bindings_repo.list_bindings("proj-test-a")
    assert any(b["kind"] == "rule" and str(b["asset_id"]) == str(new_id) for b in bindings)


def test_apply_create_hook_persists_and_binds(isolated_db):
    _seed_project("proj-test-h")
    patch = EvolutionPatch(
        entries=[
            PatchEntry(
                op="create",
                kind="hook",
                name="block-rm",
                payload={
                    "event": "PreToolUse",
                    "content": '#!/bin/sh\necho \'{"decision":"block"}\'',
                },
            ),
        ]
    )
    applied, _journal = apply_patch(patch, "proj-test-h")
    assert applied[0]["kind"] == "hook"

    persisted = hooks_repo.get_hook(applied[0]["asset_id"])
    assert persisted["event"] == "PreToolUse"
    assert persisted["project_id"] == "proj-test-h"


def test_apply_update_modifies_existing(isolated_db):
    _seed_project("proj-update")
    rid = rules_repo.create_rule(
        name="r",
        description="v1",
        project_id="proj-update",
    )
    patch = EvolutionPatch(
        entries=[
            PatchEntry(
                op="update",
                kind="rule",
                name="r",
                existing_asset_id=rid,
                payload={
                    "description": "v2",
                    "rule_type": "validation",
                },
            ),
        ]
    )
    apply_patch(patch, "proj-update")
    assert rules_repo.get_rule(rid)["description"] == "v2"


def test_apply_delete_removes(isolated_db):
    _seed_project("proj-del")
    cid = commands_repo.create_command(
        name="c",
        content="hi",
        project_id="proj-del",
    )
    patch = EvolutionPatch(
        entries=[
            PatchEntry(op="delete", kind="command", name="c", existing_asset_id=cid),
        ]
    )
    apply_patch(patch, "proj-del")
    assert commands_repo.get_command(cid) is None


# --------------------------------------------------------------------------
# parse_patch — diff Forge directories before/after Codex edits
# --------------------------------------------------------------------------


def test_parse_patch_classifies_create_update_delete(tmp_path, isolated_db):
    # Seed: one rule + one hook bound to the project.
    _seed_project("proj-parse")
    rid = rules_repo.create_rule(
        name="existing-rule",
        description="keep me",
        project_id="proj-parse",
    )
    bindings_repo.add_binding("proj-parse", "rule", str(rid))
    hid = hooks_repo.create_hook(
        name="existing-hook",
        event="PreToolUse",
        content="echo hi",
        project_id="proj-parse",
    )
    bindings_repo.add_binding("proj-parse", "hook", str(hid))

    inputs = gather_inputs("proj-parse", limit=5)
    scratch = build_workspace(inputs, tmp_path / "ws")

    # Simulate Codex edits: modify the rule, delete the hook, add a new command.
    rule_path = scratch / "forge" / "rules" / "existing-rule.json"
    rule_doc = json.loads(rule_path.read_text())
    rule_doc["payload"]["description"] = "now v2"
    rule_path.write_text(json.dumps(rule_doc))

    (scratch / "forge" / "hooks" / "existing-hook.json").unlink()

    (scratch / "forge" / "commands" / "new-cmd.json").write_text(
        json.dumps(
            {
                "id": None,
                "name": "new-cmd",
                "payload": {"content": "do the thing"},
            }
        )
    )

    patch = parse_patch(scratch, inputs)
    ops = sorted((e.op, e.kind, e.name) for e in patch.entries)
    assert ops == [
        ("create", "command", "new-cmd"),
        ("delete", "hook", "existing-hook"),
        ("update", "rule", "existing-rule"),
    ]


# --------------------------------------------------------------------------
# Takeaways → workspace (positive-learning evidence stream)
# --------------------------------------------------------------------------


def test_build_workspace_writes_takeaways_to_disk(tmp_path, isolated_db):
    """Each gathered takeaway lands as a JSON file under ``takeaways/``
    so Codex can read it alongside trajectories. The projection contains
    the operator-meaningful fields (kind, content, confidence,
    suggested_target) but excludes DB-internal flags."""
    from app.db import harness_takeaways as takeaways_repo

    _seed_project("proj-tk-evol")
    [tk1, tk2] = takeaways_repo.insert_many(
        [
            {
                "session_kind": "trigger_execution",
                "session_id": "exec-tk-1",
                "project_id": "proj-tk-evol",
                "kind": "discovered_procedure",
                "content": "Run migrations with `just db-migrate` before each deploy.",
                "confidence": 0.85,
                "suggested_target": "skill",
                "suggested_payload": {"title": "deploy-flow"},
                "extractor_version": "test",
            },
            {
                "session_kind": "team_session",
                "session_id": "team-exec-tk-1",
                "project_id": "proj-tk-evol",
                "kind": "user_preference",
                "content": "Prefer pytest over unittest for new test files.",
                "confidence": 0.9,
                "suggested_target": "rule",
                "suggested_payload": {},
                "extractor_version": "test",
            },
        ]
    )

    inputs = gather_inputs("proj-tk-evol", limit=10)
    assert len(inputs["takeaways"]) == 2

    scratch = build_workspace(inputs, tmp_path / "ws")
    tk_dir = scratch / "takeaways"
    assert tk_dir.is_dir()
    files = sorted(tk_dir.iterdir())
    assert len(files) == 2

    bodies = {f.name: json.loads(f.read_text()) for f in files}
    by_id = {b["id"]: b for b in bodies.values()}
    assert tk1 in by_id and tk2 in by_id
    # Operator-meaningful fields preserved.
    assert by_id[tk1]["kind"] == "discovered_procedure"
    assert by_id[tk1]["suggested_target"] == "skill"
    assert by_id[tk2]["content"].startswith("Prefer pytest")
    assert by_id[tk2]["session_kind"] == "team_session"


def test_build_workspace_takeaway_dir_empty_when_no_takeaways(tmp_path, isolated_db):
    """No takeaways for the project → the directory is still created
    (so Codex's prompt instructions don't reference a missing path)
    but empty. Codex tolerates an empty evidence stream."""
    _seed_project("proj-tk-none")
    inputs = gather_inputs("proj-tk-none", limit=10)
    assert inputs["takeaways"] == []
    scratch = build_workspace(inputs, tmp_path / "ws")
    tk_dir = scratch / "takeaways"
    assert tk_dir.is_dir()
    assert list(tk_dir.iterdir()) == []


def test_build_workspace_prompt_references_takeaways(tmp_path, isolated_db):
    """The PROMPT.md + DESIGN_GUIDE.md materials must reference the
    takeaways/ directory so Codex actually looks at it. Regression
    guard: gather_inputs used to fill the inputs dict and the workspace
    builder used to create the empty directory — but neither the
    prompt nor the design guide pointed at it. (Fixed alongside the
    workspace write itself.)"""
    _seed_project("proj-tk-prompt")
    inputs = gather_inputs("proj-tk-prompt", limit=10)
    scratch = build_workspace(inputs, tmp_path / "ws")
    prompt = (scratch / "PROMPT.md").read_text()
    guide = (scratch / "DESIGN_GUIDE.md").read_text()
    assert "takeaways/" in prompt
    assert "takeaways/" in guide
    # And the prompt actually tells Codex how to weigh them.
    assert "positive" in prompt.lower() or "positive" in guide.lower()


# --------------------------------------------------------------------------
# Codex CLI invocation defaults
# --------------------------------------------------------------------------


def test_default_codex_cmd_includes_workspace_write_sandbox(monkeypatch):
    """Regression from the live-data dogfood: ``codex exec`` defaults
    to ``--sandbox read-only``, which silently rejects every file
    write the model attempts. The subprocess still exits 0, so the
    evolver sees an empty scratch_dir, parse_patch returns 0 entries,
    and the operator gets awaiting_approval with nothing to review.
    The fix is non-negotiable: the default CLI MUST include
    ``--sandbox workspace-write`` so Codex can write into the
    ephemeral scratch_dir."""
    monkeypatch.delenv("AGENTED_CODEX_CMD", raising=False)
    cmd = evolver._default_codex_cmd()
    assert "--sandbox" in cmd, f"missing --sandbox in {cmd}"
    sandbox_value = cmd[cmd.index("--sandbox") + 1]
    assert sandbox_value == "workspace-write", (
        f"sandbox must be 'workspace-write' (read-only would silently "
        f"reject writes); got {sandbox_value!r}"
    )
    # And --skip-git-repo-check is also load-bearing (scratch_dir
    # isn't a git repo); locking both together.
    assert "--skip-git-repo-check" in cmd


# --------------------------------------------------------------------------
# Full round with Codex mocked
# --------------------------------------------------------------------------


@pytest.fixture
def mock_codex():
    """Patch Codex; tests configure what files the fake Codex creates / edits.

    Also patches ``evaluate_patch`` to return a passing verdict so that the
    eval gate does not block any existing round tests — those tests are not
    about the gate and should not require a live eval environment.
    """
    edits = {"files": {}, "deletes": [], "notes": ""}

    def _fake(scratch_dir: Path, *, timeout: int = 600) -> None:
        for rel, content in edits["files"].items():
            target = scratch_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        for rel in edits["deletes"]:
            try:
                (scratch_dir / rel).unlink()
            except FileNotFoundError:
                pass
        if edits["notes"]:
            (scratch_dir / "NOTES.md").write_text(edits["notes"])

    _passing_verdict = EvalVerdict(
        passed=True, score=1.0, per_check=[CheckResult(name="static", passed=True, detail="ok")]
    )

    with (
        patch.object(evolver, "_run_codex_in_workspace", _fake),
        patch.object(evolver, "evaluate_patch", return_value=_passing_verdict),
    ):

        def _configure(*, files=None, deletes=None, notes=""):
            edits["files"] = files or {}
            edits["deletes"] = deletes or []
            edits["notes"] = notes

        yield _configure


def test_run_evolution_round_applies_codex_edits(isolated_db, mock_codex):
    _seed_project("proj-run")
    mock_codex(
        files={
            "forge/rules/new-rule.json": json.dumps(
                {
                    "id": None,
                    "name": "new-rule",
                    "payload": {"description": "Codex added me"},
                }
            ),
        },
        notes="Found 3 H3 mismatches — added a rule.",
    )

    result = evolver.run_evolution_round("proj-run")
    assert result.status == "applied"
    assert len(result.applied_asset_ids) == 1
    assert result.applied_asset_ids[0]["kind"] == "rule"
    assert "Found 3 H3" in result.notes


def test_run_evolution_round_rejects_invalid_patch(isolated_db, mock_codex):
    """Codex emits a hook without content → validation fails, no Forge writes."""
    _seed_project("proj-rej")
    mock_codex(
        files={
            "forge/hooks/broken.json": json.dumps(
                {
                    "id": None,
                    "name": "broken",
                    "payload": {"event": "PreToolUse"},
                }
            ),
        }
    )
    result = evolver.run_evolution_round("proj-rej")
    assert result.status == "failed"
    assert "patch validation failed" in (result.error or "")
    assert hooks_repo.get_hooks_by_project("proj-rej") == []


def test_run_evolution_round_dry_run_holds_for_approval(isolated_db, mock_codex):
    _seed_project("proj-dry")
    mock_codex(
        files={
            "forge/rules/dr.json": json.dumps(
                {
                    "id": None,
                    "name": "dr",
                    "payload": {"description": "dr"},
                }
            ),
        }
    )
    result = evolver.run_evolution_round("proj-dry", dry_run=True)
    assert result.status == "awaiting_approval"
    # No rule was written yet.
    assert rules_repo.get_rules_by_project("proj-dry") == []

    promoted = evolver.apply_dry_run_round(result.round_id)
    assert promoted.status == "applied"
    assert rules_repo.get_rules_by_project("proj-dry")


def test_run_evolution_round_abort_drops_pending_patch(
    isolated_db,
    mock_codex,
):
    _seed_project("proj-abort")
    mock_codex(
        files={
            "forge/rules/x.json": json.dumps(
                {
                    "id": None,
                    "name": "x",
                    "payload": {"description": "x"},
                }
            ),
        }
    )
    dr = evolver.run_evolution_round("proj-abort", dry_run=True)
    res = evolver.abort_dry_run_round(dr.round_id, reason="nope")
    assert res.status == "aborted"
    assert rules_repo.get_rules_by_project("proj-abort") == []


def test_rate_limit_aborts_burst_triggers(isolated_db, mock_codex):
    _seed_project("proj-rate")
    mock_codex(files={})
    first = evolver.run_evolution_round("proj-rate", dry_run=True)
    assert first.status == "awaiting_approval"
    second = evolver.run_evolution_round("proj-rate", dry_run=True)
    assert second.status == "aborted"
    assert "rate-limited" in (second.error or "")
    # force=True bypasses
    third = evolver.run_evolution_round("proj-rate", dry_run=True, force=True)
    assert third.status == "awaiting_approval"


def test_rate_limit_ignores_failed_rounds(isolated_db, mock_codex):
    """A failed round (e.g. Codex CLI errored before producing edits)
    must not block a retry — the operator should be able to fix the
    failure and try again immediately."""
    _seed_project("proj-retry")

    # First call: simulate Codex crash.
    def _crash(scratch_dir, *, timeout=600):
        raise RuntimeError("codex CLI exited 2: --auto not found")

    with patch.object(evolver, "_run_codex_in_workspace", _crash):
        first = evolver.run_evolution_round("proj-retry", dry_run=True)
    assert first.status == "failed"

    # Second call should NOT be rate-limited because the first round
    # never actually succeeded at running Codex.
    mock_codex(files={})
    second = evolver.run_evolution_round("proj-retry", dry_run=True)
    assert second.status == "awaiting_approval", second.error


def test_rate_limit_ignores_aborted_rounds(isolated_db, mock_codex):
    """An operator-aborted round shouldn't block a fresh attempt either."""
    _seed_project("proj-aborted-retry")
    mock_codex(files={})

    first = evolver.run_evolution_round("proj-aborted-retry", dry_run=True)
    assert first.status == "awaiting_approval"
    evolver.abort_dry_run_round(first.round_id, reason="changed my mind")

    second = evolver.run_evolution_round("proj-aborted-retry", dry_run=True)
    assert second.status == "awaiting_approval", second.error


def test_rate_limit_reaps_stale_running_round(isolated_db, mock_codex):
    """Regression from the live-data dogfood: a parent process killed
    mid-evolution leaves the round in ``status='running'`` forever.
    The rate limiter used to block all future runs on that project
    indefinitely. Fix: in-flight rounds older than the configurable
    max age (default 30 min) are silently reaped (marked failed) so
    subsequent runs can proceed."""
    from app.db import harness_evolution as evo_repo
    from app.db.connection import get_connection

    _seed_project("proj-reap")

    # Plant an old "running" round directly. ``start_round`` only
    # accepts ``project_id``; we set started_at via UPDATE.
    rid = evo_repo.start_round(
        project_id="proj-reap",
        input_window_since=None,
        input_window_until=None,
        input_execution_count=0,
        input_forge={},
        scratch_dir="/tmp/x",
    )
    evo_repo.mark_running(rid)
    with get_connection() as conn:
        # Backdate by 1 hour — well past the 30-min default threshold.
        conn.execute(
            "UPDATE harness_evolution_rounds "
            "SET started_at = datetime('now', '-1 hour') WHERE id = ?",
            (rid,),
        )
        conn.commit()

    # A new run should reap the stale round and proceed (don't get
    # blocked by the rate-limit in-flight check).
    mock_codex(files={})
    fresh = evolver.run_evolution_round("proj-reap", dry_run=True)
    assert fresh.status == "awaiting_approval", fresh.error

    # And the stale round is now marked failed with a reaper message.
    with get_connection() as conn:
        row = conn.execute(
            "SELECT status, error_message FROM harness_evolution_rounds WHERE id = ?",
            (rid,),
        ).fetchone()
    assert row["status"] == "failed"
    assert "reaped" in (row["error_message"] or "").lower()


def test_rate_limit_does_not_reap_fresh_in_flight_round(
    isolated_db,
    mock_codex,
):
    """An in-flight round STARTED RECENTLY should still block — the
    reaper must only fire on truly stale rounds, not interrupt a
    healthy concurrent attempt."""
    from app.db import harness_evolution as evo_repo

    _seed_project("proj-no-reap")

    rid = evo_repo.start_round(
        project_id="proj-no-reap",
        input_window_since=None,
        input_window_until=None,
        input_execution_count=0,
        input_forge={},
        scratch_dir="/tmp/y",
    )
    evo_repo.mark_running(rid)
    # started_at left at NOW (just now). Reaper threshold is 30 min,
    # so this should NOT be reaped.

    mock_codex(files={})
    blocked = evolver.run_evolution_round("proj-no-reap", dry_run=True)
    assert blocked.status == "aborted"
    assert "already" in (blocked.error or "")


def test_replay_samples_populate_real_trajectory_excerpt():
    """Loop 4: the eval-gate samples must carry the REAL session trajectory (via
    the annotator fetcher), not a hardcoded empty string."""
    from app.services import harness_evolver as he
    from app.services.harness_failure_annotator import SessionPayload

    payload = SessionPayload(
        text="user: do X\nassistant: [tool_error] boom rm failed with permission denied",
        backend_type="claude",
        project_id=None,
        outcome="failure",
    )
    inputs = {
        "trajectories": [
            {
                "session_kind": "trigger_execution",
                "session_id": "exec-1",
                "incidents": [{"kind": "h2_invalid_tool_call", "layer": "h2", "evidence": {}}],
            }
        ]
    }
    with patch.dict(
        "app.services.harness_failure_annotator._FETCHERS",
        {"trigger_execution": lambda sid: payload},
    ):
        samples = he._replay_samples_from_inputs(inputs)
    assert len(samples) == 1
    assert samples[0].trajectory_excerpt  # not the old hardcoded ""
    assert "boom rm failed" in samples[0].trajectory_excerpt


def test_replay_excerpt_empty_when_no_fetcher():
    """Best-effort: an unknown session kind yields "" (judge sees 'unavailable')."""
    from app.services import harness_evolver as he

    inputs = {
        "trajectories": [
            {
                "session_kind": "no_such_kind",
                "session_id": "s1",
                "incidents": [{"kind": "x", "layer": "h2", "evidence": {}}],
            }
        ]
    }
    samples = he._replay_samples_from_inputs(inputs)
    assert len(samples) == 1
    assert samples[0].trajectory_excerpt == ""
