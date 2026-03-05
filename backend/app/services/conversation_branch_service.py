"""Conversation branching service for execution transcripts.

Creates branches from any point in a conversation, preserving the original
thread intact (immutable). Based on ContextBranch paper (arXiv:2512.13914)
achieving 58% context reduction and improved focus.

Messages are stored as normalized rows with parent_message_id references
forming a tree structure -- NOT as JSON blobs.
"""

import json
import logging

from ..db.agents import get_agent_conversation
from ..db.conversation_branches import (
    count_messages_for_branch,
    create_branch,
    create_message,
    get_branch,
    get_branches_for_conversation,
    get_messages_for_branch,
)

logger = logging.getLogger(__name__)


class ConversationBranchService:
    """Service for creating and navigating conversation branches."""

    @classmethod
    def create_branch(
        cls, conversation_id: str, fork_message_index: int, name: str | None = None
    ) -> dict:
        """Create a new branch forking from a specific message index.

        Deep-copies messages from index 0 to fork_message_index (inclusive)
        into the new branch. The original conversation's messages JSON field
        is NEVER modified (immutable per ContextBranch paper).

        Args:
            conversation_id: The conversation to branch from.
            fork_message_index: Index of the last message to include (inclusive).
            name: Optional branch name.

        Returns:
            Branch details dict.

        Raises:
            ValueError: If conversation not found or index out of bounds.
        """
        conversation = get_agent_conversation(conversation_id)
        if not conversation:
            raise ValueError(f"Conversation not found: {conversation_id}")

        # Parse messages from the conversation's JSON field
        try:
            messages = json.loads(conversation.get("messages", "[]"))
        except (json.JSONDecodeError, TypeError):
            messages = []

        if not messages:
            raise ValueError("Conversation has no messages to branch from")

        if fork_message_index < 0 or fork_message_index >= len(messages):
            raise ValueError(
                f"fork_message_index {fork_message_index} out of bounds (0 to {len(messages) - 1})"
            )

        # Create the branch record
        branch_id = create_branch(
            conversation_id=conversation_id,
            name=name,
        )
        if not branch_id:
            raise ValueError("Failed to create branch record")

        # Deep-copy messages up to the fork point into individual rows
        prev_message_id = None
        fork_msg_id = None

        for idx in range(fork_message_index + 1):
            msg = messages[idx]
            role = msg.get("role", "user")
            content = msg.get("content", "")

            message_id = create_message(
                conversation_id=conversation_id,
                branch_id=branch_id,
                role=role,
                content=content,
                parent_message_id=prev_message_id,
                message_index=idx,
            )
            prev_message_id = message_id

            if idx == fork_message_index:
                fork_msg_id = message_id

        # Update branch with fork_message_id
        if fork_msg_id:
            from ..db.connection import get_connection

            with get_connection() as conn:
                conn.execute(
                    "UPDATE conversation_branches SET fork_message_id = ? WHERE id = ?",
                    (fork_msg_id, branch_id),
                )
                conn.commit()

        branch = get_branch(branch_id)
        return branch if branch else {"branch_id": branch_id}

    @classmethod
    def create_main_branch(cls, conversation_id: str) -> dict:
        """Create a 'main' branch for a conversation without branch structure.

        Copies all existing messages from the JSON array into
        conversation_messages rows.

        Args:
            conversation_id: The conversation to create main branch for.

        Returns:
            Main branch details dict.

        Raises:
            ValueError: If conversation not found.
        """
        conversation = get_agent_conversation(conversation_id)
        if not conversation:
            raise ValueError(f"Conversation not found: {conversation_id}")

        try:
            messages = json.loads(conversation.get("messages", "[]"))
        except (json.JSONDecodeError, TypeError):
            messages = []

        branch_id = create_branch(
            conversation_id=conversation_id,
            name="main",
        )
        if not branch_id:
            raise ValueError("Failed to create main branch record")

        prev_message_id = None
        for idx, msg in enumerate(messages):
            role = msg.get("role", "user")
            content = msg.get("content", "")
            message_id = create_message(
                conversation_id=conversation_id,
                branch_id=branch_id,
                role=role,
                content=content,
                parent_message_id=prev_message_id,
                message_index=idx,
            )
            prev_message_id = message_id

        branch = get_branch(branch_id)
        return branch if branch else {"branch_id": branch_id}

    @classmethod
    def add_message(cls, branch_id: str, role: str, content: str) -> dict:
        """Add a new message to a branch.

        Args:
            branch_id: The branch to add the message to.
            role: Message role (user, assistant, system).
            content: Message content.

        Returns:
            Message details dict.

        Raises:
            ValueError: If branch not found.
        """
        branch = get_branch(branch_id)
        if not branch:
            raise ValueError(f"Branch not found: {branch_id}")

        conversation_id = branch["conversation_id"]
        message_count = count_messages_for_branch(branch_id)

        # Get the last message to set as parent
        branch_messages = get_messages_for_branch(branch_id, conversation_id)
        parent_message_id = branch_messages[-1]["id"] if branch_messages else None

        message_id = create_message(
            conversation_id=conversation_id,
            branch_id=branch_id,
            role=role,
            content=content,
            parent_message_id=parent_message_id,
            message_index=message_count,
        )

        if not message_id:
            raise ValueError("Failed to create message")

        from ..db.conversation_branches import get_message

        msg = get_message(message_id)
        return msg if msg else {"id": message_id}

    @classmethod
    def get_branch_messages(cls, branch_id: str) -> list[dict]:
        """Get all messages for a branch ordered by message_index.

        Args:
            branch_id: The branch to get messages for.

        Returns:
            Ordered list of message dicts.

        Raises:
            ValueError: If branch not found.
        """
        branch = get_branch(branch_id)
        if not branch:
            raise ValueError(f"Branch not found: {branch_id}")

        return get_messages_for_branch(branch_id, branch["conversation_id"])

    @classmethod
    def get_conversation_branches(cls, conversation_id: str) -> list[dict]:
        """Get all branches for a conversation with message counts.

        Args:
            conversation_id: The conversation to get branches for.

        Returns:
            List of branch dicts with message_count field added.
        """
        branches = get_branches_for_conversation(conversation_id)
        for branch in branches:
            branch["message_count"] = count_messages_for_branch(branch["id"])
        return branches

    @classmethod
    def get_branch_tree(cls, conversation_id: str) -> dict:
        """Build a tree structure showing all branches and their relationships.

        Args:
            conversation_id: The conversation to build tree for.

        Returns:
            Nested dict: {branch_id, name, children: [...], message_count}
        """
        branches = get_branches_for_conversation(conversation_id)
        if not branches:
            return {"conversation_id": conversation_id, "branches": []}

        # Build lookup by parent_branch_id
        branch_map: dict[str, dict] = {}
        for b in branches:
            node = {
                "branch_id": b["id"],
                "name": b.get("name"),
                "status": b.get("status", "active"),
                "fork_message_id": b.get("fork_message_id"),
                "message_count": count_messages_for_branch(b["id"]),
                "children": [],
            }
            branch_map[b["id"]] = node

        # Build tree from parent relationships
        roots = []
        for b in branches:
            node = branch_map[b["id"]]
            parent_id = b.get("parent_branch_id")
            if parent_id and parent_id in branch_map:
                branch_map[parent_id]["children"].append(node)
            else:
                roots.append(node)

        return {
            "conversation_id": conversation_id,
            "branches": roots,
        }
