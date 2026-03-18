"""Centralized error capture for the Agented platform.

All error capture points in the backend call capture_error() to persist
errors to the system_errors table and optionally trigger autofix.
"""

import hashlib
import logging
import re
from typing import Optional

from app.db.system_errors import create_system_error, find_recent_duplicate
from app.logging_config import request_id_var

logger = logging.getLogger(__name__)

# Regex patterns to strip variable parts from error messages for dedup hashing
_VARIABLE_PATTERNS = [
    re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I),  # UUIDs
    re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}"),  # timestamps
    re.compile(r"(?:err|fix|agent|conv|sess|msg|trig|sketch)-[a-z0-9]+"),  # entity IDs
    re.compile(r"/[\w/.-]+\.py:\d+"),  # file paths with line numbers
    re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),  # IP addresses
]


def _normalize_message(message: str) -> str:
    """Strip variable parts from a message for consistent hashing."""
    result = message
    for pattern in _VARIABLE_PATTERNS:
        result = pattern.sub("", result)
    return result.strip()


def _compute_error_hash(category: str, message: str) -> str:
    """Compute a SHA256 hash of category + normalized message for dedup."""
    normalized = _normalize_message(message)
    return hashlib.sha256(f"{category}:{normalized}".encode()).hexdigest()


def capture_error(
    category: str,
    message: str,
    stack_trace: str = None,
    request_id: str = None,
    context: dict = None,
    source: str = "backend",
) -> Optional[str]:
    """Persist error to system_errors table and trigger autofix.

    If capture_error() itself fails, it logs to stderr and returns None
    — never crashes the main request.

    Returns:
        The error ID if successfully captured, None on failure.
    """
    try:
        if request_id is None:
            request_id = request_id_var.get()

        error_hash = _compute_error_hash(category, message)

        import json

        context_json = json.dumps(context) if context else None

        # Dedup check: skip autofix if same error occurred recently
        duplicate = find_recent_duplicate(error_hash, window_seconds=60)
        skip_autofix = duplicate is not None

        error_id = create_system_error(
            source=source,
            category=category,
            message=message,
            error_hash=error_hash,
            stack_trace=stack_trace,
            request_id=request_id,
            context_json=context_json,
        )

        if not error_id:
            logger.error("Failed to insert system error (create_system_error returned None)")
            return None

        if skip_autofix:
            logger.debug(
                "Skipping autofix for error %s (duplicate of %s)", error_id, duplicate["id"]
            )
            return error_id

        # Trigger autofix (import here to avoid circular imports)
        try:
            from app.services.autofix_service import trigger_autofix

            trigger_autofix(error_id)
        except Exception:
            logger.exception("Failed to trigger autofix for error %s", error_id)

        return error_id

    except Exception:
        logger.exception("capture_error() failed — error not persisted")
        return None
