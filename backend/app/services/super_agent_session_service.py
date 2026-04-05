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

from app import config as app_config

from ..db.super_agents import (
    add_super_agent_session,
    get_active_sessions_list,
    get_super_agent,
    get_super_agent_documents,
    update_super_agent_session,
)

logger = logging.getLogger(__name__)


class SessionLimitError(Exception):
    """Raised when no session can be created due to the global concurrent session limit."""

    pass


class SuperAgentSessionService:
    """Service for SuperAgent session lifecycle, token tracking, and prompt assembly."""

    MAX_CONCURRENT_SESSIONS = 50
    TOKEN_COMPACTION_THRESHOLD = 80_000
    OUTPUT_RING_BUFFER_SIZE = app_config.OUTPUT_RING_BUFFER_SIZE
    CHARS_PER_TOKEN = 4  # Approximate: 4 chars ~ 1 token

    _active_sessions: Dict[str, dict] = {}
    _lock = threading.RLock()

    @classmethod
    def create_session(
        cls, super_agent_id: str, instance_id: str = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """Create a new session for a super agent.

        Args:
            super_agent_id: The super agent to create a session for.
            instance_id: Optional project SA instance ID to associate with this session.

        Returns (session_id, None) on success or (None, error_message) on failure.
        """
        with cls._lock:
            # Verify super agent exists
            sa = get_super_agent(super_agent_id)
            if not sa:
                return None, "SuperAgent not found"

            # Check per-SA concurrency limit
            sa_limit = sa.get("max_concurrent_sessions", cls.MAX_CONCURRENT_SESSIONS)
            sa_active = sum(
                1
                for s in cls._active_sessions.values()
                if s.get("super_agent_id") == super_agent_id and s["status"] == "active"
            )
            if sa_active >= sa_limit:
                return None, f"Maximum concurrent sessions ({sa_limit}) reached for this agent"

            # Persist to DB
            session_id = add_super_agent_session(super_agent_id, instance_id=instance_id)
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
                "instance_id": instance_id,
            }

            return session_id, None

    @classmethod
    def get_or_create_session(cls, super_agent_id: str) -> str:
        """Return an existing session for the super agent, or create a new one.

        - If an active session exists for the super_agent_id, return its session_id.
        - If a paused session exists, resume it and return its session_id.
        - Otherwise, create a new session and return its session_id.

        Raises SessionLimitError if create_session fails (e.g., concurrency limit reached).
        """
        with cls._lock:
            for session in cls._active_sessions.values():
                if session["super_agent_id"] == super_agent_id:
                    if session["status"] == "active":
                        return session["session_id"]
                    if session["status"] == "paused":
                        paused_session_id = session["session_id"]
                        break
            else:
                paused_session_id = None

            if paused_session_id is not None:
                cls.resume_session(paused_session_id)
                return paused_session_id

            session_id, error = cls.create_session(super_agent_id)
            if session_id is None:
                raise SessionLimitError(error or "Failed to create session")
            return session_id

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
        """Resume a paused or completed session.

        Returns (True, None) on success or (False, error_message) on failure.
        """
        with cls._lock:
            session = cls._active_sessions.get(session_id)
            if not session:
                # Session not in memory — reload from DB and add to active sessions
                from ..database import get_super_agent_session

                db_session = get_super_agent_session(session_id)
                if not db_session:
                    return False, "Session not found"
                import collections
                import json

                session = {
                    "session_id": session_id,
                    "super_agent_id": db_session.get("super_agent_id", ""),
                    "instance_id": db_session.get("instance_id"),
                    "status": db_session.get("status", "active"),
                    "conversation_log": json.loads(db_session.get("conversation_log") or "[]"),
                    "summary": db_session.get("summary"),
                    "token_count": db_session.get("token_count", 0),
                    "output_buffer": collections.deque(maxlen=cls.OUTPUT_RING_BUFFER_SIZE),
                }
                cls._active_sessions[session_id] = session

            if session["status"] == "active":
                return True, None  # Already active, just needed to be in memory

            if session["status"] not in ("paused", "completed"):
                return False, f"Session is {session['status']}"

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
    def assemble_system_prompt(
        cls,
        super_agent_id: str,
        session_id: str,
        chat_mode: Optional[str] = None,
        instance_id: Optional[str] = None,
    ) -> str:
        """Assemble a system prompt from identity documents and session state.

        Includes SOUL, IDENTITY, MEMORY, ROLE documents, session summary,
        and recent conversation history (last 20 messages).

        When instance_id is provided, appends project context (name, description,
        repository, working directory, chat mode).
        """
        # If super_agent_id is a psa- instance, resolve the template SA
        effective_sa_id = super_agent_id
        if super_agent_id.startswith("psa-") and not instance_id:
            instance_id = super_agent_id
        if instance_id and instance_id.startswith("psa-"):
            try:
                from ..db.project_sa_instances import get_project_sa_instance

                inst = get_project_sa_instance(instance_id)
                if inst:
                    effective_sa_id = inst["template_sa_id"]
            except Exception:
                pass

        documents = get_super_agent_documents(effective_sa_id)

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

        pending_msgs = get_pending_messages(effective_sa_id)
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

        # Append project context when associated with an instance
        if instance_id:
            try:
                from ..db.project_sa_instances import get_project_sa_instance
                from ..db.projects import get_project

                instance = get_project_sa_instance(instance_id)
                if instance:
                    project = get_project(instance["project_id"])
                    if project:
                        project_context = f"\n\n## Project Context\nProject: {project['name']}"
                        if project.get("description"):
                            project_context += f"\nDescription: {project['description']}"
                        if project.get("github_repo"):
                            project_context += f"\nRepository: {project['github_repo']}"
                        if instance.get("worktree_path"):
                            project_context += f"\nWorking Directory: {instance['worktree_path']}"
                        project_context += f"\nChat Mode: {chat_mode or 'management'}"
                        parts.append(project_context)
            except Exception:
                logger.debug("Failed to load project context for instance %s", instance_id)

        return "\n".join(parts)

    @classmethod
    def _compact_session(cls, session_id: str) -> None:
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
            "Compacted session %s: %d old messages summarized, %d recent kept, new token_count=%d",
            session_id,
            len(old_messages),
            len(recent_messages),
            session["token_count"],
        )

    @classmethod
    def restore_active_sessions(cls) -> None:
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
                    "instance_id": row.get("instance_id"),
                }

            logger.info("Restored %d active sessions from database", len(active_rows))

    @classmethod
    def cleanup_stale_sessions(cls, max_age_days: int = 7) -> int:
        """End active sessions that haven't been used for more than max_age_days."""
        from ..database import get_connection

        cutoff = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=max_age_days)
        ).strftime("%Y-%m-%d %H:%M:%S")

        with get_connection() as conn:
            cursor = conn.execute(
                """UPDATE super_agent_sessions
                   SET status = 'completed', ended_at = CURRENT_TIMESTAMP
                   WHERE status = 'active'
                   AND started_at < ?""",
                (cutoff,),
            )
            conn.commit()
            count = cursor.rowcount

        if count > 0:
            # Also remove from in-memory cache
            with cls._lock:
                stale_ids = [
                    sid
                    for sid, s in cls._active_sessions.items()
                    if s["status"] == "active"
                    and sid not in {r["id"] for r in get_active_sessions_list()}
                ]
                for sid in stale_ids:
                    del cls._active_sessions[sid]

            logger.info("Cleaned up %d stale sessions (older than %d days)", count, max_age_days)
        return count

    @classmethod
    def get_output_lines(cls, session_id: str) -> List[str]:
        """Return output buffer lines for a session."""
        with cls._lock:
            session = cls._active_sessions.get(session_id)
            if not session:
                return []
            return list(session["output_buffer"])
