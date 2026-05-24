"""Tests for T3 dry-run mode + admin routes (apply / abort / list / detail)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from litestar.testing import create_test_client

from app.db import harness_evolution as evolution_repo
from app.db import harness_layers as layers_repo
from app.services import harness_evolver as evolver
from app_litestar.auth import provide_caller
from app_litestar.routes.harness_evolution import harness_evolution_router


def _client():
    return create_test_client(
        route_handlers=[harness_evolution_router],
        dependencies={"caller": provide_caller},
    )


@pytest.fixture
def mock_codex_emits():
    """Patch Codex; tests configure the harness.json edits + NOTES.md the
    fake Codex would write."""
    edits = {"after": None, "notes": ""}

    def _fake(scratch_dir: Path, *, timeout: int = 600) -> None:
        if edits["after"] is not None:
            (scratch_dir / "harness.json").write_text(
                json.dumps(edits["after"], indent=2)
            )
        if edits["notes"]:
            (scratch_dir / "NOTES.md").write_text(edits["notes"])

    with patch.object(evolver, "_run_codex_in_workspace", _fake):
        def _configure(after, notes=""):
            edits["after"] = after
            edits["notes"] = notes
        yield _configure


# --------------------------------------------------------------------------
# dry-run service-level
# --------------------------------------------------------------------------

def test_dry_run_stops_at_awaiting_approval_no_layers_applied(
    isolated_db, mock_codex_emits,
):
    layers_repo.create_layer(
        bot_id="bot-dry-a", layer="h3", name="existing",
        payload={"title": "existing"},
    )
    mock_codex_emits(
        after={
            "h2": [{"name": "block-rm", "payload": {
                "title": "Block rm -rf",
                "match": {"tool": "Bash",
                          "arg_regex": {"command": "rm\\s+-rf"}},
                "action": {"kind": "block"}, "message": "no",
            }}],
            "h3": [], "h4": [], "h5": [],
        },
        notes="Found 3 rm -rf attempts.",
    )

    result = evolver.run_evolution_round("bot-dry-a", dry_run=True)
    assert result.status == "awaiting_approval"
    assert result.applied_layer_ids == []

    # No new layer rows yet — the only enabled one is the seed.
    enabled = layers_repo.list_enabled_for_bot("bot-dry-a")
    assert {e["name"] for e in enabled} == {"existing"}

    row = evolution_repo.get_round(result.round_id)
    assert row["status"] == "awaiting_approval"
    assert row["output_patch"]["entries"]
    assert "Found 3" in row["notes"]


def test_apply_dry_run_round_promotes_to_applied(
    isolated_db, mock_codex_emits,
):
    mock_codex_emits(after={
        "h2": [{"name": "block-rm", "payload": {
            "title": "Block rm",
            "match": {"tool": "Bash",
                      "arg_regex": {"command": "rm\\s+-rf"}},
            "action": {"kind": "block"}, "message": "no",
        }}],
        "h3": [], "h4": [], "h5": [],
    })
    dry = evolver.run_evolution_round("bot-dry-b", dry_run=True)
    assert dry.status == "awaiting_approval"

    applied = evolver.apply_dry_run_round(dry.round_id)
    assert applied.status == "applied"
    assert len(applied.applied_layer_ids) == 1

    enabled = layers_repo.list_enabled_for_bot("bot-dry-b")
    assert {e["name"] for e in enabled} == {"block-rm"}

    row = evolution_repo.get_round(dry.round_id)
    assert row["status"] == "applied"
    assert row["applied_layer_ids"] == applied.applied_layer_ids


def test_abort_dry_run_round_leaves_layers_untouched(
    isolated_db, mock_codex_emits,
):
    layers_repo.create_layer(
        bot_id="bot-abort", layer="h3", name="keep",
        payload={"title": "keep"},
    )
    mock_codex_emits(after={
        "h2": [{"name": "x", "payload": {
            "title": "x",
            "match": {"tool": "Bash"},
            "action": {"kind": "block"},
        }}],
        "h3": [], "h4": [], "h5": [],
    })
    dry = evolver.run_evolution_round("bot-abort", dry_run=True)
    aborted = evolver.abort_dry_run_round(dry.round_id, reason="not aligned")
    assert aborted.status == "aborted"

    row = evolution_repo.get_round(dry.round_id)
    assert row["status"] == "aborted"
    assert row["error_message"] == "not aligned"
    # Layer set unchanged from before the round.
    assert {e["name"] for e in layers_repo.list_enabled_for_bot("bot-abort")} == {"keep"}


def test_apply_dry_run_on_non_pending_round_is_a_failed_result(
    isolated_db, mock_codex_emits,
):
    """Cannot apply a round that's already applied / aborted / failed."""
    mock_codex_emits(after={"h2": [], "h3": [], "h4": [], "h5": []})
    live = evolver.run_evolution_round("bot-rejapply", dry_run=False)
    assert live.status == "applied"
    second = evolver.apply_dry_run_round(live.round_id)
    assert second.status == "failed"
    assert "not awaiting approval" in (second.error or "")


