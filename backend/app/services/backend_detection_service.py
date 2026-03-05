"""Backend detection service for CLI backend discovery and capability flags."""

import logging
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


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

    # Strip nesting-detection vars so CLIs like claude don't refuse to start
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}

    try:
        result = subprocess.run(
            [cli_path, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            env=env,
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


CLI_INSTALL_COMMANDS: dict[str, list[str]] = {
    "claude": ["npm", "install", "-g", "@anthropic-ai/claude-code"],
    "codex": ["npm", "install", "-g", "@openai/codex"],
    "gemini": ["npm", "install", "-g", "@google/gemini-cli"],
    "opencode": ["bash", "-c", "curl -fsSL https://opencode.dev/install | bash"],
}


def install_cli(backend_type: str, timeout: int = 180) -> dict:
    """Install a CLI backend and verify installation.

    Returns: {success: bool, version: str|None, error: str|None}
    """
    cmd = CLI_INSTALL_COMMANDS.get(backend_type)
    if not cmd:
        return {"success": False, "version": None, "error": f"Unknown backend type: {backend_type}"}

    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        if result.returncode != 0:
            error = (
                result.stderr.strip() or result.stdout.strip() or f"Exit code {result.returncode}"
            )
            return {"success": False, "version": None, "error": error}
    except subprocess.TimeoutExpired:
        return {"success": False, "version": None, "error": f"Install timed out after {timeout}s"}
    except FileNotFoundError as e:
        return {"success": False, "version": None, "error": f"Command not found: {e}"}
    except Exception as e:
        return {"success": False, "version": None, "error": str(e)}

    # Verify installation
    installed, version, _ = detect_backend(backend_type)
    if installed:
        logger.info("Installed %s CLI: %s", backend_type, version)
        return {"success": True, "version": version, "error": None}
    return {
        "success": False,
        "version": None,
        "error": "Install succeeded but CLI not found on PATH",
    }


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
