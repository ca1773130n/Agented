"""Collaborative execution viewer service with presence tracking and inline commenting.

Enables multiple team members to watch the same live execution stream
simultaneously with real-time presence awareness and inline commenting.
Uses existing SSE fan-out pattern (ExecutionLogService._broadcast) for
real-time notifications -- no WebSockets.

Viewer presence is ephemeral in-memory state. Comments are persisted to SQLite.
"""

import datetime
import logging
import threading
from typing import Dict

from ..db.viewer_comments import (
    create_viewer_comment,
    get_comment,
    get_comments_for_execution,
)

logger = logging.getLogger(__name__)


class CollaborativeViewerService:
    """Service for collaborative execution viewing with presence and comments.

    Uses class-level state and threading.Lock following ExecutionLogService pattern.
    Viewer presence is ephemeral (in-memory only). Comments are persisted to DB.
    """

    # {execution_id: {viewer_id: {"name": str, "joined_at": str, "last_seen": datetime}}}
    _viewers: Dict[str, Dict[str, dict]] = {}
    _lock = threading.Lock()
    HEARTBEAT_INTERVAL = 30  # seconds
    HEARTBEAT_MISS_THRESHOLD = 2  # misses before removal

    @classmethod
    def join(cls, execution_id: str, viewer_id: str, viewer_name: str) -> list[dict]:
        """Register a viewer for an execution and broadcast presence_join.

        Args:
            execution_id: Execution being watched.
            viewer_id: Unique viewer identifier.
            viewer_name: Display name.

        Returns:
            Current list of viewers for the execution.
        """
        now = datetime.datetime.now()
        with cls._lock:
            if execution_id not in cls._viewers:
                cls._viewers[execution_id] = {}
            cls._viewers[execution_id][viewer_id] = {
                "name": viewer_name,
                "joined_at": now.isoformat(),
                "last_seen": now,
            }
            viewers = cls._get_viewer_list_locked(execution_id)

        # Broadcast presence_join via existing SSE infrastructure
        cls._broadcast_presence(execution_id, "join", viewer_id, viewer_name, viewers)

        return viewers

    @classmethod
    def leave(cls, execution_id: str, viewer_id: str) -> None:
        """Remove a viewer from an execution and broadcast presence_leave."""
        viewer_name = "unknown"
        viewers = []
        with cls._lock:
            if execution_id in cls._viewers:
                viewer_data = cls._viewers[execution_id].pop(viewer_id, None)
                if viewer_data:
                    viewer_name = viewer_data["name"]
                # Clean up empty execution entries
                if not cls._viewers[execution_id]:
                    del cls._viewers[execution_id]
                else:
                    viewers = cls._get_viewer_list_locked(execution_id)

        cls._broadcast_presence(execution_id, "leave", viewer_id, viewer_name, viewers)

    @classmethod
    def heartbeat(cls, execution_id: str, viewer_id: str) -> None:
        """Update last_seen timestamp for a viewer. Silent -- no broadcast."""
        with cls._lock:
            if execution_id in cls._viewers and viewer_id in cls._viewers[execution_id]:
                cls._viewers[execution_id][viewer_id]["last_seen"] = datetime.datetime.now()

    @classmethod
    def get_viewers(cls, execution_id: str) -> list[dict]:
        """Return list of current viewers for an execution."""
        with cls._lock:
            return cls._get_viewer_list_locked(execution_id)

    @classmethod
    def cleanup_stale_viewers(cls) -> int:
        """Remove viewers that have missed 2+ heartbeats.

        Per 08-RESEARCH.md Pitfall 3: prevents orphaned Queue subscriber leak.
        Returns count of removed viewers.
        """
        threshold = cls.HEARTBEAT_INTERVAL * cls.HEARTBEAT_MISS_THRESHOLD
        now = datetime.datetime.now()
        stale_entries = []  # [(execution_id, viewer_id, viewer_name)]

        with cls._lock:
            for execution_id, viewer_dict in list(cls._viewers.items()):
                for viewer_id, data in list(viewer_dict.items()):
                    elapsed = (now - data["last_seen"]).total_seconds()
                    if elapsed > threshold:
                        stale_entries.append((execution_id, viewer_id, data["name"]))
                        del viewer_dict[viewer_id]
                # Clean up empty execution entries
                if not viewer_dict:
                    del cls._viewers[execution_id]

        # Broadcast leave for each removed viewer (outside lock to avoid deadlock)
        for execution_id, viewer_id, viewer_name in stale_entries:
            with cls._lock:
                viewers = cls._get_viewer_list_locked(execution_id)
            cls._broadcast_presence(execution_id, "leave", viewer_id, viewer_name, viewers)
            logger.info("Removed stale viewer %s from execution %s", viewer_id, execution_id)

        if stale_entries:
            logger.info("Cleaned up %d stale viewer(s)", len(stale_entries))
        return len(stale_entries)

    @classmethod
    def post_comment(
        cls,
        execution_id: str,
        viewer_id: str,
        viewer_name: str,
        line_number: int,
        content: str,
    ) -> dict:
        """Persist an inline comment and broadcast via SSE.

        Per 08-RESEARCH.md Open Question 3: comments anchor to stdout line numbers
        (immutable once execution completes).

        Returns:
            Created comment dict with id, viewer_id, viewer_name, line_number, content, created_at.
        """
        comment_id = create_viewer_comment(
            execution_id=execution_id,
            viewer_id=viewer_id,
            viewer_name=viewer_name,
            line_number=line_number,
            content=content,
        )
        if not comment_id:
            raise ValueError("Failed to persist comment")

        comment = get_comment(comment_id)

        # Broadcast inline_comment event via existing SSE infrastructure
        try:
            from .execution_log_service import ExecutionLogService

            ExecutionLogService._broadcast(
                execution_id,
                "inline_comment",
                {
                    "comment_id": comment_id,
                    "viewer_id": viewer_id,
                    "name": viewer_name,
                    "line_number": line_number,
                    "content": content,
                    "timestamp": comment["created_at"] if comment else "",
                },
            )
        except Exception as e:
            logger.warning("Failed to broadcast inline_comment: %s", e)

        return comment or {
            "id": comment_id,
            "execution_id": execution_id,
            "viewer_id": viewer_id,
            "viewer_name": viewer_name,
            "line_number": line_number,
            "content": content,
            "created_at": "",
        }

    @classmethod
    def get_execution_comments(cls, execution_id: str) -> list[dict]:
        """Return all persisted comments for an execution from DB.

        Enables viewing comments on historical executions (not just live SSE).
        """
        return get_comments_for_execution(execution_id)

    # -- Internal helpers --

    @classmethod
    def _get_viewer_list_locked(cls, execution_id: str) -> list[dict]:
        """Build viewer list from _viewers dict. Must be called under _lock."""
        if execution_id not in cls._viewers:
            return []
        return [
            {
                "viewer_id": vid,
                "name": data["name"],
                "joined_at": data["joined_at"],
            }
            for vid, data in cls._viewers[execution_id].items()
        ]

    @classmethod
    def _broadcast_presence(
        cls,
        execution_id: str,
        event_type: str,
        viewer_id: str,
        viewer_name: str,
        viewers: list[dict],
    ) -> None:
        """Broadcast a presence event via ExecutionLogService SSE infrastructure."""
        try:
            from .execution_log_service import ExecutionLogService

            ExecutionLogService._broadcast(
                execution_id,
                f"presence_{event_type}",
                {
                    "event_type": event_type,
                    "viewer_id": viewer_id,
                    "name": viewer_name,
                    "viewers": viewers,
                },
            )
        except Exception as e:
            logger.warning("Failed to broadcast presence_%s: %s", event_type, e)
