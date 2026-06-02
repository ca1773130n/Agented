"""Rate limit detection and account cooldown management service."""

import logging
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

logger = logging.getLogger(__name__)

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

    # Claude Code writes this into a session transcript (as an
    # isApiErrorMessage assistant turn) when the model API returns a 429
    # usage-limit block, e.g. "You've hit your weekly limit · resets Jun 5
    # at 6am (Asia/Seoul)". This is the AUTHORITATIVE "account is blocked"
    # signal — Anthropic's /api/oauth/usage utilization can read low (e.g. 7%)
    # while the account is actually locked out, so we cannot rely on it.
    USAGE_BLOCK_PATTERN = re.compile(
        r"hit your (?P<kind>weekly|5-hour|five-hour|usage|opus|sonnet)[\s\-]*limit"
        r"|usage limit reached|reached your usage limit",
        re.IGNORECASE,
    )

    @staticmethod
    def _message_text(message: object) -> str:
        """Flatten a transcript message's content into plain text."""
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts = []
                for blk in content:
                    if isinstance(blk, dict) and isinstance(blk.get("text"), str):
                        parts.append(blk["text"])
                    elif isinstance(blk, str):
                        parts.append(blk)
                return " ".join(parts)
        if isinstance(message, str):
            return message
        return ""

    @classmethod
    def detect_usage_limit_block(cls, config_path: Optional[str]) -> Optional[dict]:
        """Return a CURRENTLY-ACTIVE usage-limit block for the account, or None.

        Looks only at the account's most-recent sessions and reports a block
        ONLY when the latest API outcome is a limit error with NO successful
        API call after it. A block the user has since recovered from — or a
        stale / transient / model-specific error from days ago — is NOT
        reported, because a later successful call proves the account is usable
        again. (Earlier this over-fired on any 7-day-old error, flagging
        accounts that work fine.)

        Returns ``{"message": str, "limit_kind": str}`` or None.
        """
        import json
        import os
        from datetime import datetime
        from pathlib import Path

        base = Path(os.path.expanduser(config_path)) if config_path else (Path.home() / ".claude")
        projects = base / "projects"
        if not projects.is_dir():
            return None

        files: list[tuple[float, Path]] = []
        try:
            for proj in projects.iterdir():
                if not proj.is_dir():
                    continue
                for f in proj.glob("*.jsonl"):
                    try:
                        files.append((f.stat().st_mtime, f))
                    except OSError:
                        continue
        except OSError:
            return None
        files.sort(reverse=True)  # newest first

        def _ts(entry: dict):
            t = entry.get("timestamp")
            if not isinstance(t, str):
                return None
            try:
                return datetime.fromisoformat(t.replace("Z", "+00:00"))
            except ValueError:
                return None

        latest_block = None  # (ts, message, kind)
        latest_ok = None  # ts of most recent SUCCESSFUL assistant turn

        # Only the most-recent sessions decide current state — a newer success
        # means the account is usable again.
        for _mt, f in files[:30]:
            try:
                with open(f, "r", errors="replace") as fh:
                    for line in fh:
                        is_err = "isApiErrorMessage" in line
                        is_asst = '"assistant"' in line
                        if not (is_err or is_asst):
                            continue
                        try:
                            entry = json.loads(line)
                        except (json.JSONDecodeError, ValueError):
                            continue
                        ts = _ts(entry)
                        if ts is None:
                            continue
                        if entry.get("isApiErrorMessage"):
                            text = cls._message_text(entry.get("message", {}))
                            m = cls.USAGE_BLOCK_PATTERN.search(text)
                            if m and (latest_block is None or ts > latest_block[0]):
                                kind_raw = (m.groupdict().get("kind") or "usage").lower()
                                kind = {
                                    "weekly": "weekly",
                                    "opus": "weekly_opus",
                                    "sonnet": "weekly_sonnet",
                                    "5-hour": "five_hour",
                                    "five-hour": "five_hour",
                                }.get(kind_raw, "usage")
                                latest_block = (ts, text.strip(), kind)
                        elif entry.get("type") == "assistant":
                            msg = entry.get("message")
                            if isinstance(msg, dict) and msg.get("usage"):
                                if latest_ok is None or ts > latest_ok:
                                    latest_ok = ts
            except OSError:
                continue

        # Blocked only if the most recent block is NEWER than the most recent
        # successful call (or there is no later success).
        if latest_block and (latest_ok is None or latest_block[0] > latest_ok):
            return {"message": latest_block[1], "limit_kind": latest_block[2]}
        return None

    @classmethod
    def mark_blocked_until(cls, account_id: int, until_iso: str, reason: str) -> bool:
        """Mark an account blocked until an absolute ISO time (from the
        provider's reset), with a human reason (the transcript message)."""
        return update_account_rate_limit(account_id, until_iso, reason[:300])

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
                    pass  # Intentionally silenced: type mismatch handled gracefully
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
                    pass  # Intentionally silenced: type mismatch handled gracefully

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
