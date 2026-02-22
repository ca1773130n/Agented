"""Integration test fixtures and contract assertion helpers.

These fixtures complement the parent conftest.py's isolated_db, app, and client
fixtures. Integration tests use the real Flask test client and real database --
no mocking of database or service layer.
"""

import pytest

from app.database import get_connection


def assert_response_contract(response_dict, expected_fields, entity_name="entity"):
    """Assert that a response dict contains all fields expected by the frontend.

    Compares the response dict keys against a reference set derived from
    frontend TypeScript interface definitions (frontend/src/services/api/types.ts).

    Args:
        response_dict: The JSON response dictionary to validate.
        expected_fields: Set of field names expected by the frontend.
        entity_name: Human-readable name for error messages.

    Raises:
        AssertionError: If any expected fields are missing, with details about
            which fields are missing and what actual fields were present.
    """
    actual = set(response_dict.keys())
    missing = expected_fields - actual
    assert not missing, (
        f"{entity_name} response missing fields expected by frontend: {missing}. "
        f"Actual fields: {sorted(actual)}"
    )


@pytest.fixture()
def seed_test_execution(isolated_db):
    """Insert a test execution log record for use by execution tests.

    Inserts into execution_logs with only the columns that exist in the table
    schema (see backend/app/db/schema.py). NOTE: trigger_name is NOT a column
    in execution_logs -- it is a JOIN alias derived at query time by
    get_all_execution_logs().

    Yields:
        The execution_id of the seeded record ("exec-test-001").
    """
    execution_id = "exec-test-001"
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO execution_logs
                (execution_id, trigger_id, trigger_type, backend_type, status, started_at, finished_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                execution_id,
                "bot-security",
                "manual",
                "claude",
                "success",
                "2026-01-15T10:00:00",
                "2026-01-15T10:05:00",
            ),
        )
        conn.commit()
    yield execution_id
