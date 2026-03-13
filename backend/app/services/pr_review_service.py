"""PR review management service."""

import logging
from http import HTTPStatus
from typing import Tuple

from app.models.common import error_response

from ..database import (
    add_pr_review,
    delete_pr_review,
    get_pr_review,
    get_pr_review_history,
    get_pr_review_learning_loop,
    get_pr_review_stats,
    get_pr_reviews_count,
    get_pr_reviews_for_trigger,
    update_pr_review,
)

logger = logging.getLogger(__name__)


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
            return error_response("NOT_FOUND", "PR review not found", HTTPStatus.NOT_FOUND)
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
            return error_response(
                "INTERNAL_SERVER_ERROR",
                "Failed to create PR review",
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    @staticmethod
    def update_review(review_id: int, data: dict) -> Tuple[dict, HTTPStatus]:
        """Update a PR review record."""
        existing = get_pr_review(review_id)
        if not existing:
            return error_response("NOT_FOUND", "PR review not found", HTTPStatus.NOT_FOUND)

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
            return error_response("BAD_REQUEST", "No changes made", HTTPStatus.BAD_REQUEST)

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
            return error_response("NOT_FOUND", "PR review not found", HTTPStatus.NOT_FOUND)

        success = delete_pr_review(review_id)
        if success:
            return {"message": "PR review deleted"}, HTTPStatus.OK
        else:
            return error_response(
                "INTERNAL_SERVER_ERROR",
                "Failed to delete PR review",
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    @staticmethod
    def get_history(trigger_id: str = "bot-pr-review", days: int = 30) -> Tuple[dict, HTTPStatus]:
        """Get PR activity grouped by date for time-series visualization."""
        history = get_pr_review_history(trigger_id, days)
        return {"history": history}, HTTPStatus.OK

    @staticmethod
    def get_learning_loop(trigger_id: str = "bot-pr-review") -> Tuple[dict, HTTPStatus]:
        """Derive learning-loop signals and refinement suggestions from PR review data."""
        rows = get_pr_review_learning_loop(trigger_id)

        signals = []
        suggestions = []

        for i, row in enumerate(rows):
            total = row["total"]
            accepted = row["accepted_count"]
            accept_rate = accepted / total if total > 0 else 0.0

            # Compute trend from two 7-day windows
            recent_total = row["recent_total"]
            recent_accepted = row["recent_accepted"]
            prev_total = row["prev_total"]
            prev_accepted = row["prev_accepted"]

            recent_rate = recent_accepted / recent_total if recent_total > 0 else None
            prev_rate = prev_accepted / prev_total if prev_total > 0 else None

            if recent_rate is None or prev_rate is None:
                trend = "stable"
            elif recent_rate > prev_rate + 0.05:
                trend = "up"
            elif recent_rate < prev_rate - 0.05:
                trend = "down"
            else:
                trend = "stable"

            signals.append(
                {
                    "id": f"sig-{i + 1:03d}",
                    "category": "correctness",
                    "pattern": row["pattern"] or "Unknown project",
                    "acceptedCount": accepted,
                    "dismissedCount": row["dismissed_count"],
                    "commentedCount": row["commented_count"],
                    "resolvedCount": row["resolved_count"],
                    "acceptRate": round(accept_rate, 4),
                    "trend": trend,
                    "lastSeen": row["last_seen"] or "",
                    "examplePromptFragment": "",
                }
            )

            # Generate suggestions for extreme accept rates
            if accept_rate < 0.25 and total >= 3:
                suggestions.append(
                    {
                        "id": f"ref-sup-{i + 1:03d}",
                        "type": "suppress",
                        "category": "correctness",
                        "description": (
                            f'Consider suppressing findings for "{row["pattern"]}" '
                            f"— {round((1 - accept_rate) * 100)}% dismiss rate "
                            "suggests low value for this project."
                        ),
                        "impact": "high" if accept_rate < 0.10 else "medium",
                    }
                )
            elif accept_rate > 0.85 and total >= 3:
                suggestions.append(
                    {
                        "id": f"ref-pro-{i + 1:03d}",
                        "type": "promote",
                        "category": "correctness",
                        "description": (
                            f'Increase coverage for "{row["pattern"]}" '
                            f"— {round(accept_rate * 100)}% acceptance rate "
                            "signals high value for this project."
                        ),
                        "impact": "high",
                    }
                )

        return {"signals": signals, "suggestions": suggestions}, HTTPStatus.OK
