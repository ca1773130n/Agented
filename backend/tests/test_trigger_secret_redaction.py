"""Regression: trigger read/list APIs must never return webhook_secret (H1).

The secret authenticates inbound webhooks; leaking it to a read-only viewer lets
them forge signed payloads. The internal dispatch path reads the secret from the
DB layer directly, which is unaffected.
"""

from app.services.trigger_service import TriggerService


def _make_webhook_trigger(secret: str = "super-secret-hmac") -> str:
    from app.db.triggers import create_trigger

    return create_trigger(
        name="redact-me",
        prompt_template="do {x}",
        backend_type="claude",
        trigger_source="webhook",
        webhook_secret=secret,
    )


def test_get_trigger_detail_redacts_secret(isolated_db):
    tid = _make_webhook_trigger()
    body, status = TriggerService.get_trigger_detail(tid)
    assert status == 200
    assert "webhook_secret" not in body
    assert body.get("has_webhook_secret") is True


def test_list_triggers_redacts_secret(isolated_db):
    _make_webhook_trigger()
    body, status = TriggerService.list_triggers()
    assert status == 200
    for trig in body["triggers"]:
        assert "webhook_secret" not in trig


def test_internal_dispatch_still_sees_secret(isolated_db):
    # The DB layer (used by the dispatcher) must still expose the secret.
    from app.db.triggers import get_trigger

    tid = _make_webhook_trigger("keep-me")
    row = get_trigger(tid)
    assert row["webhook_secret"] == "keep-me"
