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
