from app.db import forge_promotion as fp
from app.services.forge_fingerprint import fingerprint


def test_fingerprint_stable_for_same_content():
    a = {"name": "r", "rule_type": "validation", "description": "d", "action": "x", "enabled": 1}
    b = {
        "name": "r",
        "rule_type": "validation",
        "description": "d",
        "action": "x",
        "enabled": 1,
        "id": 9,
    }
    # id/timestamps don't change the fingerprint; only content fields matter
    assert fingerprint("rule", a) == fingerprint("rule", b)


def test_fingerprint_differs_on_content_change():
    a = {"name": "r", "rule_type": "validation", "action": "x"}
    b = {"name": "r", "rule_type": "validation", "action": "y"}
    assert fingerprint("rule", a) != fingerprint("rule", b)


def test_fingerprint_includes_kind():
    payload = {"name": "x", "description": "d", "content": "c"}
    assert fingerprint("hook", payload) != fingerprint("command", payload)


def test_fingerprint_name_matters():
    a = {"name": "alpha", "rule_type": "validation", "action": "x"}
    b = {"name": "beta", "rule_type": "validation", "action": "x"}
    assert fingerprint("rule", a) != fingerprint("rule", b)


def test_record_evidence_and_score(isolated_db):
    fp.record_evidence(
        fingerprint="fp1", kind="rule", asset_id="1", project_id="p1", eval_score=0.9
    )
    fp.record_evidence(
        fingerprint="fp1", kind="rule", asset_id="2", project_id="p2", eval_score=0.8
    )
    score = fp.promotion_score("fp1", half_life_days=30)
    assert 1.6 <= score <= 1.8  # age ~0 → ~0.9 + 0.8


def test_promotion_score_decays_with_age(isolated_db):
    from app.database import get_connection

    fp.record_evidence(
        fingerprint="fpOld", kind="rule", asset_id="1", project_id="p", eval_score=1.0
    )
    # backdate the evidence 30 days → decayed to ~0.5 (one half life)
    with get_connection() as conn:
        conn.execute(
            "UPDATE forge_promotion_evidence SET created_at = datetime('now','-30 days')"
            " WHERE fingerprint='fpOld'"
        )
        conn.commit()
    assert 0.4 <= fp.promotion_score("fpOld", half_life_days=30) <= 0.6


def test_create_and_list_shared_binding(isolated_db):
    sbid = fp.create_shared_binding(scope="global", kind="rule", asset_id="9", fingerprint="fp1")
    assert sbid is not None
    rows = fp.list_shared_bindings(enabled_only=True)
    assert any(r["id"] == sbid and r["fingerprint"] == "fp1" for r in rows)
    # UNIQUE(scope,kind,fingerprint): re-create returns the SAME id (idempotent)
    assert (
        fp.create_shared_binding(scope="global", kind="rule", asset_id="9", fingerprint="fp1")
        == sbid
    )


def test_get_shared_binding(isolated_db):
    sbid = fp.create_shared_binding(scope="global", kind="hook", asset_id="3", fingerprint="fpH")
    b = fp.get_shared_binding(sbid)
    assert b["kind"] == "hook" and b["asset_id"] == "3"


def test_record_adoption_idempotent(isolated_db):
    sbid = fp.create_shared_binding(scope="global", kind="rule", asset_id="9", fingerprint="fpA")
    fp.record_adoption(project_id="padopt", shared_binding_id=sbid)
    fp.record_adoption(project_id="padopt", shared_binding_id=sbid)  # idempotent
    assert fp.is_adopted("padopt", sbid) is True
    assert fp.is_adopted("other", sbid) is False


# ---------------------------------------------------------------------------
# Task 3 — project_forge_bindings propagation columns
# ---------------------------------------------------------------------------
from app.database import get_connection
from app.db import project_forge_bindings as bindings_repo


def test_add_binding_records_source_scope(isolated_db):
    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('ps', 'P', 'active')")
        conn.commit()
    bid = bindings_repo.add_binding(
        "ps",
        "rule",
        "9",
        source_scope="shared",
        source_shared_binding_id=3,
        fingerprint="fpX",
    )
    b = bindings_repo.get_binding(bid["id"])
    assert b["source_scope"] == "shared"
    assert b["source_shared_binding_id"] == 3
    assert b["fingerprint"] == "fpX"


def test_default_source_scope_is_project(isolated_db):
    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('pp', 'P', 'active')")
        conn.commit()
    bid = bindings_repo.add_binding("pp", "rule", "1")
    b = bindings_repo.get_binding(bid["id"])
    assert b["source_scope"] == "project"
    assert b["source_shared_binding_id"] is None
    assert b.get("fingerprint") is None


def test_list_bindings_returns_propagation_fields(isolated_db):
    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('pl', 'P', 'active')")
        conn.commit()
    bindings_repo.add_binding("pl", "rule", "1", source_scope="shared", fingerprint="fpY")
    rows = bindings_repo.list_bindings("pl")
    assert rows and rows[0]["source_scope"] == "shared" and rows[0]["fingerprint"] == "fpY"
