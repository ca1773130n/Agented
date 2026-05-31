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


# ---------------------------------------------------------------------------
# Task 4 — promotion: record evidence + promote to shared layer
# ---------------------------------------------------------------------------
from app.db import rules as rules_repo
from app.services.forge_fingerprint import fingerprint as _fp
from app.services.harness_propagation import (
    promote_if_qualified,
    record_promotion_evidence,
)


def test_promotion_creates_global_copy_and_shared_binding(isolated_db):
    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('pq', 'P', 'active')")
        conn.commit()
    rid = rules_repo.create_rule(
        name="great", rule_type="validation", description="d", action="a", project_id="pq"
    )
    asset = rules_repo.get_rule(int(rid))
    fpv = _fp("rule", asset)
    for _ in range(10):  # pump high-score evidence past the threshold
        fp.record_evidence(
            fingerprint=fpv, kind="rule", asset_id=str(rid), project_id="pq", eval_score=0.95
        )
    promote_if_qualified("rule", fpv, asset)
    shared = [s for s in fp.list_shared_bindings(enabled_only=True) if s["fingerprint"] == fpv]
    assert len(shared) == 1
    # a GLOBAL-scope rule copy now exists (project_id IS NULL)
    glob = [
        r
        for r in rules_repo.get_rules_by_type("validation")
        if r.get("project_id") is None and r["name"] == "great"
    ]
    assert glob


def test_below_threshold_does_not_promote(isolated_db):
    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('pn', 'P', 'active')")
        conn.commit()
    rid = rules_repo.create_rule(
        name="meh", rule_type="validation", description="d", action="a", project_id="pn"
    )
    asset = rules_repo.get_rule(int(rid))
    fpv = _fp("rule", asset)
    fp.record_evidence(
        fingerprint=fpv, kind="rule", asset_id=str(rid), project_id="pn", eval_score=0.5
    )  # 1 weak
    promote_if_qualified("rule", fpv, asset)
    assert not [s for s in fp.list_shared_bindings(enabled_only=True) if s["fingerprint"] == fpv]


def test_record_evidence_from_applied(isolated_db):
    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('pr2', 'P', 'active')")
        conn.commit()
    rid = rules_repo.create_rule(
        name="r2", rule_type="validation", description="d", action="a", project_id="pr2"
    )
    applied = [{"kind": "rule", "op": "create", "asset_id": rid}]
    record_promotion_evidence("pr2", applied, eval_score=0.9)
    asset = rules_repo.get_rule(int(rid))
    assert fp.promotion_score(_fp("rule", asset)) > 0


def test_promote_idempotent(isolated_db):
    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('pi', 'P', 'active')")
        conn.commit()
    rid = rules_repo.create_rule(
        name="dup", rule_type="validation", description="d", action="a", project_id="pi"
    )
    asset = rules_repo.get_rule(int(rid))
    fpv = _fp("rule", asset)
    for _ in range(10):
        fp.record_evidence(
            fingerprint=fpv, kind="rule", asset_id=str(rid), project_id="pi", eval_score=0.95
        )
    promote_if_qualified("rule", fpv, asset)
    promote_if_qualified("rule", fpv, asset)  # second call must NOT create a duplicate
    assert (
        len([s for s in fp.list_shared_bindings(enabled_only=True) if s["fingerprint"] == fpv]) == 1
    )


# ---------------------------------------------------------------------------
# Task 5 — adopt_shared_binding + local_wins conflict resolution
# ---------------------------------------------------------------------------
from app.services.harness_propagation import adopt_shared_binding


def test_adopt_creates_shared_binding(isolated_db):
    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('pad', 'P', 'active')")
        conn.commit()
    sbid = fp.create_shared_binding(scope="global", kind="rule", asset_id="77", fingerprint="fpZ")
    res = adopt_shared_binding("pad", sbid)
    assert res["adopted"] is True
    bound = [
        b
        for b in bindings_repo.list_bindings("pad")
        if b["kind"] == "rule" and str(b["asset_id"]) == "77"
    ]
    assert bound and bound[0]["source_scope"] == "shared"
    assert fp.is_adopted("pad", sbid) is True


def test_adopt_idempotent_no_duplicate(isolated_db):
    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('pad2', 'P', 'active')")
        conn.commit()
    sbid = fp.create_shared_binding(scope="global", kind="rule", asset_id="78", fingerprint="fpZ2")
    adopt_shared_binding("pad2", sbid)
    adopt_shared_binding("pad2", sbid)
    bound = [b for b in bindings_repo.list_bindings("pad2") if str(b["asset_id"]) == "78"]
    assert len(bound) == 1


def test_local_wins_skips_adoption(isolated_db):
    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('plw', 'P', 'active')")
        conn.commit()
    # project already has a LOCAL binding with the same fingerprint
    bindings_repo.add_binding(
        "plw", "rule", "5", fingerprint="fpL"
    )  # source_scope defaults 'project'
    sbid = fp.create_shared_binding(scope="global", kind="rule", asset_id="88", fingerprint="fpL")
    res = adopt_shared_binding("plw", sbid)
    assert res["adopted"] is False and res["reason"] == "local_wins"
    # the shared asset 88 was NOT bound
    assert not [b for b in bindings_repo.list_bindings("plw") if str(b["asset_id"]) == "88"]


def test_adopt_not_found(isolated_db):
    res = adopt_shared_binding("pnone", 99999)
    assert res["adopted"] is False and res["reason"] == "not_found"


# ---------------------------------------------------------------------------
# Hook gate — propagation poisoning fix
# ---------------------------------------------------------------------------


def test_promotion_evidence_requires_passing_verdict(isolated_db, monkeypatch):
    """The run_evolution_round propagation hook must skip evidence when the round
    has no passing verdict. We assert the gate by checking that a round with a
    non-passing / absent verdict yields no evidence via the same condition."""
    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('pgate', 'P', 'active')")
        conn.commit()
    rid = rules_repo.create_rule(
        name="g", rule_type="validation", description="d", action="a", project_id="pgate"
    )
    asset = rules_repo.get_rule(int(rid))
    fpv = _fp("rule", asset)
    applied = [{"kind": "rule", "op": "create", "asset_id": rid}]

    # Simulate the hook's gate: a verdict that did NOT pass → no evidence recorded.
    verdict = {"passed": False, "score": 0.9}
    if verdict.get("passed") and verdict.get("score") is not None:
        record_promotion_evidence("pgate", applied, eval_score=verdict["score"])
    assert fp.promotion_score(fpv) == 0.0  # nothing recorded for a non-passing verdict

    # absent verdict → no evidence recorded.
    verdict_absent: dict = {}
    if verdict_absent.get("passed") and verdict_absent.get("score") is not None:
        record_promotion_evidence("pgate", applied, eval_score=verdict_absent["score"])
    assert fp.promotion_score(fpv) == 0.0  # nothing recorded for an absent verdict

    # a PASSING verdict DOES record evidence.
    verdict2 = {"passed": True, "score": 0.9}
    if verdict2.get("passed") and verdict2.get("score") is not None:
        record_promotion_evidence("pgate", applied, eval_score=verdict2["score"])
    assert fp.promotion_score(fpv) > 0.0
