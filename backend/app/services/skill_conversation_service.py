"""Skill conversation service for interactive skill creation with SSE streaming."""

import datetime
import json
import logging
import os
import secrets
import string
import threading
from dataclasses import asdict, dataclass
from http import HTTPStatus
from queue import Empty, Queue
from typing import Dict, Generator, List, Tuple

logger = logging.getLogger(__name__)

from ..database import (
    add_user_skill,
    get_user_skill,
)
from .skill_discovery_service import get_playground_working_dir

# Stale conversation cleanup threshold (30 minutes)
STALE_CONVERSATION_THRESHOLD = 1800

# System prompt for skill creation conversation
SKILL_CREATION_SYSTEM_PROMPT = """You are an AI assistant helping to create a new Claude Code Skill. Your job is to guide the user through defining their skill step by step.

A skill in Claude Code is a markdown file that contains instructions for Claude to follow when performing a specific task. Skills are triggered by matching patterns in user prompts.

Help the user define:
1. **Skill Name** - A short, descriptive name (e.g., "code-review", "test-generator")
2. **Description** - What will this skill do? When should it be triggered?
3. **Trigger Phrases** - What phrases or patterns should trigger this skill? (e.g., "review this code", "generate tests")
4. **Instructions** - The detailed instructions for Claude to follow
5. **Examples** - Optional examples of how to use the skill

Ask clarifying questions and provide suggestions. Be conversational and helpful.

When you have gathered enough information, summarize the skill configuration and ask the user to confirm.

When the user confirms, output the final configuration in this exact format:
---SKILL_CONFIG---
{
  "skill_name": "skill-name",
  "description": "Brief description of what this skill does",
  "triggers": ["trigger phrase 1", "trigger phrase 2"],
  "instructions": "The detailed markdown instructions for the skill...",
  "examples": ["example 1", "example 2"]
}
---END_CONFIG---

Start by asking the user what kind of skill they want to create."""


@dataclass
class ConversationMessage:
    """A message in a skill creation conversation."""

    role: str  # 'user' | 'assistant' | 'system'
    content: str
    timestamp: str


