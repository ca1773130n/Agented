"""v0.5.13: env-var validator.

Single source of truth for which env vars Agented requires in
production. Used at gunicorn/sidecar startup AND as a standalone
CLI (`python -m scripts.check_env`).

Supports the `*_FILE` convention: any var named `FOO_FILE=/path` is
resolved by reading the file's contents into `FOO` before validation.
This works for Docker secrets, host-mount secret files, etc.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional


REQUIRED_VARS: list[dict] = [
    {
        "name": "AGENTED_API_KEY",
        "description": "Backend admin API key.",
        "example": "(generate with: openssl rand -hex 32)",
        "secret": True,
    },
    {
        "name": "AI_ACCOUNTS_API_KEY",
        "description": "Sidecar admin API key. May reuse AGENTED_API_KEY.",
        "example": "(generate with: openssl rand -hex 32)",
        "secret": True,
    },
    {
        "name": "AI_ACCOUNTS_VAULT_KEY",
        "description": "Sidecar vault encryption key. Required in production.",
        "example": "(generate with: openssl rand -base64 32)",
        "secret": True,
    },
    {
        "name": "AGENTED_VAULT_KEYS",
        "description": (
            "Backend secrets-vault Fernet keys (comma-separated). First key "
            "is used for encryption; later keys decrypt rotated entries. "
            "Required for /admin/secrets/* routes to function."
        ),
        "example": "(generate with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')",
        "secret": True,
    },
    {
        "name": "AGENTED_ENV",
        "description": "Deployment posture. Must be 'production' for prod deploys.",
        "example": "production",
        "secret": False,
    },
]

OPTIONAL_VARS: list[dict] = [
    {
        "name": "AGENTED_DB_PATH",
        "description": "SQLite database path. Defaults to backend/agented.db; in containers set to /app/data/agented.db.",
        "example": "/app/data/agented.db",
        "default": "(repo-relative)",
        "secret": False,
    },
    {
        "name": "LOG_LEVEL",
        "description": "Gunicorn log level.",
        "example": "info",
        "default": "info",
        "secret": False,
    },
    {
        "name": "LOG_FORMAT",
        "description": "Logger format: 'json' (production) or 'text'.",
        "example": "json",
        "default": "text",
        "secret": False,
    },
    {
        "name": "GUNICORN_BIND",
        "description": "Backend bind address.",
        "example": "0.0.0.0:20000",
        "default": "0.0.0.0:20000",
        "secret": False,
    },
    {
        "name": "AGENTED_BACKEND_URL",
        "description": "Healthcheck CLI's backend probe URL.",
        "example": "http://127.0.0.1:20000",
        "default": "http://127.0.0.1:20000",
        "secret": False,
    },
    {
        "name": "AGENTED_SIDECAR_URL",
        "description": "Healthcheck CLI's sidecar probe URL.",
        "example": "http://127.0.0.1:20001",
        "default": "http://127.0.0.1:20001",
        "secret": False,
    },
    {
        "name": "AI_ACCOUNTS_ALLOW_NOAUTH",
        "description": "Set to 1 to allow sidecar to start without any keyed identity (DEV ONLY).",
        "example": "(unset)",
        "default": "(unset)",
        "secret": False,
    },
    {
        "name": "ANTHROPIC_API_KEY",
        "description": "Anthropic API key (sk-ant-...). Optional; per-account vault is the canonical store.",
        "example": "sk-ant-...",
        "default": "(unset)",
        "secret": True,
    },
    {
        "name": "GITHUB_WEBHOOK_SECRET",
        "description": "Secret for verifying GitHub webhook signatures.",
        "example": "(generate with: openssl rand -hex 32)",
        "default": "(unset)",
        "secret": True,
    },
    {
        "name": "GITHUB_TOKEN",
        "description": "GitHub PAT for `gh` CLI + GitHub API. Recommend macOS Keychain export from ~/.zshrc.",
        "example": "ghp_...",
        "default": "(unset)",
        "secret": True,
    },
    {
        "name": "CORS_ALLOWED_ORIGINS",
        "description": "Comma-separated CORS allowlist for browser requests.",
        "example": "https://agented.example.com",
        "default": "(localhost only)",
        "secret": False,
    },
    {
        "name": "SENTRY_DSN",
        "description": "Sentry DSN for error reporting.",
        "example": "https://xxx@sentry.io/yyy",
        "default": "(unset; Sentry disabled)",
        "secret": True,
    },
    {
        "name": "SENTRY_ENVIRONMENT",
        "description": "Sentry environment tag.",
        "example": "production",
        "default": "(uses AGENTED_ENV)",
        "secret": False,
    },
    {
        "name": "SENTRY_RELEASE",
        "description": "Sentry release tag (e.g., v0.5.13).",
        "example": "v0.5.13",
        "default": "(unset)",
        "secret": False,
    },
    {
        "name": "VITE_HOST",
        "description": "Frontend dev-server bind. Unused in container deploy.",
        "example": "127.0.0.1",
        "default": "127.0.0.1",
        "secret": False,
    },
    {
        "name": "VITE_ALLOWED_HOSTS",
        "description": "Comma-separated host allowlist for the dev server.",
        "example": "agented.local",
        "default": "",
        "secret": False,
    },
]


_PERMISSION_WARNINGS: list[str] = []


def _resolve_file_redirect(name: str) -> Optional[str]:
    """If `<NAME>_FILE` is set in env, read the file and return its
    stripped contents. Used for Docker-secrets / mounted secret files.

    Records a warning into `_PERMISSION_WARNINGS` if the file is
    world-readable — Docker-secrets mounts are typically 0644 so
    this is informational unless the secret is on a host filesystem.
    """
    import stat

    file_var = f"{name}_FILE"
    path_str = os.environ.get(file_var, "").strip()
    if not path_str:
        return None
    path = Path(path_str)
    if not path.is_file():
        return None
    try:
        mode = path.stat().st_mode
        if mode & (stat.S_IROTH | stat.S_IWOTH):
            _PERMISSION_WARNINGS.append(
                f"{file_var}={path_str} is world-readable/writable; "
                f"recommend chmod 600"
            )
    except OSError:
        pass
    return path.read_text().strip()


def resolve(name: str) -> Optional[str]:
    """Get a var's value: prefer literal env; fall back to *_FILE redirect."""
    val = os.environ.get(name)
    if val:
        return val
    return _resolve_file_redirect(name)


