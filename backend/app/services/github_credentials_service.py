"""Per-host GitHub credentials on top of the encrypted Secret Vault.

One token per git host (github.com, GHE Server, GHE Cloud data-residency),
stored in the existing vault (Fernet-encrypted, audit-logged) under scope
``GITHUB_HOST_SCOPE`` with name ``github-token:<host>`` — no new table, no
parallel crypto.

Resolution order everywhere: the STORED token first (explicit operator
intent), then the ambient env var gh itself would read for that host class
(GITHUB_TOKEN for github.com / *.ghe.com, GH_ENTERPRISE_TOKEN otherwise).
When neither exists callers fall back to today's ambient behavior (server's
gh login / git credential helper), so an instance with nothing stored is
byte-for-byte unchanged.
"""

import logging
import os
import re
from typing import Optional

from app.db import secrets as db_secrets
from app.services.secret_vault_service import SecretVaultService

logger = logging.getLogger(__name__)

GITHUB_HOST_SCOPE = "github-host"

_SECRET_NAME_PREFIX = "github-token:"

# hostname (dots/dashes) with optional :port — enough to reject URLs/paths.
_HOST_RE = re.compile(r"^[a-z0-9][a-z0-9.-]*(:\d{1,5})?$")


def is_dotcom_class(host: str) -> bool:
    """github.com and GHE Cloud data-residency (*.ghe.com) are 'dotcom-class'
    per gh's own token resolution; everything else is GHE Server."""
    return host == "github.com" or host.endswith(".ghe.com")


def env_token_var(host: str) -> str:
    """The ambient env var the backend reads for this host class."""
    return "GITHUB_TOKEN" if is_dotcom_class(host) else "GH_ENTERPRISE_TOKEN"


def gh_env_token_var(host: str) -> str:
    """The env var to SET for gh CLI subprocesses (gh reads GH_TOKEN with
    priority over GITHUB_TOKEN for dotcom-class hosts)."""
    return "GH_TOKEN" if is_dotcom_class(host) else "GH_ENTERPRISE_TOKEN"


def normalize_host(host: Optional[str]) -> str:
    return (host or "github.com").strip().lower()


class GithubCredentialsService:
    """CRUD + resolution for per-host GitHub tokens (vault-backed)."""

    @staticmethod
    def _secret_name(host: str) -> str:
        return f"{_SECRET_NAME_PREFIX}{host}"

    @staticmethod
    def validate_host(host: str) -> bool:
        return bool(_HOST_RE.match(host))

    @classmethod
    def set_token(cls, host: str, token: str, actor: str = "api") -> dict:
        """Create or rotate the stored token for a host. Returns metadata."""
        host = normalize_host(host)
        if not cls.validate_host(host):
            raise ValueError(f"Invalid host: {host!r}")
        existing = db_secrets.get_secret_by_name(cls._secret_name(host))
        if existing:
            SecretVaultService.update_secret(existing["id"], value=token, actor=actor)
            secret_id = existing["id"]
        else:
            secret_id = SecretVaultService.create_secret(
                name=cls._secret_name(host),
                value=token,
                description=f"GitHub token for {host}",
                scope=GITHUB_HOST_SCOPE,
                created_by=actor,
            )
        secret = db_secrets.get_secret(secret_id)
        return cls._host_metadata(secret)

    @classmethod
    def delete_token(cls, host: str, actor: str = "api") -> bool:
        host = normalize_host(host)
        existing = db_secrets.get_secret_by_name(cls._secret_name(host))
        if not existing:
            return False
        return SecretVaultService.delete_secret(existing["id"], actor=actor)

    @classmethod
    def list_hosts(cls) -> list:
        """Stored hosts (metadata only — never token values)."""
        rows = db_secrets.list_secrets(scope=GITHUB_HOST_SCOPE)
        return [cls._host_metadata(r) for r in rows]

    @staticmethod
    def _host_metadata(secret: dict) -> dict:
        return {
            "host": secret["name"].removeprefix(_SECRET_NAME_PREFIX),
            "created_at": secret.get("created_at"),
            "updated_at": secret.get("updated_at"),
            "last_accessed_at": secret.get("last_accessed_at"),
        }

    @classmethod
    def stored_token_for_host(cls, host: str, accessor: str = "system") -> Optional[str]:
        """Vault-stored token for the host, or None. Never consults env."""
        if not SecretVaultService.is_configured():
            return None
        host = normalize_host(host)
        try:
            existing = db_secrets.get_secret_by_name(cls._secret_name(host))
            if not existing:
                return None
            return SecretVaultService.get_secret_value(existing["id"], accessor=accessor)
        except Exception as e:
            logger.warning("Could not resolve stored GitHub token for %s: %s", host, e)
            return None

    @classmethod
    def token_for_host(cls, host: str, accessor: str = "system") -> Optional[str]:
        """Stored token first, then the host class's ambient env var."""
        host = normalize_host(host)
        token = cls.stored_token_for_host(host, accessor=accessor)
        if token:
            return token
        return (os.environ.get(env_token_var(host)) or "").strip() or None