class SkillConversationService:
    """Service for managing skill creation conversations with real-time SSE streaming."""

    # In-memory conversation state: {conv_id: {'messages': [ConversationMessage], 'processing': bool}}
    _conversations: Dict[str, dict] = {}
    # SSE subscribers: {conv_id: [Queue]}
    _subscribers: Dict[str, List[Queue]] = {}
    # Track conversation start times for cleanup
    _start_times: Dict[str, datetime.datetime] = {}
    # Lock for thread-safe operations
    _lock = threading.Lock()

    @classmethod
    def _generate_conv_id(cls) -> str:
        """Generate a unique conversation ID."""
        chars = string.ascii_lowercase + string.digits
        return "skill_" + "".join(secrets.choice(chars) for _ in range(16))

    @classmethod
    def start_conversation(cls) -> Tuple[dict, HTTPStatus]:
        """Start a new skill creation conversation."""
        conv_id = cls._generate_conv_id()

        # Initialize in-memory state
        initial_messages = [
            ConversationMessage(
                role="system",
                content=SKILL_CREATION_SYSTEM_PROMPT,
                timestamp=datetime.datetime.now().isoformat(),
            )
        ]

        with cls._lock:
            cls._conversations[conv_id] = {"messages": initial_messages, "processing": False}
            cls._subscribers[conv_id] = []
            cls._start_times[conv_id] = datetime.datetime.now()

        # Trigger initial assistant greeting
        cls._process_with_claude(conv_id, "Hello, I'd like to create a new skill.")

        return {
            "conversation_id": conv_id,
            "message": "Skill creation conversation started",
        }, HTTPStatus.CREATED

    @classmethod
    def get_conversation(cls, conv_id: str) -> Tuple[dict, HTTPStatus]:
        """Get conversation details and messages."""
        if conv_id not in cls._conversations:
            return {"error": "Conversation not found"}, HTTPStatus.NOT_FOUND

        conv = cls._conversations[conv_id]
        messages = [asdict(m) for m in conv["messages"] if m.role != "system"]

        return {
            "id": conv_id,
            "status": "active" if not conv.get("finalized") else "completed",
            "messages_parsed": messages,
        }, HTTPStatus.OK

    @classmethod
    def send_message(
        cls,
        conv_id: str,
        message: str,
        backend: str | None = None,
        account_id: str | None = None,
        model: str | None = None,
    ) -> Tuple[dict, HTTPStatus]:
        """Send a user message and process with Claude."""
        if conv_id not in cls._conversations:
            return {"error": "Conversation not found"}, HTTPStatus.NOT_FOUND

        conv = cls._conversations[conv_id]
        if conv.get("processing"):
            return {"error": "Conversation is processing"}, HTTPStatus.CONFLICT

        # Add user message
        user_msg = ConversationMessage(
            role="user",
            content=message,
            timestamp=datetime.datetime.now().isoformat(),
        )
        conv["messages"].append(user_msg)

        # Broadcast to subscribers
        cls._broadcast(conv_id, "user_message", asdict(user_msg))

        # Process with Claude in background
        threading.Thread(
            target=cls._process_with_claude,
            args=(conv_id, message),
            kwargs={"backend": backend, "account_id": account_id, "model": model},
        ).start()

        return {"message_id": conv_id, "status": "processing"}, HTTPStatus.OK

    @classmethod
    def subscribe(cls, conv_id: str) -> Generator[str, None, None]:
        """Subscribe to SSE events for a conversation."""
        if conv_id not in cls._conversations:
            yield f"event: error\ndata: {json.dumps({'error': 'Conversation not found'})}\n\n"
            return

        queue: Queue = Queue()
        with cls._lock:
            if conv_id in cls._subscribers:
                cls._subscribers[conv_id].append(queue)

        try:
            # Send existing messages
            conv = cls._conversations.get(conv_id)
            if conv:
                for msg in conv["messages"]:
                    if msg.role != "system":
                        yield f"event: message\ndata: {json.dumps(asdict(msg))}\n\n"

            # Stream new events
            while True:
                try:
                    event = queue.get(timeout=30)
                    if event is None:
                        break
                    yield event
                except Empty:
                    yield f"event: ping\ndata: {json.dumps({'time': datetime.datetime.now().isoformat()})}\n\n"
        finally:
            with cls._lock:
                if conv_id in cls._subscribers and queue in cls._subscribers[conv_id]:
                    cls._subscribers[conv_id].remove(queue)

    @classmethod
    def finalize_skill(cls, conv_id: str) -> Tuple[dict, HTTPStatus]:
        """Finalize the conversation and create the skill."""
        if conv_id not in cls._conversations:
            return {"error": "Conversation not found"}, HTTPStatus.NOT_FOUND

        conv = cls._conversations[conv_id]

        # Find the skill config in the last assistant message
        skill_config = None
        for msg in reversed(conv["messages"]):
            if msg.role == "assistant" and "---SKILL_CONFIG---" in msg.content:
                try:
                    start = msg.content.index("---SKILL_CONFIG---") + len("---SKILL_CONFIG---")
                    end = msg.content.index("---END_CONFIG---")
                    config_str = msg.content[start:end].strip()
                    skill_config = json.loads(config_str)
                    break
                except (ValueError, json.JSONDecodeError) as e:
                    logger.error(f"Failed to parse skill config: {e}")
                    continue

        if not skill_config:
            return {
                "error": "No skill configuration found. Please continue the conversation."
            }, HTTPStatus.BAD_REQUEST

        # Create the skill
        skill_name = skill_config.get("skill_name", "Untitled Skill")
        description = skill_config.get("description", "")
        instructions = skill_config.get("instructions", "")
        triggers = skill_config.get("triggers", [])
        examples = skill_config.get("examples", [])

        # Build the skill content as markdown
        skill_content = f"""# {skill_name}

{description}

## Triggers

Use this skill when:
"""
        for trigger in triggers:
            skill_content += f"- {trigger}\n"

        skill_content += f"""
## Instructions

{instructions}
"""

        if examples:
            skill_content += "\n## Examples\n\n"
            for example in examples:
                skill_content += f"- {example}\n"

        # Create skill path
        skill_path = f".claude/skills/{skill_name}/SKILL.md"

        # Write SKILL.md to filesystem
        try:
            abs_path = os.path.join(get_playground_working_dir(), skill_path)
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, "w") as f:
                f.write(skill_content)
            logger.info(f"Wrote SKILL.md to {abs_path}")
        except OSError as e:
            logger.error(f"Failed to write SKILL.md to disk: {e}")

        # Add to database
        try:
            skill_id = add_user_skill(
                skill_name=skill_name,
                skill_path=skill_path,
                description=description,
                enabled=1,
                selected_for_harness=0,
                metadata=json.dumps(
                    {
                        "triggers": triggers,
                        "examples": examples,
                        "content": skill_content,
                    }
                ),
            )

            if not skill_id:
                return {"error": "Failed to create skill"}, HTTPStatus.INTERNAL_SERVER_ERROR

            # Mark conversation as finalized
            conv["finalized"] = True

            # Clean up
            cls._cleanup_conversation(conv_id)

            skill = get_user_skill(skill_id)

            return {
                "message": "Skill created successfully",
                "skill_id": skill_id,
                "skill": skill,
            }, HTTPStatus.CREATED

        except Exception as e:
            logger.error(f"Failed to create skill: {e}")
            return {"error": f"Failed to create skill: {str(e)}"}, HTTPStatus.INTERNAL_SERVER_ERROR

    @classmethod
    def abandon_conversation(cls, conv_id: str) -> Tuple[dict, HTTPStatus]:
        """Abandon a conversation without creating a skill."""
        if conv_id not in cls._conversations:
            return {"error": "Conversation not found"}, HTTPStatus.NOT_FOUND

        cls._cleanup_conversation(conv_id)
        return {"message": "Conversation abandoned"}, HTTPStatus.OK

    @classmethod
    def _broadcast(cls, conv_id: str, event_type: str, data: dict):
        """Broadcast an SSE event to all subscribers of a conversation."""
        if conv_id not in cls._subscribers:
            return

        event = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

        with cls._lock:
            for queue in cls._subscribers.get(conv_id, []):
                queue.put(event)

    @classmethod
    def _process_with_claude(
        cls,
        conv_id: str,
        user_message: str,
        backend: str | None = None,
        account_id: str | None = None,
        model: str | None = None,
    ):
        """Process a message with Claude using real-time LLM streaming."""
        if conv_id not in cls._conversations:
            return

        conv = cls._conversations[conv_id]
        conv["processing"] = True

        cls._broadcast(
            conv_id, "response_start", {"timestamp": datetime.datetime.now().isoformat()}
        )

        try:
            from .conversation_streaming import stream_llm_response

            # Build messages from conversation history
            messages = []
            for msg in conv["messages"]:
                messages.append({"role": msg.role, "content": msg.content})

            # Stream response chunks in real-time
            full_response_parts = []
            for chunk in stream_llm_response(
                messages, model=model, account_email=account_id, backend=backend
            ):
                full_response_parts.append(chunk)
                cls._broadcast(conv_id, "response_chunk", {"content": chunk})

            response = "".join(full_response_parts).strip()
            if not response:
                response = "(No response generated)"

            assistant_msg = ConversationMessage(
                role="assistant",
                content=response,
                timestamp=datetime.datetime.now().isoformat(),
            )
            conv["messages"].append(assistant_msg)

            cls._broadcast(
                conv_id,
                "response_complete",
                {"content": response, "backend": backend or "claude"},
            )

        except Exception as e:
            logger.error(f"Error processing with Claude: {e}")
            cls._broadcast(conv_id, "error", {"error": str(e)})
        finally:
            conv["processing"] = False

    @classmethod
    def _cleanup_conversation(cls, conv_id: str):
        """Clean up a conversation and its resources."""
        with cls._lock:
            # Signal subscribers to stop
            for queue in cls._subscribers.get(conv_id, []):
                queue.put(None)

            cls._conversations.pop(conv_id, None)
            cls._subscribers.pop(conv_id, None)
            cls._start_times.pop(conv_id, None)
