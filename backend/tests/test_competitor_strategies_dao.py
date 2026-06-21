"""Competitor-strategy DAO tests (phase 26) — the §5B legal gate is the headline.

Covers: create → 'proposed' round-trip; the status machine + illegal-transition
ValueErrors; the NON-BYPASSABLE legal gate (mark_implementing raises
LegalGateNotCleared with no status mutation until all 7 items affirmed, then
succeeds); record_legal_item validation + the 6/7-still-locked rule; and
edit-resets-clearance (update_body NULLs clearance and re-locks the gate).
"""

import pytest

from app.db import competitor_strategies as dao
from app.db.competitor_strategies import LEGAL_CHECKLIST_ITEMS, LegalGateNotCleared


def _seed_project(name: str) -> str:
    from app.db.projects import create_project

    return create_project(name=name)


def _affirm_all(strategy_id, project_id=None):
    row = None
    for item in LEGAL_CHECKLIST_ITEMS:
        row = dao.record_legal_item(strategy_id, item, True, project_id=project_id)
    return row


def test_create_strategy_proposed_round_trip(isolated_db):
    project_id = _seed_project("CS create")
    row = dao.create_strategy(
        project_id,
        signal_ids=["csig-aaa", "csig-bbb"],
        title="Ship faster onboarding",
        body="behavior-level proposal",
        backend_kind="claude",
        model="claude-x",
    )
    assert row["id"].startswith("cstr-")
    assert row["project_id"] == project_id
    assert row["status"] == "proposed"
    assert row["signal_ids"] == ["csig-aaa", "csig-bbb"]  # JSON round-trip
    assert row["legal_cleared_at"] is None
    assert row["backend_kind"] == "claude"
    assert row["model"] == "claude-x"

    # exactly one row for this project
    rows = dao.list_strategies(project_id)
    assert len(rows) == 1
    assert rows[0]["id"] == row["id"]


def test_set_status_legal_transitions(isolated_db):
    project_id = _seed_project("CS status")
    row = dao.create_strategy(project_id, signal_ids=["csig-1"])
    updated = dao.set_status(row["id"], "approved")
    assert updated["status"] == "approved"


def test_set_status_illegal_jump_raises(isolated_db):
    project_id = _seed_project("CS illegal")
    row = dao.create_strategy(project_id, signal_ids=["csig-1"])
    # proposed -> implementing is illegal (and gated): must NOT be reachable here
    with pytest.raises(ValueError):
        dao.set_status(row["id"], "implementing")
    # approved -> done skips implementing: illegal
    dao.set_status(row["id"], "approved")
    with pytest.raises(ValueError):
        dao.set_status(row["id"], "done")
    # status unchanged after the failed jumps
    assert dao.get_strategy(row["id"])["status"] == "approved"


def test_legal_gate_hard_block_then_clear(isolated_db):
    """The non-bypassable gate: mark_implementing raises until 7/7, then succeeds."""
    project_id = _seed_project("CS gate")
    row = dao.create_strategy(project_id, signal_ids=["csig-1"])
    dao.set_status(row["id"], "approved")

    # <7 items affirmed -> hard block, NO status mutation
    with pytest.raises(LegalGateNotCleared):
        dao.mark_implementing(row["id"])
    assert dao.get_strategy(row["id"])["status"] == "approved"

    # affirm all 7 -> legal_cleared_at set
    cleared = _affirm_all(row["id"])
    assert cleared["legal_cleared_at"] is not None

    # now the gate opens
    impl = dao.mark_implementing(row["id"])
    assert impl["status"] == "implementing"

    # implementing -> done is legal
    done = dao.set_status(row["id"], "done")
    assert done["status"] == "done"


def test_record_legal_item_unknown_key_raises(isolated_db):
    project_id = _seed_project("CS unknown item")
    row = dao.create_strategy(project_id, signal_ids=["csig-1"])
    with pytest.raises(ValueError):
        dao.record_legal_item(row["id"], "not_a_real_item", True)


def test_six_of_seven_leaves_clearance_null(isolated_db):
    project_id = _seed_project("CS sixofseven")
    row = dao.create_strategy(project_id, signal_ids=["csig-1"])
    for item in LEGAL_CHECKLIST_ITEMS[:-1]:  # affirm 6 of 7
        last = dao.record_legal_item(row["id"], item, True)
    assert last["legal_cleared_at"] is None
    # affirming the 7th flips clearance on
    final = dao.record_legal_item(row["id"], LEGAL_CHECKLIST_ITEMS[-1], True)
    assert final["legal_cleared_at"] is not None


def test_deny_after_clearance_relocks_gate(isolated_db):
    project_id = _seed_project("CS deny")
    row = dao.create_strategy(project_id, signal_ids=["csig-1"])
    dao.set_status(row["id"], "approved")
    _affirm_all(row["id"])
    # deny one item -> clearance NULLed
    relocked = dao.record_legal_item(row["id"], "patent_fto", False)
    assert relocked["legal_cleared_at"] is None
    with pytest.raises(LegalGateNotCleared):
        dao.mark_implementing(row["id"])


def test_edit_resets_clearance(isolated_db):
    """update_body NULLs clearance AND flips authorship/copied-code items false."""
    project_id = _seed_project("CS editreset")
    row = dao.create_strategy(project_id, signal_ids=["csig-1"], body="v1")
    dao.set_status(row["id"], "approved")
    _affirm_all(row["id"])
    assert dao.get_strategy(row["id"])["legal_cleared_at"] is not None

    edited = dao.update_body(row["id"], body="v2 — revised plan")
    assert edited["body"] == "v2 — revised plan"
    assert edited["legal_cleared_at"] is None
    assert edited["legal_checklist"]["independent_authorship"] is False
    assert edited["legal_checklist"]["no_copied_code"] is False
    # other affirmed items survive the edit
    assert edited["legal_checklist"]["clean_room"] is True

    # the gate is re-locked
    with pytest.raises(LegalGateNotCleared):
        dao.mark_implementing(row["id"])


