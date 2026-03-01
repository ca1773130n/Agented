"""Backend detection service for CLI backend discovery and capability flags."""

import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional, Tuple


@dataclass
class BackendCapabilities:
    """Capability flags for a detected CLI backend."""

    supports_json_output: bool = False
    supports_token_usage: bool = False
    supports_streaming: bool = True
    supports_non_interactive: bool = False
    json_output_flag: Optional[str] = None
    non_interactive_flag: Optional[str] = None


BACKEND_CAPABILITIES = {
    "claude": BackendCapabilities(
        supports_json_output=True,
        supports_token_usage=True,
        supports_streaming=True,
        supports_non_interactive=True,
        json_output_flag="--output-format json",
        non_interactive_flag="-p",
    ),
    "opencode": BackendCapabilities(
        supports_json_output=True,
        supports_token_usage=True,
        supports_streaming=True,
        supports_non_interactive=True,
        json_output_flag="--format json",
        non_interactive_flag="run",
    ),
    "gemini": BackendCapabilities(
        supports_json_output=True,
        supports_token_usage=True,
        supports_streaming=True,
        supports_non_interactive=True,
        json_output_flag="--output-format json",
        non_interactive_flag="-p",
    ),
    "codex": BackendCapabilities(
        supports_json_output=True,
        supports_token_usage=True,
        supports_streaming=True,
        supports_non_interactive=True,
        json_output_flag="--json",
        non_interactive_flag="exec",
    ),
}


# Well-known install locations per backend (checked when not on PATH)
_FALLBACK_PATHS = {
    "opencode": [Path.home() / ".opencode" / "bin" / "opencode"],
    "claude": [Path.home() / ".local" / "bin" / "claude"],
}


def detect_backend(backend_type: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """Detect if a CLI backend is installed.

    Uses shutil.which() for cross-platform PATH lookup, falling back to
    well-known install locations, then subprocess.run() with --version
    for version extraction.

    Returns: (is_installed, version, cli_path)
    """
    cli_path = shutil.which(backend_type)
    if not cli_path:
        for fallback in _FALLBACK_PATHS.get(backend_type, []):
            if fallback.is_file() and os.access(fallback, os.X_OK):
                cli_path = str(fallback)
                break
    if not cli_path:
        return False, None, None

    try:
        result = subprocess.run(
            [cli_path, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        raw = result.stdout.strip() or result.stderr.strip()
        version = raw.split("\n")[0] if raw else "unknown"
        return True, version, cli_path
    except subprocess.TimeoutExpired:
        return True, "unknown (timeout)", cli_path
    except Exception:
        return True, "unknown", cli_path


def get_capabilities(backend_type: str) -> Optional[BackendCapabilities]:
    """Get capability flags for a backend type.

    Returns BackendCapabilities instance or None for unknown backends.
    """
    return BACKEND_CAPABILITIES.get(backend_type)


def get_all_backends_status() -> list:
    """Get detection status for all 4 supported backends.

    Returns a list of dicts with type, installed, version, cli_path, and capabilities.
    """
    results = []
    for backend_type in BACKEND_CAPABILITIES:
        installed, version, cli_path = detect_backend(backend_type)
        caps = BACKEND_CAPABILITIES[backend_type]
        results.append(
            {
                "type": backend_type,
                "installed": installed,
                "version": version,
                "cli_path": cli_path,
                "capabilities": asdict(caps),
            }
        )
    return results
