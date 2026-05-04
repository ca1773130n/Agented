"""Local timezone detection — reads the system IANA timezone name.

Also exposes `utcnow()` — a Python 3.12+ deprecation shim for
`datetime.datetime.utcnow()`. Returns a NAIVE datetime in UTC,
preserving the historical comparison semantics of utcnow() across
the codebase (most call sites compare against ISO strings or other
naive datetimes; switching to aware datetimes would require an
audit of every comparison).
"""

import datetime as _dt
import logging
import os

logger = logging.getLogger(__name__)

_FALLBACK_TZ = "Asia/Seoul"


def utcnow() -> _dt.datetime:
    """v0.6.1 shim for `datetime.datetime.utcnow()`.

    `datetime.utcnow()` was deprecated in Python 3.12 in favor of
    `datetime.now(datetime.UTC)` (aware). Switching wholesale would
    break naive-vs-aware comparisons elsewhere — many call sites
    compare against `datetime.fromisoformat(...)` results which are
    naive. This shim returns a NAIVE UTC datetime so the call-sites
    keep working unchanged while killing the DeprecationWarning.

    Future cleanup (deferred): audit every consumer + migrate to
    aware datetimes throughout. Not in scope for v0.6.1.
    """
    return _dt.datetime.now(_dt.UTC).replace(tzinfo=None)


def get_local_timezone() -> str:
    """Detect the system's IANA timezone (e.g. 'Asia/Seoul').

    Detection order:
    1. TZ environment variable
    2. /etc/localtime symlink (macOS: /var/db/timezone/zoneinfo/..., Linux: /usr/share/zoneinfo/...)
    3. Falls back to Asia/Seoul
    """
    # 1. TZ environment variable
    tz = os.environ.get("TZ")
    if tz and "/" in tz:
        return tz

    # 2. /etc/localtime symlink
    try:
        link = os.readlink("/etc/localtime")
        parts = link.split("/zoneinfo/")
        if len(parts) > 1 and "/" in parts[1]:
            return parts[1]
    except (OSError, IndexError):
        pass

    logger.debug(f"Could not detect system timezone, using fallback: {_FALLBACK_TZ}")
    return _FALLBACK_TZ
