"""v0.6.4: filesystem plugin discovery.

Operators install plugins by dropping them into one of the known
plugin directories. The DB-backed plugin CRUD only sees plugins
the operator has explicitly registered. This service walks the
filesystem to surface "what's actually installed" so the UI can
show a complete picture.

Search order (highest precedence first):
  1. AGENTED_PLUGIN_PATHS env var (colon-separated, like $PATH)
  2. ~/.claude/plugins/
  3. ~/.config/superpowers/plugins/

Each plugin is identified by either:
  - a top-level directory containing a `plugin.json` manifest, OR
  - a top-level `*.plugin.py` single-file plugin.

Manifest format (best effort):
  {
    "name": "my-plugin",
    "version": "1.0.0",
    "description": "What this does",
    "type": "harness-extension" | "skill-bundle" | "command-set"
  }
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _candidate_dirs() -> list[Path]:
    """Resolve the search path. Returns absolute Path objects in
    precedence order. Non-existent paths are skipped."""
    explicit = os.environ.get("AGENTED_PLUGIN_PATHS", "")
    paths: list[Path] = []
    if explicit:
        for raw in explicit.split(":"):
            raw = raw.strip()
            if raw:
                paths.append(Path(raw).expanduser())
    home = Path.home()
    paths.append(home / ".claude" / "plugins")
    paths.append(home / ".config" / "superpowers" / "plugins")
    return [p for p in paths if p.is_dir()]


def _read_manifest(manifest_path: Path) -> dict:
    """Best-effort manifest read. Returns {} on any error."""
    try:
        with manifest_path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return {}
        return data
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("plugin_discovery: bad manifest %s: %s", manifest_path, exc)
        return {}


def _describe_directory_plugin(plugin_dir: Path) -> Optional[dict]:
    manifest = plugin_dir / "plugin.json"
    if not manifest.is_file():
        return None
    data = _read_manifest(manifest)
    return {
        "name": data.get("name") or plugin_dir.name,
        "version": data.get("version"),
        "description": data.get("description"),
        "type": data.get("type", "directory-plugin"),
        "path": str(plugin_dir),
        "source": "directory",
    }


def _describe_single_file_plugin(plugin_file: Path) -> dict:
    name = plugin_file.stem
    if name.endswith(".plugin"):
        name = name[: -len(".plugin")]
    return {
        "name": name,
        "version": None,
        "description": None,
        "type": "single-file-plugin",
        "path": str(plugin_file),
        "source": "single-file",
    }


def discover() -> list[dict]:
    """Walk the configured plugin directories and return every plugin
    found. Each entry has a stable schema (see module docstring).

    Stable order: by name + path so callers don't see jitter.
    """
    found: list[dict] = []
    for base in _candidate_dirs():
        try:
            entries = sorted(base.iterdir(), key=lambda p: p.name.lower())
        except OSError as exc:
            logger.debug("plugin_discovery: cannot read %s: %s", base, exc)
            continue
        for entry in entries:
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                meta = _describe_directory_plugin(entry)
                if meta is not None:
                    found.append(meta)
            elif entry.is_file() and entry.name.endswith(".plugin.py"):
                found.append(_describe_single_file_plugin(entry))

    # Stable sort by (name, path) so the same input → same output.
    found.sort(key=lambda d: (d["name"].lower(), d["path"]))
    return found