def test_apply_dry_run_unknown_round_id(isolated_db):
    result = evolver.apply_dry_run_round("her-nope")
    assert result.status == "failed"
    assert "not found" in (result.error or "")


# --------------------------------------------------------------------------
# Rate limit
# --------------------------------------------------------------------------

def test_rate_limit_blocks_burst_triggers(isolated_db, mock_codex_emits):
    """A second round within the default 24h window is aborted with a
    rate-limit reason and ``round_id`` is empty (nothing was started)."""
    mock_codex_emits(after={"h2": [], "h3": [], "h4": [], "h5": []})
    first = evolver.run_evolution_round("bot-rate-a", dry_run=True)
    assert first.status == "awaiting_approval"

    second = evolver.run_evolution_round("bot-rate-a", dry_run=True)
    assert second.status == "aborted"
    assert second.round_id == ""
    assert "rate-limited" in (second.error or "")


def test_rate_limit_force_bypasses(isolated_db, mock_codex_emits):
    mock_codex_emits(after={"h2": [], "h3": [], "h4": [], "h5": []})
    evolver.run_evolution_round("bot-rate-b", dry_run=True)
    second = evolver.run_evolution_round("bot-rate-b", dry_run=True, force=True)
    assert second.status == "awaiting_approval"


def test_rate_limit_zero_interval_disables_the_guard(
    isolated_db, mock_codex_emits, monkeypatch,
):
    """Setting ``AGENTED_EVOLUTION_MIN_INTERVAL_HOURS=0`` opts out of
    rate-limiting entirely (useful in test environments)."""
    monkeypatch.setenv("AGENTED_EVOLUTION_MIN_INTERVAL_HOURS", "0")
    mock_codex_emits(after={"h2": [], "h3": [], "h4": [], "h5": []})
    evolver.run_evolution_round("bot-rate-c", dry_run=True)
    second = evolver.run_evolution_round("bot-rate-c", dry_run=True)
    assert second.status == "awaiting_approval"


def test_rate_limit_route_passes_force_through(isolated_db, mock_codex_emits):
    """``POST .../dry-run`` accepts ``{"force": true}`` to override."""
    mock_codex_emits(after={"h2": [], "h3": [], "h4": [], "h5": []})
    evolver.run_evolution_round("bot-rate-d", dry_run=True)
    with _client() as c:
        resp = c.post(
            "/admin/bots/bot-rate-d/evolution/dry-run", json={"force": True},
        )
    assert resp.status_code == 201
    assert resp.json()["status"] == "awaiting_approval"


# --------------------------------------------------------------------------
# Admin route surface
# --------------------------------------------------------------------------

