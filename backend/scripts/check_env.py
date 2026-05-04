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
        "name": "AGENTED_ENV",
        "description": "Deployment posture. Must be 'production' for prod deploys.",
        "example": "production",
        "secret": False,
    },
]

OPTIONAL_VARS: list[dict] = [
    {
        "name": "LOG_LEVEL",
        "description": "Gunicorn log level.",
        "example": "info",
        "default": "info",
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


def _resolve_file_redirect(name: str) -> Optional[str]:
    """If `<NAME>_FILE` is set in env, read the file and return its
    stripped contents. Used for Docker-secrets / mounted secret files."""
    file_var = f"{name}_FILE"
    path_str = os.environ.get(file_var, "").strip()
    if not path_str:
        return None
    path = Path(path_str)
    if not path.is_file():
        return None
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
