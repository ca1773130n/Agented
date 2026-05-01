"""Wave 47: end-to-end scoping for the batch-2 owned-entity routes."""

import pytest

from app.db.connection import get_connection
from app.db.rbac import create_user_role
from app.db.users import create_user


@pytest.fixture()
def two_users(client, isolated_db):
    alice = create_user("alice@example.com", "Alice")
    bob = create_user("bob@example.com", "Bob")
    create_user_role("alice-key", "Alice", "admin", user_id=alice)
    create_user_role("bob-key", "Bob", "admin", user_id=bob)
    return alice, bob


# (table, row_id_prefix, kwarg-style insert spec, response key in JSON, identifying field)
# For tables with TEXT id, we generate a unique row id; for INTEGER-id
# tables (hooks, commands, rules) SQLite assigns one via the autoincrement.
SEED_SPECS = {
    "super_agents": (
        "INSERT INTO super_agents (id, name, backend_type, user_id) VALUES (?, ?, ?, ?)",
        lambda label, rid: (rid, label, "claude", "user_id_placeholder"),
        "super_agents",
        "name",
        True,  # text id
    ),
    "hooks": (
        "INSERT INTO hooks (name, event, user_id) VALUES (?, ?, ?)",
        lambda label, _rid: (label, "PreToolUse", "user_id_placeholder"),
        "hooks",
        "name",
        False,
    ),
    "commands": (
        "INSERT INTO commands (name, user_id) VALUES (?, ?)",
        lambda label, _rid: (label, "user_id_placeholder"),
        "commands",
        "name",
        False,
    ),
    "rules": (
        "INSERT INTO rules (name, rule_type, user_id) VALUES (?, ?, ?)",
        lambda label, _rid: (label, "general", "user_id_placeholder"),
        "rules",
        "name",
        False,
    ),
    "sketches": (
        "INSERT INTO sketches (id, title, content, status, user_id) VALUES (?, ?, ?, ?, ?)",
        lambda label, rid: (rid, label, "body", "draft", "user_id_placeholder"),
        "sketches",
        "title",
        True,
    ),
    "workflows": (
        "INSERT INTO workflows (id, name, user_id) VALUES (?, ?, ?)",
        lambda label, rid: (rid, label, "user_id_placeholder"),
        "workflows",
        "name",
        True,
    ),
}


def _seed(table: str, row_id: str, label: str, user_id: str) -> None:
    sql, value_fn, *_ = SEED_SPECS[table]
    raw_values = list(value_fn(label, row_id))
    raw_values[-1] = user_id  # replace placeholder
    with get_connection() as conn:
        conn.execute(sql, tuple(raw_values))
        conn.commit()


@pytest.mark.parametrize(
    "url,table",
    [
        ("/admin/super-agents/", "super_agents"),
        ("/admin/hooks/", "hooks"),
        ("/admin/commands/", "commands"),
        ("/admin/rules/", "rules"),
        ("/admin/sketches/", "sketches"),
        ("/admin/workflows/", "workflows"),
    ],
)
def test_route_scoping_for_table(client, two_users, url, table):
    alice, bob = two_users
    spec = SEED_SPECS[table]
    response_key = spec[2]
    identifying_field = spec[3]
    _seed(table, f"{table[:3]}-aaaaaa", f"alice-{table}", alice)
    _seed(table, f"{table[:3]}-bbbbbb", f"bob-{table}", bob)

    resp = client.get(url, headers={"X-API-Key": "alice-key"})
    assert resp.status_code == 200, resp.data
    body = resp.get_json()
    rows = body[response_key]
    labels = {r[identifying_field] for r in rows if identifying_field in r}
    assert all("alice" in lbl for lbl in labels), (
        f"{url} leaked across users: {labels}"
    )
    assert not any("bob" in lbl for lbl in labels)
