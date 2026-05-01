"""Verify the user_id column + scoping helper work across the batch-1
owned-entity tables (track B, wave 41)."""

import pytest

from app.db.connection import get_connection
from app.db.owned_entities import _VALID_TABLES, count_for_user, get_for_user
from app.db.users import create_user

# Tables migrated in wave 41.
BATCH_1 = ["projects", "teams", "agents", "plugins", "super_agents"]


@pytest.mark.parametrize("table", BATCH_1)
def test_table_has_user_id_column(table, isolated_db):
    with get_connection() as conn:
        cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    assert "user_id" in cols, f"{table} missing user_id column after wave 41"


@pytest.mark.parametrize("table", BATCH_1)
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
