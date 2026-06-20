"""Account rotation on rate-limit for chat streaming.

When a chat turn's account hits a provider rate limit (e.g. Claude's
weekly cap → HTTP 429), the streaming chokepoint (``streaming_helper``)
rotates to the next eligible account and retries the turn. This module
owns the two pure pieces of that decision so they can be unit-tested
independently of the threaded SSE loop:

1. **Detection** — recognise a rate-limit signal in a backend's output.
   Claude's ``--output-format stream-json`` carries it as a structured
   event (``api_error_status: 429`` / ``error: "rate_limit"`` on the
   ``assistant``/``result`` events); codex/gemini print human text, so a
   conservative text matcher backs the structured check.
2. **Candidate ordering** — given the failed backend + already-tried
   accounts, produce the ordered list of accounts to try next: the same
   backend's still-eligible accounts first (matching the existing
   ``is_default DESC, last_used_at ASC`` pick order), then — for the
   "same backend, then other backends" policy — the other CLI backends'
   eligible accounts. Rate-limited and already-attempted accounts are
   filtered out.

Rotation only happens BEFORE any assistant content has streamed (a 429
fires with zero output tokens), so a retry never duplicates text.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# CLI backends that can run as autonomous chat agents, in cross-backend
# fallback order. The failed backend is always tried first regardless.
CLI_BACKENDS: tuple[str, ...] = ("claude", "codex", "gemini")

# Default cooldown when the provider message gives no parseable reset time.
# A weekly cap won't actually reset for days, but the periodic re-check
# (Phase 2) and the operator can clear it; this just keeps the account out
# of the immediate rotation so we don't hammer a known-limited account.
DEFAULT_COOLDOWN_SECONDS = 3600

# Strong rate-limit phrasing. Kept conservative for the text path (codex/
# gemini) so ordinary output mentioning "limit" doesn't trip a false
# rotation. The structured event path does not rely on this.
_RATE_LIMIT_TEXT_RE = re.compile(
    r"(?:"
    r"rate[ _-]?limit"
    r"|weekly\s+limit"
    r"|usage\s+limit"
    r"|too\s+many\s+requests"
    r"|quota\b.*\bexceed"
    r"|\b429\b"
    r"|hit\s+your\s+(?:weekly|usage|daily)\s+limit"
    r")",
    re.IGNORECASE,
)

_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

# "resets Jun 12 at 6am" / "resets June 12 at 6:30pm" — best-effort.
_RESET_RE = re.compile(
    r"reset[s]?\s+([A-Za-z]{3,9})\s+(\d{1,2})(?:\w{0,2})?\s+at\s+(\d{1,2})(?::(\d{2}))?\s*([ap]m)?",
    re.IGNORECASE,
)


@dataclass
class RateLimitInfo:
    """A detected rate-limit, ready to record + surface to the operator."""

    reason: str  # human message, e.g. "You've hit your weekly limit · resets Jun 12 at 6am"
    reset_at: Optional[str] = None  # best-effort ISO timestamp, else None


@dataclass
class RateLimitEvent:
    """Typed stream item the CLI runner yields in place of text when it
    detects a rate limit, so the streaming loop can rotate instead of
    treating the limit message as assistant content."""

    info: RateLimitInfo


@dataclass
class RotationCandidate:
    """An account+backend to (re)try a chat turn on."""

    account_id: Optional[int]
    backend: str
    config_dir: Optional[str]
    display_name: str


def _parse_reset(message: str) -> Optional[str]:
    """Best-effort parse of a provider reset time into a naive-local ISO
    string. Returns ``None`` when nothing parseable is present (caller
    falls back to a default cooldown). Timezone nuance in the message
    (e.g. "(Asia/Seoul)") is intentionally ignored — the value is only
    used to keep an account out of rotation until roughly its reset."""
    if not message:
        return None
    m = _RESET_RE.search(message)
    if not m:
        return None
    mon_raw, day_raw, hour_raw, minute_raw, ampm = m.groups()
    month = _MONTHS.get(mon_raw[:3].lower())
    if not month:
        return None
    try:
        day = int(day_raw)
        hour = int(hour_raw)
        minute = int(minute_raw) if minute_raw else 0
    except ValueError:
        return None
    if ampm:
        ampm = ampm.lower()
        if ampm == "pm" and hour != 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
    if not (0 <= hour <= 23 and 1 <= day <= 31 and 0 <= minute <= 59):
        return None
    now = datetime.now()
    year = now.year
    try:
        reset = datetime(year, month, day, hour, minute)
    except ValueError:
        return None
    # If the parsed date already passed this year, it's next year's date.
    if reset < now:
        try:
            reset = datetime(year + 1, month, day, hour, minute)
        except ValueError:
            return None
    return reset.isoformat()


def _first_text(event: dict) -> Optional[str]:
    """Pull the first text block out of a Claude ``assistant`` event."""
    msg = event.get("message")
    if isinstance(msg, dict):
        for block in msg.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
                return block["text"]
    return None


def detect_rate_limit_from_event(event: dict) -> Optional[RateLimitInfo]:
    """Detect a rate limit in a Claude stream-json event dict.

    Matches the structured signals first (``api_error_status == 429`` or
    ``error == "rate_limit"`` on ``assistant``/``result`` events), then a
    text fallback on a ``result`` event flagged ``is_error``.
    """
    if not isinstance(event, dict):
        return None
    if event.get("api_error_status") == 429 or event.get("error") == "rate_limit":
        msg = event.get("result") or _first_text(event) or "rate limit reached"
        msg = str(msg)
        return RateLimitInfo(reason=msg[:300], reset_at=_parse_reset(msg))
    if event.get("type") == "result" and event.get("is_error"):
        msg = str(event.get("result") or "")
        if _RATE_LIMIT_TEXT_RE.search(msg):
            return RateLimitInfo(reason=msg[:300], reset_at=_parse_reset(msg))
    return None


def detect_rate_limit_from_text(text: str) -> Optional[RateLimitInfo]:
    """Conservative text-based detection for codex/gemini passthrough lines."""
    if text and _RATE_LIMIT_TEXT_RE.search(text):
        stripped = text.strip()
        return RateLimitInfo(reason=stripped[:300], reset_at=_parse_reset(stripped))
    return None


def _account_is_available(acct: dict, now: datetime) -> bool:
    """True when the account isn't currently rate-limited."""
    rl = acct.get("rate_limited_until")
    if not rl:
        return True
    try:
        return datetime.fromisoformat(rl) <= now
    except (ValueError, TypeError):
        # Unparseable timestamp — treat as available rather than wedge it.
        return True


