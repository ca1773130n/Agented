"""In-memory tracking for team executions."""

import logging
import threading
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Terminal states + bounds for the sweep backstop (06 H3): cleanup_execution is
# normally called by a 5-min Timer, but that is lost on restart / daemon kill.
# A TTL + size-cap sweep on register guarantees the map can't grow unbounded.
_TERMINAL_STATES = {"completed", "failed", "approval_timeout"}
_ENTRY_TTL_SECONDS = 1800
_MAX_ENTRIES = 5000


class TeamExecutionTracker:
    """Tracks team execution state in memory with thread-safe access."""

    # In-memory tracking of team executions: {team_exec_id: status_dict}
    _executions: Dict[str, dict] = {}
    _lock = threading.Lock()

    @classmethod
    def _sweep_locked(cls) -> None:
        """Evict old terminal entries; hard-cap total size. Caller holds _lock."""
        now = time.time()
        stale = [
            k
            for k, e in cls._executions.items()
            if e.get("status") in _TERMINAL_STATES and now - e.get("_ts", now) > _ENTRY_TTL_SECONDS
        ]
        for k in stale:
            del cls._executions[k]
        if len(cls._executions) > _MAX_ENTRIES:
            # Drop oldest terminal entries first.
            terminal = sorted(
                (k for k, e in cls._executions.items() if e.get("status") in _TERMINAL_STATES),
                key=lambda k: cls._executions[k].get("_ts", 0),
            )
            for k in terminal[: len(cls._executions) - _MAX_ENTRIES]:
                del cls._executions[k]

    @classmethod
    def register(cls, team_exec_id: str, team_id: str, topology: str, trigger_type: str) -> None:
        """Register a new team execution entry."""
        with cls._lock:
            cls._sweep_locked()
            cls._executions[team_exec_id] = {
                "team_id": team_id,
                "topology": topology,
                "trigger_type": trigger_type,
                "status": "running",
                "execution_ids": [],
                "_ts": time.time(),
            }

    @classmethod
    def set_failed(cls, team_exec_id: str) -> None:
        """Mark an execution as failed (no error message)."""
        with cls._lock:
            if team_exec_id in cls._executions:
                cls._executions[team_exec_id]["status"] = "failed"

    @classmethod
    def set_completed(cls, team_exec_id: str, execution_ids: list) -> None:
        """Mark an execution as completed with its execution IDs.

        Does not overwrite an approval_timeout status set by human_in_loop.
        """
        with cls._lock:
            exec_entry = cls._executions.get(team_exec_id, {})
            exec_entry["execution_ids"] = execution_ids or []
            if exec_entry.get("status") != "approval_timeout":
                exec_entry["status"] = "completed"

    @classmethod
    def set_error(cls, team_exec_id: str, error: str) -> None:
        """Mark an execution as failed with an error message."""
        with cls._lock:
            if team_exec_id in cls._executions:
                cls._executions[team_exec_id]["status"] = "failed"
                cls._executions[team_exec_id]["error"] = error

    @classmethod
    def cleanup_execution(cls, team_exec_id: str) -> None:
        """Remove an execution entry from tracking."""
        with cls._lock:
            cls._executions.pop(team_exec_id, None)

    @classmethod
    def get_execution_status(cls, team_exec_id: str) -> Optional[dict]:
        """Get the status of a team execution."""
        with cls._lock:
            return cls._executions.get(team_exec_id)

    @classmethod
    def find_exec_id_for_team(cls, team_id: str) -> Optional[str]:
        """Find the current running team_exec_id for a team_id."""
        with cls._lock:
            for exec_id, entry in cls._executions.items():
                if entry.get("team_id") == team_id and entry.get("status") == "running":
                    return exec_id
        return None

    @classmethod
    def set_pending_approval(
        cls,
        team_exec_id: str,
        agent_id: str,
        approval_timeout: int,
        approval_event: threading.Event,
    ) -> None:
        """Set execution to pending_approval state with an approval event."""
        with cls._lock:
            exec_entry = cls._executions.get(team_exec_id)
            if exec_entry:
                exec_entry["status"] = "pending_approval"
                exec_entry["awaiting_approval"] = agent_id
                exec_entry["approval_timeout"] = approval_timeout
                exec_entry["_approval_event"] = approval_event

    @classmethod
    def set_approval_timeout(cls, team_exec_id: str) -> None:
        """Set execution to approval_timeout state and clean up the event."""
        with cls._lock:
            exec_entry = cls._executions.get(team_exec_id)
            if exec_entry:
                exec_entry["status"] = "approval_timeout"
                exec_entry.pop("_approval_event", None)

    @classmethod
    def clear_approval(cls, team_exec_id: str) -> None:
        """Clear approval state and resume running."""
        with cls._lock:
            exec_entry = cls._executions.get(team_exec_id)
            if exec_entry:
                exec_entry["status"] = "running"
                exec_entry.pop("awaiting_approval", None)
                exec_entry.pop("_approval_event", None)

    @classmethod
    def approve_execution(cls, team_exec_id: str) -> bool:
        """Approve a pending human-in-loop execution.

        Returns True if the execution was in pending_approval state and was
        successfully approved, False otherwise.
        """
        with cls._lock:
            exec_entry = cls._executions.get(team_exec_id)
            if not exec_entry:
                return False
            if exec_entry.get("status") != "pending_approval":
                return False
            approval_event = exec_entry.get("_approval_event")
            if not approval_event:
                return False

        # Set the event outside the lock to avoid potential deadlock
        approval_event.set()
        return True
