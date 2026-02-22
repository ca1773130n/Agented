"""In-process message bus for inter-agent messaging with SSE delivery and TTL sweep."""

import datetime
import json
import logging
import threading
from queue import Empty, Queue
from typing import Dict, Generator, List, Optional

from ..db.messages import (
    add_agent_message,
    batch_add_broadcast_messages,
    expire_stale_messages,
    update_message_status,
)
from ..db.super_agents import get_all_super_agents

logger = logging.getLogger(__name__)


class AgentMessageBusService:
    """In-process message bus with Queue-per-agent, SSE delivery, and background TTL sweep."""

    # Subscribers: {agent_id: [Queue]}
    _subscribers: Dict[str, List[Queue]] = {}
    _lock = threading.Lock()
    _shutdown_event = threading.Event()
    _flush_thread: Optional[threading.Thread] = None

    @classmethod
    def start(cls):
        """Start the background worker for TTL sweeps."""
        cls._shutdown_event.clear()
        cls._flush_thread = threading.Thread(
            target=cls._background_worker, daemon=True, name="message-bus-worker"
        )
        cls._flush_thread.start()
        logger.info("AgentMessageBusService started")

    @classmethod
    def stop(cls):
        """Stop the background worker."""
        cls._shutdown_event.set()
        if cls._flush_thread and cls._flush_thread.is_alive():
            cls._flush_thread.join(timeout=10)
        cls._flush_thread = None
        logger.info("AgentMessageBusService stopped")

    @classmethod
    def send_message(
        cls,
        from_agent_id: str,
        to_agent_id: str = None,
        message_type: str = "message",
        priority: str = "normal",
        subject: str = None,
        content: str = "",
        ttl_seconds: int = None,
    ) -> Optional[str]:
        """Send a message from one agent to another (or broadcast).

        For broadcast messages, creates individual messages for all other SuperAgents.
        Returns the message_id (or first msg_id for broadcast), or None on failure.
        """
        # Calculate expires_at from ttl_seconds
        expires_at = None
        if ttl_seconds:
            expires_at = (
                datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(seconds=ttl_seconds)
            ).strftime("%Y-%m-%d %H:%M:%S")

        if message_type == "broadcast":
            return cls._send_broadcast(
                from_agent_id, priority, subject, content, ttl_seconds, expires_at
            )
        else:
            return cls._send_single(
                from_agent_id,
                to_agent_id,
                message_type,
                priority,
                subject,
                content,
                ttl_seconds,
                expires_at,
            )

    @classmethod
    def _send_single(
        cls,
        from_agent_id: str,
        to_agent_id: str,
        message_type: str,
        priority: str,
        subject: str,
        content: str,
        ttl_seconds: int,
        expires_at: str,
    ) -> Optional[str]:
        """Send a single message. Persist first, then push to subscriber if connected."""
        # FIRST: persist to DB as 'pending'
        msg_id = add_agent_message(
            from_agent_id=from_agent_id,
            to_agent_id=to_agent_id,
            message_type=message_type,
            priority=priority,
            subject=subject,
            content=content,
            ttl_seconds=ttl_seconds,
            expires_at=expires_at,
        )
        if not msg_id:
            return None

        # THEN: push to active subscriber if connected
        cls._push_to_subscriber(to_agent_id, msg_id, from_agent_id, subject, content, priority)

        return msg_id

    @classmethod
    def _send_broadcast(
        cls,
        from_agent_id: str,
        priority: str,
        subject: str,
        content: str,
        ttl_seconds: int,
        expires_at: str,
    ) -> Optional[str]:
        """Send broadcast to all SuperAgents except sender."""
        all_agents = get_all_super_agents()
        recipients = [a["id"] for a in all_agents if a["id"] != from_agent_id]

        if not recipients:
            return None

        # Persist all messages in one transaction
        msg_ids = batch_add_broadcast_messages(
            from_agent_id=from_agent_id,
            recipients=recipients,
            message_type="broadcast",
            priority=priority,
            subject=subject,
            content=content,
            ttl_seconds=ttl_seconds,
            expires_at=expires_at,
        )

        # Push to active subscribers
        for i, recipient_id in enumerate(recipients):
            cls._push_to_subscriber(
                recipient_id, msg_ids[i], from_agent_id, subject, content, priority
            )

        return msg_ids[0] if msg_ids else None

    @classmethod
    def _push_to_subscriber(
        cls,
        agent_id: str,
        msg_id: str,
        from_agent_id: str,
        subject: str,
        content: str,
        priority: str,
    ):
        """Push an SSE event to an active subscriber and mark as delivered."""
        with cls._lock:
            queues = cls._subscribers.get(agent_id, [])
            if not queues:
                return  # No active subscriber, leave as pending for prompt injection

            event = cls._format_sse(
                "message",
                {
                    "message_id": msg_id,
                    "from_agent_id": from_agent_id,
                    "subject": subject,
                    "content": content,
                    "priority": priority,
                },
            )
            for q in queues:
                q.put(event)

        # Mark as delivered AFTER successful push
        update_message_status(msg_id, "delivered")

    @classmethod
    def subscribe(cls, agent_id: str) -> Generator[str, None, None]:
        """SSE generator for real-time message notifications.

        Yields SSE-formatted events. Sends keepalive every 30 seconds.
        """
        queue: Queue = Queue()

        with cls._lock:
            if agent_id not in cls._subscribers:
                cls._subscribers[agent_id] = []
            cls._subscribers[agent_id].append(queue)

        try:
            while True:
                try:
                    event = queue.get(timeout=30)
                    if event is None:
                        break  # End of stream
                    yield event
                except Empty:
                    # Send keepalive comment
                    yield ": keepalive\n\n"
        finally:
            # Cleanup: remove queue from subscribers
            with cls._lock:
                if agent_id in cls._subscribers:
                    try:
                        cls._subscribers[agent_id].remove(queue)
                    except ValueError:
                        pass

    @staticmethod
    def _format_sse(event_type: str, data: dict) -> str:
        """Format data as an SSE message."""
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

    @classmethod
    def _background_worker(cls):
        """Background worker that runs TTL sweeps every 60 seconds."""
        logger.info("Message bus background worker started")
        while not cls._shutdown_event.is_set():
            try:
                expired_count = expire_stale_messages()
                if expired_count > 0:
                    logger.info("Expired %d stale messages", expired_count)
            except Exception:
                logger.exception("Error in message bus background worker")

            # Interruptible sleep for 60 seconds
            cls._shutdown_event.wait(60)

        logger.info("Message bus background worker stopped")
