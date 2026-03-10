"""Team AI generation API endpoints."""

import subprocess
import threading
import uuid
from http import HTTPStatus

from flask import Response, request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..models.common import error_response
from ..services.rbac_service import require_role
from ..services.team_generation_service import TeamGenerationService

tag = Tag(name="team-generation", description="AI-powered team configuration generation")
team_generation_bp = APIBlueprint(
    "team_generation", __name__, url_prefix="/admin/teams", abp_tags=[tag]
)

# In-memory job store for async team generation (job_id -> result dict).
# Limited to 200 entries; oldest are evicted when full.
_generation_jobs: dict = {}
_jobs_lock = threading.Lock()
_MAX_JOBS = 200


class GenerateJobPath(BaseModel):
    job_id: str = Field(..., description="Job ID returned by POST /generate")


@team_generation_bp.post("/generate")
@require_role("editor", "admin")
def generate_team_config():
    """Generate a team configuration from a natural language description using AI.

    Returns a job_id immediately (202 Accepted). Poll GET /generate/<job_id> for the result.
    This avoids blocking a Flask worker thread for the full Claude CLI duration (up to 2 min).
    """
    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)

    description = data.get("description", "")
    if not description or len(description) < 10:
        return error_response(
            "BAD_REQUEST",
            "description is required and must be at least 10 characters",
            HTTPStatus.BAD_REQUEST,
        )

    job_id = f"gen-{uuid.uuid4().hex[:8]}"

    with _jobs_lock:
        # Evict oldest entries when the store is full
        if len(_generation_jobs) >= _MAX_JOBS:
            oldest_key = next(iter(_generation_jobs))
            del _generation_jobs[oldest_key]
        _generation_jobs[job_id] = {"status": "pending"}

    def _run():
        try:
            result = TeamGenerationService.generate(description)
            with _jobs_lock:
                _generation_jobs[job_id] = {"status": "complete", **result}
        except subprocess.TimeoutExpired:
            with _jobs_lock:
                _generation_jobs[job_id] = {
                    "status": "error",
                    "error": "Team generation timed out. The AI service took too long to respond. Please try again.",
                }
        except RuntimeError as e:
            with _jobs_lock:
                _generation_jobs[job_id] = {"status": "error", "error": str(e)}
        except Exception as e:
            with _jobs_lock:
                _generation_jobs[job_id] = {
                    "status": "error",
                    "error": f"Team generation failed: {str(e)}",
                }

    threading.Thread(target=_run, daemon=True).start()
    return {"job_id": job_id}, HTTPStatus.ACCEPTED


@team_generation_bp.get("/generate/<job_id>")
@require_role("viewer", "operator", "editor", "admin")
def get_generation_job(path: GenerateJobPath):
    """Poll the result of a team generation job started by POST /generate."""
    with _jobs_lock:
        job = dict(_generation_jobs.get(path.job_id, {}))
    if not job:
        return error_response("NOT_FOUND", "Job not found", HTTPStatus.NOT_FOUND)
    if job["status"] == "error":
        error_msg = job.get("error", "Unknown error")
        status_code = (
            HTTPStatus.SERVICE_UNAVAILABLE
            if "timed out" in error_msg or "not found" in error_msg.lower()
            else HTTPStatus.INTERNAL_SERVER_ERROR
        )
        error_code = (
            "SERVICE_UNAVAILABLE"
            if status_code == HTTPStatus.SERVICE_UNAVAILABLE
            else "INTERNAL_SERVER_ERROR"
        )
        return error_response(error_code, error_msg, status_code)
    return job, HTTPStatus.OK


@team_generation_bp.post("/generate/stream")
@require_role("editor", "admin")
def generate_team_config_stream():
    """Stream team configuration generation with real-time AI output via SSE."""
    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)

    description = data.get("description", "")
    if not description or len(description) < 10:
        return error_response(
            "BAD_REQUEST",
            "description is required and must be at least 10 characters",
            HTTPStatus.BAD_REQUEST,
        )

    def generate():
        """Yield SSE events from the team configuration generation stream."""
        yield from TeamGenerationService.generate_streaming(description)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
