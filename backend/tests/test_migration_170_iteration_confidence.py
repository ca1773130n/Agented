def test_columns_exist(isolated_db):
    from app.db.connection import get_connection

    with get_connection() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(goal_loop_iterations)")}
    assert "confidence" in cols and "judge_version" in cols


def test_record_persists_confidence_and_version(isolated_db):
    from app.db.goal_loop import list_iterations, record_iteration_complete, record_iteration_start

    rid = record_iteration_start("s", 1)
    record_iteration_complete(
        rid,
        verdict="met",
        judge_source="llm",
        judge_reason="r",
        judge_stdout="",
        tokens_in=1,
        tokens_out=2,
        cost_usd=0.0,
        confidence=0.91,
        judge_version="v2",
    )
    row = list_iterations("s")[0]
    assert row["confidence"] == 0.91 and row["judge_version"] == "v2"
