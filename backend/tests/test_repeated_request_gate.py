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


# --- convert_signal: effects (P2 — create called once / zero) ----------------

from app.db import harness_takeaways  # noqa: E402
from app.db import repeated_request_signals as rrs  # noqa: E402
from app.db.connection import get_connection  # noqa: E402
from app.services import harness_evolver as ev  # noqa: E402


def _make_signal(*, occurrence_count, verified_success_count, project_id=None):
    """Persist a signal via the 22-01 store, then bump the counters to the
    requested values, and return the read model (with a recent first_seen)."""
    rrs.upsert_signal(
        request_hash="rh-test",
        project_id=project_id,
        session_kind="project",
        representative_text="add a changelog entry",
        embedding=None,
        session_id="sess-1",
    )
    with get_connection() as conn:
        conn.execute(
            "UPDATE repeated_request_signals SET occurrence_count = ?, "
            "verified_success_count = ? WHERE request_hash = 'rh-test'",
            (occurrence_count, verified_success_count),
        )
        conn.commit()
    return rrs.get_signal("rh-test")


def _convert(signal, *, monkeypatch, **overrides):
    """Run convert_signal with the create/update dispatch mocked so we can count
    calls. Returns (result, create_mock, update_mock)."""
    create_calls: list[dict] = []
    update_calls: list[dict] = []

    def fake_create(*, name, payload, project_id):
        create_calls.append({"name": name, "payload": payload, "project_id": project_id})
        return "42"

    def fake_update(*, asset_id, payload):
        update_calls.append({"asset_id": asset_id, "payload": payload})

    monkeypatch.setitem(ev._create_dispatch, "skill", fake_create)
    monkeypatch.setitem(ev._update_dispatch, "skill", fake_update)

    kwargs = dict(
        skill_name="add-changelog",
        skill_description="Add a changelog entry on each feature merge",
        skill_content="Run the changelog updater and commit it.",
        scan_safe=True,
        dedup_existing=None,
        provenance_ok=True,
        now=_NOW,
    )
    kwargs.update(overrides)
    result = gate.convert_signal(signal, **kwargs)
    return result, create_calls, update_calls


def _enable_project(project_id, enabled, policy_json="{}"):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO project_autonomy_config (project_id, enabled, policy_json) "
            "VALUES (?, ?, ?)",
            (project_id, 1 if enabled else 0, policy_json),
        )
        conn.commit()


def test_convert_auto_creates_skill_exactly_once(monkeypatch):
    _enable_project("proj-auto", True)
    signal = _make_signal(occurrence_count=4, verified_success_count=2, project_id="proj-auto")

    result, create_calls, update_calls = _convert(signal, monkeypatch=monkeypatch)

    assert result["route"] == "auto"
    assert result["confidence"] == 0.9
    assert len(create_calls) == 1
    assert len(update_calls) == 0
    # discovered_procedure takeaway at 0.9
    tk = harness_takeaways.get(result["takeaway_id"])
    assert tk is not None
    assert tk["kind"] == "discovered_procedure"
    assert tk["confidence"] == 0.9
    # origin recorded + skill_created marked
    from app.db.forge_origin import get_origin

    assert get_origin("42", "skill") is not None
    assert rrs.get_signal("rh-test").skill_created is True


def test_convert_origin_hash_matches_rendered_skill_md(monkeypatch):
    """Blocker guard: the recorded origin hash must be the hash of the rendered
    SKILL.md (frontmatter + body) exactly as _create_skill writes it — NOT the
    bare body. Otherwise every auto-skill looks operator-edited on re-drive."""
    from app.db.forge_origin import get_origin
    from app.utils.plugin_format import content_hash

    _enable_project("proj-auto", True)
    signal = _make_signal(occurrence_count=4, verified_success_count=2, project_id="proj-auto")

    result, create_calls, _ = _convert(signal, monkeypatch=monkeypatch)

    assert result["route"] == "auto"
    payload = create_calls[0]["payload"]
    expected = content_hash(ev._render_skill_md("add-changelog", payload))
    assert get_origin("42", "skill")["origin_hash"] == expected
    # And explicitly NOT the bare-body hash (the pre-fix bug).
    assert get_origin("42", "skill")["origin_hash"] != content_hash(payload["content"])


