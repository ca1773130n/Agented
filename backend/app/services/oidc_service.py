"""OidcService — optional OIDC SSO (Phase 25, 25-04).

Authorization-code flow whose callback maps a VERIFIED ``(issuer, subject)`` to a
local user, then issues a session through the EXISTING create_session +
litestar_cookies path — the X-API-Key auth path is literally untouched.

Security (locked decisions #3 / #6):
  * JWT/JWKS validation uses authlib (NOT hand-rolled crypto). The id_token
    signature, issuer, audience and expiry are all verified against the
    provider's JWKS; an unverified token is never trusted.
  * Providers are CONFIG, not code: each is read from env
    (``OIDC_<PROVIDER>_CLIENT_ID`` / ``_CLIENT_SECRET`` / ``_ISSUER``) and
    resolved provider-agnostically via the issuer's
    ``.well-known/openid-configuration``. A provider with no configured secret is
    simply not offered (graceful-without-key) → absent config disables OIDC
    entirely, leaving the API-key path unaffected.
  * Subject mapping never bypasses ``AGENTED_DISABLE_SIGNUP``: an unlinked
    identity is provisioned ONLY while ``registration_open()``; when signup is
    closed, only an already-linked identity is allowed, else DENY.
  * Account-takeover guard: an existing local user is matched by email ONLY when
    the id_token asserts ``email_verified`` — an unverified email creates a fresh
    subject-keyed user instead of hijacking an existing account.
"""

from __future__ import annotations

import logging
import os
from typing import Optional
from urllib.parse import urlencode

import httpx

from ..db.oidc_identities import get_user_for_identity, link_identity
from ..db.rbac import ensure_user_admin, registration_open
from ..db.users import create_user, get_user_by_email

logger = logging.getLogger(__name__)

# Known providers → default issuer (None = issuer MUST be configured via env).
KNOWN_PROVIDERS: dict[str, Optional[str]] = {
    "google": "https://accounts.google.com",
    "microsoft": "https://login.microsoftonline.com/common/v2.0",
    "okta": None,
    "github": None,
}

_DISCOVERY_CACHE: dict[str, dict] = {}


class OidcError(Exception):
    """Raised on any OIDC configuration / validation failure (fail closed)."""


