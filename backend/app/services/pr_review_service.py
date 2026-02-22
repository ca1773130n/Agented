"""PR review management service."""

from http import HTTPStatus
from typing import Tuple

from ..database import (
    add_pr_review,
    delete_pr_review,
    get_pr_review,
    get_pr_review_history,
    get_pr_review_stats,
    get_pr_reviews_count,
    get_pr_reviews_for_trigger,
    update_pr_review,
)


class PrReviewService:
    """Service for PR review CRUD operations."""

    @staticmethod
    def list_reviews(
        trigger_id: str = "bot-pr-review",
        limit: int = 50,
        offset: int = 0,
        pr_status: str = None,
        review_status: str = None,
    ) -> Tuple[dict, HTTPStatus]:
        """List PR reviews with optional filters."""
        reviews = get_pr_reviews_for_trigger(
            trigger_id=trigger_id,
            limit=limit,
            offset=offset,
            pr_status=pr_status,
            review_status=review_status,
        )
        total = get_pr_reviews_count(
            trigger_id=trigger_id,
            pr_status=pr_status,
            review_status=review_status,
        )
        return {"reviews": reviews, "total": total}, HTTPStatus.OK

    @staticmethod
    def get_review(review_id: int) -> Tuple[dict, HTTPStatus]:
        """Get a single PR review."""
        review = get_pr_review(review_id)
        if not review:
            return {"error": "PR review not found"}, HTTPStatus.NOT_FOUND
        return review, HTTPStatus.OK

    @staticmethod
    def create_review(data: dict) -> Tuple[dict, HTTPStatus]:
        """Create a new PR review record."""
        project_name = data.get("project_name")
        pr_number = data.get("pr_number")
        pr_url = data.get("pr_url")
        pr_title = data.get("pr_title")

        if not all([project_name, pr_number is not None, pr_url, pr_title]):
            return {
                "error": "project_name, pr_number, pr_url, and pr_title are required"
            }, HTTPStatus.BAD_REQUEST

        review_id = add_pr_review(
            project_name=project_name,
            pr_number=pr_number,
            pr_url=pr_url,
            pr_title=pr_title,
            github_repo_url=data.get("github_repo_url"),
            pr_author=data.get("pr_author"),
        )

        if review_id:
            return {
                "message": "PR review created",
                "id": review_id,
            }, HTTPStatus.CREATED
        else:
            return {"error": "Failed to create PR review"}, HTTPStatus.INTERNAL_SERVER_ERROR

    @staticmethod
    def update_review(review_id: int, data: dict) -> Tuple[dict, HTTPStatus]:
        """Update a PR review record."""
        existing = get_pr_review(review_id)
        if not existing:
            return {"error": "PR review not found"}, HTTPStatus.NOT_FOUND

        success = update_pr_review(
            review_id,
            pr_status=data.get("pr_status"),
            review_status=data.get("review_status"),
            review_comment=data.get("review_comment"),
            fixes_applied=data.get("fixes_applied"),
            fix_comment=data.get("fix_comment"),
        )

        if success:
            return {"message": "PR review updated"}, HTTPStatus.OK
        else:
            return {"error": "No changes made"}, HTTPStatus.BAD_REQUEST

    @staticmethod
    def get_stats(trigger_id: str = "bot-pr-review") -> Tuple[dict, HTTPStatus]:
        """Get aggregate PR review statistics."""
        stats = get_pr_review_stats(trigger_id)
        return stats, HTTPStatus.OK

    @staticmethod
    def delete_review(review_id: int) -> Tuple[dict, HTTPStatus]:
        """Delete a PR review record."""
        existing = get_pr_review(review_id)
        if not existing:
            return {"error": "PR review not found"}, HTTPStatus.NOT_FOUND

        success = delete_pr_review(review_id)
        if success:
            return {"message": "PR review deleted"}, HTTPStatus.OK
        else:
            return {"error": "Failed to delete PR review"}, HTTPStatus.INTERNAL_SERVER_ERROR

    @staticmethod
    def get_history(trigger_id: str = "bot-pr-review", days: int = 30) -> Tuple[dict, HTTPStatus]:
        """Get PR activity grouped by date for time-series visualization."""
        history = get_pr_review_history(trigger_id, days)
        return {"history": history}, HTTPStatus.OK
