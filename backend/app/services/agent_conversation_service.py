"""Agent conversation service for interactive agent creation with SSE streaming."""

import datetime
import json
import logging
import secrets
import string
import subprocess
import threading
from dataclasses import asdict, dataclass
from http import HTTPStatus
from queue import Empty, Queue
from typing import Dict, Generator, List, Tuple

logger = logging.getLogger(__name__)

from ..database import (
    add_agent,
    create_agent_conversation,
    get_agent_conversation,
    update_agent_conversation,
)
from ..services.conversation_streaming import stream_llm_response

# Stale conversation cleanup threshold (30 minutes)
STALE_CONVERSATION_THRESHOLD = 1800

# System prompt for agent creation conversation
AGENT_CREATION_SYSTEM_PROMPT = """You are an AI assistant helping to create a new AI Agent. Your job is to guide the user through defining their agent step by step.

Help the user define:
1. **Purpose & Description** - What will this agent do?
2. **Role** - What role should the agent take on? (e.g., "You are a senior code reviewer...")
3. **Goals** - What specific objectives should the agent accomplish?
4. **Skills** - What Claude skills should this agent use?
5. **Context** - Any additional context the agent needs?

Ask clarifying questions and provide suggestions. Be conversational and helpful.

When you have gathered enough information, summarize the agent configuration and ask the user to confirm.

When the user confirms, output the final configuration in this exact format:
---AGENT_CONFIG---
{
  "name": "Agent Name",
  "description": "Brief description",
  "role": "The role prompt",
  "goals": ["goal1", "goal2"],
  "skills": ["skill1", "skill2"],
  "context": "Additional context",
  "system_prompt": "Optional system prompt override"
}
---END_CONFIG---

Start by asking the user what kind of agent they want to create."""


@dataclass
class ConversationMessage:
    """A message in an agent creation conversation."""

    role: str  # 'user' | 'assistant' | 'system'
    content: str
    timestamp: str


