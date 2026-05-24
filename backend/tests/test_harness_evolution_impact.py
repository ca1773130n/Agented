"""Tests for the A/B impact summary on applied evolution rounds."""

from __future__ import annotations

import time

import pytest
from litestar.testing import create_test_client

from app.db import harness_evolution as evolution_repo
from app.db import harness_snapshots as snapshots_repo
from app.services.harness_evolution_impact import compute_impact
from app.services.harness_failure_annotator import annotate_from_text
from app_litestar.auth import provide_caller
from app_litestar.routes.harness_evolution import harness_evolution_router


def _client():
    return create_test_client(
        route_handlers=[harness_evolution_router],
        dependencies={"caller": provide_caller},
    )


H2_STREAM = (
    '{"type": "assistant", "message": {"content": '
    '[{"type": "text", "text": "I will take_action({a:1})"}]}}'
)


def _seed_execution(execution_id: str, bot_id: str, *, outcome: str,
                    stream: str = "") -> None:
    """Plant a snapshot + (optional) annotation for one execution."""
    snapshots_repo.upsert_snapshot(
        execution_id=execution_id, bot_id=bot_id,
        harness_kind="claude",
        layer_versions={"h3": 1},
        artifact={"hook_specs": []},
        applied=True,
    )
    annotate_from_text(
        execution_id, stream, backend_type="claude", outcome=outcome,
    )


# --------------------------------------------------------------------------
# Service-level
# --------------------------------------------------------------------------

def test_compute_impact_unavailable_when_round_missing(isolated_db):
    out = compute_impact("her-nope")
    assert out["available"] is False
    assert "not found" in out["reason"]


def test_compute_impact_unavailable_when_round_not_applied(isolated_db):
    rid = evolution_repo.start_round(
        bot_id="bot-imp-a",
        input_window_since=None,
        input_window_until=None,
        input_execution_count=0,
        input_layers={},
    )
    out = compute_impact(rid)
    assert out["available"] is False
    assert "not applied" in out["reason"]


def test_compute_impact_partitions_windows_around_round(isolated_db):
    """Seed three failed executions before the round, three clean ones
    after — the summary should show 0% → 100% success."""
    bot = "bot-imp-b"

    # BEFORE: three failures with H2 incidents.
    _seed_execution("exec-before-1", bot, outcome="failed", stream=H2_STREAM)
    _seed_execution("exec-before-2", bot, outcome="failed", stream=H2_STREAM)
    _seed_execution("exec-before-3", bot, outcome="failed", stream=H2_STREAM)

    # Sleep just enough that the round's started_at strictly exceeds the
    # before-seeds' snapshot timestamps (SQLite's datetime('now') has 1s
    # resolution).
    time.sleep(1.05)

    rid = evolution_repo.start_round(
        bot_id=bot,
        input_window_since=None, input_window_until=None,
        input_execution_count=3, input_layers={},
    )
    evolution_repo.mark_applied(
        rid, output_patch={"entries": []},
        applied_layer_ids=[], notes="ok",
    )

    time.sleep(1.05)

    # AFTER: three successes.
    _seed_execution("exec-after-1", bot, outcome="success", stream="")
    _seed_execution("exec-after-2", bot, outcome="success", stream="")
    _seed_execution("exec-after-3", bot, outcome="success", stream="")

    out = compute_impact(rid, window_size=10)
    assert out["available"] is True
    assert out["before"]["executions"] == 3
    assert out["after"]["executions"] == 3
    assert out["before"]["success_rate"] == 0.0
    assert out["after"]["success_rate"] == 1.0
    assert out["before"]["failure_layers"]["h2"] == 3
    assert out["after"]["failure_layers"]["h2"] == 0
    # Delta: success_rate up 1.0; H2 incidents down by 3.
    assert out["delta"]["success_rate"] == 1.0
    assert out["delta"]["failure_layers"]["h2"] == -3


def test_compute_impact_handles_empty_windows(isolated_db):
    """Applied round with no preceding/following executions yields
    ``executions == 0`` and ``success_rate is None`` (no division)."""
    rid = evolution_repo.start_round(
        bot_id="bot-imp-c",
        input_window_since=None, input_window_until=None,
        input_execution_count=0, input_layers={},
    )
    evolution_repo.mark_applied(
        rid, output_patch={"entries": []}, applied_layer_ids=[], notes=None,
    )

    out = compute_impact(rid)
    assert out["available"] is True
    assert out["before"]["executions"] == 0
    assert out["after"]["executions"] == 0
    assert out["before"]["success_rate"] is None
    assert out["after"]["success_rate"] is None
    # When either side is None, the corresponding delta is None.
    assert out["delta"]["success_rate"] is None


# --------------------------------------------------------------------------
# Route
# --------------------------------------------------------------------------

def test_impact_route_returns_summary_for_applied(isolated_db):
    bot = "bot-imp-r"
    _seed_execution("exec-rbefore", bot, outcome="failed", stream=H2_STREAM)
    time.sleep(1.05)
    rid = evolution_repo.start_round(
        bot_id=bot, input_window_since=None, input_window_until=None,
        input_execution_count=1, input_layers={},
    )
    evolution_repo.mark_applied(
        rid, output_patch={"entries": []}, applied_layer_ids=[], notes=None,
    )
    time.sleep(1.05)
    _seed_execution("exec-rafter", bot, outcome="success")

    with _client() as c:
        resp = c.get(f"/admin/evolution/rounds/{rid}/impact?window=5")
    body = resp.json()
    assert resp.status_code == 200
    assert body["available"] is True
    assert body["before"]["executions"] == 1
    assert body["after"]["executions"] == 1
    assert body["delta"]["success_rate"] == pytest.approx(1.0)


def test_impact_route_404ish_for_missing(isolated_db):
    """Missing round returns 200 with available=False (the UI can still
    render an explanatory empty state)."""
    with _client() as c:
        resp = c.get("/admin/evolution/rounds/her-nope/impact")
    assert resp.status_code == 200
    assert resp.json() == {"available": False, "reason": "round not found"}
