"""Tests for the capture-only harness snapshot service (T2 integration)."""

from __future__ import annotations

import sqlite3
from unittest.mock import patch

from app.db import harness_layers as layers_repo
from app.db import harness_snapshots as snap_repo
from app.services.harness_snapshot_service import (
    prepare_harness_for_execution,
    snapshot_for_execution,
)


def _seed_h3(bot_id: str, *, title: str = "Quote spaced cols", text: str = "ok") -> str:
    return layers_repo.create_layer(
        bot_id=bot_id,
        layer="h3",
        name=title.lower().replace(" ", "-"),
        payload={"title": title, "rule_text": text},
    )


def test_snapshot_writes_row_when_layers_exist(isolated_db):
    _seed_h3("bot-snap-a")
    art = snapshot_for_execution(
        execution_id="exec-snap-1",
        bot_id="bot-snap-a",
        harness_kind="claude",
    )
    assert art is not None
    assert "system_prompt_overlay" in art

    row = snap_repo.get_snapshot("exec-snap-1")
    assert row is not None
    assert row["bot_id"] == "bot-snap-a"
    assert row["harness_kind"] == "claude"
    assert row["applied"] is False
    assert row["layer_versions"].get("h3") == 1
    assert "Quote spaced cols" in row["artifact"]["system_prompt_overlay"]


def test_no_layers_means_no_snapshot(isolated_db):
    """A bot with zero layers must not produce an empty row — the snapshot
    table is for *configured* harnesses, not every execution Agented runs."""
    art = snapshot_for_execution(
        execution_id="exec-snap-2",
        bot_id="bot-without-layers",
        harness_kind="claude",
    )
    assert art is None
    assert snap_repo.get_snapshot("exec-snap-2") is None


def test_unknown_harness_kind_skips_silently(isolated_db):
    _seed_h3("bot-snap-c")
    art = snapshot_for_execution(
        execution_id="exec-snap-3",
        bot_id="bot-snap-c",
        harness_kind="totally-fake-kind",
    )
    assert art is None
    assert snap_repo.get_snapshot("exec-snap-3") is None


def test_repository_error_does_not_raise(isolated_db):
    """The spawn path must never crash because of snapshot bookkeeping."""
    _seed_h3("bot-snap-d")
    with patch(
        "app.services.harness_snapshot_service.snapshot_repo.upsert_snapshot",
        side_effect=sqlite3.OperationalError("disk full"),
    ):
        # Must not raise; returns None on swallowed error.
        result = snapshot_for_execution(
            execution_id="exec-snap-4",
            bot_id="bot-snap-d",
            harness_kind="claude",
        )
    assert result is None


def test_supersede_advances_version_in_subsequent_snapshot(isolated_db):
    v1 = _seed_h3("bot-snap-e", title="rule v1", text="v1")
    snapshot_for_execution(
        execution_id="exec-snap-5a",
        bot_id="bot-snap-e",
        harness_kind="claude",
    )

    layers_repo.supersede_layer(
        v1,
        new_payload={"title": "rule v1", "rule_text": "v2"},
        source_kind="evolved",
    )
    snapshot_for_execution(
        execution_id="exec-snap-5b",
        bot_id="bot-snap-e",
        harness_kind="claude",
    )

    snap_a = snap_repo.get_snapshot("exec-snap-5a")
    snap_b = snap_repo.get_snapshot("exec-snap-5b")
    assert snap_a["layer_versions"]["h3"] == 1
    assert snap_b["layer_versions"]["h3"] == 2


def test_prepare_injects_overlay_into_cmd_and_marks_applied(isolated_db):
    """Happy path: bot has H3 → overlay injected via --append-system-prompt
    AND the snapshot row reflects ``applied = True``."""
    _seed_h3("bot-prep-a", title="My rule", text="follow this rule")
    base_cmd = ["claude", "-p", "hello", "--verbose"]

    new_cmd, new_env, artifact, overlay_dir = prepare_harness_for_execution(
        execution_id="exec-prep-1",
        bot_id="bot-prep-a",
        harness_kind="claude",
        cmd=base_cmd,
    )
    assert artifact is not None
    assert new_cmd[: len(base_cmd)] == base_cmd
    assert "--append-system-prompt" in new_cmd
    overlay = new_cmd[new_cmd.index("--append-system-prompt") + 1]
    assert "My rule" in overlay
    assert "follow this rule" in overlay
    # H3-only bot has no hook_specs, so no env overlay should have been built.
    assert overlay_dir is None
    assert new_env is None  # env not passed in, never created

    snap = snap_repo.get_snapshot("exec-prep-1")
    assert snap["applied"] is True
    assert snap["artifact"]["injected_components"]["system_prompt"] is True
    assert snap["artifact"]["injected_components"]["hooks"] is False


def test_prepare_no_layers_returns_cmd_unchanged(isolated_db):
    base_cmd = ["claude", "-p", "x"]
    new_cmd, new_env, artifact, overlay_dir = prepare_harness_for_execution(
        execution_id="exec-prep-2",
        bot_id="bot-without-layers",
        harness_kind="claude",
        cmd=base_cmd,
    )
    assert new_cmd == base_cmd
    assert artifact is None
    assert overlay_dir is None
    assert snap_repo.get_snapshot("exec-prep-2") is None


