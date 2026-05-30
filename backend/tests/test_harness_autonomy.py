from app.db import project_autonomy_config as cfg
from app.models.autonomy_policy import AutonomyDecision, AutonomyPolicy, GateResult


def test_policy_defaults_are_safe():
    p = AutonomyPolicy()
    assert p.enabled is False  # review-mode default
    assert 0.0 <= p.confidence_threshold <= 1.0
    assert p.confidence_threshold == 0.85
    assert p.max_ops_per_round == 5
    assert p.block_deletes is True  # safe default
    assert p.cooldown_seconds == 3600


def test_policy_bounds_enforced():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AutonomyPolicy(confidence_threshold=1.5)


def test_decision_shape():
    d = AutonomyDecision(
        eligible=False, gates=[GateResult(name="confidence", passed=False, detail="0.4 < 0.85")]
    )
    assert d.eligible is False
    assert d.gates[0].name == "confidence"
    assert AutonomyDecision.model_validate_json(d.model_dump_json()).eligible is False


def test_upsert_and_get_policy(isolated_db):
    from app.database import get_connection

    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('pa', 'P', 'active')")
        conn.commit()
    assert cfg.get_policy("pa") is None
    cfg.upsert_policy("pa", AutonomyPolicy(enabled=True, confidence_threshold=0.9))
    p = cfg.get_policy("pa")
    assert p.enabled is True and p.confidence_threshold == 0.9


def test_upsert_updates_existing(isolated_db):
    from app.database import get_connection

    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('pu', 'P', 'active')")
        conn.commit()
    cfg.upsert_policy("pu", AutonomyPolicy(enabled=True, max_ops_per_round=3))
    cfg.upsert_policy("pu", AutonomyPolicy(enabled=False, max_ops_per_round=7))
    p = cfg.get_policy("pu")
    assert p.enabled is False and p.max_ops_per_round == 7


def test_list_enabled(isolated_db):
    from app.database import get_connection

    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('pa1', 'P', 'active')")
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('pa2', 'P', 'active')")
        conn.commit()
    cfg.upsert_policy("pa1", AutonomyPolicy(enabled=True))
    cfg.upsert_policy("pa2", AutonomyPolicy(enabled=False))
    ids = {row["project_id"] for row in cfg.list_enabled()}
    assert "pa1" in ids and "pa2" not in ids


from app.db import harness_evolution as evo


def _awaiting_round(project_id="pr", verdict=None, entries=1):
    from app.database import get_connection

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, status) VALUES (?, 'P', 'active')", (project_id,)
        )
        conn.commit()
    rid = evo.start_round(
        project_id=project_id,
        input_window_since=None,
        input_window_until=None,
        input_execution_count=0,
        input_forge={},
        scratch_dir="/tmp/x",
    )
    evo.mark_running(rid)
    evo.mark_awaiting_approval(
        rid, output_patch={"entries": [{"op": "create", "kind": "rule"}] * entries}
    )
    if verdict is not None:
        evo.store_eval_verdict(rid, verdict)
    return rid


def test_mark_applied_records_auto_fields(isolated_db):
    rid = _awaiting_round()
    evo.mark_applied(
        rid,
        output_patch={"entries": []},
        applied_asset_ids=[],
        notes="",
        auto_applied=True,
        auto_apply_reason={"eligible": True, "score": 0.9},
    )
    row = evo.get_round(rid)
    assert row["auto_applied"] == 1
    assert row["auto_apply_reason"]["score"] == 0.9


def test_mark_auto_apply_blocked(isolated_db):
    rid = _awaiting_round("prb")
    evo.mark_auto_apply_blocked(rid, {"eligible": False, "gate": "confidence"})
    row = evo.get_round(rid)
    assert row["status"] == "awaiting_approval"
    assert row["auto_apply_blocked_reason"]["gate"] == "confidence"


def test_count_recent_auto_applies(isolated_db):
    rid = _awaiting_round("prc")
    evo.mark_applied(
        rid,
        output_patch={"entries": []},
        applied_asset_ids=[],
        notes="",
        auto_applied=True,
        auto_apply_reason={"eligible": True},
    )
    assert evo.count_recent_auto_applies("prc", since="2000-01-01T00:00:00") >= 1
    # a far-future 'since' excludes it
    assert evo.count_recent_auto_applies("prc", since="2999-01-01T00:00:00") == 0


