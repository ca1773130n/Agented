from app.models.harness_evolution import ApplyJournalEntry, RevertResult


def test_apply_journal_entry_create():
    e = ApplyJournalEntry(kind="rule", op="create", asset_id="5", before=None)
    assert e.op == "create" and e.before is None


def test_apply_journal_entry_update_carries_before():
    e = ApplyJournalEntry(kind="rule", op="update", asset_id="5",
                          before={"name": "r", "action": "old"})
    assert e.before["action"] == "old"


def test_apply_journal_entry_rejects_bad_op():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ApplyJournalEntry(kind="rule", op="frobnicate", asset_id="5")


def test_revert_result_shape():
    r = RevertResult(status="reverted", reversed_count=3, git_reverted=True)
    assert r.status == "reverted"
    assert r.reversed_count == 3
    assert RevertResult.model_validate_json(r.model_dump_json()).git_reverted is True
