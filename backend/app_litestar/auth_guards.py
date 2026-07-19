"""v0.5.12: RBAC enforcement helpers — coarse method+prefix table
and a per-route guard factory.

The middleware (`ApiKeyMiddleware`) calls `required_role(method, path)`
to derive the coarse-default required role, then compares it against
the principal's role. Sensitive routes can override with
`requires_role('admin')` as a Litestar guard for a stricter check.
"""

from __future__ import annotations

from typing import Optional

from litestar.exceptions import PermissionDeniedException

ROLE_RANK: dict[str, int] = {
    "viewer": 0,
    "operator": 1,
    "editor": 2,
    "admin": 3,
}

# (method, prefix) → required role. Order matters for prefix matching:
# the table is iterated and the first method-and-prefix match wins.
# Coverage closes the v0.5.12 critical: mutating /api/* must be gated.
ROLE_REQUIRED: list[tuple[str, str, str]] = [
    ("GET", "/api/", "viewer"),
    ("POST", "/api/", "editor"),
    ("PUT", "/api/", "editor"),
    ("PATCH", "/api/", "editor"),
    ("DELETE", "/api/", "admin"),
    # Secret vault: admin for every method. Listed before the generic
    # /admin/ rows (first-match-wins) so a missing per-route guard can never
    # downgrade reveal/list to editor/viewer. Defence-in-depth alongside the
    # router-level requires_role("admin") guard.
    ("GET", "/admin/secrets", "admin"),
    ("POST", "/admin/secrets", "admin"),
    ("PUT", "/admin/secrets", "admin"),
    ("PATCH", "/admin/secrets", "admin"),
    ("DELETE", "/admin/secrets", "admin"),
    # Per-host GitHub tokens are vault secrets behind a friendlier surface —
    # same admin-for-every-method posture as /admin/secrets, same reason.
    ("GET", "/admin/github-credentials", "admin"),
    ("POST", "/admin/github-credentials", "admin"),
    ("PUT", "/admin/github-credentials", "admin"),
    ("PATCH", "/admin/github-credentials", "admin"),
    ("DELETE", "/admin/github-credentials", "admin"),
    # Policy / governance engine: admin for every method. Listed before the
    # generic /admin/ rows (first-match-wins) so a missing per-route guard can
    # never downgrade policy reads/writes to editor/viewer. Defence-in-depth
    # alongside the router-level requires_role("admin") guard on policies_router.
    # Policies are the governance substrate — mutating them disables other
    # controls — so they are gated as strictly as the secret vault (23 BLOCKER 2).
    ("GET", "/admin/policies", "admin"),
    ("POST", "/admin/policies", "admin"),
    ("PUT", "/admin/policies", "admin"),
    ("PATCH", "/admin/policies", "admin"),
    ("DELETE", "/admin/policies", "admin"),
    ("GET", "/admin/", "viewer"),
    ("POST", "/admin/", "editor"),
    ("PUT", "/admin/", "editor"),
    ("PATCH", "/admin/", "editor"),
    ("DELETE", "/admin/", "admin"),
]

# Public paths bypass the coarse role check (still authenticated by
# ApiKeyMiddleware unless the path is also in middleware's
# _AUTH_BYPASS_PREFIXES).
#
# Logout is here so any authenticated principal — including viewer —
# can end their session. Login/signup/password-reset bypass auth
# entirely at the middleware level (see _AUTH_BYPASS_PREFIXES).
PUBLIC_PATHS: tuple[str, ...] = (
    "/health/",
    "/docs",
    "/schema",
    "/api/auth/logout",
    "/admin/auth/logout",
)


def required_role(method: str, path: str) -> Optional[str]:
    """Return required role for (method, path), or None if public.

    A None return means either:
      - the path matches PUBLIC_PATHS (no role check)
      - the path is unmapped (default-public is intentional — unmapped
        paths get authentication only, not authorization)
    """
    for prefix in PUBLIC_PATHS:
        if path.startswith(prefix):
            return None
    for m, prefix, role in ROLE_REQUIRED:
        if method == m and path.startswith(prefix):
            return role
    return None


def has_sufficient_role(principal_role: Optional[str], required: Optional[str]) -> bool:
    """True iff `principal_role` is at least as senior as `required`.
    Treats None role (unauthenticated context) as insufficient unless
    `required` is also None. Unknown roles compare as below the floor."""
    if required is None:
        return True
    if principal_role is None:
        return False
    return ROLE_RANK.get(principal_role, -1) >= ROLE_RANK.get(required, -1)


def requires_role(min_role: str):
    """Litestar guard factory. Use as `guards=[requires_role('admin')]`
    on individual route handlers to enforce a stricter check than the
    coarse default. Validates `min_role` at construction time."""
    if min_role not in ROLE_RANK:
        raise ValueError(
            f"requires_role: unknown role {min_role!r}; valid roles are {sorted(ROLE_RANK)}"
        )

    def guard(connection, _route_handler) -> None:
        principal = connection.scope.get("state", {}).get("principal")
        if principal is None:
            # Explicit per-route guards always require a real authenticated
            # principal — bootstrap mode does NOT weaken them. Fresh-install UX
            # is served by ungated routes; sensitive guarded routes (e.g. the
            # secret vault) stay closed until a real admin role exists.
            raise PermissionDeniedException(detail="not authenticated")
        if not has_sufficient_role(principal.get("role"), min_role):
            raise PermissionDeniedException(detail=f"requires {min_role}")

    return guard
