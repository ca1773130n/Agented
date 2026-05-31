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
