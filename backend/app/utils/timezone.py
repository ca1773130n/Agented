"""Local timezone detection — reads the system IANA timezone name."""

import logging
import os

logger = logging.getLogger(__name__)

_FALLBACK_TZ = "Asia/Seoul"


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
