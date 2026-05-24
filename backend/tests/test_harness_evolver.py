"""Tests for the Forge-pivoted, project-scoped evolution loop."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.db import harness_evolution as evolution_repo
from app.db import hooks as hooks_repo
from app.db import project_forge_bindings as bindings_repo
from app.db import rules as rules_repo
from app.db import commands as commands_repo
from app.db.connection import get_connection
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
    patch = EvolutionPatch(entries=[
        PatchEntry(op="create", kind="rule", name="r", payload={
            "description": "Quote spaced cols.",
        }),
        PatchEntry(op="create", kind="hook", name="h", payload={
            "event": "PreToolUse", "content": "#!/bin/sh\nexit 0",
        }),
        PatchEntry(op="create", kind="command", name="c", payload={
            "content": "Do the thing.",
        }),
        PatchEntry(op="create", kind="mcp_server", name="m", payload={
            "command": "node",
        }),
    ])
    assert validate_patch(patch) == []


def test_validate_rejects_unknown_kind():
    patch = EvolutionPatch(entries=[
        PatchEntry(op="create", kind="banana", name="x", payload={}),
    ])
    problems = validate_patch(patch)
    assert problems and "not an auto-evolvable" in problems[0]


def test_validate_rejects_skill_create():
    """Skill create/update isn't auto-applied — Codex must propose those
    in NOTES.md, not as patch entries."""
    patch = EvolutionPatch(entries=[
        PatchEntry(op="create", kind="skill", name="s",
                   payload={"description": "x"}),
    ])
    problems = validate_patch(patch)
    assert problems and "not an auto-evolvable" in problems[0]


def test_validate_hook_requires_known_event():
    patch = EvolutionPatch(entries=[
        PatchEntry(op="create", kind="hook", name="h", payload={
            "event": "MadeUpEvent", "content": "echo hi",
        }),
    ])
    problems = validate_patch(patch)
    assert problems and "unknown hook event" in problems[0]


def test_validate_hook_requires_content():
    patch = EvolutionPatch(entries=[
        PatchEntry(op="create", kind="hook", name="h", payload={
            "event": "PreToolUse",
        }),
    ])
    problems = validate_patch(patch)
    assert any("hook.content is required" in p for p in problems)


def test_validate_mcp_server_requires_command_or_url():
    patch = EvolutionPatch(entries=[
        PatchEntry(op="create", kind="mcp_server", name="m", payload={
            "description": "missing transport",
        }),
    ])
    problems = validate_patch(patch)
    assert any("mcp_server needs command" in p for p in problems)


def test_validate_update_requires_existing_asset_id():
    patch = EvolutionPatch(entries=[
        PatchEntry(op="update", kind="rule", name="r", payload={
            "description": "x",
        }),
    ])
    problems = validate_patch(patch)
    assert any("missing existing_asset_id" in p for p in problems)


# --------------------------------------------------------------------------
# apply_patch — calls into the Forge repos + binds new assets to project
# --------------------------------------------------------------------------

def test_apply_create_rule_persists_and_binds(isolated_db):
    _seed_project("proj-test-a")
    patch = EvolutionPatch(entries=[
        PatchEntry(op="create", kind="rule", name="quote-cols", payload={
            "description": "Quote spaced cols.",
            "rule_type": "validation",
        }),
    ])
    applied = apply_patch(patch, "proj-test-a")
    assert len(applied) == 1
    assert applied[0]["kind"] == "rule"
    assert applied[0]["op"] == "create"
    new_id = applied[0]["asset_id"]

    persisted = rules_repo.get_rule(new_id)
    assert persisted is not None
    assert persisted["name"] == "quote-cols"
    assert persisted["project_id"] == "proj-test-a"

    bindings = bindings_repo.list_bindings("proj-test-a")
    assert any(
        b["kind"] == "rule" and str(b["asset_id"]) == str(new_id)
        for b in bindings
    )


def test_apply_create_hook_persists_and_binds(isolated_db):
    _seed_project("proj-test-h")
    patch = EvolutionPatch(entries=[
        PatchEntry(op="create", kind="hook", name="block-rm", payload={
            "event": "PreToolUse",
            "content": "#!/bin/sh\necho '{\"decision\":\"block\"}'",
        }),
    ])
    applied = apply_patch(patch, "proj-test-h")
    assert applied[0]["kind"] == "hook"

    persisted = hooks_repo.get_hook(applied[0]["asset_id"])
    assert persisted["event"] == "PreToolUse"
    assert persisted["project_id"] == "proj-test-h"


def test_apply_update_modifies_existing(isolated_db):
    _seed_project("proj-update")
    rid = rules_repo.create_rule(
        name="r", description="v1", project_id="proj-update",
    )
    patch = EvolutionPatch(entries=[
        PatchEntry(op="update", kind="rule", name="r",
                   existing_asset_id=rid, payload={
                       "description": "v2",
                       "rule_type": "validation",
                   }),
    ])
    apply_patch(patch, "proj-update")
    assert rules_repo.get_rule(rid)["description"] == "v2"


def test_apply_delete_removes(isolated_db):
    _seed_project("proj-del")
    cid = commands_repo.create_command(
        name="c", content="hi", project_id="proj-del",
    )
    patch = EvolutionPatch(entries=[
        PatchEntry(op="delete", kind="command", name="c",
                   existing_asset_id=cid),
    ])
    apply_patch(patch, "proj-del")
    assert commands_repo.get_command(cid) is None


# --------------------------------------------------------------------------
# parse_patch — diff Forge directories before/after Codex edits
# --------------------------------------------------------------------------

def test_parse_patch_classifies_create_update_delete(tmp_path, isolated_db):
    # Seed: one rule + one hook bound to the project.
    _seed_project("proj-parse")
    rid = rules_repo.create_rule(
        name="existing-rule", description="keep me",
        project_id="proj-parse",
    )
    bindings_repo.add_binding("proj-parse", "rule", str(rid))
    hid = hooks_repo.create_hook(
        name="existing-hook", event="PreToolUse", content="echo hi",
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

    (scratch / "forge" / "commands" / "new-cmd.json").write_text(json.dumps({
        "id": None,
        "name": "new-cmd",
        "payload": {"content": "do the thing"},
    }))

    patch = parse_patch(scratch, inputs)
    ops = sorted((e.op, e.kind, e.name) for e in patch.entries)
    assert ops == [
        ("create", "command", "new-cmd"),
        ("delete", "hook", "existing-hook"),
        ("update", "rule", "existing-rule"),
    ]


# --------------------------------------------------------------------------
# Full round with Codex mocked
# --------------------------------------------------------------------------

@pytest.fixture
def mock_codex():
    """Patch Codex; tests configure what files the fake Codex creates / edits."""
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

    with patch.object(evolver, "_run_codex_in_workspace", _fake):
        def _configure(*, files=None, deletes=None, notes=""):
            edits["files"] = files or {}
            edits["deletes"] = deletes or []
            edits["notes"] = notes
        yield _configure


def test_run_evolution_round_applies_codex_edits(isolated_db, mock_codex):
    _seed_project("proj-run")
    mock_codex(files={
        "forge/rules/new-rule.json": json.dumps({
            "id": None, "name": "new-rule",
            "payload": {"description": "Codex added me"},
        }),
    }, notes="Found 3 H3 mismatches — added a rule.")

    result = evolver.run_evolution_round("proj-run")
    assert result.status == "applied"
    assert len(result.applied_asset_ids) == 1
    assert result.applied_asset_ids[0]["kind"] == "rule"
    assert "Found 3 H3" in result.notes


def test_run_evolution_round_rejects_invalid_patch(isolated_db, mock_codex):
    """Codex emits a hook without content → validation fails, no Forge writes."""
    _seed_project("proj-rej")
    mock_codex(files={
        "forge/hooks/broken.json": json.dumps({
            "id": None, "name": "broken",
            "payload": {"event": "PreToolUse"},
        }),
    })
    result = evolver.run_evolution_round("proj-rej")
    assert result.status == "failed"
    assert "patch validation failed" in (result.error or "")
    assert hooks_repo.get_hooks_by_project("proj-rej") == []


def test_run_evolution_round_dry_run_holds_for_approval(isolated_db, mock_codex):
    _seed_project("proj-dry")
    mock_codex(files={
        "forge/rules/dr.json": json.dumps({
            "id": None, "name": "dr",
            "payload": {"description": "dr"},
        }),
    })
    result = evolver.run_evolution_round("proj-dry", dry_run=True)
    assert result.status == "awaiting_approval"
    # No rule was written yet.
    assert rules_repo.get_rules_by_project("proj-dry") == []

    promoted = evolver.apply_dry_run_round(result.round_id)
    assert promoted.status == "applied"
    assert rules_repo.get_rules_by_project("proj-dry")


def test_run_evolution_round_abort_drops_pending_patch(
    isolated_db, mock_codex,
):
    _seed_project("proj-abort")
    mock_codex(files={
        "forge/rules/x.json": json.dumps({
            "id": None, "name": "x", "payload": {"description": "x"},
        }),
    })
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
