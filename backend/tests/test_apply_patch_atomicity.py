"""Regression: apply_patch compensates on a mid-loop failure (C1).

A patch whose 2nd entry fails must not leave the 1st entry's mutation applied —
apply_patch reverses the partial journal and re-raises.
"""

from unittest.mock import patch

import pytest

import app.services.harness_evolver as hv


class _Entry:
    def __init__(self, op, kind, name=None, payload=None, existing_asset_id=None):
        self.op = op
        self.kind = kind
        self.name = name
        self.payload = payload or {}
        self.existing_asset_id = existing_asset_id


class _Patch:
    def __init__(self, entries):
        self.entries = entries


def test_midloop_failure_reverses_partial_journal(isolated_db):
    entries = [
        _Entry("create", "rule", name="r1", payload={"description": "first"}),
        _Entry("create", "hook", name="h1", payload={"event": "boom"}),
    ]

    calls = {"reverse_args": None}

    def _fake_reverse(project_id, journal):
        calls["reverse_args"] = (project_id, list(journal))
        return (len(journal), [])

    # First create succeeds (returns an id); second raises mid-loop.
    create_dispatch = {
        "rule": lambda **kw: "rule-123",
        "hook": lambda **kw: (_ for _ in ()).throw(RuntimeError("hook create blew up")),
    }

    with (
        patch.dict(hv._create_dispatch, create_dispatch),
        patch("app.services.harness_evolution_rollback.reverse_apply_journal", _fake_reverse),
        patch.object(hv.bindings_repo, "add_binding", lambda *a, **k: None),
    ):
        with pytest.raises(RuntimeError, match="hook create blew up"):
            hv.apply_patch(_Patch(entries), project_id="proj-xyz")

    # The compensating rollback ran with the partial journal (the 1st create).
    assert calls["reverse_args"] is not None
    pid, journal = calls["reverse_args"]
    assert pid == "proj-xyz"
    assert len(journal) == 1
    assert journal[0]["kind"] == "rule"
    assert journal[0]["op"] == "create"


def test_incomplete_rollback_raises_partial_apply_error(isolated_db):
    """When reverse_apply_journal reports failures, apply_patch raises
    PartialApplyError carrying the residual journal (durable rollback, HIGH)."""
    entries = [
        _Entry("create", "rule", name="r1", payload={"description": "first"}),
        _Entry("create", "hook", name="h1", payload={"event": "boom"}),
    ]

    def _fake_reverse(project_id, journal):
        # Rollback could not reverse the entry → 0 reversed, 1 failure.
        return (0, [{"entry": journal[0], "error": "reverse blew up"}])

    create_dispatch = {
        "rule": lambda **kw: "rule-123",
        "hook": lambda **kw: (_ for _ in ()).throw(RuntimeError("hook create blew up")),
    }

    with (
        patch.dict(hv._create_dispatch, create_dispatch),
        patch("app.services.harness_evolution_rollback.reverse_apply_journal", _fake_reverse),
        patch.object(hv.bindings_repo, "add_binding", lambda *a, **k: None),
    ):
        with pytest.raises(hv.PartialApplyError) as ei:
            hv.apply_patch(_Patch(entries), project_id="proj-xyz")

    # Residual journal is carried so the caller can persist it for later revert.
    assert len(ei.value.residual_journal) == 1
    assert ei.value.residual_journal[0]["kind"] == "rule"


def test_clean_patch_returns_applied_and_journal(isolated_db):
    entries = [_Entry("create", "rule", name="ok", payload={"description": "fine"})]
    create_dispatch = {"rule": lambda **kw: "rule-ok"}
    with (
        patch.dict(hv._create_dispatch, create_dispatch),
        patch.object(hv.bindings_repo, "add_binding", lambda *a, **k: None),
    ):
        applied, journal = hv.apply_patch(_Patch(entries), project_id="proj-1")
    assert applied == [{"kind": "rule", "op": "create", "asset_id": "rule-ok"}]
    assert journal[0]["op"] == "create"