def rotation_candidates(
    backend: str,
    exclude_account_ids: Optional[set[int]] = None,
    *,
    allow_cross_backend: bool = True,
    now: Optional[datetime] = None,
) -> list[RotationCandidate]:
    """Ordered accounts to try next after a rate limit.

    Same backend's eligible accounts first (DB order: ``is_default DESC,
    last_used_at ASC``), then — when ``allow_cross_backend`` — the other
    CLI backends' eligible accounts. Skips rate-limited and excluded
    accounts. Accounts with no ``config_path`` are still returned (the CLI
    falls back to its default vault) but only when they carry an id we can
    mark on a subsequent limit.
    """
    from ..db.backends import get_accounts_for_backend_type

    exclude = set(exclude_account_ids or ())
    now = now or datetime.now()
    backend_norm = (backend or "").lower()

    ordered = [backend_norm]
    if allow_cross_backend:
        ordered += [b for b in CLI_BACKENDS if b != backend_norm]

    out: list[RotationCandidate] = []
    for b in ordered:
        if b not in CLI_BACKENDS:
            continue
        try:
            accounts = get_accounts_for_backend_type(b)
        except Exception:
            logger.debug("rotation: account lookup failed for %s", b, exc_info=True)
            continue
        for acct in accounts:
            aid = acct.get("id")
            if aid in exclude:
                continue
            if not _account_is_available(acct, now):
                continue
            cfg = acct.get("config_path")
            out.append(
                RotationCandidate(
                    account_id=aid,
                    backend=b,
                    config_dir=os.path.expanduser(cfg) if cfg else None,
                    # backend_accounts stores the label as ``account_name``;
                    # keep display_name fallbacks for forward-compat.
                    display_name=(
                        acct.get("account_name") or acct.get("display_name") or f"{b} #{aid}"
                    ),
                )
            )
    return out


def soonest_reset_message(backend: str, *, allow_cross_backend: bool = True) -> str:
    """Human summary for when every candidate is rate-limited."""
    from ..db.backends import get_accounts_for_backend_type

    backend_norm = (backend or "").lower()
    backends = [backend_norm]
    if allow_cross_backend:
        backends += [b for b in CLI_BACKENDS if b != backend_norm]

    soonest: Optional[datetime] = None
    for b in backends:
        if b not in CLI_BACKENDS:
            continue
        try:
            accounts = get_accounts_for_backend_type(b)
        except Exception:
            continue
        for acct in accounts:
            rl = acct.get("rate_limited_until")
            if not rl:
                continue
            try:
                ts = datetime.fromisoformat(rl)
            except (ValueError, TypeError):
                continue
            if soonest is None or ts < soonest:
                soonest = ts
    if soonest is not None:
        return (
            f"All accounts are rate-limited — soonest reset {soonest.strftime('%b %-d %-I:%M%p')}."
        )
    return "All accounts are rate-limited."