class AgentConversationService:
    """Service for managing agent creation conversations with real-time SSE streaming."""

    # In-memory conversation state: {conv_id: {'messages': [ConversationMessage], 'processing': bool}}
    _conversations: Dict[str, dict] = {}
    # SSE subscribers: {conv_id: [Queue]}
    _subscribers: Dict[str, List[Queue]] = {}
    # Track conversation start times for cleanup
    _start_times: Dict[str, datetime.datetime] = {}
    # Lock for thread-safe operations
    _lock = threading.Lock()

    @classmethod
    def start_conversation(cls) -> Tuple[dict, HTTPStatus]:
        """Start a new agent creation conversation."""
        conv_id = create_agent_conversation()

        # Initialize in-memory state
        initial_messages = [
            ConversationMessage(
                role="system",
                content=AGENT_CREATION_SYSTEM_PROMPT,
                timestamp=datetime.datetime.now().isoformat(),
            )
        ]

        with cls._lock:
            cls._conversations[conv_id] = {"messages": initial_messages, "processing": False}
            cls._subscribers[conv_id] = []
            cls._start_times[conv_id] = datetime.datetime.now()

        # Store messages in database
        update_agent_conversation(
            conv_id, messages=json.dumps([asdict(m) for m in initial_messages])
        )

        return {
            "conversation_id": conv_id,
            "message": "Conversation started. Ready to help you create an agent.",
        }, HTTPStatus.CREATED

    @classmethod
    def send_message(
        cls,
        conv_id: str,
        message: str,
        backend: str | None = None,
        account_id: str | None = None,
        model: str | None = None,
    ) -> Tuple[dict, HTTPStatus]:
        """Send a user message to the conversation and trigger Claude response."""
        conv = get_agent_conversation(conv_id)
        if not conv:
            return {"error": "Conversation not found"}, HTTPStatus.NOT_FOUND

        if conv.get("status") != "active":
            return {"error": "Conversation is not active"}, HTTPStatus.BAD_REQUEST

        # Check if already processing
        with cls._lock:
            if conv_id in cls._conversations and cls._conversations[conv_id].get("processing"):
                return {"error": "Already processing a message"}, HTTPStatus.CONFLICT

            # Initialize conversation state if not exists
            if conv_id not in cls._conversations:
                existing_messages = []
                if conv.get("messages"):
                    try:
                        msg_data = json.loads(conv["messages"])
                        existing_messages = [ConversationMessage(**m) for m in msg_data]
                    except (json.JSONDecodeError, TypeError):
                        existing_messages = []
                cls._conversations[conv_id] = {"messages": existing_messages, "processing": False}
                cls._subscribers[conv_id] = []
                cls._start_times[conv_id] = datetime.datetime.now()

            cls._conversations[conv_id]["processing"] = True

        # Add user message
        user_msg = ConversationMessage(
            role="user", content=message, timestamp=datetime.datetime.now().isoformat()
        )

        with cls._lock:
            cls._conversations[conv_id]["messages"].append(user_msg)

        # Generate message ID
        msg_id = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8))

        # Broadcast user message to subscribers
        cls._broadcast(conv_id, "user_message", asdict(user_msg))

        # Run Claude in background thread
        thread = threading.Thread(
            target=cls._run_claude_response,
            args=(conv_id, msg_id),
            kwargs={"backend": backend, "account_id": account_id, "model": model},
            daemon=True,
        )
        thread.start()

        return {"message_id": msg_id, "status": "processing"}, HTTPStatus.ACCEPTED

    @classmethod
    def _run_claude_response(
        cls,
        conv_id: str,
        msg_id: str,
        backend: str | None = None,
        account_id: str | None = None,
        model: str | None = None,
    ):
        """Stream an LLM response in real-time (runs in background thread)."""
        try:
            # Build conversation context as OpenAI-format messages
            with cls._lock:
                if conv_id not in cls._conversations:
                    logger.warning(f"Conversation {conv_id} not found in memory")
                    return
                conv_messages = cls._conversations[conv_id]["messages"]

            messages = [{"role": msg.role, "content": msg.content} for msg in conv_messages]

            logger.info(f"Streaming LLM response for conversation {conv_id}")

            # Broadcast that we're starting response generation
            cls._broadcast(conv_id, "response_start", {"msg_id": msg_id})

            # Stream chunks from the shared streaming utility
            response_chunks: list[str] = []
            for chunk in stream_llm_response(
                messages, model=model, account_email=account_id, backend=backend
            ):
                response_chunks.append(chunk)
                logger.debug(f"LLM chunk for {conv_id}: {chunk[:100]}...")
                cls._broadcast(conv_id, "response_chunk", {"msg_id": msg_id, "content": chunk})

            full_response = "".join(response_chunks)
            if not full_response.strip():
                logger.warning(f"LLM returned empty output for conversation {conv_id}")
                full_response = "(No response generated)"

            # Create assistant message
            assistant_msg = ConversationMessage(
                role="assistant",
                content=full_response,
                timestamp=datetime.datetime.now().isoformat(),
            )

            with cls._lock:
                if conv_id in cls._conversations:
                    cls._conversations[conv_id]["messages"].append(assistant_msg)
                    cls._conversations[conv_id]["processing"] = False

                    # Update database
                    all_messages = [asdict(m) for m in cls._conversations[conv_id]["messages"]]
                    update_agent_conversation(conv_id, messages=json.dumps(all_messages))

            # Broadcast completion
            cls._broadcast(
                conv_id,
                "response_complete",
                {"msg_id": msg_id, "content": full_response, "backend": backend or "claude"},
            )

        except FileNotFoundError as e:
            error_msg = "Claude CLI not found. Please ensure 'claude' is installed and in PATH."
            logger.error(f"Claude CLI not found for conversation {conv_id}: {e}")
            with cls._lock:
                if conv_id in cls._conversations:
                    cls._conversations[conv_id]["processing"] = False
            cls._broadcast(conv_id, "error", {"msg_id": msg_id, "error": error_msg})

        except subprocess.SubprocessError as e:
            error_msg = f"Subprocess error: {str(e)}"
            logger.error(f"Subprocess error for conversation {conv_id}: {e}")
            with cls._lock:
                if conv_id in cls._conversations:
                    cls._conversations[conv_id]["processing"] = False
            cls._broadcast(conv_id, "error", {"msg_id": msg_id, "error": error_msg})

        except Exception as e:
            logger.exception(f"Unexpected error in Claude response for conversation {conv_id}")
            with cls._lock:
                if conv_id in cls._conversations:
                    cls._conversations[conv_id]["processing"] = False
            cls._broadcast(conv_id, "error", {"msg_id": msg_id, "error": str(e)})

    @classmethod
    def subscribe(cls, conv_id: str) -> Generator[str, None, None]:
        """SSE generator for real-time conversation streaming."""
        queue: Queue = Queue()

        # Check if conversation exists
        conv = get_agent_conversation(conv_id)
        if not conv:
            yield cls._format_sse("error", {"error": "Conversation not found"})
            return

        with cls._lock:
            # Initialize if needed
            if conv_id not in cls._conversations:
                existing_messages = []
                if conv.get("messages"):
                    try:
                        msg_data = json.loads(conv["messages"])
                        existing_messages = [ConversationMessage(**m) for m in msg_data]
                    except (json.JSONDecodeError, TypeError):
                        existing_messages = []
                cls._conversations[conv_id] = {"messages": existing_messages, "processing": False}
                cls._subscribers[conv_id] = []
                cls._start_times[conv_id] = datetime.datetime.now()

            # Send existing messages
            for msg in cls._conversations[conv_id]["messages"]:
                if msg.role != "system":  # Don't send system prompt to client
                    yield cls._format_sse("message", asdict(msg))

            # Register subscriber
            cls._subscribers[conv_id].append(queue)

        try:
            while True:
                try:
                    event = queue.get(timeout=30)
                    if event is None:
                        break
                    yield event
                except Empty:
                    yield ": keepalive\n\n"
        finally:
            with cls._lock:
                if conv_id in cls._subscribers:
                    try:
                        cls._subscribers[conv_id].remove(queue)
                    except ValueError:
                        pass

    @classmethod
    def finalize_agent(cls, conv_id: str) -> Tuple[dict, HTTPStatus]:
        """Parse conversation to create an agent and return it."""
        conv = get_agent_conversation(conv_id)
        if not conv:
            return {"error": "Conversation not found"}, HTTPStatus.NOT_FOUND

        # Get messages
        messages = []
        with cls._lock:
            if conv_id in cls._conversations:
                messages = cls._conversations[conv_id]["messages"]

        if not messages and conv.get("messages"):
            try:
                msg_data = json.loads(conv["messages"])
                messages = [ConversationMessage(**m) for m in msg_data]
            except (json.JSONDecodeError, TypeError):
                pass

        # Find the agent config in the last assistant message
        agent_config = None
        for msg in reversed(messages):
            if msg.role == "assistant" and "---AGENT_CONFIG---" in msg.content:
                # Extract JSON between markers
                try:
                    start = msg.content.index("---AGENT_CONFIG---") + len("---AGENT_CONFIG---")
                    end = msg.content.index("---END_CONFIG---")
                    config_json = msg.content[start:end].strip()
                    agent_config = json.loads(config_json)
                    break
                except (ValueError, json.JSONDecodeError):
                    continue

        if not agent_config:
            return {
                "error": "No valid agent configuration found in conversation. Please complete the agent creation process."
            }, HTTPStatus.BAD_REQUEST

        # Create the agent
        name = agent_config.get("name", "Unnamed Agent")
        agent_id = add_agent(
            name=name,
            description=agent_config.get("description"),
            role=agent_config.get("role"),
            goals=json.dumps(agent_config.get("goals", [])),
            context=agent_config.get("context"),
            backend_type="claude",
            skills=json.dumps(agent_config.get("skills", [])),
            documents=None,
            system_prompt=agent_config.get("system_prompt"),
            creation_conversation_id=conv_id,
            creation_status="completed",
        )

        if not agent_id:
            return {"error": "Failed to create agent"}, HTTPStatus.INTERNAL_SERVER_ERROR

        # Update conversation with agent_id and mark as completed
        update_agent_conversation(conv_id, agent_id=agent_id, status="completed")

        # Cleanup in-memory state
        cls._cleanup_conversation(conv_id)

        # Return the created agent
        from ..database import get_agent

        agent = get_agent(agent_id)

        return {
            "message": f"Agent '{name}' created successfully",
            "agent_id": agent_id,
            "agent": agent,
        }, HTTPStatus.CREATED

    @classmethod
    def abandon_conversation(cls, conv_id: str) -> Tuple[dict, HTTPStatus]:
        """Abandon a conversation without creating an agent."""
        conv = get_agent_conversation(conv_id)
        if not conv:
            return {"error": "Conversation not found"}, HTTPStatus.NOT_FOUND

        update_agent_conversation(conv_id, status="abandoned")
        cls._cleanup_conversation(conv_id)

        return {"message": "Conversation abandoned"}, HTTPStatus.OK

    @classmethod
    def get_conversation(cls, conv_id: str) -> Tuple[dict, HTTPStatus]:
        """Get a conversation with its messages."""
        conv = get_agent_conversation(conv_id)
        if not conv:
            return {"error": "Conversation not found"}, HTTPStatus.NOT_FOUND

        # Parse messages
        messages = []
        if conv.get("messages"):
            try:
                messages = json.loads(conv["messages"])
            except json.JSONDecodeError:
                pass

        conv["messages_parsed"] = messages
        return conv, HTTPStatus.OK

    @classmethod
    def _broadcast(cls, conv_id: str, event_type: str, data: dict):
        """Broadcast an event to all subscribers."""
        message = cls._format_sse(event_type, data)
        with cls._lock:
            if conv_id in cls._subscribers:
                for q in cls._subscribers[conv_id]:
                    q.put(message)

    @staticmethod
    def _format_sse(event_type: str, data: dict) -> str:
        """Format data as SSE message."""
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

    @classmethod
    def _cleanup_conversation(cls, conv_id: str):
        """Clean up in-memory conversation state."""
        with cls._lock:
            cls._conversations.pop(conv_id, None)
            cls._start_times.pop(conv_id, None)
            if conv_id in cls._subscribers:
                for q in cls._subscribers[conv_id]:
                    q.put(None)  # Signal end of stream
                cls._subscribers.pop(conv_id, None)

    @classmethod
    def cleanup_stale_conversations(cls) -> int:
        """Clean up stale conversation buffers."""
        now = datetime.datetime.now()
        stale_ids = []

        with cls._lock:
            for conv_id, start_time in list(cls._start_times.items()):
                elapsed = (now - start_time).total_seconds()
                if elapsed > STALE_CONVERSATION_THRESHOLD:
                    stale_ids.append(conv_id)

        cleaned = 0
        for conv_id in stale_ids:
            cls._cleanup_conversation(conv_id)
            update_agent_conversation(conv_id, status="abandoned")
            cleaned += 1

        return cleaned
