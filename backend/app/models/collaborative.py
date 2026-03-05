"""Pydantic v2 models for collaborative execution viewing."""

from pydantic import BaseModel, Field


class ViewerInfo(BaseModel):
    """A single viewer currently watching an execution stream."""

    viewer_id: str = Field(..., description="Unique viewer identifier")
    name: str = Field(..., description="Display name of the viewer")
    joined_at: str = Field(..., description="ISO-8601 timestamp when the viewer joined")


class PresenceEvent(BaseModel):
    """SSE event payload for viewer presence changes."""

    event_type: str = Field(
        ..., description="Presence event type: join, leave, or heartbeat"
    )
    viewer_id: str = Field(..., description="Viewer who triggered the event")
    name: str = Field(..., description="Display name of the viewer")
    viewers: list[ViewerInfo] = Field(
        default_factory=list, description="Current list of all viewers"
    )


class InlineCommentCreate(BaseModel):
    """Request body for creating an inline comment."""

    execution_id: str = Field(..., description="Execution being commented on")
    line_number: int = Field(..., ge=0, description="Stdout line number to anchor comment")
    content: str = Field(..., min_length=1, description="Comment text")
    viewer_id: str = Field(..., description="Viewer posting the comment")
    viewer_name: str = Field(..., description="Display name of the commenter")


class InlineComment(BaseModel):
    """A persisted inline comment on an execution log line."""

    id: str = Field(..., description="Comment ID (cmt-XXXXXX)")
    execution_id: str = Field(..., description="Execution this comment belongs to")
    viewer_id: str = Field(..., description="Viewer who posted the comment")
    viewer_name: str = Field(..., description="Display name of the commenter")
    line_number: int = Field(..., description="Stdout line number this comment anchors to")
    content: str = Field(..., description="Comment text")
    created_at: str = Field(..., description="ISO-8601 creation timestamp")


class CommentEvent(BaseModel):
    """SSE event payload for a new inline comment broadcast."""

    comment_id: str = Field(..., description="ID of the created comment")
    viewer_id: str = Field(..., description="Viewer who posted the comment")
    name: str = Field(..., description="Display name of the commenter")
    line_number: int = Field(..., description="Stdout line number")
    content: str = Field(..., description="Comment text")
    timestamp: str = Field(..., description="ISO-8601 creation timestamp")
