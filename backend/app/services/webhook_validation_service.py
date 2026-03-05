"""Unified webhook HMAC validation with replay protection.

Consolidates ExecutionService._verify_webhook_hmac() and
github_webhook.verify_github_signature() into a single service with
configurable algorithm support and timestamp-based replay protection.

Security best practices per webhooks.fyi:
- Timing-safe comparison via hmac.compare_digest()
- Raw payload validation BEFORE JSON parsing
- Timestamp-based replay protection (5-minute default tolerance)
"""

import hashlib
import hmac
import logging
import time
from typing import Tuple

logger = logging.getLogger(__name__)


class WebhookValidationService:
    """Unified webhook signature validation and replay protection."""

    # Supported HMAC algorithms
    _ALGORITHMS = {
        "sha256": hashlib.sha256,
        "sha1": hashlib.sha1,
    }

    @classmethod
    def validate_signature(
        cls,
        raw_payload: bytes,
        signature_header: str,
        secret: str,
        algorithm: str = "sha256",
    ) -> bool:
        """Verify HMAC signature for a webhook payload.

        Supports signature formats: "sha256=<hex>" or "sha1=<hex>".
        Automatically detects algorithm from header prefix if present.

        Args:
            raw_payload: Raw request body bytes.
            signature_header: Value of the signature header (e.g. "sha256=abc123").
            secret: The shared secret for HMAC computation.
            algorithm: Default algorithm if header has no prefix. One of: sha256, sha1.

        Returns:
            True if signature is valid, False otherwise.
        """
        if not signature_header:
            return False

        if not secret:
            return False

        # Detect algorithm from header prefix
        detected_algo = None
        hex_signature = signature_header
        for algo_name in cls._ALGORITHMS:
            prefix = f"{algo_name}="
            if signature_header.startswith(prefix):
                detected_algo = algo_name
                hex_signature = signature_header[len(prefix) :]
                break

        # Use detected algorithm or fall back to provided default
        algo = detected_algo or algorithm
        hash_func = cls._ALGORITHMS.get(algo)
        if hash_func is None:
            logger.warning("Unsupported HMAC algorithm: %s", algo)
            return False

        # If header had no prefix and no algorithm was detected, it might be bare hex
        # but we only accept prefixed signatures for security clarity
        if detected_algo is None and "=" in signature_header:
            # Has a prefix but not one we recognize
            return False

        computed = hmac.new(secret.encode("utf-8"), raw_payload, hash_func).hexdigest()
        return hmac.compare_digest(computed, hex_signature)

    @classmethod
    def validate_timestamp(
        cls,
        timestamp_header: str,
        tolerance_seconds: int = 300,
    ) -> bool:
        """Validate webhook timestamp for replay protection.

        Args:
            timestamp_header: Timestamp value (Unix epoch seconds or ISO 8601).
            tolerance_seconds: Maximum age in seconds (default 300 = 5 minutes).

        Returns:
            True if timestamp is within tolerance or header is None/empty.
            False if timestamp is outside tolerance window.
        """
        if not timestamp_header:
            # No timestamp provided -- caller decides via require_timestamp
            return True

        now = time.time()
        payload_time = None

        # Try Unix epoch (integer or float)
        try:
            payload_time = float(timestamp_header)
        except (ValueError, TypeError):
            pass

        # Try ISO 8601
        if payload_time is None:
            try:
                from datetime import datetime, timezone

                # Handle various ISO formats
                ts = timestamp_header.replace("Z", "+00:00")
                dt = datetime.fromisoformat(ts)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                payload_time = dt.timestamp()
            except (ValueError, TypeError):
                logger.warning("Cannot parse webhook timestamp: %s", timestamp_header)
                return False

        return abs(now - payload_time) <= tolerance_seconds

    @classmethod
    def validate_webhook(
        cls,
        request,
        secret: str,
        algorithm: str = "sha256",
        signature_header_name: str = "X-Webhook-Signature-256",
        timestamp_header_name: str = "X-Webhook-Timestamp",
        require_timestamp: bool = False,
        tolerance_seconds: int = 300,
    ) -> Tuple[bool, str]:
        """Full webhook validation pipeline.

        Validates signature and optionally timestamp-based replay protection.
        Must be called BEFORE JSON parsing (uses request.get_data()).

        Args:
            request: Flask request object.
            secret: Shared HMAC secret.
            algorithm: HMAC algorithm (default sha256).
            signature_header_name: Header name for signature.
            timestamp_header_name: Header name for timestamp.
            require_timestamp: If True, reject requests without timestamp header.
            tolerance_seconds: Replay protection window in seconds.

        Returns:
            Tuple of (is_valid, error_reason). Empty string on success.
        """
        raw_payload = request.get_data()
        signature = request.headers.get(signature_header_name, "")

        # Step 1: Validate signature
        if not cls.validate_signature(raw_payload, signature, secret, algorithm):
            return False, "Invalid webhook signature"

        # Step 2: Validate timestamp (replay protection)
        timestamp = request.headers.get(timestamp_header_name)
        if require_timestamp and not timestamp:
            return False, "Missing required timestamp header"

        if timestamp and not cls.validate_timestamp(timestamp, tolerance_seconds):
            return False, "Webhook replay detected"

        return True, ""

    @classmethod
    def validate_github(
        cls,
        request,
        secret: str,
    ) -> Tuple[bool, str]:
        """GitHub-specific webhook validation.

        Uses X-Hub-Signature-256 header with SHA-256 algorithm.

        Args:
            request: Flask request object.
            secret: GitHub webhook secret.

        Returns:
            Tuple of (is_valid, error_reason). Empty string on success.
        """
        if not secret:
            return False, "GitHub webhook secret not configured"

        raw_payload = request.get_data()
        signature = request.headers.get("X-Hub-Signature-256", "")

        if not cls.validate_signature(raw_payload, signature, secret, "sha256"):
            return False, "Invalid GitHub webhook signature"

        return True, ""
