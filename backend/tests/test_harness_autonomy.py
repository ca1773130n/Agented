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
