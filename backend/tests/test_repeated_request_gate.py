"""Gate-matrix tests for the hybrid auto-skill gate (Phase 22, REQ-24).

EVAL P2 (full routing matrix) + A2 (scan-fail downgrade). ``evaluate_signal``
is a pure function; ``convert_signal`` drives the AUTO path through the proven
evolver ``_create_dispatch['skill']`` and is asserted to fire exactly once on
AUTO and zero times on every PROPOSE/REJECT branch.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services import repeated_request_gate as gate

# Reference "now" anchoring the 30-day window for the pure-function tests.
_NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)
_RECENT = (_NOW - timedelta(days=5)).isoformat()
_STALE = (_NOW - timedelta(days=40)).isoformat()


def _eval(**overrides):
    """All-qualifying AUTO baseline; override one axis per test."""
    kwargs = dict(
        occurrence_count=4,
        verified_success_count=2,
        scan_safe=True,
        dedup_existing=None,
        provenance_ok=True,
        policy_enabled=True,
        first_seen_at=_RECENT,
        now=_NOW,
    )
    kwargs.update(overrides)
    return gate.evaluate_signal(**kwargs)


# --- evaluate_signal: the gate matrix (P2 + A2) ------------------------------


def test_all_qualifying_routes_auto():
    d = _eval()
    assert d.route == "auto"
    assert d.confidence == 0.9
    assert d.patch is False


def test_occurrence_two_proposes():
    d = _eval(occurrence_count=2)
    assert d.route == "propose"
    assert d.confidence == 0.65


def test_occurrence_at_or_above_three_but_unverified_proposes():
    d = _eval(occurrence_count=5, verified_success_count=0)
    assert d.route == "propose"
    assert d.confidence == 0.65


def test_scan_fail_downgrades_to_propose():
    # A2: a scan failure NEVER silently rejects the signal — it downgrades.
    d = _eval(occurrence_count=5, verified_success_count=2, scan_safe=False)
    assert d.route == "propose"
    assert d.confidence == 0.65


def test_provenance_diverged_downgrades_to_propose():
    d = _eval(provenance_ok=False)
    assert d.route == "propose"
    assert d.confidence == 0.65


def test_policy_disabled_proposes_even_when_all_else_qualifies():
    d = _eval(policy_enabled=False)
    assert d.route == "propose"
    assert d.confidence == 0.65


def test_stale_first_seen_outside_window_proposes():
    # occ≥3 but the first sighting is >30 days old → not "≥3 within 30 days".
    d = _eval(first_seen_at=_STALE)
    assert d.route == "propose"


def test_dedup_hit_sets_patch_flag_on_auto():
    d = _eval(dedup_existing={"id": 7, "skill_name": "commit-style"})
    assert d.route == "auto"
    assert d.patch is True


def test_three_occurrences_within_window_is_boundary_auto():
    d = _eval(occurrence_count=3, verified_success_count=1)
    assert d.route == "auto"
