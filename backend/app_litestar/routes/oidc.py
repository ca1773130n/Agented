"""OIDC SSO start/callback routes (Phase 25, 25-04).

``GET /api/auth/oidc/{provider}/start``     — build state+nonce, stash in a
    short-lived HttpOnly cookie, redirect to the provider's authorize URL.
``GET /api/auth/oidc/{provider}/callback``  — verify state, exchange the code,
    validate the id_token, map (issuer, subject) → user, then issue a session via
    the EXISTING create_session + litestar_cookies path and redirect to the SPA.

Both routes are in the ApiKeyMiddleware bypass set (``/api/auth/oidc`` prefix,
25-01) — they establish a session for a credential-less caller, exactly like the
existing /api/auth/login bypass. The X-API-Key resolution branch is untouched.
"""

from __future__ import annotations

import secrets

from litestar import Request, Router, get
from litestar.datastructures import Cookie
from litestar.exceptions import ClientException, NotFoundException, PermissionDeniedException
from litestar.response import Redirect

from app.db.sessions import create_session
from app.services.oidc_service import OidcError, OidcService
from app_litestar.cookie_auth import cookie_secure, generate_csrf_token, litestar_cookies

_STATE_COOKIE = "oidc_state"
_STATE_TTL_SECONDS = 600


def _redirect_uri(request: Request, provider: str) -> str:
    """Absolute callback URL for this provider (mirrors the mounted route path)."""
    scheme = request.url.scheme or "http"
    host = request.headers.get("host", "") or getattr(request.url, "netloc", "")
    return f"{scheme}://{host}/api/auth/oidc/{provider}/callback"


@get("/{provider:str}/start", sync_to_thread=False)
def oidc_start(provider: str, request: Request) -> Redirect:
    """Begin the OIDC auth-code flow — redirect to the provider's authorize URL."""
    if OidcService._provider_config(provider) is None:
        raise NotFoundException(detail=f"OIDC provider not configured: {provider}")

    state = generate_csrf_token()
    nonce = secrets.token_urlsafe(24)
    authorize_url = OidcService.build_authorize_url(
        provider, state, nonce, _redirect_uri(request, provider)
    )
    secure = cookie_secure(request.url.scheme)
    # SameSite=Lax so the cookie survives the IdP's cross-site redirect back to
    # our callback (a top-level GET navigation), unlike the Strict session cookie.
    state_cookie = Cookie(
        key=_STATE_COOKIE,
        value=f"{state}:{nonce}",
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
        max_age=_STATE_TTL_SECONDS,
    )
    return Redirect(authorize_url, cookies=[state_cookie])


@get("/{provider:str}/callback", sync_to_thread=False)
def oidc_callback(provider: str, request: Request) -> Redirect:
    """Complete the flow: verify state → exchange code → map subject → session."""
    if OidcService._provider_config(provider) is None:
        raise NotFoundException(detail=f"OIDC provider not configured: {provider}")

    state_q = request.query_params.get("state")
    code = request.query_params.get("code")
    cookie_val = request.cookies.get(_STATE_COOKIE)
    if not state_q or not cookie_val:
        raise PermissionDeniedException(detail="missing OIDC state")
    state_c, _, nonce = cookie_val.partition(":")
    # Constant-time compare of the state (CSRF / auth-code injection guard).
    if not secrets.compare_digest(state_q, state_c):
        raise PermissionDeniedException(detail="OIDC state mismatch")
    if not code:
        raise ClientException(detail="missing authorization code")

    claims = OidcService.exchange_code(
        provider, code, _redirect_uri(request, provider), nonce or None
    )
    email = claims.get("email") if claims.get("email_verified") else None
    try:
        user_id = OidcService.map_subject_to_user(
            claims["iss"],
            claims["sub"],
            email,
            email_verified=bool(claims.get("email_verified")),
            provider=provider,
        )
    except OidcError as exc:
        # Signup closed for an unlinked identity, or provisioning refused.
        raise PermissionDeniedException(detail=str(exc)) from exc

    session = create_session(user_id)
    if session is None:
        raise PermissionDeniedException(detail="session creation failed")

    csrf = generate_csrf_token()
    secure = cookie_secure(request.url.scheme)
    cookies = litestar_cookies(session["token"], csrf, secure=secure)
    # Clear the one-shot state cookie.
    cookies.append(Cookie(key=_STATE_COOKIE, value="", max_age=0, path="/"))
    return Redirect("/", cookies=cookies)


oidc_router = Router(
    path="/api/auth/oidc",
    route_handlers=[oidc_start, oidc_callback],
)