def test_prepare_kill_switch_disables_injection(isolated_db, monkeypatch):
    """``AGENTED_HARNESS_INJECT=0`` keeps the snapshot but leaves cmd/env alone."""
    monkeypatch.setenv("AGENTED_HARNESS_INJECT", "0")
    _seed_h3("bot-prep-c")
    base_cmd = ["claude", "-p", "hello"]
    new_cmd, new_env, artifact, overlay_dir = prepare_harness_for_execution(
        execution_id="exec-prep-3",
        bot_id="bot-prep-c",
        harness_kind="claude",
        cmd=base_cmd,
        env={"X": "1"},
    )
    assert new_cmd == base_cmd
    assert new_env == {"X": "1"}
    assert overlay_dir is None
    assert artifact is not None

    snap = snap_repo.get_snapshot("exec-prep-3")
    assert snap is not None
    assert snap["applied"] is False
    assert snap["artifact"]["injected_components"]["system_prompt"] is False
    assert snap["artifact"]["injected_components"]["hooks"] is False


def test_prepare_unregistered_translator_returns_cmd_unchanged(isolated_db):
    _seed_h3("bot-prep-d")
    base_cmd = ["fake-cli", "-p", "x"]
    new_cmd, new_env, artifact, overlay_dir = prepare_harness_for_execution(
        execution_id="exec-prep-4",
        bot_id="bot-prep-d",
        harness_kind="totally-fake-kind",
        cmd=base_cmd,
    )
    assert new_cmd == base_cmd
    assert overlay_dir is None
    assert artifact is None
    assert snap_repo.get_snapshot("exec-prep-4") is None


def test_prepare_non_claude_translator_records_snapshot_without_injection(
    isolated_db,
):
    """Codex / gemini / opencode have translators but the live injector is
    Claude-only today. The snapshot must be recorded with
    ``applied=False`` so T3 can still reason about which layers *would*
    have been active."""
    _seed_h3("bot-prep-codex")
    base_cmd = ["codex", "exec", "x"]
    new_cmd, new_env, artifact, overlay_dir = prepare_harness_for_execution(
        execution_id="exec-prep-codex",
        bot_id="bot-prep-codex",
        harness_kind="codex",
        cmd=base_cmd,
    )
    assert new_cmd == base_cmd
    assert overlay_dir is None
    assert artifact is not None
    snap = snap_repo.get_snapshot("exec-prep-codex")
    assert snap is not None
    assert snap["applied"] is False
    assert snap["artifact"]["injected_components"]["system_prompt"] is False
    assert snap["artifact"]["injected_components"]["hooks"] is False


def test_prepare_with_hooks_sets_claude_config_dir(isolated_db):
    """Happy path for hook injection: bot has an H2 layer → overlay is
    materialized, env gets CLAUDE_CONFIG_DIR, snapshot.applied = True with
    both system_prompt and hooks components flagged."""
    from unittest.mock import patch

    layers_repo.create_layer(
        bot_id="bot-prep-e", layer="h2", name="no-rm-rf",
        payload={
            "title": "Block rm -rf",
            "match": {"tool": "Bash", "arg_regex": {"command": "rm\\s+-rf"}},
            "action": {"kind": "block"},
            "message": "no",
        },
    )
    base_cmd = ["claude", "-p", "x"]
    fake_overlay = "/tmp/fake-overlay-e"
    with patch(
        "app.services.harness_overlay.prepare_overlay_for_execution",
        return_value=fake_overlay,
    ):
        new_cmd, new_env, artifact, overlay_dir = prepare_harness_for_execution(
            execution_id="exec-prep-5",
            bot_id="bot-prep-e",
            harness_kind="claude",
            cmd=base_cmd,
            env={"PATH": "/usr/bin"},
        )
    assert overlay_dir == fake_overlay
    assert new_env["CLAUDE_CONFIG_DIR"] == fake_overlay
    assert new_env["PATH"] == "/usr/bin"

    snap = snap_repo.get_snapshot("exec-prep-5")
    assert snap["applied"] is True
    assert snap["artifact"]["injected_components"]["hooks"] is True


def test_list_for_bot_filters_by_layer_version(isolated_db):
    v1 = _seed_h3("bot-snap-f", title="filter rule")
    snapshot_for_execution(
        execution_id="exec-f1", bot_id="bot-snap-f", harness_kind="claude",
    )
    layers_repo.supersede_layer(
        v1, new_payload={"title": "filter rule", "rule_text": "v2"},
    )
    snapshot_for_execution(
        execution_id="exec-f2", bot_id="bot-snap-f", harness_kind="claude",
    )

    only_v1 = snap_repo.list_for_bot("bot-snap-f", layer="h3", version=1)
    only_v2 = snap_repo.list_for_bot("bot-snap-f", layer="h3", version=2)
    assert [r["execution_id"] for r in only_v1] == ["exec-f1"]
    assert [r["execution_id"] for r in only_v2] == ["exec-f2"]
