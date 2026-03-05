"""Conversation branching API endpoints for execution transcripts."""

from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..services.conversation_branch_service import ConversationBranchService

tag = Tag(
    name="conversation-branches",
    description="Conversation branching for execution transcripts",
)
conversation_branches_bp = APIBlueprint(
    "conversation_branches", __name__, url_prefix="/admin", abp_tags=[tag]
)


class ConversationPath(BaseModel):
    conversation_id: str = Field(..., description="Conversation ID")


class BranchPath(BaseModel):
    branch_id: str = Field(..., description="Branch ID")


@conversation_branches_bp.post("/conversations/<conversation_id>/branches")
def create_branch(path: ConversationPath):
    """Create a new branch from a conversation at a specific message index.

    Deep-copies messages up to the fork point into the new branch.
    The original conversation messages are never modified.
    """
    body = request.get_json(silent=True) or {}
    fork_message_index = body.get("fork_message_index")

    if fork_message_index is None:
        return {
            "error": "Missing required field: fork_message_index"
        }, HTTPStatus.BAD_REQUEST

    try:
        fork_message_index = int(fork_message_index)
    except (TypeError, ValueError):
        return {
            "error": "fork_message_index must be an integer"
        }, HTTPStatus.BAD_REQUEST

    name = body.get("name")

    try:
        branch = ConversationBranchService.create_branch(
            path.conversation_id, fork_message_index, name=name
        )
        return branch, HTTPStatus.CREATED
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            return {"error": msg}, HTTPStatus.NOT_FOUND
        return {"error": msg}, HTTPStatus.BAD_REQUEST


@conversation_branches_bp.get("/conversations/<conversation_id>/branches")
def list_branches(path: ConversationPath):
    """List all branches for a conversation with message counts."""
    branches = ConversationBranchService.get_conversation_branches(
        path.conversation_id
    )
    return {"branches": branches, "total": len(branches)}, HTTPStatus.OK


@conversation_branches_bp.get("/conversations/<conversation_id>/branches/tree")
def get_branch_tree(path: ConversationPath):
    """Get the branch tree structure for a conversation.

    Returns a nested tree showing branch relationships and message counts.
    """
    tree = ConversationBranchService.get_branch_tree(path.conversation_id)
    return tree, HTTPStatus.OK


@conversation_branches_bp.get("/branches/<branch_id>/messages")
def get_branch_messages(path: BranchPath):
    """Get all messages for a branch, ordered by message index."""
    try:
        messages = ConversationBranchService.get_branch_messages(path.branch_id)
        return {"messages": messages, "total": len(messages)}, HTTPStatus.OK
    except ValueError as e:
        return {"error": str(e)}, HTTPStatus.NOT_FOUND


@conversation_branches_bp.post("/branches/<branch_id>/messages")
def add_branch_message(path: BranchPath):
    """Add a new message to a branch.

    Automatically links to the previous message in the branch
    via parent_message_id for tree navigation.
    """
    body = request.get_json(silent=True) or {}
    role = body.get("role")
    content = body.get("content")

    if not role or not content:
        return {
            "error": "Missing required fields: role, content"
        }, HTTPStatus.BAD_REQUEST

    try:
        message = ConversationBranchService.add_message(
            path.branch_id, role, content
        )
        return message, HTTPStatus.CREATED
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            return {"error": msg}, HTTPStatus.NOT_FOUND
        return {"error": msg}, HTTPStatus.BAD_REQUEST
