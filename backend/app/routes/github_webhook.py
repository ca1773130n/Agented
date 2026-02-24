"""GitHub webhook endpoint for PR events."""

import hashlib
import hmac
import logging
import os
import threading
import time
from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag

from ..database import add_pr_review
from ..services.execution_service import ExecutionService

logger = logging.getLogger(__name__)

tag = Tag(name="github-webhook", description="GitHub webhook receiver")
github_webhook_bp = APIBlueprint(
    "github_webhook", __name__, url_prefix="/api/webhooks/github", abp_tags=[tag]
)

MAX_GITHUB_WEBHOOK_PAYLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
# Disable strict slashes to avoid 308 redirects - GitHub doesn't follow redirects for webhooks
github_webhook_bp.strict_slashes = False

# GitHub webhook secret from environment
GITHUB_WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")

# Per-repo rate limiting: prevent a flood of valid-signature webhooks from triggering
# many concurrent executions from the same repository.
_repo_rate_limit_lock = threading.Lock()
_repo_last_event: dict = {}  # {repo_full_name: last_event_epoch}
_REPO_RATE_LIMIT_SECONDS = 60  # Minimum seconds between actionable events per repo

# Log warning at module load if secret is not configured
if not GITHUB_WEBHOOK_SECRET:
    logger.warning(
        "GITHUB_WEBHOOK_SECRET environment variable not set. "
        "GitHub webhooks will be rejected until this is configured."
    )


def verify_github_signature(payload: bytes, signature_header: str) -> bool:
    """Verify the GitHub webhook signature using HMAC-SHA256."""
    if not GITHUB_WEBHOOK_SECRET:
        logger.warning("GITHUB_WEBHOOK_SECRET not configured, rejecting webhook")
        return False

    if not signature_header:
        return False

    # GitHub sends signature as "sha256=<signature>"
    if not signature_header.startswith("sha256="):
        return False

    expected_signature = signature_header[7:]  # Remove "sha256=" prefix
    computed_signature = hmac.new(
        GITHUB_WEBHOOK_SECRET.encode("utf-8"), payload, hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(computed_signature, expected_signature)


@github_webhook_bp.post("/")
def github_webhook():
    """
    Receive GitHub webhook events.

    Handles pull_request events to trigger PR review triggers.
    Requires X-Hub-Signature-256 header for signature verification.
    """
    if request.content_length and request.content_length > MAX_GITHUB_WEBHOOK_PAYLOAD_BYTES:
        return {"error": "Payload too large"}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE

    # Get raw payload for signature verification
    payload = request.get_data()

    # Guard against payloads that omit Content-Length (bypassing the header-based check above)
    if len(payload) > MAX_GITHUB_WEBHOOK_PAYLOAD_BYTES:
        return {"error": "Payload too large"}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE

    signature = request.headers.get("X-Hub-Signature-256", "")

    # Verify signature
    if not verify_github_signature(payload, signature):
        logger.warning("GitHub webhook signature verification failed")
        return {"error": "Invalid signature"}, HTTPStatus.UNAUTHORIZED

    # Get event type
    event_type = request.headers.get("X-GitHub-Event", "")

    # Handle ping event (sent when webhook is first configured)
    if event_type == "ping":
        return {"message": "pong"}, HTTPStatus.OK

    # Only process pull_request events
    if event_type != "pull_request":
        logger.debug(f"Ignoring GitHub event type: {event_type}")
        return {"message": f"Event type '{event_type}' ignored"}, HTTPStatus.OK

    # Parse and validate JSON — these are client errors (400)
    data = request.get_json(silent=True)
    if data is None:
        return {"error": "Content-Type must be application/json"}, HTTPStatus.BAD_REQUEST
    if not isinstance(data, dict):
        return {"error": "Invalid JSON body: expected object"}, HTTPStatus.BAD_REQUEST

    action = data.get("action", "")

    # Only process relevant PR actions
    if action not in ("opened", "synchronize", "reopened"):
        logger.debug(f"Ignoring PR action: {action}")
        return {"message": f"PR action '{action}' ignored"}, HTTPStatus.OK

    # Extract PR information
    pr = data.get("pull_request", {})
    repo = data.get("repository", {})

    pr_number = pr.get("number")
    pr_title = pr.get("title", "")
    pr_url = pr.get("html_url", "")
    pr_author = pr.get("user", {}).get("login", "")
    repo_full_name = repo.get("full_name", "")  # e.g., "owner/repo"
    repo_url = repo.get("html_url", "")

    if not all([pr_number, pr_url, repo_full_name]):
        return {"error": "Missing required PR data"}, HTTPStatus.BAD_REQUEST

    # Per-repo rate limiting: reject if same repo sent an actionable event recently
    now = time.time()
    with _repo_rate_limit_lock:
        last_event = _repo_last_event.get(repo_full_name, 0)
        if now - last_event < _REPO_RATE_LIMIT_SECONDS:
            retry_after = int(_REPO_RATE_LIMIT_SECONDS - (now - last_event)) + 1
            logger.warning(
                f"Rate limit: ignoring PR event from {repo_full_name} "
                f"(last event {now - last_event:.1f}s ago)"
            )
            return {
                "message": "Rate limit: event ignored",
                "retry_after": retry_after,
            }, HTTPStatus.TOO_MANY_REQUESTS
        _repo_last_event[repo_full_name] = now

    logger.info(f"Received PR event: {action} #{pr_number} from {repo_full_name}")

    # Create PR review record and dispatch — server errors here return 500
    # (GitHub should NOT retry on 5xx from execution failures; rate limiting above prevents duplicates)
    try:
        review_id = add_pr_review(
            project_name=repo_full_name,
            pr_number=pr_number,
            pr_url=pr_url,
            pr_title=pr_title,
            github_repo_url=repo_url,
            pr_author=pr_author,
        )

        if review_id:
            logger.info(f"Created PR review record: {review_id}")

        # Dispatch to GitHub-triggered triggers
        pr_data = {
            "pr_number": pr_number,
            "pr_title": pr_title,
            "pr_url": pr_url,
            "pr_author": pr_author,
            "repo_full_name": repo_full_name,
            "repo_url": repo_url,
            "action": action,
        }

        triggered = ExecutionService.dispatch_github_event(repo_url, pr_data)

        return {
            "message": "PR event processed",
            "review_id": review_id,
            "triggered": triggered,
        }, HTTPStatus.OK

    except Exception:
        logger.exception("GitHub webhook error")
        return {"error": "Internal server error"}, HTTPStatus.INTERNAL_SERVER_ERROR
