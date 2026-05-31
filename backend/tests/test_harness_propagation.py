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
