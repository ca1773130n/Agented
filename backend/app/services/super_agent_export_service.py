"""SuperAgent export and import service for packaging SuperAgents.

Supports two export formats:
- Directory: creates a directory structure with manifest.json, config.json, and identity doc .md files
- ZIP: creates a ZIP archive containing the directory structure
"""

import json
import logging
import os
import re
import tempfile
import zipfile
from pathlib import Path

from app.database import (
    add_super_agent,
    add_super_agent_document,
    get_all_backends,
    get_all_super_agents,
    get_super_agent,
    get_super_agent_documents,
)

log = logging.getLogger(__name__)


class SuperAgentExportService:
    """Service for exporting and importing SuperAgents as portable packages."""

    # =========================================================================
    # Export Methods
    # =========================================================================

    @staticmethod
    def _slugify(name: str) -> str:
        """Convert a name to kebab-case suitable for directory names.

        Prevents path traversal by stripping all non-alphanumeric characters.
        """
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        return slug or "unnamed"

    @staticmethod
    def export_super_agent(super_agent_id: str, output_dir: str) -> dict:
        """Export a SuperAgent as a directory structure.

        Creates: {output_dir}/super_agents/{slug}/manifest.json, config.json, {DOC_TYPE}.md files.

        Args:
            super_agent_id: The SuperAgent ID to export.
            output_dir: Base directory to write the export into.

        Returns:
            Summary dict with export_path, name, documents count, and format.

        Raises:
            ValueError: If SuperAgent not found.
        """
        sa = get_super_agent(super_agent_id)
        if not sa:
            raise ValueError(f"SuperAgent not found: {super_agent_id}")

        documents = get_super_agent_documents(super_agent_id)
        slug = SuperAgentExportService._slugify(sa["name"])
        base_dir = Path(output_dir) / "super_agents" / slug

        # Write identity documents as {DOC_TYPE}.md files
        for doc in documents:
            _write_text(base_dir / f"{doc['doc_type']}.md", doc["content"])

        # Write config.json
        config = {
            "name": sa["name"],
            "description": sa["description"],
            "backend_type": sa["backend_type"],
            "preferred_model": sa["preferred_model"],
            "max_concurrent_sessions": sa["max_concurrent_sessions"],
            "config_json": sa["config_json"],
        }
        _write_json(base_dir / "config.json", config)

        # Write manifest.json
        doc_types = [doc["doc_type"] for doc in documents]
        manifest = {
            "name": sa["name"],
            "version": "1.0.0",
            "type": "super_agent",
            "dependencies": {
                "backends": [sa["backend_type"]],
                "skills": [],
                "mcp_servers": [],
            },
            "documents": doc_types,
        }
        _write_json(base_dir / "manifest.json", manifest)

        return {
            "export_path": str(base_dir),
            "name": slug,
            "documents": len(documents),
            "format": "directory",
        }

    @staticmethod
    def export_as_zip(super_agent_id: str, output_path: str) -> dict:
        """Export a SuperAgent as a ZIP archive.

        Args:
            super_agent_id: The SuperAgent ID to export.
            output_path: File path for the output ZIP archive.

        Returns:
            Summary dict with export_path, name, and format.

        Raises:
            ValueError: If SuperAgent not found.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            result = SuperAgentExportService.export_super_agent(super_agent_id, tmpdir)
            export_dir = result["export_path"]

            # Walk the export directory and add all files to ZIP
            with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(export_dir):
                    for fname in files:
                        fpath = os.path.join(root, fname)
                        # Archive path relative to parent of super_agents/
                        arcname = os.path.relpath(fpath, tmpdir)
                        zf.write(fpath, arcname)

            return {
                "export_path": output_path,
                "name": result["name"],
                "documents": result["documents"],
                "format": "zip",
            }

    # =========================================================================
    # Import Methods
    # =========================================================================

    @staticmethod
    def validate_manifest(manifest: dict) -> dict:
        """Validate a SuperAgent package manifest.

        Checks required keys, type field, and dependency availability.

        Args:
            manifest: Parsed manifest.json dict.

        Returns:
            Dict with valid (bool), errors (list), and warnings (list).
        """
        errors = []
        warnings = []

        # Check required keys
        for key in ("name", "type", "dependencies"):
            if key not in manifest:
                errors.append(f"Missing required key: '{key}'")

        if errors:
            return {"valid": False, "errors": errors, "warnings": warnings}

        # Check type
        if manifest["type"] != "super_agent":
            errors.append(f"Invalid type: '{manifest['type']}' (expected 'super_agent')")

        # Validate backend dependencies
        deps = manifest.get("dependencies", {})
        required_backends = deps.get("backends", [])
        if required_backends:
            installed_backends = get_all_backends()
            installed_types = {b.get("backend_type", b.get("type", "")) for b in installed_backends}
            for backend in required_backends:
                if backend not in installed_types:
                    errors.append(f"Required backend '{backend}' not installed")

        # Check optional skills
        for skill in deps.get("skills", []):
            warnings.append(f"Optional skill '{skill}' availability not checked")

        return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}

    @staticmethod
    def import_from_directory(source_path: str) -> dict:
        """Import a SuperAgent from an export directory.

        Reads manifest.json, validates dependencies, reads config.json,
        creates a new SuperAgent with identity documents.

        Args:
            source_path: Path to the directory containing manifest.json and config.json.

        Returns:
            Dict with super_agent_id, name, documents_imported, and warnings.

        Raises:
            ValueError: If manifest.json or config.json is missing.
        """
        source = Path(source_path)

        # Read and validate manifest
        manifest_path = source / "manifest.json"
        if not manifest_path.exists():
            raise ValueError(f"manifest.json not found in {source_path}")

        manifest = _read_json(manifest_path)
        validation = SuperAgentExportService.validate_manifest(manifest)
        if not validation["valid"]:
            return {
                "error": "Validation failed",
                "errors": validation["errors"],
                "warnings": validation["warnings"],
            }

        # Read config
        config_path = source / "config.json"
        if not config_path.exists():
            raise ValueError(f"config.json not found in {source_path}")

        config = _read_json(config_path)

        # Ensure unique name (append "-imported" if collision)
        existing = get_all_super_agents()
        existing_names = {sa["name"] for sa in existing}
        name = config["name"]
        if name in existing_names:
            name = f"{name}-imported"
            # Keep appending suffix if still collides
            counter = 2
            while name in existing_names:
                name = f"{config['name']}-imported-{counter}"
                counter += 1

        # Create SuperAgent
        new_id = add_super_agent(
            name=name,
            description=config.get("description"),
            backend_type=config.get("backend_type", "claude"),
            preferred_model=config.get("preferred_model"),
            max_concurrent_sessions=config.get("max_concurrent_sessions", 10),
            config_json=config.get("config_json"),
        )

        if not new_id:
            raise ValueError("Failed to create SuperAgent during import")

        # Import identity documents
        doc_types = manifest.get("documents", [])
        docs_imported = 0
        for doc_type in doc_types:
            doc_path = source / f"{doc_type}.md"
            if doc_path.exists():
                content = doc_path.read_text(encoding="utf-8")
                result = add_super_agent_document(new_id, doc_type, doc_type, content)
                if result is not None:
                    docs_imported += 1
                else:
                    log.warning("Failed to import document %s for %s", doc_type, new_id)
            else:
                log.warning("Document file %s.md not found in %s", doc_type, source_path)

        return {
            "super_agent_id": new_id,
            "name": name,
            "documents_imported": docs_imported,
            "warnings": validation["warnings"],
        }

    @staticmethod
    def import_from_zip(zip_path: str) -> dict:
        """Import a SuperAgent from a ZIP archive.

        Extracts ZIP to temp directory, finds the super_agents/{name}/ directory,
        and calls import_from_directory.

        Args:
            zip_path: Path to the ZIP archive.

        Returns:
            Result dict from import_from_directory.

        Raises:
            ValueError: If ZIP does not contain expected structure.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(tmpdir)

            # Find the super_agents/{name}/ directory
            sa_dir = Path(tmpdir) / "super_agents"
            if not sa_dir.exists():
                raise ValueError("ZIP does not contain a 'super_agents/' directory")

            # Find first subdirectory under super_agents/
            subdirs = [d for d in sa_dir.iterdir() if d.is_dir()]
            if not subdirs:
                raise ValueError("No SuperAgent package found in ZIP")

            return SuperAgentExportService.import_from_directory(str(subdirs[0]))


# =============================================================================
# File I/O helpers
# =============================================================================


def _write_text(path: Path, content: str):
    """Write text content to a file, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_json(path: Path, data: dict):
    """Write a dict as formatted JSON to a file."""
    _write_text(path, json.dumps(data, indent=2) + "\n")


def _read_json(path: Path) -> dict:
    """Read and parse a JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))