def test_convert_idempotent_when_already_created(monkeypatch):
    """W1 guard: re-driving a signal already marked skill_created must not create
    a second skill or duplicate the discovered_procedure takeaway."""
    _enable_project("proj-auto", True)
    signal = _make_signal(occurrence_count=4, verified_success_count=2, project_id="proj-auto")

    first, create_calls, _ = _convert(signal, monkeypatch=monkeypatch)
    assert first["route"] == "auto"
    assert len(create_calls) == 1

    # Re-read the signal (now skill_created=True) and convert again.
    reread = rrs.get_signal("rh-test")
    assert reread.skill_created is True
    second, create_calls_2, update_calls_2 = _convert(reread, monkeypatch=monkeypatch)
    assert len(create_calls_2) == 0
    assert len(update_calls_2) == 0
    assert second["asset_id"] is None
    assert second["takeaway_id"] is None
    assert "already-created" in second["reasons"]


def test_convert_create_failure_leaves_signal_unconverted(monkeypatch):
    """A failed skill create (_create_skill -> None, e.g. project without
    local_path) must NOT mark the signal skill_created — otherwise the
    idempotency guard permanently blocks retries for a transient failure."""
    _enable_project("proj-auto", True)
    signal = _make_signal(occurrence_count=4, verified_success_count=2, project_id="proj-auto")

    monkeypatch.setitem(ev._create_dispatch, "skill", lambda *, name, payload, project_id: None)
    result = gate.convert_signal(
        signal,
        skill_name="add-changelog",
        skill_description="Add a changelog entry on each feature merge",
        skill_content="Run the changelog updater and commit it.",
        scan_safe=True,
        dedup_existing=None,
        provenance_ok=True,
        now=_NOW,
    )

    assert result["route"] == "auto"
    assert result["asset_id"] is None
    assert "skill-create-failed" in result["reasons"]
    assert rrs.get_signal("rh-test").skill_created is False


def test_convert_dedup_hit_patches_instead_of_creating(monkeypatch):
    _enable_project("proj-auto", True)
    signal = _make_signal(occurrence_count=4, verified_success_count=2, project_id="proj-auto")

    result, create_calls, update_calls = _convert(
        signal, monkeypatch=monkeypatch, dedup_existing={"id": 7, "skill_name": "x"}
    )

    assert result["route"] == "auto"
    assert result["patch"] is True
    assert len(create_calls) == 0
    assert len(update_calls) == 1
    assert update_calls[0]["asset_id"] == 7


def test_convert_propose_when_unverified_never_creates(monkeypatch):
    _enable_project("proj-auto", True)
    signal = _make_signal(occurrence_count=5, verified_success_count=0, project_id="proj-auto")

    result, create_calls, update_calls = _convert(signal, monkeypatch=monkeypatch)

    assert result["route"] == "propose"
    assert result["confidence"] == 0.65
    assert len(create_calls) == 0
    assert len(update_calls) == 0
    assert result["takeaway_id"] is None


def test_convert_scan_fail_never_creates(monkeypatch):
    _enable_project("proj-auto", True)
    signal = _make_signal(occurrence_count=5, verified_success_count=2, project_id="proj-auto")

    result, create_calls, _ = _convert(signal, monkeypatch=monkeypatch, scan_safe=False)

    assert result["route"] == "propose"
    assert len(create_calls) == 0


def test_convert_provenance_diverged_never_creates(monkeypatch):
    _enable_project("proj-auto", True)
    signal = _make_signal(occurrence_count=5, verified_success_count=2, project_id="proj-auto")

    result, create_calls, _ = _convert(signal, monkeypatch=monkeypatch, provenance_ok=False)

    assert result["route"] == "propose"
    assert len(create_calls) == 0


def test_policy_disabled_row_forces_propose(monkeypatch):
    _enable_project("proj-off", False)
    signal = _make_signal(occurrence_count=4, verified_success_count=2, project_id="proj-off")

    result, create_calls, _ = _convert(signal, monkeypatch=monkeypatch)

    assert result["route"] == "propose"
    assert len(create_calls) == 0


def test_no_policy_row_env_flag_allows_auto(monkeypatch):
    # No project_autonomy_config row → fall back to AGENTED_TAKEAWAY_AUTOAPPLY.
    monkeypatch.setenv("AGENTED_TAKEAWAY_AUTOAPPLY", "1")
    signal = _make_signal(occurrence_count=4, verified_success_count=2, project_id="proj-norow")

    result, create_calls, _ = _convert(signal, monkeypatch=monkeypatch)

    assert result["route"] == "auto"
    assert len(create_calls) == 1


def test_no_policy_row_env_flag_off_proposes(monkeypatch):
    monkeypatch.setenv("AGENTED_TAKEAWAY_AUTOAPPLY", "0")
    signal = _make_signal(occurrence_count=4, verified_success_count=2, project_id="proj-norow")

    result, create_calls, _ = _convert(signal, monkeypatch=monkeypatch)

    assert result["route"] == "propose"
    assert len(create_calls) == 0
