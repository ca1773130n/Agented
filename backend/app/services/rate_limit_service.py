"""Rate limit detection and account cooldown management service."""

import re
from datetime import datetime, timedelta
from typing import List, Optional

from ..database import (
    clear_account_rate_limit as db_clear_rate_limit,
)
from ..database import (
    get_account_rate_limit_state,
    get_accounts_for_backend_type,
    get_all_accounts_with_health,
    update_account_rate_limit,
)

# Default cooldown when no retry-after header is found
DEFAULT_COOLDOWN_SECONDS = 60


class RateLimitService:
    """Service for detecting rate limits from CLI stderr and managing account cooldowns."""

    # Compiled regex patterns per backend type for detecting rate limits in stderr
    RATE_LIMIT_PATTERNS = {
        "claude": [
            re.compile(r"429", re.IGNORECASE),
            re.compile(r"rate_limit_error", re.IGNORECASE),
            re.compile(r"rate.limit", re.IGNORECASE),
            re.compile(r"exceeded.*quota", re.IGNORECASE),
        ],
        "opencode": [
            re.compile(r"statusCode.*429", re.IGNORECASE),
            re.compile(r"Rate limit exceeded", re.IGNORECASE),
            re.compile(r"rate.limited", re.IGNORECASE),
        ],
        "gemini": [
            re.compile(r"429", re.IGNORECASE),
            re.compile(r"RESOURCE_EXHAUSTED", re.IGNORECASE),
            re.compile(r"rate.limit", re.IGNORECASE),
            re.compile(r"quota.*exceeded", re.IGNORECASE),
        ],
        "codex": [
            re.compile(r"429", re.IGNORECASE),
            re.compile(r"rate_limit", re.IGNORECASE),
            re.compile(r"rate.limit", re.IGNORECASE),
            re.compile(r"too many requests", re.IGNORECASE),
        ],
    }

    # Pattern to extract retry-after seconds from stderr
    RETRY_AFTER_PATTERN = re.compile(r"retry.after.*?(\d+)", re.IGNORECASE)

    @classmethod
    def check_stderr_line(cls, line: str, backend_type: str) -> Optional[int]:
        """Check a stderr line for rate limit indicators.

        Returns cooldown seconds if rate limit detected, None otherwise.
        If retry-after found in line, uses that value; else DEFAULT_COOLDOWN_SECONDS.
        """
        patterns = cls.RATE_LIMIT_PATTERNS.get(backend_type, [])
        for pattern in patterns:
            if pattern.search(line):
                # Try to extract retry-after value
                retry_match = cls.RETRY_AFTER_PATTERN.search(line)
                if retry_match:
                    return int(retry_match.group(1))
                return DEFAULT_COOLDOWN_SECONDS
        return None

    @classmethod
    def mark_rate_limited(cls, account_id: int, cooldown_seconds: int) -> bool:
        """Mark an account as rate-limited with a cooldown period.

        Persists rate_limited_until timestamp and reason to database.
        """
        limited_until = (datetime.now() + timedelta(seconds=cooldown_seconds)).isoformat()
        return update_account_rate_limit(account_id, limited_until, "rate_limit_429")

    @classmethod
    def clear_rate_limit(cls, account_id: int) -> bool:
        """Clear rate limit for an account."""
        return db_clear_rate_limit(account_id)

    @classmethod
    def is_rate_limited(cls, account_id: int) -> bool:
        """Check if an account is currently rate-limited."""
        state = get_account_rate_limit_state(account_id)
        if not state or not state.get("rate_limited_until"):
            return False
        try:
            limited_until = datetime.fromisoformat(state["rate_limited_until"])
            return limited_until > datetime.now()
        except (ValueError, TypeError):
            return False

    @classmethod
    def pick_best_account(cls, backend_type: str) -> Optional[dict]:
        """Pick the best available account for a backend type.

        Filters out rate-limited accounts, then sorts by:
        1. is_default DESC (prefer default account)
        2. last_used_at ASC (prefer least-recently-used)

        Returns the best account dict, or None if all are rate-limited.
        """
        accounts = get_accounts_for_backend_type(backend_type)
        now = datetime.now()

        available = []
        for account in accounts:
            rate_limited_until = account.get("rate_limited_until")
            if rate_limited_until:
                try:
                    if datetime.fromisoformat(rate_limited_until) > now:
                        continue  # Still rate-limited, skip
                except (ValueError, TypeError):
                    pass
            available.append(account)

        if not available:
            return None

        # Already ordered by is_default DESC, last_used_at ASC from DB query
        return available[0]

    @classmethod
    def get_all_account_states(cls, backend_type: str = None) -> List[dict]:
        """Get health state for all accounts, optionally filtered by backend type.

        Returns list of dicts with rate limit state and cooldown info.
        """
        accounts = get_all_accounts_with_health(backend_type)
        now = datetime.now()
        result = []

        for account in accounts:
            is_limited = False
            cooldown_remaining = None
            rate_limited_until = account.get("rate_limited_until")

            if rate_limited_until:
                try:
                    limited_dt = datetime.fromisoformat(rate_limited_until)
                    if limited_dt > now:
                        is_limited = True
                        cooldown_remaining = int((limited_dt - now).total_seconds())
                except (ValueError, TypeError):
                    pass

            result.append(
                {
                    "account_id": account["id"],
                    "account_name": account["account_name"],
                    "backend_id": account.get("backend_id", ""),
                    "backend_type": account.get("backend_type", "unknown"),
                    "backend_name": account.get("backend_name", ""),
                    "is_rate_limited": is_limited,
                    "rate_limited_until": rate_limited_until,
                    "rate_limit_reason": account.get("rate_limit_reason"),
                    "cooldown_remaining_seconds": cooldown_remaining,
                    "total_executions": account.get("total_executions") or 0,
                    "last_used_at": account.get("last_used_at"),
                    "is_default": bool(account.get("is_default")),
                    "plan": account.get("plan"),
                }
            )

        return result