def test_list_strategies_project_scoped_and_filtered(isolated_db):
    project_a = _seed_project("CS proj A")
    project_b = _seed_project("CS proj B")
    a1 = dao.create_strategy(project_a, signal_ids=["csig-a1"])
    a2 = dao.create_strategy(project_a, signal_ids=["csig-a2"])
    dao.create_strategy(project_b, signal_ids=["csig-b1"])

    # project-scoped: only project_a's rows
    rows_a = dao.list_strategies(project_a)
    assert {r["id"] for r in rows_a} == {a1["id"], a2["id"]}
    # newest first (a2 created after a1)
    assert rows_a[0]["id"] == a2["id"]

    # status filter
    dao.set_status(a1["id"], "approved")
    approved = dao.list_strategies(project_a, statuses=["approved"])
    assert {r["id"] for r in approved} == {a1["id"]}


def test_get_strategy_project_scoped_idor(isolated_db):
    project_a = _seed_project("CS idor A")
    project_b = _seed_project("CS idor B")
    a = dao.create_strategy(project_a, signal_ids=["csig-a"])
    # foreign project scope returns None (IDOR guard)
    assert dao.get_strategy(a["id"], project_id=project_b) is None
    assert dao.get_strategy(a["id"], project_id=project_a)["id"] == a["id"]


# ---------------------------------------------------------------------------
# §5B gate-bypass regression: only Python True affirms — truthy junk must NOT.
# A caller must not be able to "affirm" all 7 items with "false"/"0"/0/1/"true"
# and slip past the legal gate (legal_cleared_at must stay NULL).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("junk", ["false", "0", "no", "true", 0, 1, "yes", [], {}, None])
def test_record_legal_item_truthy_junk_does_not_affirm(isolated_db, junk):
    """Non-``True`` values (even truthy ones like ``1``/``"true"``) never affirm."""
    project_id = _seed_project("CS junk")
    row = dao.create_strategy(project_id, signal_ids=["csig-1"])
    # affirm 6 of 7 with real True, then pass junk for the 7th
    for item in LEGAL_CHECKLIST_ITEMS[:-1]:
        dao.record_legal_item(row["id"], item, True, project_id=project_id)
    out = dao.record_legal_item(row["id"], LEGAL_CHECKLIST_ITEMS[-1], junk, project_id=project_id)
    # the 7th item is NOT affirmed → stored as False, gate stays NULL
    assert out["legal_checklist"][LEGAL_CHECKLIST_ITEMS[-1]] is False
    assert out["legal_cleared_at"] is None
    # and the hard gate still blocks
    dao.set_status(row["id"], "approved", project_id=project_id)
    with pytest.raises(LegalGateNotCleared):
        dao.mark_implementing(row["id"], project_id=project_id)


def test_record_legal_item_only_true_affirms_and_clears_at_seven(isolated_db):
    """Exactly Python ``True`` x7 is the ONLY thing that sets legal_cleared_at."""
    project_id = _seed_project("CS true7")
    row = dao.create_strategy(project_id, signal_ids=["csig-1"])
    last = None
    for item in LEGAL_CHECKLIST_ITEMS:
        last = dao.record_legal_item(row["id"], item, True, project_id=project_id)
        assert last["legal_checklist"][item] is True
    assert last["legal_cleared_at"] is not None


def test_record_legal_item_string_true_does_not_clear_full_checklist(isolated_db):
    """All 7 items set to the STRING ``"true"`` must NOT clear the gate."""
    project_id = _seed_project("CS strtrue")
    row = dao.create_strategy(project_id, signal_ids=["csig-1"])
    last = None
    for item in LEGAL_CHECKLIST_ITEMS:
        last = dao.record_legal_item(row["id"], item, "true", project_id=project_id)
    assert last["legal_cleared_at"] is None
    dao.set_status(row["id"], "approved", project_id=project_id)
    with pytest.raises(LegalGateNotCleared):
        dao.mark_implementing(row["id"], project_id=project_id)


def test_mark_implementing_atomic_gate_is_only_path(isolated_db):
    """The atomic UPDATE: approved+cleared → implementing; uncleared/not-approved
    raise the precise exception with NO status mutation."""
    project_id = _seed_project("CS atomic")

    # not-approved → ValueError, status unchanged
    r1 = dao.create_strategy(project_id, signal_ids=["csig-1"])
    with pytest.raises(ValueError):
        dao.mark_implementing(r1["id"], project_id=project_id)
    assert dao.get_strategy(r1["id"], project_id=project_id)["status"] == "proposed"

    # approved + uncleared → LegalGateNotCleared, status stays 'approved'
    dao.set_status(r1["id"], "approved", project_id=project_id)
    with pytest.raises(LegalGateNotCleared):
        dao.mark_implementing(r1["id"], project_id=project_id)
    assert dao.get_strategy(r1["id"], project_id=project_id)["status"] == "approved"
    assert dao.get_strategy(r1["id"], project_id=project_id)["legal_cleared_at"] is None

    # approved + cleared → implementing (the only path)
    _affirm_all(r1["id"], project_id=project_id)
    impl = dao.mark_implementing(r1["id"], project_id=project_id)
    assert impl["status"] == "implementing"


def test_mark_implementing_not_found_raises(isolated_db):
    """Missing strategy → ValueError 'not found' (no row mutated)."""
    project_id = _seed_project("CS missing")
    with pytest.raises(ValueError, match="not found"):
        dao.mark_implementing("cstr-doesnotexist", project_id=project_id)
