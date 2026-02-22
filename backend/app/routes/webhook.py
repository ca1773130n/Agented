"""General-purpose webhook endpoint for JSON payloads."""

from dataclasses import asdict, dataclass
from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag

from ..services.execution_service import ExecutionService

tag = Tag(name="webhook", description="General JSON webhook receiver")
webhook_bp = APIBlueprint("webhook", __name__, abp_tags=[tag])


@dataclass
class ChallengeResponse:
    """Response for URL verification challenges."""

    challenge: str


@webhook_bp.route("/", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
def webhook():
    """Receive webhook events from any JSON-based provider."""
    if request.method == "GET":
        return "", HTTPStatus.OK

    if request.method == "POST":
        return handle_webhook_request()

    return {"error": "Unsupported method"}, HTTPStatus.NOT_IMPLEMENTED


def handle_webhook_request():
    """Handle webhook POST requests with configurable field matching."""
    try:
        payload = request.get_json()
        print(f"Webhook received: {payload}")

        # Support challenge-response verification (common pattern for webhook setup)
        # Check for type field indicating verification request
        payload_type = payload.get("type") if isinstance(payload, dict) else None
        if payload_type == "url_verification":
            challenge = payload.get("challenge")
            if challenge:
                return asdict(ChallengeResponse(challenge)), HTTPStatus.OK

        # Dispatch to execution service for field-based matching
        ExecutionService.dispatch_webhook_event(payload)
        return "", HTTPStatus.OK

    except Exception as e:
        print(f"Webhook error: {e}")
        return {"error": "Internal server error"}, HTTPStatus.INTERNAL_SERVER_ERROR
