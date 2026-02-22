"""SuperAgent session lifecycle management service.

Provides session creation with concurrency limits, message handling with token
tracking, compaction when exceeding threshold, system prompt assembly from
identity documents, and a ring buffer for output lines.
"""

import collections
import datetime
import json
import logging
import threading
from typing import Dict, List, Optional, Tuple

from ..db.super_agents import (
    add_super_agent_session,
    get_active_sessions_list,
    get_super_agent,
    get_super_agent_documents,
    update_super_agent_session,
)

logger = logging.getLogger(__name__)


class SuperAgentSessionService:
    """Service for SuperAgent session lifecycle, token tracking, and prompt assembly."""

    MAX_CONCURRENT_SESSIONS = 10
    TOKEN_COMPACTION_THRESHOLD = 80_000
    OUTPUT_RING_BUFFER_SIZE = 1000
    CHARS_PER_TOKEN = 4  # Approximate: 4 chars ~ 1 token

    _active_sessions: Dict[str, dict] = {}
    _lock = threading.Lock()

    @classmethod
    def create_session(cls, super_agent_id: str) -> Tuple[Optional[str], Optional[str]]:
        """Create a new session for a super agent.

        Returns (session_id, None) on success or (None, error_message) on failure.
        """
        with cls._lock:
            # Check concurrency limit
            active_count = sum(1 for s in cls._active_sessions.values() if s["status"] == "active")
            if active_count >= cls.MAX_CONCURRENT_SESSIONS:
                return None, "Maximum concurrent sessions reached"

            # Verify super agent exists
            sa = get_super_agent(super_agent_id)
            if not sa:
                return None, "SuperAgent not found"

            # Persist to DB
            session_id = add_super_agent_session(super_agent_id)
            if not session_id:
                return None, "Failed to create session"

            # Create in-memory state
            cls._active_sessions[session_id] = {
                "session_id": session_id,
                "super_agent_id": super_agent_id,
                "status": "active",
                "conversation_log": [],
                "summary": None,
                "token_count": 0,
                "output_buffer": collections.deque(maxlen=cls.OUTPUT_RING_BUFFER_SIZE),
            }

            return session_id, None

    @classmethod
    def send_message(
        cls, session_id: str, content: str, backend: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """Append a user message to the session conversation log.

        Returns (True, None) on success or (False, error_message) on failure.
        """
        with cls._lock:
            session = cls._active_sessions.get(session_id)
            if not session:
                return False, "Session not found"
            if session["status"] != "active":
                return False, "Session is not active"

            iso_now = datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z"
            token_estimate = len(content) // cls.CHARS_PER_TOKEN

            message = {
                "role": "user",
                "content": content,
                "timestamp": iso_now,
                "token_count": token_estimate,
            }
            if backend:
                message["backend"] = backend

            session["conversation_log"].append(message)
            session["token_count"] += token_estimate

            # Check compaction threshold
            if session["token_count"] > cls.TOKEN_COMPACTION_THRESHOLD:
                cls._compact_session(session_id)

            # Persist to DB
            update_super_agent_session(
                session_id,
                conversation_log=json.dumps(session["conversation_log"]),
                token_count=session["token_count"],
            )

            # Add to output buffer
            session["output_buffer"].append(f"[user] {content}")

            return True, None

    @classmethod
    def add_assistant_message(
        cls, session_id: str, content: str, backend: Optional[str] = None
    ) -> bool:
        """Append an assistant message to the session conversation log.

        Called after streaming completes to persist the full response.
        Returns True on success.
        """
        with cls._lock:
            session = cls._active_sessions.get(session_id)
            if not session:
                return False

            iso_now = datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z"
            token_estimate = len(content) // cls.CHARS_PER_TOKEN

            message = {
                "role": "assistant",
                "content": content,
                "timestamp": iso_now,
                "token_count": token_estimate,
            }
            if backend:
                message["backend"] = backend

            session["conversation_log"].append(message)
            session["token_count"] += token_estimate

            # Check compaction threshold
            if session["token_count"] > cls.TOKEN_COMPACTION_THRESHOLD:
                cls._compact_session(session_id)

            # Persist to DB
            update_super_agent_session(
                session_id,
                conversation_log=json.dumps(session["conversation_log"]),
                token_count=session["token_count"],
            )
            return True

    @classmethod
    def end_session(cls, session_id: str) -> Tuple[bool, Optional[str]]:
        """End a session, persisting final state and removing from active sessions.

        Returns (True, None) on success or (False, error_message) on failure.
        """
        with cls._lock:
            session = cls._active_sessions.get(session_id)
            if not session:
                return False, "Session not found"

            iso_now = datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z"

            # Persist final state
            update_super_agent_session(
                session_id,
                status="completed",
                ended_at=iso_now,
                conversation_log=json.dumps(session["conversation_log"]),
                summary=session["summary"],
                token_count=session["token_count"],
            )

            # Remove from active sessions
            del cls._active_sessions[session_id]

            return True, None

    @classmethod
    def pause_session(cls, session_id: str) -> Tuple[bool, Optional[str]]:
        """Pause an active session.

        Returns (True, None) on success or (False, error_message) on failure.
        """
        with cls._lock:
            session = cls._active_sessions.get(session_id)
            if not session:
                return False, "Session not found"
            if session["status"] != "active":
                return False, "Session is not active"

            session["status"] = "paused"
            update_super_agent_session(session_id, status="paused")

            return True, None

    @classmethod
    def resume_session(cls, session_id: str) -> Tuple[bool, Optional[str]]:
        """Resume a paused session.

        Returns (True, None) on success or (False, error_message) on failure.
        """
        with cls._lock:
            session = cls._active_sessions.get(session_id)
            if not session:
                return False, "Session not found"
            if session["status"] != "paused":
                return False, "Session is not paused"

            session["status"] = "active"
            update_super_agent_session(session_id, status="active")

            return True, None

    @classmethod
    def get_session_state(cls, session_id: str) -> Optional[dict]:
        """Return a copy of in-memory session state (without output_buffer)."""
        with cls._lock:
            session = cls._active_sessions.get(session_id)
            if not session:
                return None
            # Return a copy without the non-serializable deque
            return {
                "session_id": session["session_id"],
                "super_agent_id": session["super_agent_id"],
                "status": session["status"],
                "conversation_log": list(session["conversation_log"]),
                "summary": session["summary"],
                "token_count": session["token_count"],
            }

    @classmethod
    def assemble_system_prompt(cls, super_agent_id: str, session_id: str) -> str:
        """Assemble a system prompt from identity documents and session state.

        Includes SOUL, IDENTITY, MEMORY, ROLE documents, session summary,
        and recent conversation history (last 20 messages).
        """
        documents = get_super_agent_documents(super_agent_id)

        # Group documents by type
        docs_by_type: Dict[str, List[dict]] = {}
        for doc in documents:
            dt = doc["doc_type"]
            if dt not in docs_by_type:
                docs_by_type[dt] = []
            docs_by_type[dt].append(doc)

        parts = []

        # Add each document type in canonical order
        for doc_type in ("SOUL", "IDENTITY", "MEMORY", "ROLE"):
            if doc_type in docs_by_type:
                for doc in docs_by_type[doc_type]:
                    parts.append(f"## {doc_type}\n\n{doc['content']}\n")

        # Add session summary if available
        with cls._lock:
            session = cls._active_sessions.get(session_id)

        if session and session.get("summary"):
            parts.append(f"## Session Summary\n\n{session['summary']}\n")

        # Add recent conversation history (last 20 messages)
        if session and session.get("conversation_log"):
            recent = session["conversation_log"][-20:]
            if recent:
                history_lines = []
                for msg in recent:
                    role = msg.get("role", "unknown")
                    content = msg.get("content", "")
                    history_lines.append(f"{role}: {content}")
                parts.append("## Recent History\n\n" + "\n".join(history_lines) + "\n")

        # Inject pending messages from other agents
        from ..db.messages import get_pending_messages, update_message_status

        pending_msgs = get_pending_messages(super_agent_id)
        if pending_msgs:
            msg_lines = []
            for msg in pending_msgs:
                from_id = msg["from_agent_id"]
                subject = msg.get("subject") or "(no subject)"
                content = msg["content"]
                priority = msg["priority"]
                msg_lines.append(f"- [{priority.upper()}] From {from_id}: {subject}\n  {content}")
                update_message_status(msg["id"], "delivered")
            parts.append("## Pending Messages\n\n" + "\n".join(msg_lines) + "\n")

        return "\n".join(parts)

    @classmethod
    def _compact_session(cls, session_id: str):
        """Compact a session's conversation log by summarizing old messages.

        This method must be called with the lock held.

        Placeholder implementation: creates an extractive summary by concatenating
        old message content (truncated to 2000 chars). Real LLM-based summarization
        will be added when AI backend integration lands in a later phase.
        """
        session = cls._active_sessions.get(session_id)
        if not session:
            return

        log = session["conversation_log"]
        if len(log) <= 10:
            return

        # Take all messages except the last 10
        old_messages = log[:-10]
        recent_messages = log[-10:]

        # Create extractive summary from old messages
        old_content = " ".join(msg.get("content", "") for msg in old_messages)
        if len(old_content) > 2000:
            old_content = old_content[:2000]
        summary = f"Summary of prior conversation: {old_content}"

        # Replace conversation log with just recent messages
        session["conversation_log"] = recent_messages
        session["summary"] = summary

        # Recalculate token count from summary + remaining messages
        summary_tokens = len(summary) // cls.CHARS_PER_TOKEN
        message_tokens = sum(msg.get("token_count", 0) for msg in recent_messages)
        session["token_count"] = summary_tokens + message_tokens

        iso_now = datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z"
        session["last_compacted_at"] = iso_now

        logger.info(
            "Compacted session %s: %d old messages summarized, %d recent kept, "
            "new token_count=%d",
            session_id,
            len(old_messages),
            len(recent_messages),
            session["token_count"],
        )

    @classmethod
    def restore_active_sessions(cls):
        """Restore active sessions from database on startup."""
        with cls._lock:
            active_rows = get_active_sessions_list()
            for row in active_rows:
                session_id = row["id"]
                try:
                    conversation_log = json.loads(row.get("conversation_log") or "[]")
                except (json.JSONDecodeError, TypeError):
                    conversation_log = []

                cls._active_sessions[session_id] = {
                    "session_id": session_id,
                    "super_agent_id": row["super_agent_id"],
                    "status": row["status"],
                    "conversation_log": conversation_log,
                    "summary": row.get("summary"),
                    "token_count": row.get("token_count", 0),
                    "output_buffer": collections.deque(maxlen=cls.OUTPUT_RING_BUFFER_SIZE),
                }

            logger.info("Restored %d active sessions from database", len(active_rows))

    @classmethod
    def get_output_lines(cls, session_id: str) -> List[str]:
        """Return output buffer lines for a session."""
        with cls._lock:
            session = cls._active_sessions.get(session_id)
            if not session:
                return []
            return list(session["output_buffer"])
