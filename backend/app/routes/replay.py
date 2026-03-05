"""Replay and diff-context API endpoints for execution A/B comparison."""

from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..db.replay import (
    get_replay_comparison,
    get_replay_comparisons_for_execution,
)
from ..services.diff_context_service import DiffContextService
from ..services.execution_log_service import ExecutionLogService
from ..services.replay_service import ReplayService

tag = Tag(name="replay", description="Execution replay and A/B comparison")
replay_bp = APIBlueprint("replay", __name__, url_prefix="/admin", abp_tags=[tag])


class ExecutionPath(BaseModel):
    execution_id: str = Field(..., description="Execution ID")


class ComparisonPath(BaseModel):
    comparison_id: str = Field(..., description="Replay comparison ID")


@replay_bp.post("/executions/<execution_id>/replay")
def replay_execution(path: ExecutionPath):
    """Replay an execution with identical prompt and command.

    Creates a new execution record and tracks the relationship in
    replay_comparisons for A/B comparison.
    """
    body = request.get_json(silent=True) or {}
    notes = body.get("notes")

    try:
        result = ReplayService.replay_execution(path.execution_id, notes=notes)
        return result, HTTPStatus.CREATED
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            return {"error": msg}, HTTPStatus.NOT_FOUND
        if "running" in msg:
            return {"error": msg}, HTTPStatus.BAD_REQUEST
        return {"error": msg}, HTTPStatus.BAD_REQUEST


@replay_bp.get("/executions/<execution_id>/comparisons")
def list_execution_comparisons(path: ExecutionPath):
    """List all replay comparisons for an execution.

    Returns comparisons where the execution is either the original or the replay.
    """
    comparisons = get_replay_comparisons_for_execution(path.execution_id)
    return {"comparisons": comparisons, "total": len(comparisons)}, HTTPStatus.OK


@replay_bp.get("/replay-comparisons/<comparison_id>")
def get_comparison(path: ComparisonPath):
    """Get a specific replay comparison by ID."""
    comparison = get_replay_comparison(path.comparison_id)
    if not comparison:
        return {"error": "Comparison not found"}, HTTPStatus.NOT_FOUND
    return comparison, HTTPStatus.OK


@replay_bp.get("/replay-comparisons/<comparison_id>/diff")
def get_comparison_diff(path: ComparisonPath):
    """Get side-by-side output diff for a replay comparison.

    Produces a structured unified diff with line-level change markers
    (added, removed, unchanged) and a change summary.
    """
    comparison = get_replay_comparison(path.comparison_id)
    if not comparison:
        return {"error": "Comparison not found"}, HTTPStatus.NOT_FOUND

    original_id = comparison["original_execution_id"]
    replay_id = comparison["replay_execution_id"]

    # Check if either execution is still running
    if ExecutionLogService.is_running(original_id) or ExecutionLogService.is_running(replay_id):
        return {
            "error": "Cannot diff: one or both executions are still running"
        }, HTTPStatus.CONFLICT

    try:
        diff = ReplayService.compare_outputs(original_id, replay_id)
        return diff, HTTPStatus.OK
    except ValueError as e:
        return {"error": str(e)}, HTTPStatus.NOT_FOUND


@replay_bp.post("/diff-context/preview")
def preview_diff_context():
    """Preview diff-aware context extraction without a real PR.

    Accepts raw unified diff text and returns the extracted focused context
    along with token reduction estimates.
    """
    body = request.get_json(silent=True)
    if not body or "diff_text" not in body:
        return {"error": "Missing required field: diff_text"}, HTTPStatus.BAD_REQUEST

    diff_text = body["diff_text"]
    context_lines = body.get("context_lines")

    context = DiffContextService.extract_pr_diff_context(diff_text, context_lines)
    token_estimate = DiffContextService.estimate_token_reduction(diff_text, context)

    return {
        "context": context,
        "token_estimate": token_estimate,
    }, HTTPStatus.OK
