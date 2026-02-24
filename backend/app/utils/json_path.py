"""Utility functions for extracting values from nested JSON structures."""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def get_nested_value(data: dict, path: str) -> Optional[Any]:
    """
    Extract a value from nested JSON using dot notation.

    Args:
        data: The dictionary to extract from
        path: Dot-separated path to the value (e.g., "event.type", "data.0.id")

    Returns:
        The value at the path, or None if not found

    Examples:
        >>> get_nested_value({"event": {"type": "alert"}}, "event.type")
        'alert'
        >>> get_nested_value({"action": "create"}, "action")
        'create'
        >>> get_nested_value({"data": [{"id": 1}]}, "data.0.id")
        1
        >>> get_nested_value({"a": {"b": None}}, "a.b.c")
        None
    """
    if not path or not isinstance(data, dict):
        return None

    keys = path.split(".")
    current = data

    for key in keys:
        if current is None:
            return None

        if isinstance(current, dict):
            current = current.get(key)
        elif isinstance(current, list):
            try:
                index = int(key)
                current = current[index] if 0 <= index < len(current) else None
            except ValueError:
                logger.warning("Non-numeric array index %r in JSON path %r", key, path)
                return None
            except IndexError:
                return None
        else:
            return None

    return current
