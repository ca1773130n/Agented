"""Collaborative execution viewer API endpoints.

Live collaborative execution viewing with presence indicators and inline comments.
Viewers subscribe to the existing execution SSE stream which now includes
presence_join, presence_leave, and inline_comment event types.
"""

from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..db.viewer_comments import delete_comment, get_comment
from ..services.collaborative_viewer_service import CollaborativeViewerService

tag = Tag(
    name="collaborative",
    description="Live collaborative execution viewing with presence and comments",
)
collaborative_bp = APIBlueprint("collaborative", __name__, url_prefix="/admin", abp_tags=[tag])


# -- Path models --


class ExecutionPath(BaseModel):
    execution_id: str = Field(..., description="Execution ID")


class CommentPath(BaseModel):
    comment_id: str = Field(..., description="Comment ID")


# -- Request body models --


class ViewerJoinBody(BaseModel):
    viewer_id: str = Field(..., description="Unique viewer identifier")
    name: str = Field(..., description="Display name of the viewer")


class ViewerLeaveBody(BaseModel):
    viewer_id: str = Field(..., description="Unique viewer identifier")


class HeartbeatBody(BaseModel):
    viewer_id: str = Field(..., description="Unique viewer identifier")


class PostCommentBody(BaseModel):
    viewer_id: str = Field(..., description="Viewer posting the comment")
    viewer_name: str = Field(..., description="Display name of the commenter")
    line_number: int = Field(..., ge=0, description="Stdout line number to anchor the comment")
    content: str = Field(..., min_length=1, description="Comment text")


# -- Endpoints --


@collaborative_bp.post("/executions/<execution_id>/viewers/join")
def join_execution_viewer(path: ExecutionPath):
    """Join as a viewer of an execution stream.

    Registers the viewer for presence tracking and broadcasts a
    presence_join event to all subscribers of the execution SSE stream.
    """
    body = request.get_json(silent=True) or {}
    viewer_id = body.get("viewer_id")
    name = body.get("name")

    if not viewer_id or not name:
        return {"error": "viewer_id and name are required"}, HTTPStatus.BAD_REQUEST

    viewers = CollaborativeViewerService.join(path.execution_id, viewer_id, name)
    return {"viewers": viewers}, HTTPStatus.OK


@collaborative_bp.post("/executions/<execution_id>/viewers/leave")
def leave_execution_viewer(path: ExecutionPath):
    """Leave as a viewer of an execution stream.

    Removes the viewer from presence tracking and broadcasts a
    presence_leave event to all subscribers.
    """
    body = request.get_json(silent=True) or {}
    viewer_id = body.get("viewer_id")

    if not viewer_id:
        return {"error": "viewer_id is required"}, HTTPStatus.BAD_REQUEST

    CollaborativeViewerService.leave(path.execution_id, viewer_id)
    return {"status": "left"}, HTTPStatus.OK


@collaborative_bp.post("/executions/<execution_id>/viewers/heartbeat")
def viewer_heartbeat(path: ExecutionPath):
    """Send a heartbeat to keep viewer presence alive.

    Must be called within the heartbeat interval (30s) to prevent
    the viewer from being cleaned up as stale.
    """
    body = request.get_json(silent=True) or {}
    viewer_id = body.get("viewer_id")

    if not viewer_id:
        return {"error": "viewer_id is required"}, HTTPStatus.BAD_REQUEST

    CollaborativeViewerService.heartbeat(path.execution_id, viewer_id)
    return {"status": "ok"}, HTTPStatus.OK


@collaborative_bp.get("/executions/<execution_id>/viewers")
def get_execution_viewers(path: ExecutionPath):
    """Get the list of current viewers for an execution."""
    viewers = CollaborativeViewerService.get_viewers(path.execution_id)
    return {"viewers": viewers}, HTTPStatus.OK


@collaborative_bp.post("/executions/<execution_id>/comments")
def post_inline_comment(path: ExecutionPath):
    """Post an inline comment on an execution log line.

    Persists the comment to the database and broadcasts an inline_comment
    event to all subscribers of the execution SSE stream.
    """
    body = request.get_json(silent=True) or {}
    viewer_id = body.get("viewer_id")
    viewer_name = body.get("viewer_name")
    line_number = body.get("line_number")
    content = body.get("content")

    if not all([viewer_id, viewer_name, content]) or line_number is None:
        return {
            "error": "viewer_id, viewer_name, line_number, and content are required"
        }, HTTPStatus.BAD_REQUEST

    try:
        comment = CollaborativeViewerService.post_comment(
            execution_id=path.execution_id,
            viewer_id=viewer_id,
            viewer_name=viewer_name,
            line_number=int(line_number),
            content=content,
        )
        return comment, HTTPStatus.CREATED
    except ValueError as e:
        return {"error": str(e)}, HTTPStatus.INTERNAL_SERVER_ERROR


@collaborative_bp.get("/executions/<execution_id>/comments")
def list_execution_comments(path: ExecutionPath):
    """List all inline comments for an execution.

    Returns comments ordered by line_number then created_at,
    including comments from historical (completed) executions.
    """
    comments = CollaborativeViewerService.get_execution_comments(path.execution_id)
    return {"comments": comments}, HTTPStatus.OK


@collaborative_bp.delete("/comments/<comment_id>")
def delete_inline_comment(path: CommentPath):
    """Delete an inline comment by ID."""
    existing = get_comment(path.comment_id)
    if not existing:
        return {"error": "Comment not found"}, HTTPStatus.NOT_FOUND

    delete_comment(path.comment_id)
    return {"status": "deleted"}, HTTPStatus.OK