def test_dry_run_route_returns_awaiting_approval(
    isolated_db, mock_codex_emits,
):
    mock_codex_emits(after={
        "h2": [{"name": "block-rm", "payload": {
            "title": "Block rm",
            "match": {"tool": "Bash",
                      "arg_regex": {"command": "rm\\s+-rf"}},
            "action": {"kind": "block"}, "message": "no",
        }}],
        "h3": [], "h4": [], "h5": [],
    }, notes="hi")

    with _client() as c:
        resp = c.post("/admin/bots/bot-route-a/evolution/dry-run", json={})
    body = resp.json()
    assert resp.status_code == 201
    assert body["status"] == "awaiting_approval"
    assert body["notes"] == "hi"

    # No layers applied yet.
    assert layers_repo.list_enabled_for_bot("bot-route-a") == []


def test_list_rounds_route(isolated_db, mock_codex_emits):
    mock_codex_emits(after={"h2": [], "h3": [], "h4": [], "h5": []})
    evolver.run_evolution_round("bot-list", dry_run=True)
    # Second call against the same bot in quick succession would normally
    # hit the rate-limit guard — bypass it explicitly here.
    evolver.run_evolution_round("bot-list", dry_run=False, force=True)

    with _client() as c:
        resp = c.get("/admin/bots/bot-list/evolution/rounds")
    body = resp.json()
    assert resp.status_code == 200
    assert body["bot_id"] == "bot-list"
    assert len(body["rounds"]) == 2


def test_round_detail_route_404s_unknown(isolated_db):
    with _client() as c:
        resp = c.get("/admin/evolution/rounds/her-nope")
    assert resp.status_code == 404


def test_round_detail_route_returns_patch(isolated_db, mock_codex_emits):
    mock_codex_emits(after={
        "h3": [{"name": "n", "payload": {"title": "n", "rule_text": "ok"}}],
        "h2": [], "h4": [], "h5": [],
    })
    dry = evolver.run_evolution_round("bot-detail", dry_run=True)

    with _client() as c:
        resp = c.get(f"/admin/evolution/rounds/{dry.round_id}")
    body = resp.json()
    assert resp.status_code == 200
    assert body["status"] == "awaiting_approval"
    assert body["output_patch"]["entries"][0]["op"] == "create"


def test_list_all_rounds_route_returns_cross_bot(isolated_db, mock_codex_emits):
    """``GET /admin/evolution/rounds`` returns rounds for every bot, newest
    first, with optional status filter."""
    mock_codex_emits(after={"h2": [], "h3": [], "h4": [], "h5": []})
    evolver.run_evolution_round("bot-cross-a", dry_run=False)
    evolver.run_evolution_round("bot-cross-b", dry_run=True)

    with _client() as c:
        all_resp = c.get("/admin/evolution/rounds?limit=10")
        awaiting_resp = c.get(
            "/admin/evolution/rounds?status=awaiting_approval&limit=10"
        )
    all_rounds = all_resp.json()["rounds"]
    awaiting_rounds = awaiting_resp.json()["rounds"]
    assert len(all_rounds) == 2
    assert {r["bot_id"] for r in all_rounds} == {"bot-cross-a", "bot-cross-b"}
    assert [r["bot_id"] for r in awaiting_rounds] == ["bot-cross-b"]


def test_approve_route_applies_and_aborts_route_rejects(
    isolated_db, mock_codex_emits,
):
    mock_codex_emits(after={
        "h3": [{"name": "n", "payload": {"title": "n", "rule_text": "ok"}}],
        "h2": [], "h4": [], "h5": [],
    })
    a = evolver.run_evolution_round("bot-approve", dry_run=True)
    b = evolver.run_evolution_round("bot-approve", dry_run=True, force=True)

    with _client() as c:
        approve_resp = c.post(f"/admin/evolution/rounds/{a.round_id}/apply")
        abort_resp = c.post(
            f"/admin/evolution/rounds/{b.round_id}/abort",
            json={"reason": "not now"},
        )
    assert approve_resp.json()["status"] == "applied"
    assert abort_resp.json()["status"] == "aborted"

    enabled = layers_repo.list_enabled_for_bot("bot-approve")
    # Approve created one new layer; abort created none.
    assert {e["name"] for e in enabled} == {"n"}
