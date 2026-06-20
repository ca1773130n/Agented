"""v0.5.12: session_events insert + list helpers."""


class TestSessionEvents:
    def test_log_and_list_round_trip(self, isolated_db):
        from app.db.session_events import list_session_events, log_session_event

        log_session_event("sess-1", "user-1", "created", metadata={"reason": "login"})
        events = list_session_events(session_id="sess-1")
        assert len(events) == 1
        assert events[0]["event_type"] == "created"
        assert events[0]["session_id"] == "sess-1"
        assert events[0]["user_id"] == "user-1"

    def test_metadata_round_trips_as_json(self, isolated_db):
        from app.db.session_events import list_session_events, log_session_event

        log_session_event(
            "sess-1",
            "user-1",
            "rotated",
            metadata={"previous_token_hash": "abc123"},
        )
        events = list_session_events(session_id="sess-1")
        assert events[0]["metadata"]["previous_token_hash"] == "abc123"

    def test_filter_by_user_id(self, isolated_db):
        from app.db.session_events import list_session_events, log_session_event

        log_session_event("sess-1", "user-1", "created")
        log_session_event("sess-2", "user-2", "created")
        events = list_session_events(user_id="user-1")
        assert len(events) == 1
        assert events[0]["session_id"] == "sess-1"

    def test_filter_by_event_type(self, isolated_db):
        from app.db.session_events import list_session_events, log_session_event

        log_session_event("sess-1", "user-1", "created")
        log_session_event("sess-1", "user-1", "rotated")
        events = list_session_events(session_id="sess-1", event_type="rotated")
        assert len(events) == 1
        assert events[0]["event_type"] == "rotated"

    def test_pagination_returns_newest_first(self, isolated_db):
        from app.db.session_events import list_session_events, log_session_event

        for i in range(5):
            log_session_event(f"sess-{i}", "user-1", "created")
        events = list_session_events(user_id="user-1", limit=3, offset=0)
        assert len(events) == 3
        # Newest first: sess-4, sess-3, sess-2
        assert events[0]["session_id"] == "sess-4"
        assert events[2]["session_id"] == "sess-2"

    def test_log_swallows_db_errors_with_warning(self, isolated_db, caplog, monkeypatch):
        """If the DB write fails, log_session_event must NOT raise — audit is best-effort."""
        from app.db import session_events as se

        def boom(*args, **kwargs):
            raise RuntimeError("simulated DB failure")

        monkeypatch.setattr(se, "_insert_event_row", boom)
        # Must not raise.
        se.log_session_event("sess-x", "user-x", "created")

    def test_combined_filters(self, isolated_db):
        """Filter combinations must AND correctly — guards against parameter-ordering bugs."""
        from app.db.session_events import list_session_events, log_session_event

        log_session_event("sess-A", "user-1", "created")
        log_session_event("sess-A", "user-1", "rotated")
        log_session_event("sess-B", "user-1", "created")
        log_session_event("sess-A", "user-2", "created")
        events = list_session_events(user_id="user-1", event_type="created")
        assert len(events) == 2
        assert {e["session_id"] for e in events} == {"sess-A", "sess-B"}

    def test_corrupt_metadata_row_does_not_raise(self, isolated_db):
        """A row with non-JSON metadata must yield metadata=None, not raise."""
        from app.database import get_connection
        from app.db.session_events import list_session_events

        with get_connection() as conn:
            conn.execute(
                "INSERT INTO session_events (session_id, user_id, event_type, metadata) "
                "VALUES (?, ?, ?, ?)",
                ("sess-bad", "user-1", "created", "not-json{"),
            )
            conn.commit()
        events = list_session_events(session_id="sess-bad")
        assert len(events) == 1
        assert events[0]["metadata"] is None
