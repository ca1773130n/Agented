"""PolicyService.evaluate — stacking + short-circuit unit tests (SC1).

The locked invariant: evaluation walks scopes in order [session, team, server]
(SESSION first — the stricter scope, per the standing session-not-bot rule),
reads enabled rows per scope ORDER BY priority DESC, and returns the FIRST DENY
immediately without consulting any later scope. A session-scope DENY therefore
short-circuits a server-scope ALLOW. ASK is collected (first wins) only if no
DENY is found; ALLOW is the default fall-through.

These tests seed rows directly into the ``policies`` table (migration 176) via
the isolated_db fixture and assert the PolicyVerdict dict shape. Short-circuit
is proven by spying on PolicyService._rows_for and asserting "server" is never
queried after a session DENY.
"""


def _seed(scope, scope_id, effect, *, kind="manual", priority=0, enabled=1):
    from app.services.policy_service import PolicyService

    return PolicyService.create_policy(
        scope=scope,
        scope_id=scope_id,
        kind=kind,
        effect=effect,
        priority=priority,
        enabled=enabled,
    )


def test_session_deny_short_circuits_server_allow(isolated_db, monkeypatch):
    from app.services.policy_service import PolicyService

    _seed("server", None, "allow")
    session_row = _seed("session", "sess-aaa", "deny")

    # Spy: record the scopes _rows_for is consulted with.
    original = PolicyService._rows_for.__func__
    seen_scopes = []

    @classmethod
    def spy(cls, scope, scope_id):
        seen_scopes.append(scope)
        return original(cls, scope, scope_id)

    monkeypatch.setattr(PolicyService, "_rows_for", spy)

    verdict = PolicyService.evaluate(session_id="sess-aaa", team_id=None, action={})

    assert verdict["decision"] == "deny"
    assert verdict["scope"] == "session"
    assert verdict["policy_id"] == session_row["id"]
    # Short-circuit: server scope is NEVER consulted after the session DENY.
    assert "server" not in seen_scopes, f"server should not be queried; saw {seen_scopes}"


def test_session_ask_collected_over_server_allow(isolated_db):
    from app.services.policy_service import PolicyService

    _seed("server", None, "allow")
    _seed("session", "sess-bbb", "ask")

    verdict = PolicyService.evaluate(session_id="sess-bbb", team_id=None, action={})

    assert verdict["decision"] == "ask"
    assert verdict["scope"] == "session"


def test_only_server_allow_falls_through(isolated_db):
    from app.services.policy_service import PolicyService

    _seed("server", None, "allow")

    verdict = PolicyService.evaluate(session_id="sess-ccc", team_id=None, action={})

    # ALLOW rows do not short-circuit; default ALLOW fall-through (scope None).
    assert verdict["decision"] == "allow"
    assert verdict["scope"] is None


def test_no_rows_defaults_to_allow(isolated_db):
    from app.services.policy_service import PolicyService

    verdict = PolicyService.evaluate(session_id="sess-ddd", team_id=None, action={})

    assert verdict == {
        "decision": "allow",
        "policy_id": None,
        "kind": None,
        "reason": verdict["reason"],
        "scope": None,
    }
    assert verdict["decision"] == "allow"


def test_team_deny_when_no_session_row(isolated_db):
    from app.services.policy_service import PolicyService

    team_row = _seed("team", "team-xyz", "deny")

    verdict = PolicyService.evaluate(session_id="sess-eee", team_id="team-xyz", action={})

    assert verdict["decision"] == "deny"
    assert verdict["scope"] == "team"
    assert verdict["policy_id"] == team_row["id"]


def test_policy_denied_is_exported():
    from app.services.policy_service import PolicyDenied

    assert issubclass(PolicyDenied, Exception)


def test_crud_roundtrip(isolated_db):
    from app.services.policy_service import PolicyService

    created = PolicyService.create_policy(
        scope="session", scope_id="sess-crud", kind="manual", effect="deny"
    )
    assert created["id"].startswith("pol-")

    fetched = PolicyService.get_policy(created["id"])
    assert fetched["effect"] == "deny"
    assert fetched["scope"] == "session"

    PolicyService.update_policy(created["id"], effect="allow")
    assert PolicyService.get_policy(created["id"])["effect"] == "allow"

    listed = PolicyService.list_policies(scope="session")
    assert any(p["id"] == created["id"] for p in listed)

    PolicyService.delete_policy(created["id"])
    assert PolicyService.get_policy(created["id"]) is None


def test_priority_orders_rows_desc(isolated_db):
    """Higher priority is evaluated first within a scope."""
    from app.services.policy_service import PolicyService

    _seed("session", "sess-prio", "allow", priority=1)
    _seed("session", "sess-prio", "deny", priority=10)

    verdict = PolicyService.evaluate(session_id="sess-prio", team_id=None, action={})
    # The deny (priority 10) is seen first -> short-circuit deny.
    assert verdict["decision"] == "deny"


def test_disabled_rows_are_ignored(isolated_db):
    from app.services.policy_service import PolicyService

    _seed("session", "sess-dis", "deny", enabled=0)

    verdict = PolicyService.evaluate(session_id="sess-dis", team_id=None, action={})
    assert verdict["decision"] == "allow"
