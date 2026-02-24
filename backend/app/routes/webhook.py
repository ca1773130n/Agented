"""General-purpose webhook endpoint for JSON payloads."""

import logging
from dataclasses import asdict, dataclass
from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag

logger = logging.getLogger(__name__)

from ..services.execution_service import ExecutionService

tag = Tag(name="webhook", description="General JSON webhook receiver")
webhook_bp = APIBlueprint("webhook", __name__, abp_tags=[tag])

MAX_WEBHOOK_PAYLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


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
    if request.content_length and request.content_length > MAX_WEBHOOK_PAYLOAD_BYTES:
        return {"error": "Payload too large"}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE

    # Capture raw bytes for HMAC validation before parsing JSON
    raw_payload = request.get_data()

    # Guard against payloads that omit Content-Length (bypassing the header-based check above)
    if len(raw_payload) > MAX_WEBHOOK_PAYLOAD_BYTES:
        return {"error": "Payload too large"}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE

    signature_header = request.headers.get("X-Webhook-Signature-256", "")

    # Parse and validate JSON — these are client errors (400)
    payload = request.get_json(silent=True)
    if payload is None:
        return {"error": "Content-Type must be application/json"}, HTTPStatus.BAD_REQUEST
    if not isinstance(payload, dict):
        return {"error": "Invalid JSON body: expected object"}, HTTPStatus.BAD_REQUEST

    # Support challenge-response verification (common pattern for webhook setup)
    payload_type = payload.get("type")
    if payload_type == "url_verification":
        challenge = payload.get("challenge")
        if challenge:
            return asdict(ChallengeResponse(challenge)), HTTPStatus.OK

    # Dispatch to execution service — failures here are server errors (500)
    try:
        ExecutionService.dispatch_webhook_event(
            payload, raw_payload=raw_payload, signature_header=signature_header
        )
    except Exception:
        logger.exception("Webhook processing error")
        return {"error": "Internal server error"}, HTTPStatus.INTERNAL_SERVER_ERROR

    return "", HTTPStatus.OK
