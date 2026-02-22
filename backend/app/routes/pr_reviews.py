"""PR review API endpoints."""

from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..services.pr_review_service import PrReviewService

tag = Tag(name="pr-reviews", description="PR review operations")
pr_reviews_bp = APIBlueprint("pr_reviews", __name__, url_prefix="/api/pr-reviews", abp_tags=[tag])


class PrReviewIdPath(BaseModel):
    review_id: int = Field(..., description="PR review ID")


@pr_reviews_bp.get("/")
def list_pr_reviews():
    """List PR reviews with optional filters."""
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)
    pr_status = request.args.get("pr_status", None)
    review_status = request.args.get("review_status", None)
    result, status = PrReviewService.list_reviews(
        limit=limit,
        offset=offset,
        pr_status=pr_status,
        review_status=review_status,
    )
    return result, status


@pr_reviews_bp.get("/stats")
def get_pr_review_stats():
    """Get aggregate PR review statistics."""
    result, status = PrReviewService.get_stats()
    return result, status


@pr_reviews_bp.get("/history")
def get_pr_review_history():
    """Get PR activity grouped by date for time-series charts."""
    days = request.args.get("days", 30, type=int)
    result, status = PrReviewService.get_history(days=days)
    return result, status


@pr_reviews_bp.get("/<int:review_id>")
def get_pr_review(path: PrReviewIdPath):
    """Get a single PR review by ID."""
    result, status = PrReviewService.get_review(path.review_id)
    return result, status


@pr_reviews_bp.post("/")
def create_pr_review():
    """Create a new PR review record."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST
    result, status = PrReviewService.create_review(data)
    return result, status


@pr_reviews_bp.put("/<int:review_id>")
def update_pr_review(path: PrReviewIdPath):
    """Update a PR review record."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST
    result, status = PrReviewService.update_review(path.review_id, data)
    return result, status


@pr_reviews_bp.delete("/<int:review_id>")
def delete_pr_review(path: PrReviewIdPath):
    """Delete a PR review record."""
    result, status = PrReviewService.delete_review(path.review_id)
    return result, status
