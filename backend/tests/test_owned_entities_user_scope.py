"""Verify the user_id column + scoping helper work across the batch-1
owned-entity tables (track B, wave 41)."""

import pytest

from app.db.connection import get_connection
from app.db.owned_entities import _VALID_TABLES, count_for_user, get_for_user
from app.db.users import create_user

BATCH_1 = ["projects", "teams", "agents", "plugins", "super_agents"]
BATCH_2 = [
    "hooks",
    "commands",
    "rules",
    "triggers",
    "mcp_servers",
    "sketches",
    "workflows",
    "user_skills",
    "agent_conversations",
    "design_conversations",
]
ALL_TABLES = BATCH_1 + BATCH_2


@pytest.mark.parametrize("table", ALL_TABLES)
def test_table_has_user_id_column(table, isolated_db):
    with get_connection() as conn:
        cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    assert "user_id" in cols, f"{table} missing user_id column"


@pytest.mark.parametrize("table", ALL_TABLES)
def test_user_id_index_present(table, isolated_db):
    with get_connection() as conn:
        idx_names = {row[1] for row in conn.execute("PRAGMA index_list(" + table + ")")}
    assert f"idx_{table}_user_id" in idx_names


def test_get_for_user_isolation(isolated_db):
    alice = create_user("alice@example.com", "Alice")
    bob = create_user("bob@example.com", "Bob")
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO teams (id, name, user_id) VALUES (?, ?, ?)",
            ("team-aaa111", "Alice Team", alice),
        )
        conn.execute(
            "INSERT INTO teams (id, name, user_id) VALUES (?, ?, ?)",
            ("team-bbb222", "Bob Team", bob),
        )
        conn.commit()

    alice_rows = get_for_user("teams", alice)
    bob_rows = get_for_user("teams", bob)
    assert {r["id"] for r in alice_rows} == {"team-aaa111"}
    assert {r["id"] for r in bob_rows} == {"team-bbb222"}


def test_count_for_user(isolated_db):
    alice = create_user("alice@example.com", "Alice")
    with get_connection() as conn:
        for n in range(3):
            conn.execute(
                "INSERT INTO teams (id, name, user_id) VALUES (?, ?, ?)",
                (f"team-c{n:05d}", f"T{n}", alice),
            )
        conn.commit()
    assert count_for_user("teams", alice) == 3


def test_unknown_table_rejected(isolated_db):
    with pytest.raises(ValueError):
        get_for_user("not_a_real_table", "user-x")
    with pytest.raises(ValueError):
        count_for_user("also_fake", "user-x")


def test_valid_tables_includes_batch1():
    for t in BATCH_1:
        assert t in _VALID_TABLES


# ---------------------------------------------------------------------------
# Server-side search + sort (server-search-sort feature)
# ---------------------------------------------------------------------------


def _seed_teams(user_id, names):
    import uuid

    with get_connection() as conn:
        for name in names:
            conn.execute(
                "INSERT INTO teams (id, name, description, user_id) VALUES (?, ?, ?, ?)",
                (f"team-{uuid.uuid4().hex[:8]}", name, f"desc for {name}", user_id),
            )
        conn.commit()


def test_get_for_user_search_finds_off_page_row(isolated_db):
    """Search must find a row that is NOT on the first paginated page."""
    alice = create_user("alice@example.com", "Alice")
    # Deterministic ids: 25 fillers sort (default id ASC) before the needle,
    # so the needle is guaranteed off the first 10-row page.
    with get_connection() as conn:
        for i in range(25):
            conn.execute(
                "INSERT INTO teams (id, name, description, user_id) VALUES (?, ?, ?, ?)",
                (f"team-a{i:05d}", f"filler-{i:02d}", "filler", alice),
            )
        conn.execute(
            "INSERT INTO teams (id, name, description, user_id) VALUES (?, ?, ?, ?)",
            ("team-z99999", "needle-team", "the unique target", alice),
        )
        conn.commit()

    page1 = get_for_user("teams", alice, limit=10, offset=0)
    assert "needle-team" not in [r["name"] for r in page1]

    found = get_for_user("teams", alice, limit=10, offset=0, search="needle")
    assert "needle-team" in [r["name"] for r in found]

    # Description match also works.
    found_desc = get_for_user("teams", alice, limit=10, offset=0, search="unique target")
    assert "needle-team" in [r["name"] for r in found_desc]


def test_count_for_user_reflects_search(isolated_db):
    alice = create_user("alice@example.com", "Alice")
    _seed_teams(alice, [f"alpha-{i}" for i in range(5)] + ["zzz-special"])
    assert count_for_user("teams", alice, search="special") == 1
    assert count_for_user("teams", alice, search="alpha") == 5
    assert count_for_user("teams", alice) == 6


def test_get_for_user_sort_by_name(isolated_db):
    alice = create_user("alice@example.com", "Alice")
    _seed_teams(alice, ["charlie", "alpha", "bravo"])
    asc = [r["name"] for r in get_for_user("teams", alice, sort_field="name", sort_order="asc")]
    desc = [r["name"] for r in get_for_user("teams", alice, sort_field="name", sort_order="desc")]
    assert asc == ["alpha", "bravo", "charlie"]
    assert desc == ["charlie", "bravo", "alpha"]


def test_get_for_user_sort_by_created_at(isolated_db):
    import time

    alice = create_user("alice@example.com", "Alice")
    _seed_teams(alice, ["first"])
    time.sleep(1.05)  # CURRENT_TIMESTAMP is second-granular
    _seed_teams(alice, ["second"])
    # _seed_teams reuses id prefixes; fetch by created_at to assert ordering.
    asc = [
        r["name"] for r in get_for_user("teams", alice, sort_field="created_at", sort_order="asc")
    ]
    assert asc.index("first") < asc.index("second")
    desc = [
        r["name"] for r in get_for_user("teams", alice, sort_field="created_at", sort_order="desc")
    ]
    assert desc.index("second") < desc.index("first")


def test_get_for_user_default_sort_is_id_asc(isolated_db):
    """No sort args → preserve historical ORDER BY id ASC."""
    alice = create_user("alice@example.com", "Alice")
    with get_connection() as conn:
        # Insert out of id order; default fetch must come back id-ascending.
        for tid, name in [("team-zzz999", "zeta"), ("team-aaa111", "alpha")]:
            conn.execute(
                "INSERT INTO teams (id, name, user_id) VALUES (?, ?, ?)",
                (tid, name, alice),
            )
        conn.commit()
    rows = get_for_user("teams", alice)
    ids = [r["id"] for r in rows]
    assert ids == sorted(ids)
    assert ids[0] == "team-aaa111"


def test_get_for_user_bogus_sort_does_not_error_or_inject(isolated_db):
    """Malicious/invalid sort/order falls back to default; no error, no injection."""
    alice = create_user("alice@example.com", "Alice")
    _seed_teams(alice, ["safe-team"])
    rows = get_for_user(
        "teams",
        alice,
        sort_field="name); DROP TABLE teams;--",
        sort_order="evil",
    )
    assert "safe-team" in [r["name"] for r in rows]
    # Table survived — injection did not execute.
    assert get_for_user("teams", alice)