def validate(*, strict: bool = True) -> tuple[bool, list[str], list[str]]:
    """Returns (ok, missing_required, warnings).

    strict=True (default) treats missing required vars as failure.
    When AGENTED_ENV != 'production', strict is silently downgraded
    to False — dev environments boot with sparse env."""
    _PERMISSION_WARNINGS.clear()
    posture = resolve("AGENTED_ENV") or "development"
    if strict and posture != "production":
        strict = False

    missing: list[str] = []
    warnings: list[str] = []
    for spec in REQUIRED_VARS:
        if spec["name"] == "AGENTED_ENV":
            if not resolve("AGENTED_ENV"):
                warnings.append("AGENTED_ENV unset — defaulting to development")
            continue
        if not resolve(spec["name"]):
            if strict:
                missing.append(spec["name"])
            else:
                warnings.append(f"{spec['name']} unset (ok in dev, required in prod)")
    warnings.extend(_PERMISSION_WARNINGS)
    return (len(missing) == 0, missing, warnings)


def main(argv: Optional[list[str]] = None) -> int:
    ok, missing, warnings = validate(strict=True)
    if missing:
        print("ERROR: missing required environment variables:", file=sys.stderr)
        for name in missing:
            spec = next(s for s in REQUIRED_VARS if s["name"] == name)
            print(f"  {name} — {spec['description']}", file=sys.stderr)
            print(f"    example: {spec['example']}", file=sys.stderr)
        print("", file=sys.stderr)
        print("See docs/deploy/RUNBOOK.md for setup.", file=sys.stderr)
        return 1
    for w in warnings:
        print(f"WARNING: {w}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
