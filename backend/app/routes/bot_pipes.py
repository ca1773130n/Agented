"""Bot output piping API endpoints."""

from http import HTTPStatus

from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from app.models.common import error_response

from ..db.bot_pipes import create_pipe, get_all_pipes, get_pipe_executions, update_pipe

tag = Tag(name="bot_pipes", description="Bot output piping operations")
bot_pipes_bp = APIBlueprint("bot_pipes", __name__, url_prefix="/admin/bot-pipes", abp_tags=[tag])


class PipePath(BaseModel):
    pipe_id: str = Field(..., description="Pipe ID")


class CreatePipeBody(BaseModel):
    name: str = Field(..., description="Pipe name")
    source_bot_id: str = Field(..., description="Source bot ID")
    dest_bot_id: str = Field(..., description="Destination bot ID")
    transform: str = Field("passthrough", description="Transform type")
    enabled: bool = Field(True, description="Whether the pipe is enabled")


class UpdatePipeBody(BaseModel):
    name: str | None = Field(None, description="Pipe name")
    source_bot_id: str | None = Field(None, description="Source bot ID")
    dest_bot_id: str | None = Field(None, description="Destination bot ID")
    transform: str | None = Field(None, description="Transform type")
    enabled: bool | None = Field(None, description="Whether the pipe is enabled")


@bot_pipes_bp.get("/")
def list_pipes():
    """List all configured bot pipes."""
    pipes = get_all_pipes()
    return {"pipes": pipes}, HTTPStatus.OK


@bot_pipes_bp.post("/")
def create_pipe_endpoint(body: CreatePipeBody):
    """Create a new bot pipe."""
    data = body.model_dump()
    pipe = create_pipe(data)
    return {"message": "Pipe created", "pipe": pipe}, HTTPStatus.CREATED


@bot_pipes_bp.patch("/<pipe_id>")
def update_pipe_endpoint(path: PipePath, body: UpdatePipeBody):
    """Toggle or update a bot pipe."""
    data = body.model_dump(exclude_none=True)
    pipe = update_pipe(path.pipe_id, data)
    if pipe is None:
        return error_response("NOT_FOUND", "Pipe not found", HTTPStatus.NOT_FOUND)
    return {"message": "Pipe updated", "pipe": pipe}, HTTPStatus.OK


@bot_pipes_bp.get("/executions")
def list_pipe_executions():
    """List recent bot pipe executions."""
    executions = get_pipe_executions(limit=50)
    return {"executions": executions}, HTTPStatus.OK