class OidcService:
    """Classmethod service (no instance state) for optional OIDC SSO."""

    # -- provider registry (env-driven) -----------------------------------

    @staticmethod
    def _provider_config(provider: str) -> Optional[dict]:
        """Resolve a provider's client_id/secret/issuer from env, or None.

        A provider missing ANY of client_id / client_secret / issuer is treated
        as not configured (graceful-without-key).
        """
        if provider not in KNOWN_PROVIDERS:
            return None
        up = provider.upper()
        client_id = os.environ.get(f"OIDC_{up}_CLIENT_ID")
        client_secret = os.environ.get(f"OIDC_{up}_CLIENT_SECRET")
        issuer = os.environ.get(f"OIDC_{up}_ISSUER") or KNOWN_PROVIDERS[provider]
        if not client_id or not client_secret or not issuer:
            return None
        return {"client_id": client_id, "client_secret": client_secret, "issuer": issuer}

    @classmethod
    def configured_providers(cls) -> list[str]:
        """Provider names that have full env config (empty when none) for auth-status."""
        return [p for p in KNOWN_PROVIDERS if cls._provider_config(p) is not None]

    # -- OIDC discovery ---------------------------------------------------

    @staticmethod
    def _discover(issuer: str) -> dict:
        """Fetch (and cache) the issuer's ``.well-known/openid-configuration``."""
        if issuer in _DISCOVERY_CACHE:
            return _DISCOVERY_CACHE[issuer]
        url = issuer.rstrip("/") + "/.well-known/openid-configuration"
        resp = httpx.get(url, timeout=10)
        resp.raise_for_status()
        doc = resp.json()
        _DISCOVERY_CACHE[issuer] = doc
        return doc

    # -- authorize URL ----------------------------------------------------

    @classmethod
    def build_authorize_url(cls, provider: str, state: str, nonce: str, redirect_uri: str) -> str:
        """Build the provider authorize URL (state + nonce mandatory)."""
        cfg = cls._provider_config(provider)
        if cfg is None:
            raise OidcError(f"OIDC provider not configured: {provider}")
        disc = cls._discover(cfg["issuer"])
        params = {
            "response_type": "code",
            "client_id": cfg["client_id"],
            "redirect_uri": redirect_uri,
            "scope": "openid email profile",
            "state": state,
            "nonce": nonce,
        }
        return f"{disc['authorization_endpoint']}?{urlencode(params)}"

    # -- code exchange + id_token validation (authlib) --------------------

    @classmethod
    def exchange_code(
        cls, provider: str, code: str, redirect_uri: str, nonce: Optional[str] = None
    ) -> dict:
        """Exchange an auth code for a VERIFIED id_token → ``{sub, iss, email, email_verified}``.

        authlib validates the id_token signature (against the issuer's JWKS),
        issuer, audience and expiry. A ``nonce`` mismatch (replay) raises.
        """
        from authlib.jose import JsonWebKey, jwt
        from authlib.jose.errors import JoseError

        cfg = cls._provider_config(provider)
        if cfg is None:
            raise OidcError(f"OIDC provider not configured: {provider}")
        disc = cls._discover(cfg["issuer"])

        token_resp = httpx.post(
            disc["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": cfg["client_id"],
                "client_secret": cfg["client_secret"],
            },
            headers={"Accept": "application/json"},
            timeout=10,
        )
        token_resp.raise_for_status()
        tokens = token_resp.json()
        id_token = tokens.get("id_token")
        if not id_token:
            raise OidcError("token response missing id_token")

        jwks = httpx.get(disc["jwks_uri"], timeout=10).json()
        key_set = JsonWebKey.import_key_set(jwks)
        claims_options = {
            "iss": {"essential": True, "value": disc.get("issuer", cfg["issuer"])},
            "aud": {"essential": True, "value": cfg["client_id"]},
        }
        try:
            claims = jwt.decode(id_token, key_set, claims_options=claims_options)
            claims.validate()  # exp / iat / nbf
        except JoseError as exc:
            raise OidcError(f"id_token validation failed: {exc}") from exc

        if nonce is not None and claims.get("nonce") != nonce:
            raise OidcError("nonce mismatch (possible replay)")

        return {
            "sub": claims["sub"],
            "iss": claims["iss"],
            "email": claims.get("email"),
            "email_verified": bool(claims.get("email_verified")),
        }

    # -- subject → user mapping (signup-gate + takeover guard) ------------

    @classmethod
    def map_subject_to_user(
        cls,
        issuer: str,
        subject: str,
        email: Optional[str] = None,
        *,
        email_verified: bool = True,
        provider: str = "",
    ) -> str:
        """Resolve a verified (issuer, subject) to a local user_id (locked #6).

        * already-linked identity → return its user_id;
        * else, if signup CLOSED → raise ``OidcError`` (SSO never bypasses
          ``AGENTED_DISABLE_SIGNUP``);
        * else (signup OPEN) → find-or-create + link. An existing user is matched
          by email ONLY when ``email_verified`` (takeover guard); the first user
          on a fresh instance becomes admin (``ensure_user_admin``).
        """
        existing = get_user_for_identity(issuer, subject)
        if existing:
            return existing

        if not registration_open():
            raise OidcError("signup is closed; unlinked OIDC identity denied")

        user_id: Optional[str] = None
        if email and email_verified:
            found = get_user_by_email(email)
            if found:
                user_id = found["id"]
        if user_id is None:
            host = issuer.split("://")[-1].split("/")[0] or "oidc"
            # Only key the new user on the asserted email when it is VERIFIED —
            # an unverified email must NOT collide with (or hijack) an existing
            # account, so fall back to a unique subject-derived local email.
            create_email = email if (email and email_verified) else f"{subject}@{host}"
            user_id = create_user(create_email)
            if not user_id:
                raise OidcError("could not provision a user for the OIDC identity")

        # First-operator bootstrap (no-op if an admin already exists).
        ensure_user_admin(user_id)
        link_identity(
            provider or _infer_provider(issuer),
            issuer,
            subject,
            user_id,
            email if email_verified else None,
        )
        return user_id


def _infer_provider(issuer: str) -> str:
    """Best-effort provider label from a configured issuer (for the link row)."""
    for name, default_issuer in KNOWN_PROVIDERS.items():
        cfg_issuer = os.environ.get(f"OIDC_{name.upper()}_ISSUER") or default_issuer
        if cfg_issuer and cfg_issuer.rstrip("/") == issuer.rstrip("/"):
            return name
    return "oidc"
