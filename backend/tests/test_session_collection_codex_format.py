"""Codex 0.130+ rollout format coverage for SessionCollectionService.

The collector must:
* Read nested `sessions/YYYY/MM/DD/rollout-<ts>-<uuid>.jsonl` rollouts
* Parse `event_msg` entries with `payload.type == "token_count"`
* Still parse legacy `turn.completed` events
* Derive a stable session_id from the trailing UUID of `rollout-...`
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from app.services.session_collection_service import SessionCollectionService


def _write_rollout(path: Path, lines: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for entry in lines:
            f.write(json.dumps(entry) + "\n")


def test_codex_session_id_uses_trailing_uuid(tmp_path: Path) -> None:
    p = tmp_path / "rollout-2026-05-04T22-10-46-019df31c-d5f7-7f81-b575-22d748091fed.jsonl"
    p.touch()
    sid = SessionCollectionService._codex_session_id(p)
    assert sid == "019df31c-d5f7-7f81-b575-22d748091fed"


def test_codex_session_id_falls_back_to_stem(tmp_path: Path) -> None:
    p = tmp_path / "session-flat.jsonl"
    p.touch()
    assert SessionCollectionService._codex_session_id(p) == "session-flat"


def test_parse_codex_event_msg_token_count(tmp_path: Path) -> None:
    """0.130+ rollouts: event_msg payload carries cumulative totals."""
    p = tmp_path / "rollout-2026-05-04T22-10-46-019df31c-d5f7-7f81-b575-22d748091fed.jsonl"
    _write_rollout(
        p,
        [
            {"timestamp": "2026-05-04T22:10:46.000Z", "type": "session_meta",
             "payload": {"model": "gpt-5.5"}},
            {"timestamp": "2026-05-04T22:11:00.000Z", "type": "event_msg",
             "payload": {"type": "token_count", "info": {
                 "total_token_usage": {
                     "input_tokens": 1000, "output_tokens": 50, "cached_input_tokens": 200,
                 }}}},
            {"timestamp": "2026-05-04T22:12:00.000Z", "type": "event_msg",
             "payload": {"type": "token_count", "info": {
                 "total_token_usage": {
                     "input_tokens": 2500, "output_tokens": 120, "cached_input_tokens": 800,
                 }}}},
        ],
    )

    usage = SessionCollectionService._parse_codex_session(p)
    assert usage is not None
    assert usage["input_tokens"] == 2500
    assert usage["output_tokens"] == 120
    assert usage["cache_read_tokens"] == 800
    assert usage["model"] == "gpt-5.5"
    assert usage["num_turns"] == 2
    assert usage["last_timestamp"] == "2026-05-04T22:12:00.000Z"


def test_parse_codex_legacy_turn_completed_still_works(tmp_path: Path) -> None:
    """Older releases used `turn.completed` with top-level usage."""
    p = tmp_path / "old-format.jsonl"
    _write_rollout(
        p,
        [
            {"timestamp": "2026-01-01T00:00:00Z", "type": "turn.completed",
             "usage": {"input_tokens": 500, "output_tokens": 25, "cached_input_tokens": 50},
             "turn_context": {"model": "gpt-4o"}},
            {"timestamp": "2026-01-01T00:00:30Z", "type": "turn.completed",
             "usage": {"input_tokens": 1200, "output_tokens": 80, "cached_input_tokens": 400}},
        ],
    )

    usage = SessionCollectionService._parse_codex_session(p)
    assert usage is not None
    assert usage["input_tokens"] == 1200
    assert usage["output_tokens"] == 80
    assert usage["cache_read_tokens"] == 400
    assert usage["model"] == "gpt-4o"


def test_collect_all_walks_nested_codex_rollouts(tmp_path, monkeypatch) -> None:
    """rglob must descend into Codex's date-partitioned tree."""
    codex_home = tmp_path / "codex_home"
    nested = codex_home / "sessions" / "2026" / "05" / "04"
    rollout = nested / "rollout-2026-05-04T01-23-45-019aaaaa-bbbb-7000-8000-cccccccccccc.jsonl"
    _write_rollout(
        rollout,
        [
            {"timestamp": "2026-05-04T01:23:45Z", "type": "session_meta",
             "payload": {"model": "gpt-5.5"}},
            {"timestamp": "2026-05-04T01:24:00Z", "type": "event_msg",
             "payload": {"type": "token_count", "info": {
                 "total_token_usage": {
                     "input_tokens": 999, "output_tokens": 11, "cached_input_tokens": 0,
                 }}}},
        ],
    )

    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    # Stub out the Claude side and DB writes — we only assert codex traversal here.
    monkeypatch.setattr(SessionCollectionService, "_find_claude_project_dirs", classmethod(lambda cls: []))
    monkeypatch.setattr(SessionCollectionService, "_get_imported_sessions", classmethod(lambda cls: set()))
    monkeypatch.setattr(SessionCollectionService, "_save_imported_sessions", classmethod(lambda cls, s: None))

    recorded: list[dict] = []

    def _record(cls, session_id, backend_type, usage):
        recorded.append({"session_id": session_id, "backend_type": backend_type, "usage": usage})

    monkeypatch.setattr(SessionCollectionService, "_record_usage", classmethod(_record))

    result = SessionCollectionService.collect_all()
    assert result["codex"]["sessions"] == 1
    assert len(recorded) == 1
    assert recorded[0]["backend_type"] == "codex"
    assert recorded[0]["session_id"] == "019aaaaa-bbbb-7000-8000-cccccccccccc"
    assert recorded[0]["usage"]["input_tokens"] == 999


def test_collect_all_skips_zero_token_codex_files(tmp_path, monkeypatch) -> None:
    """A rollout with no token_count events should be skipped entirely."""
    codex_home = tmp_path / "codex_home"
    rollout = codex_home / "sessions" / "2026" / "05" / "04" / "rollout-empty-019dddddddddddddddddddddddddd.jsonl"
    _write_rollout(
        rollout,
        [
            {"timestamp": "2026-05-04T01:23:45Z", "type": "session_meta",
             "payload": {"model": "gpt-5.5"}},
            {"timestamp": "2026-05-04T01:24:00Z", "type": "event_msg",
             "payload": {"type": "agent_message", "message": "hello"}},
        ],
    )

    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setattr(SessionCollectionService, "_find_claude_project_dirs", classmethod(lambda cls: []))
    monkeypatch.setattr(SessionCollectionService, "_get_imported_sessions", classmethod(lambda cls: set()))
    monkeypatch.setattr(SessionCollectionService, "_save_imported_sessions", classmethod(lambda cls, s: None))
    monkeypatch.setattr(SessionCollectionService, "_record_usage", classmethod(lambda cls, **kw: None))

    result = SessionCollectionService.collect_all()
    assert result["codex"]["sessions"] == 0
