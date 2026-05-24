"""Tests for the T3 evolution orchestrator + its building blocks."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.db import harness_evolution as evolution_repo
from app.db import harness_layers as layers_repo
from app.db import harness_snapshots as snapshots_repo
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


# --------------------------------------------------------------------------
# parse_patch — classification logic
# --------------------------------------------------------------------------

def test_parse_patch_classifies_create_supersede_disable():
    before = {
        "h2": [
            {"id": "hl-keep", "name": "keep", "payload": {"title": "k"}},
            {"id": "hl-gone", "name": "obsolete", "payload": {"title": "g"}},
            {"id": "hl-mod", "name": "modify", "payload": {"title": "old"}},
        ],
        "h3": [],
        "h4": [],
        "h5": [],
    }
    after = {
        "h2": [
            {"id": "hl-keep", "name": "keep", "payload": {"title": "k"}},
            {"id": "hl-mod", "name": "modify", "payload": {"title": "new"}},
            {"name": "fresh", "payload": {"title": "fresh"}},  # no id → create
        ],
    }
    patch = parse_patch(before, after)
    ops = sorted((e.op, e.name) for e in patch.entries)
    assert ops == [
        ("create", "fresh"),
        ("disable", "obsolete"),
        ("supersede", "modify"),
    ]


def test_parse_patch_treats_unknown_id_as_create():
    """If Codex emits an entry with an id that doesn't exist before, we
    treat it as a create rather than blow up."""
    before = {"h2": [], "h3": [], "h4": [], "h5": []}
    after = {
        "h2": [
            {"id": "hl-invented", "name": "x", "payload": {"title": "x"}},
        ],
    }
    patch = parse_patch(before, after)
    assert [e.op for e in patch.entries] == ["create"]


def test_parse_patch_unchanged_payload_is_a_noop():
    same = {"id": "hl-1", "name": "k", "payload": {"title": "t"}}
    before = {"h2": [same], "h3": [], "h4": [], "h5": []}
    after = {"h2": [same]}
    assert parse_patch(before, after).entries == []


# --------------------------------------------------------------------------
# validate_patch — payload / regex / action allowlists
# --------------------------------------------------------------------------

def test_validate_patch_accepts_clean_payloads():
    patch = EvolutionPatch(entries=[
        PatchEntry(op="create", layer="h2", name="ok", payload={
            "title": "Block rm",
            "match": {"tool": "Bash",
                      "arg_regex": {"command": "rm\\s+-rf"}},
            "action": {"kind": "block"},
            "message": "no",
        }),
        PatchEntry(op="create", layer="h3", name="rule", payload={
            "title": "Quote columns", "rule_text": "ok",
        }),
    ])
    assert validate_patch(patch) == []


def test_validate_patch_flags_missing_title():
    patch = EvolutionPatch(entries=[
        PatchEntry(op="create", layer="h3", name="x", payload={
            "rule_text": "no title",
        }),
    ])
    problems = validate_patch(patch)
    assert problems and "title is required" in problems[0]


def test_validate_patch_flags_bad_regex():
    patch = EvolutionPatch(entries=[
        PatchEntry(op="create", layer="h2", name="x", payload={
            "title": "x",
            "match": {"tool": "Bash", "arg_regex": {"command": "[unclosed"}},
            "action": {"kind": "block"},
        }),
    ])
    problems = validate_patch(patch)
    assert problems and "invalid arg_regex" in problems[0]


def test_validate_patch_flags_unknown_action_kind():
    patch = EvolutionPatch(entries=[
        PatchEntry(op="create", layer="h2", name="x", payload={
            "title": "x",
            "match": {"tool": "Bash"},
            "action": {"kind": "self_destruct"},
        }),
    ])
    problems = validate_patch(patch)
    assert problems and "unknown action.kind" in problems[0]


def test_validate_patch_requires_existing_id_for_supersede():
    patch = EvolutionPatch(entries=[
        PatchEntry(op="supersede", layer="h3", name="x", payload={"title": "x"}),
    ])
    problems = validate_patch(patch)
    assert any("missing existing_layer_id" in p for p in problems)


# --------------------------------------------------------------------------
# build_workspace — writes the expected files
# --------------------------------------------------------------------------

def test_build_workspace_writes_all_expected_files(tmp_path):
    inputs = {
        "bot_id": "bot-test",
        "enabled_layers": [
            {"id": "hl-1", "layer": "h3", "name": "r1", "version": 1,
             "payload": {"title": "rule one"}},
        ],
        "trajectories": [
            {"execution_id": "exec-a", "outcome": "failed",
             "primary_layer": "h2", "incidents": [], "active_layers": {"h3": 1}},
        ],
    }
    scratch = build_workspace(inputs, tmp_path / "ws")

    assert (scratch / "harness.json").exists()
    assert (scratch / "DESIGN_GUIDE.md").exists()
    assert (scratch / "PROMPT.md").exists()
    assert (scratch / "NOTES.md").exists()
    assert (scratch / "trajectories" / "exec-a.json").exists()

    harness = json.loads((scratch / "harness.json").read_text())
    assert harness["h3"][0]["id"] == "hl-1"
    assert "h2" in harness  # empty layer keys present


def test_build_workspace_sanitizes_unsafe_execution_ids(tmp_path):
    inputs = {
        "bot_id": "b",
        "enabled_layers": [],
        "trajectories": [
            {"execution_id": "exec/../../etc/passwd", "outcome": "failed",
             "incidents": [], "active_layers": {}},
        ],
    }
    scratch = build_workspace(inputs, tmp_path / "ws")
    traj_dir = (scratch / "trajectories").resolve()
    children = list(traj_dir.iterdir())
    # The security property is "file stays inside trajectories/" — not "the
    # string `..` is absent". Slashes get squashed to underscores, so any
    # surviving `..` is a literal substring with no traversal effect.
    assert children
    for child in children:
        assert child.resolve().parent == traj_dir
        assert "/" not in child.name


# --------------------------------------------------------------------------
# apply_patch — touches the layers repo via the public API
# --------------------------------------------------------------------------

def test_apply_patch_creates_supersedes_and_disables(isolated_db):
    keep_id = layers_repo.create_layer(
        bot_id="bot-apply", layer="h3", name="keep",
        payload={"title": "keep"},
    )
    mod_id = layers_repo.create_layer(
        bot_id="bot-apply", layer="h2", name="mod",
        payload={"title": "mod v1",
                 "match": {"tool": "Bash"},
                 "action": {"kind": "block"}},
    )
    obsolete_id = layers_repo.create_layer(
        bot_id="bot-apply", layer="h4", name="obsolete",
        payload={"title": "old",
                 "detector": {"kind": "regex_count"},
                 "response": {"kind": "inject_hint"}},
    )

    patch = EvolutionPatch(entries=[
        PatchEntry(op="create", layer="h3", name="brand-new", payload={
            "title": "brand new rule", "rule_text": "ok",
        }),
        PatchEntry(op="supersede", layer="h2", name="mod",
                   existing_layer_id=mod_id, payload={
            "title": "mod v2",
            "match": {"tool": "Bash"},
            "action": {"kind": "block"},
        }),
        PatchEntry(op="disable", layer="h4", name="obsolete",
                   existing_layer_id=obsolete_id),
    ])

    new_ids = apply_patch(patch, "bot-apply")
    assert len(new_ids) == 2  # create + supersede emit ids; disable doesn't

    enabled = layers_repo.list_enabled_for_bot("bot-apply")
    names = sorted(e["name"] for e in enabled)
    assert names == ["brand-new", "keep", "mod"]

    # Superseded row is disabled, with a v2 successor.
    v1 = layers_repo.get_layer(mod_id)
    assert v1["enabled"] is False
    v2 = next(e for e in enabled if e["name"] == "mod")
    assert v2["version"] == 2
    assert v2["payload"]["title"] == "mod v2"
    assert v2["source_kind"] == "evolved"


# --------------------------------------------------------------------------
# gather_inputs — joins layers + snapshots + annotations
# --------------------------------------------------------------------------

def test_gather_inputs_joins_snapshot_and_annotation(isolated_db):
    layers_repo.create_layer(
        bot_id="bot-gather", layer="h3", name="r",
        payload={"title": "r"},
    )
    snapshots_repo.upsert_snapshot(
        execution_id="exec-1",
        bot_id="bot-gather",
        harness_kind="claude",
        layer_versions={"h3": 1},
        artifact={"hook_specs": []},
        applied=True,
    )
    # Drop an H2 annotation via the public service so the row+incident exist.
    from app.services.harness_failure_annotator import annotate_from_text
    annotate_from_text(
        "exec-1",
        '{"type": "assistant", "message": {"content": '
        '[{"type": "text", "text": "take_action({})"}]}}',
        backend_type="claude",
        outcome="failed",
    )

    inputs = gather_inputs("bot-gather", limit=5)
    assert inputs["bot_id"] == "bot-gather"
    assert len(inputs["enabled_layers"]) == 1
    assert len(inputs["trajectories"]) == 1
    traj = inputs["trajectories"][0]
    assert traj["execution_id"] == "exec-1"
    assert traj["primary_layer"] == "h2"
    assert traj["active_layers"] == {"h3": 1}
    assert traj["incidents"]  # at least one


# --------------------------------------------------------------------------
# run_evolution_round — full orchestrator with Codex mocked
# --------------------------------------------------------------------------

@pytest.fixture
def mock_codex_edits():
    """Patch the Codex invocation. Returns a closure the test calls to
    configure what Codex 'would have' written into harness.json + NOTES."""
    edits = {"after": None, "notes": ""}

    def _fake_codex(scratch_dir: Path, *, timeout: int = 600) -> None:
        if edits["after"] is not None:
            (scratch_dir / "harness.json").write_text(
                json.dumps(edits["after"], indent=2)
            )
        if edits["notes"]:
            (scratch_dir / "NOTES.md").write_text(edits["notes"])

    with patch.object(evolver, "_run_codex_in_workspace", _fake_codex):
        def _configure(after, notes=""):
            edits["after"] = after
            edits["notes"] = notes

        yield _configure


def test_run_evolution_round_applies_codex_edits(
    isolated_db, mock_codex_edits,
):
    layers_repo.create_layer(
        bot_id="bot-round", layer="h3", name="existing",
        payload={"title": "existing"},
    )

    mock_codex_edits(
        after={
            "h2": [{
                "name": "block-rm",
                "payload": {
                    "title": "Block rm -rf",
                    "match": {"tool": "Bash",
                              "arg_regex": {"command": "rm\\s+-rf"}},
                    "action": {"kind": "block"},
                    "message": "no",
                },
            }],
            "h3": [],
            "h4": [],
            "h5": [],
        },
        notes="Found 3 recurring rm -rf attempts; added H2 block.",
    )

    result = evolver.run_evolution_round("bot-round")
    assert result.status == "applied"
    assert len(result.applied_layer_ids) == 1
    assert "Found 3 recurring" in result.notes

    enabled = layers_repo.list_enabled_for_bot("bot-round")
    names = sorted(e["name"] for e in enabled)
    assert "block-rm" in names

    row = evolution_repo.get_round(result.round_id)
    assert row["status"] == "applied"
    assert row["applied_layer_ids"] == result.applied_layer_ids


def test_run_evolution_round_rejects_invalid_patch(
    isolated_db, mock_codex_edits,
):
    """Codex emits a payload with a broken regex → patch validation
    fails, no layers are written, the round status is `failed`."""
    mock_codex_edits(after={
        "h2": [{
            "name": "broken",
            "payload": {
                "title": "Broken",
                "match": {"tool": "Bash", "arg_regex": {"command": "[bad"}},
                "action": {"kind": "block"},
            },
        }],
        "h3": [], "h4": [], "h5": [],
    })

    result = evolver.run_evolution_round("bot-reject")
    assert result.status == "failed"
    assert "patch validation failed" in (result.error or "")
    assert layers_repo.list_enabled_for_bot("bot-reject") == []

    row = evolution_repo.get_round(result.round_id)
    assert row["status"] == "failed"
    # The proposed (rejected) patch is still recorded for audit.
    assert row["output_patch"]["entries"]


def test_run_evolution_round_records_codex_failure(isolated_db):
    """When Codex itself errors, the round is marked failed and we never
    touch the layers repo."""
    layers_repo.create_layer(
        bot_id="bot-codex-fail", layer="h3", name="x",
        payload={"title": "x"},
    )

    def _exploding_codex(scratch_dir, *, timeout=600):
        raise RuntimeError("codex CLI exited 1: boom")

    with patch.object(evolver, "_run_codex_in_workspace", _exploding_codex):
        result = evolver.run_evolution_round("bot-codex-fail")

    assert result.status == "failed"
    assert "boom" in (result.error or "")
    enabled = layers_repo.list_enabled_for_bot("bot-codex-fail")
    assert [e["name"] for e in enabled] == ["x"]  # unchanged


def test_run_evolution_round_with_no_codex_edits_is_a_noop(
    isolated_db, mock_codex_edits,
):
    """If Codex returns the workspace untouched (no edits to harness.json),
    parse_patch yields zero entries and we mark the round applied with
    an empty change set."""
    layers_repo.create_layer(
        bot_id="bot-noop", layer="h3", name="r",
        payload={"title": "r"},
    )
    # Don't configure edits — fake_codex leaves harness.json as written by
    # build_workspace, so before == after.

    result = evolver.run_evolution_round("bot-noop")
    assert result.status == "applied"
    assert result.applied_layer_ids == []