# ---------------------------------------------------------------------------
# Task 4: autonomous_apply_eligible
# ---------------------------------------------------------------------------
from app.services.harness_autonomy import autonomous_apply_eligible


def _round(entries, score=0.9, passed=True):
    return {
        "id": "r",
        "project_id": "p",
        "status": "awaiting_approval",
        "output_patch": {"entries": entries},
        "eval_verdict": {"passed": passed, "score": score, "per_check": []},
    }


def test_eligible_when_all_gates_pass(monkeypatch):
    monkeypatch.setenv("AGENTED_AUTONOMY", "1")
    policy = AutonomyPolicy(enabled=True, allowed_kinds=["rule"], confidence_threshold=0.85)
    rnd = _round([{"op": "create", "kind": "rule"}])
    d = autonomous_apply_eligible(rnd, policy, recent_auto_applies=0, recent_within_cooldown=False)
    assert d.eligible is True


def test_low_score_blocks(monkeypatch):
    monkeypatch.setenv("AGENTED_AUTONOMY", "1")
    policy = AutonomyPolicy(enabled=True, allowed_kinds=["rule"])
    d = autonomous_apply_eligible(
        _round([{"op": "create", "kind": "rule"}], score=0.4),
        policy,
        recent_auto_applies=0,
        recent_within_cooldown=False,
    )
    assert d.eligible is False
    assert any(g.name == "confidence" and not g.passed for g in d.gates)


def test_failed_verdict_blocks(monkeypatch):
    monkeypatch.setenv("AGENTED_AUTONOMY", "1")
    policy = AutonomyPolicy(enabled=True, allowed_kinds=["rule"])
    d = autonomous_apply_eligible(
        _round([{"op": "create", "kind": "rule"}], score=0.99, passed=False),
        policy,
        recent_auto_applies=0,
        recent_within_cooldown=False,
    )
    assert d.eligible is False
    assert any(g.name == "eval_present" and not g.passed for g in d.gates)


def test_kill_switch_blocks(monkeypatch):
    monkeypatch.setenv("AGENTED_AUTONOMY", "0")
    policy = AutonomyPolicy(enabled=True, allowed_kinds=["rule"])
    d = autonomous_apply_eligible(
        _round([{"op": "create", "kind": "rule"}]),
        policy,
        recent_auto_applies=0,
        recent_within_cooldown=False,
    )
    assert d.eligible is False and any(g.name == "kill_switch" and not g.passed for g in d.gates)


def test_disabled_policy_blocks(monkeypatch):
    monkeypatch.setenv("AGENTED_AUTONOMY", "1")
    policy = AutonomyPolicy(enabled=False, allowed_kinds=["rule"])
    d = autonomous_apply_eligible(
        _round([{"op": "create", "kind": "rule"}]),
        policy,
        recent_auto_applies=0,
        recent_within_cooldown=False,
    )
    assert d.eligible is False and any(g.name == "enabled" and not g.passed for g in d.gates)


def test_delete_blocked_by_default(monkeypatch):
    monkeypatch.setenv("AGENTED_AUTONOMY", "1")
    policy = AutonomyPolicy(enabled=True, allowed_kinds=["rule"], block_deletes=True)
    d = autonomous_apply_eligible(
        _round([{"op": "delete", "kind": "rule"}]),
        policy,
        recent_auto_applies=0,
        recent_within_cooldown=False,
    )
    assert d.eligible is False and any(g.name == "block_deletes" and not g.passed for g in d.gates)


def test_disallowed_kind_blocks(monkeypatch):
    monkeypatch.setenv("AGENTED_AUTONOMY", "1")
    policy = AutonomyPolicy(enabled=True, allowed_kinds=["rule"])
    d = autonomous_apply_eligible(
        _round([{"op": "create", "kind": "hook"}]),
        policy,
        recent_auto_applies=0,
        recent_within_cooldown=False,
    )
    assert d.eligible is False and any(g.name == "allowed_kinds" and not g.passed for g in d.gates)


