"""Unit tests for account_rotation_service — rate-limit detection and
candidate ordering for chat account rotation."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.services.account_rotation_service import (
    _parse_reset,
    detect_rate_limit_from_event,
    detect_rate_limit_from_text,
    rotation_candidates,
    soonest_reset_message,
)

# --- detection ------------------------------------------------------------


def test_detects_429_result_event():
    event = {
        "type": "result",
        "subtype": "success",
        "is_error": True,
        "api_error_status": 429,
        "result": "You've hit your weekly limit · resets Jun 12 at 6am (Asia/Seoul)",
    }
    info = detect_rate_limit_from_event(event)
    assert info is not None
    assert "weekly limit" in info.reason
    # reset parsed best-effort to an ISO string
    assert info.reset_at is not None and info.reset_at.startswith(
        f"{datetime.now().year if datetime(datetime.now().year, 6, 12, 6) >= datetime.now() else datetime.now().year + 1}-06-12T06:00"
    )


def test_detects_rate_limit_assistant_event_error_field():
    event = {
        "type": "assistant",
        "error": "rate_limit",
        "message": {"content": [{"type": "text", "text": "You've hit your weekly limit"}]},
    }
    info = detect_rate_limit_from_event(event)
    assert info is not None
    assert "weekly limit" in info.reason


def test_normal_assistant_event_is_not_rate_limit():
    event = {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "text", "text": "Here is your answer about rate limiting algorithms."}
            ]
        },
    }
    # No error/429 fields → not a rate limit, even though text says "rate limit".
    assert detect_rate_limit_from_event(event) is None


def test_result_event_error_without_rate_limit_text_ignored():
    event = {"type": "result", "is_error": True, "result": "tool execution failed"}
    assert detect_rate_limit_from_event(event) is None


def test_text_detector_matches_codex_style_message():
    assert detect_rate_limit_from_text("Error: 429 Too Many Requests") is not None
    assert detect_rate_limit_from_text("You've hit your usage limit for today") is not None


def test_text_detector_ignores_ordinary_lines():
    assert detect_rate_limit_from_text("Analyzing the codebase...") is None
    assert detect_rate_limit_from_text("def limit(x): return x") is None


def test_parse_reset_handles_formats():
    iso = _parse_reset("resets Jun 12 at 6am")
    assert iso is not None and "06-12T06:00" in iso
    iso2 = _parse_reset("resets December 3 at 11:30pm (Asia/Seoul)")
    assert iso2 is not None and "12-03T23:30" in iso2
    assert _parse_reset("no reset info here") is None


# --- candidate ordering (needs isolated_db) -------------------------------


def _make_backend_and_accounts(conn, backend_type: str, accounts: list[dict]):
    # Reuse the backend the DB seed already created for this type; only
    # insert one if the seed didn't. Then start its account set clean so
    # the candidate-ordering assertions are deterministic.
    row = conn.execute(
        "SELECT id FROM ai_backends WHERE type = ? LIMIT 1", (backend_type,)
    ).fetchone()
    if row:
        backend_id = row[0]
    else:
        backend_id = f"rot-{backend_type}"
        conn.execute(
            "INSERT INTO ai_backends (id, type, name, is_installed) VALUES (?, ?, ?, 1)",
            (backend_id, backend_type, backend_type.title()),
        )
    conn.execute("DELETE FROM backend_accounts WHERE backend_id = ?", (backend_id,))
    for a in accounts:
        conn.execute(
            """
            INSERT INTO backend_accounts
                (backend_id, account_name, config_path, is_default, rate_limited_until, last_used_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                backend_id,
                a["display_name"],
                a.get("config_path"),
                a.get("is_default", 0),
                a.get("rate_limited_until"),
                a.get("last_used_at"),
            ),
        )


@pytest.fixture
def seeded_db(isolated_db):
    from app.db.connection import get_connection

    future = (datetime.now() + timedelta(hours=2)).isoformat()
    with get_connection() as conn:
        _make_backend_and_accounts(
            conn,
            "claude",
            [
                {
                    "display_name": "Personal1",
                    "config_path": "~/.claude-personal1",
                    "is_default": 1,
                },
                {"display_name": "Personal2", "config_path": "~/.claude-personal2"},
                {
                    "display_name": "LimitedC",
                    "config_path": "~/.claude-limited",
                    "rate_limited_until": future,
                },
            ],
        )
        _make_backend_and_accounts(
            conn,
            "codex",
            [{"display_name": "CodexA", "config_path": "~/.codex"}],
        )
        conn.commit()
    return isolated_db


def _names(cands):
    return [c.display_name for c in cands]


def test_candidates_same_backend_first_then_cross(seeded_db):
    cands = rotation_candidates("claude", exclude_account_ids=set())
    names = _names(cands)
    # Claude (default first), then codex; the rate-limited claude account is skipped.
    assert "Personal1" in names and "Personal2" in names
    assert "LimitedC" not in names  # rate-limited → excluded
    assert "CodexA" in names
    assert names.index("Personal1") < names.index("CodexA")
    assert names.index("Personal2") < names.index("CodexA")


def test_candidates_exclude_attempted(seeded_db):
    from app.db.backends import get_accounts_for_backend_type

    p1 = next(
        a for a in get_accounts_for_backend_type("claude") if a["account_name"] == "Personal1"
    )
    cands = rotation_candidates("claude", exclude_account_ids={p1["id"]})
    assert "Personal1" not in _names(cands)
    assert "Personal2" in _names(cands)


def test_candidates_no_cross_backend(seeded_db):
    cands = rotation_candidates("claude", exclude_account_ids=set(), allow_cross_backend=False)
    assert "CodexA" not in _names(cands)
    assert "Personal2" in _names(cands)


def test_candidate_carries_expanded_config_dir(seeded_db):
    import os

    cands = rotation_candidates("claude", exclude_account_ids=set())
    p2 = next(c for c in cands if c.display_name == "Personal2")
    assert p2.config_dir == os.path.expanduser("~/.claude-personal2")
    assert p2.backend == "claude"


def test_soonest_reset_message_when_limited(seeded_db):
    msg = soonest_reset_message("claude")
    assert "rate-limited" in msg
