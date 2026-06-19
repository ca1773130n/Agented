# backend/tests/test_migration_169_loop_cols.py
def test_goal_loop_iterations_has_body_kind_and_tokens_total(isolated_db):
    from app.db.connection import get_connection

    with get_connection() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(goal_loop_iterations)")}
    assert "body_kind" in cols
    assert "tokens_total" in cols


def test_record_iteration_complete_persists_body_kind(isolated_db):
    from app.db.goal_loop import record_iteration_start, record_iteration_complete, list_iterations

    row_id = record_iteration_start("sess-x", 1)
    record_iteration_complete(
        row_id,
        verdict="not_met",
        judge_source="cmd",
        judge_reason="r",
        judge_stdout="",
        tokens_in=10,
        tokens_out=20,
        cost_usd=0.01,
        body_kind="agent_task",
    )
    rows = list_iterations("sess-x")
    assert rows[0]["body_kind"] == "agent_task"
    assert rows[0]["tokens_total"] == 30