def test_blast_radius_cooldown_rate_limit(monkeypatch):
    monkeypatch.setenv("AGENTED_AUTONOMY", "1")
    policy = AutonomyPolicy(
        enabled=True, allowed_kinds=["rule"], max_ops_per_round=2, rate_limit_per_day=3
    )
    big = _round([{"op": "create", "kind": "rule"}] * 5)
    assert (
        autonomous_apply_eligible(
            big, policy, recent_auto_applies=0, recent_within_cooldown=False
        ).eligible
        is False
    )
    ok = _round([{"op": "create", "kind": "rule"}])
    assert (
        autonomous_apply_eligible(
            ok, policy, recent_auto_applies=3, recent_within_cooldown=False
        ).eligible
        is False
    )
    assert (
        autonomous_apply_eligible(
            ok, policy, recent_auto_applies=0, recent_within_cooldown=True
        ).eligible
        is False
    )


# ---------------------------------------------------------------------------
# Task 5: process_project_autonomy poller
# ---------------------------------------------------------------------------
from unittest.mock import patch

from app.models.harness_evolution import CheckResult, EvalVerdict


def test_poller_auto_applies_eligible(isolated_db, monkeypatch):
    monkeypatch.setenv("AGENTED_AUTONOMY", "1")
    from app.db import project_autonomy_config as cfg
    from app.services.harness_autonomy import process_project_autonomy

    _awaiting_round(
        "ppa",
        verdict=EvalVerdict(
            passed=True, score=0.95, per_check=[CheckResult(name="s", passed=True)]
        ),
        entries=1,
    )
    cfg.upsert_policy("ppa", AutonomyPolicy(enabled=True, allowed_kinds=["rule"]))
    with patch("app.services.harness_autonomy.apply_dry_run_round") as mock_apply:
        process_project_autonomy("ppa")
    assert mock_apply.called
    _, kwargs = mock_apply.call_args
    assert kwargs.get("auto_applied") is True
    assert kwargs.get("auto_apply_reason") is not None


def test_poller_blocks_low_score(isolated_db, monkeypatch):
    monkeypatch.setenv("AGENTED_AUTONOMY", "1")
    from app.db import harness_evolution as evo
    from app.db import project_autonomy_config as cfg
    from app.services.harness_autonomy import process_project_autonomy

    rid = _awaiting_round(
        "ppb",
        verdict=EvalVerdict(passed=True, score=0.4, per_check=[CheckResult(name="s", passed=True)]),
        entries=1,
    )
    cfg.upsert_policy("ppb", AutonomyPolicy(enabled=True, allowed_kinds=["rule"]))
    with patch("app.services.harness_autonomy.apply_dry_run_round") as mock_apply:
        process_project_autonomy("ppb")
    assert not mock_apply.called
    assert evo.get_round(rid)["auto_apply_blocked_reason"] is not None


def test_poller_skips_disabled(isolated_db, monkeypatch):
    monkeypatch.setenv("AGENTED_AUTONOMY", "1")
    from app.db import project_autonomy_config as cfg
    from app.services.harness_autonomy import process_project_autonomy

    _awaiting_round("ppd", verdict=EvalVerdict(passed=True, score=0.95), entries=1)
    cfg.upsert_policy("ppd", AutonomyPolicy(enabled=False))
    with patch("app.services.harness_autonomy.apply_dry_run_round") as mock_apply:
        process_project_autonomy("ppd")
    assert not mock_apply.called


def test_poller_skips_empty_patch(isolated_db, monkeypatch):
    monkeypatch.setenv("AGENTED_AUTONOMY", "1")
    from app.db import project_autonomy_config as cfg
    from app.services.harness_autonomy import process_project_autonomy

    _awaiting_round("ppe", verdict=EvalVerdict(passed=True, score=0.99), entries=0)
    cfg.upsert_policy("ppe", AutonomyPolicy(enabled=True, allowed_kinds=["rule"]))
    with patch("app.services.harness_autonomy.apply_dry_run_round") as mock_apply:
        process_project_autonomy("ppe")
    assert not mock_apply.called  # 0-entry round must NOT auto-apply
