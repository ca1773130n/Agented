"""Versioned state snapshot SSE protocol with cursor-based delta delivery.

Provides per-session state management with monotonic sequence numbers,
subscriber queues for SSE delivery, event log capping, and cursor-based
replay for reconnection recovery.

Pattern: Adapted from Agent Zero's state_snapshot.py with cursor offsets.
"""

import datetime
import json
import logging
import threading
from queue import Empty, Queue
from typing import Dict, Generator, List, Optional

logger = logging.getLogger(__name__)

EVENT_LOG_MAX = 1000


class ChatStateService:
    """Versioned state snapshots for SSE delivery with cursor-based delta.

    Each session maintains a monotonic sequence number, a list of subscriber
    queues, a capped event log, and a status field. Subscribers receive SSE
    events via their queue. On reconnection, missed events are replayed from
    the event log using the client's last seen sequence number.
    """

    # {session_id: {"seq": int, "subscribers": [Queue], "event_log": [dict],
    #               "status": str, "created_at": str}}
    _sessions: Dict[str, dict] = {}
    _lock = threading.Lock()

    @classmethod
    def init_session(cls, session_id: str) -> None:
        """Create session entry in _sessions if not exists."""
        with cls._lock:
            if session_id in cls._sessions:
                return
            cls._sessions[session_id] = {
                "seq": 0,
                "subscribers": [],
                "event_log": [],
                "status": "idle",
                "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z",
            }
            logger.info("ChatStateService: initialized session %s", session_id)

    @classmethod
    def remove_session(cls, session_id: str) -> None:
        """Clean up session state and poison-pill all subscriber queues."""
        with cls._lock:
            session = cls._sessions.pop(session_id, None)
            if session is None:
                return
            # Poison-pill all subscriber queues so generators exit cleanly
            for q in session["subscribers"]:
                q.put(None)
            logger.info("ChatStateService: removed session %s", session_id)

    @classmethod
    def push_delta(cls, session_id: str, delta_type: str, data: Optional[dict] = None) -> None:
        """Push a delta event to all subscribers for a session.

        Increments the monotonic sequence number, appends to the event log
        (trimming from front if exceeding EVENT_LOG_MAX), and puts the
        SSE-formatted string into each subscriber queue.
        """
        with cls._lock:
            session = cls._sessions.get(session_id)
            if session is None:
                return

            session["seq"] += 1
            seq = session["seq"]

            event = {"seq": seq, "type": delta_type}
            if data:
                event.update(data)

            # Append to event log and trim from front if capped
            session["event_log"].append(event)
            if len(session["event_log"]) > EVENT_LOG_MAX:
                excess = len(session["event_log"]) - EVENT_LOG_MAX
                session["event_log"] = session["event_log"][excess:]

            # Build SSE string
            sse_str = f"id: {seq}\nevent: state_delta\ndata: {json.dumps(event)}\n\n"

            # Deliver to all subscribers
            for q in session["subscribers"]:
                q.put(sse_str)

    @classmethod
    def push_status(cls, session_id: str, status: str) -> None:
        """Update session status and push a status_change delta."""
        with cls._lock:
            session = cls._sessions.get(session_id)
            if session is not None:
                session["status"] = status

        # Push outside the lock to avoid nested locking (push_delta acquires lock)
        cls.push_delta(session_id, "status_change", {"status": status})

    @classmethod
    def subscribe(
        cls, session_id: str, last_seq: int = 0, heartbeat_timeout: int = 30
    ) -> Generator[str, None, None]:
        """SSE generator that yields events for a session.

        If last_seq > 0 and is older than the oldest event in the log,
        yields a full_sync event with all log entries. Otherwise, replays
        events from the log where event["seq"] > last_seq.

        Sends a heartbeat comment every heartbeat_timeout seconds when no
        events arrive. Exits cleanly on poison-pill (None) sentinel.

        Args:
            session_id: The session to subscribe to.
            last_seq: The last sequence number seen by the client (for reconnection).
            heartbeat_timeout: Seconds to wait before sending a heartbeat (default 30).
        """
        queue: Queue = Queue()
        replay_events: List[str] = []
        session_found = False

        # Collect replay events and register subscriber under lock.
        # IMPORTANT: Do NOT yield inside the lock -- yields in a generator
        # suspend execution while keeping the lock held, causing deadlock
        # when the finally block tries to re-acquire it.
        with cls._lock:
            session = cls._sessions.get(session_id)
            if session is not None:
                session_found = True
                event_log = session["event_log"]

                if last_seq > 0 and event_log:
                    oldest_seq = event_log[0]["seq"]
                    if last_seq < oldest_seq:
                        # Client cursor is too old -- send full sync
                        full_sync_data = {"events": event_log[:]}
                        replay_events.append(
                            f"event: full_sync\ndata: {json.dumps(full_sync_data)}\n\n"
                        )
                    else:
                        # Replay missed events
                        for event in event_log:
                            if event["seq"] > last_seq:
                                sse_str = (
                                    f"id: {event['seq']}\n"
                                    f"event: state_delta\n"
                                    f"data: {json.dumps(event)}\n\n"
                                )
                                replay_events.append(sse_str)

                # Add queue to subscribers
                session["subscribers"].append(queue)

        # Handle session-not-found case outside the lock
        if not session_found:
            yield f"event: error\ndata: {json.dumps({'error': 'Session not found'})}\n\n"
            return

        # Yield replay events outside the lock
        for replay_event in replay_events:
            yield replay_event

        try:
            while True:
                try:
                    event = queue.get(timeout=heartbeat_timeout)
                    if event is None:
                        break  # Poison pill -- session removed
                    yield event
                except Empty:
                    # Send heartbeat to keep connection alive
                    yield ": heartbeat\n\n"
        finally:
            # Cleanup: remove queue from subscribers
            with cls._lock:
                session = cls._sessions.get(session_id)
                if session is not None:
                    try:
                        session["subscribers"].remove(queue)
                    except ValueError:
                        pass

    @classmethod
    def get_session_status(cls, session_id: str) -> Optional[str]:
        """Return the current status for a session, or None if not found."""
        with cls._lock:
            session = cls._sessions.get(session_id)
            if session is None:
                return None
            return session["status"]

    @classmethod
    def reset(cls) -> None:
        """Reset all state. Used in tests to clean up between test runs."""
        with cls._lock:
            for session in cls._sessions.values():
                for q in session["subscribers"]:
                    q.put(None)
            cls._sessions = {}
