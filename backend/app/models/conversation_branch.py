"""Pydantic v2 models for conversation branching and chunk results."""

from typing import Optional

from pydantic import BaseModel, Field


class ChunkResult(BaseModel):
    """A single chunk's processing result."""

    chunk_index: int = Field(..., description="Zero-based index of this chunk")
    chunk_content: str = Field(..., description="The content of this chunk")
    bot_output: str = Field("", description="Bot output for this chunk")
    token_count: int = Field(0, description="Estimated token count for this chunk")


class MergedChunkResults(BaseModel):
    """Merged and deduplicated results from all chunks."""

    total_chunks: int = Field(..., description="Total number of chunks processed")
    unique_findings: list[str] = Field(
        default_factory=list, description="Deduplicated findings across all chunks"
    )
    duplicate_count: int = Field(0, description="Number of duplicate findings removed")
    merged_output: str = Field("", description="Merged output with unique findings")
    chunk_results: list[ChunkResult] = Field(
        default_factory=list, description="Individual chunk results"
    )


class BranchCreateRequest(BaseModel):
    """Request body for creating a conversation branch."""

    fork_message_index: int = Field(
        ..., description="Index of the message to fork from (inclusive)"
    )
    name: Optional[str] = Field(None, description="Optional name for the branch")


class BranchResponse(BaseModel):
    """Response after creating or retrieving a branch."""

    branch_id: str = Field(..., description="Unique branch identifier")
    conversation_id: str = Field(..., description="Parent conversation ID")
    parent_branch_id: Optional[str] = Field(None, description="Parent branch ID if forked")
    fork_message_id: Optional[str] = Field(None, description="Message ID at the fork point")
    name: Optional[str] = Field(None, description="Branch name")
    status: str = Field("active", description="Branch status")
    created_at: str = Field(..., description="Creation timestamp")


class BranchMessage(BaseModel):
    """A single message in a branch."""

    id: str = Field(..., description="Unique message identifier")
    conversation_id: str = Field(..., description="Parent conversation ID")
    branch_id: str = Field(..., description="Branch this message belongs to")
    parent_message_id: Optional[str] = Field(None, description="Parent message ID in the tree")
    message_index: int = Field(..., description="Order index within the branch")
    role: str = Field(..., description="Message role (user, assistant, system)")
    content: str = Field(..., description="Message content")
    created_at: str = Field(..., description="Creation timestamp")


class AddMessageRequest(BaseModel):
    """Request body for adding a message to a branch."""

    role: str = Field(..., description="Message role (user, assistant, system)")
    content: str = Field(..., description="Message content")


class ChunkedExecutionRequest(BaseModel):
    """Request body for running a bot against chunked content."""

    content: str = Field(..., description="Content to chunk and process")
    max_chunk_chars: Optional[int] = Field(
        None, description="Max characters per chunk (default ~2000)"
    )


class ChunkedExecutionResponse(BaseModel):
    """Response after initiating a chunked execution."""

    chunked_execution_id: str = Field(..., description="Unique chunked execution ID")
    bot_id: str = Field(..., description="Bot that will process chunks")
    total_chunks: int = Field(..., description="Number of chunks created")
    status: str = Field("processing", description="Execution status")
