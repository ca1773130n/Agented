"""v0.7.3b: confirm split schema produces expected table set."""

from app.database import get_connection
from app.db.schema import create_fresh_schema


def test_create_fresh_schema_succeeds(isolated_db):
    with get_connection() as conn:
        create_fresh_schema(conn)


def test_expected_tables_present(isolated_db):
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        tables = {row["name"] for row in cursor.fetchall()}
    expected = {
        "triggers",
        "execution_logs",
        "agents",
        "agent_conversations",
        "user_skills",
        "teams",
        "team_members",
        "products",
        "projects",
        "plugins",
        "marketplaces",
        "users",
        "sessions",
    }
    missing = expected - tables
    assert not missing, f"Missing expected tables: {missing}"
