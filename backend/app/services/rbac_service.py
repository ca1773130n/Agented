"""RBAC service -- permission matrix and @require_role() decorator.

Based on RBAC0 flat model (Sandhu et al. 1996). Uses a decorator pattern
per Flask community conventions to enforce role-based access on routes.
"""

import functools
import logging
from http import HTTPStatus
from typing import Callable, Optional

from flask import request

from app.models.common import error_response

from ..db.rbac import count_user_roles, get_role_for_api_key
from ..services.audit_log_service import AuditLogService

logger = logging.getLogger(__name__)

# Permission matrix: role -> set of allowed permissions
ROLE_PERMISSIONS = {
    "viewer": {"read"},
    "operator": {"read", "execute"},
    "editor": {"read", "execute", "edit"},
    "admin": {"read", "execute", "edit", "manage"},
}


def get_role_for_request(req=None) -> Optional[str]:
    """Extract the role for the current request from the X-API-Key header.

    Returns:
        Role string (e.g. 'admin'), or None if no key or key not found.
    """
    req = req or request
    api_key = req.headers.get("X-API-Key")
    if not api_key:
        return None
    return get_role_for_api_key(api_key)


def has_permission(api_key: str, permission: str) -> bool:
    """Check whether an API key has a specific permission.

    Args:
        api_key: The API key to check.
        permission: Permission string (read, execute, edit, manage).

    Returns:
        True if the key's role grants the permission, False otherwise.
    """
    role = get_role_for_api_key(api_key)
    if role is None:
        return False
    return permission in ROLE_PERMISSIONS.get(role, set())


def require_role(*allowed_roles) -> Callable:
    """Decorator to enforce RBAC on a Flask route.

    When no roles exist in the database, RBAC is disabled and all requests
    pass through (graceful bootstrap mode).

    IMPORTANT: Apply this decorator AFTER (below) the route decorator to
    avoid breaking flask-openapi3 schema generation.

    Usage:
        @triggers_bp.post("/")
        @require_role("editor", "admin")
        def create_trigger():
            ...

    Args:
        *allowed_roles: One or more role names that are permitted to access
                        this route.
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            # Graceful bootstrap: if no roles configured, allow all requests
            if count_user_roles() == 0:
                return fn(*args, **kwargs)

            api_key = request.headers.get("X-API-Key")
            if not api_key:
                AuditLogService.log(
                    action="rbac.denied",
                    entity_type="api",
                    entity_id=request.path,
                    outcome="denied",
                    details={"reason": "missing_api_key", "endpoint": request.path},
                )
                return error_response("FORBIDDEN", "API key required", HTTPStatus.FORBIDDEN)

            role = get_role_for_api_key(api_key)
            if role is None:
                AuditLogService.log(
                    action="rbac.denied",
                    entity_type="api",
                    entity_id=request.path,
                    outcome="denied",
                    details={"reason": "unknown_api_key", "endpoint": request.path},
                )
                return error_response("FORBIDDEN", "Invalid API key", HTTPStatus.FORBIDDEN)

            if role not in allowed_roles:
                AuditLogService.log(
                    action="rbac.denied",
                    entity_type="api",
                    entity_id=request.path,
                    outcome="denied",
                    details={
                        "reason": "insufficient_permissions",
                        "role": role,
                        "required": list(allowed_roles),
                        "endpoint": request.path,
                    },
                )
                return error_response("FORBIDDEN", "Insufficient permissions", HTTPStatus.FORBIDDEN)

            return fn(*args, **kwargs)

        return wrapper

    return decorator
