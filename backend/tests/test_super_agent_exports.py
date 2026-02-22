"""Tests for SuperAgent export and import API endpoints."""

import json
import os
import tempfile
import zipfile

import pytest

from app.database import add_super_agent, add_super_agent_document, get_super_agent


@pytest.fixture
def sample_super_agent(isolated_db):
    """Create a SuperAgent with 2 identity documents for testing."""
    sa_id = add_super_agent(
        name="Test Agent",
        description="A test super agent",
        backend_type="claude",
        max_concurrent_sessions=5,
    )
    add_super_agent_document(sa_id, "SOUL", "Soul Doc", "You are a helpful agent.")
    add_super_agent_document(sa_id, "IDENTITY", "Identity Doc", "Name: Test Agent\nRole: Assistant")
    return sa_id


@pytest.fixture
def sample_agent_no_docs(isolated_db):
    """Create a SuperAgent with no documents."""
    sa_id = add_super_agent(
        name="Empty Agent",
        description="An agent with no docs",
        backend_type="claude",
    )
    return sa_id


class TestExportDirectory:
    def test_export_directory(self, client, sample_super_agent):
        """Export as directory creates manifest.json, config.json, and .md files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            resp = client.post(
                "/admin/super-agent-exports/export",
                json={
                    "super_agent_id": sample_super_agent,
                    "export_format": "directory",
                    "output_dir": tmpdir,
                },
            )
            assert resp.status_code == 200
            body = resp.get_json()
            assert body["format"] == "directory"
            assert body["documents"] == 2

            export_path = body["export_path"]
            assert os.path.isfile(os.path.join(export_path, "manifest.json"))
            assert os.path.isfile(os.path.join(export_path, "config.json"))
            assert os.path.isfile(os.path.join(export_path, "SOUL.md"))
            assert os.path.isfile(os.path.join(export_path, "IDENTITY.md"))


class TestExportZip:
    def test_export_zip(self, client, sample_super_agent):
        """Export as ZIP creates archive containing expected files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            resp = client.post(
                "/admin/super-agent-exports/export",
                json={
                    "super_agent_id": sample_super_agent,
                    "export_format": "zip",
                    "output_dir": tmpdir,
                },
            )
            assert resp.status_code == 200
            body = resp.get_json()
            assert body["format"] == "zip"

            zip_path = body["export_path"]
            assert os.path.isfile(zip_path)

            with zipfile.ZipFile(zip_path, "r") as zf:
                names = zf.namelist()
                assert any("manifest.json" in n for n in names)
                assert any("config.json" in n for n in names)
                assert any("SOUL.md" in n for n in names)
                assert any("IDENTITY.md" in n for n in names)


class TestExportNonexistent:
    def test_export_nonexistent_agent(self, client):
        """Export nonexistent SuperAgent ID returns 404."""
        resp = client.post(
            "/admin/super-agent-exports/export",
            json={
                "super_agent_id": "super-nonexistent",
                "export_format": "directory",
            },
        )
        assert resp.status_code == 404
        assert "not found" in resp.get_json()["error"].lower()


class TestExportDefaultFormat:
    def test_export_default_format_is_zip(self, client, sample_super_agent):
        """Export without format specified defaults to ZIP."""
        with tempfile.TemporaryDirectory() as tmpdir:
            resp = client.post(
                "/admin/super-agent-exports/export",
                json={
                    "super_agent_id": sample_super_agent,
                    "output_dir": tmpdir,
                },
            )
            assert resp.status_code == 200
            body = resp.get_json()
            assert body["format"] == "zip"


class TestManifestContent:
    def test_manifest_content(self, client, sample_super_agent):
        """Verify manifest.json has correct name, type, and dependencies."""
        with tempfile.TemporaryDirectory() as tmpdir:
            resp = client.post(
                "/admin/super-agent-exports/export",
                json={
                    "super_agent_id": sample_super_agent,
                    "export_format": "directory",
                    "output_dir": tmpdir,
                },
            )
            assert resp.status_code == 200
            export_path = resp.get_json()["export_path"]

            with open(os.path.join(export_path, "manifest.json")) as f:
                manifest = json.load(f)

            assert manifest["name"] == "Test Agent"
            assert manifest["version"] == "1.0.0"
            assert manifest["type"] == "super_agent"
            assert manifest["dependencies"]["backends"] == ["claude"]
            assert "SOUL" in manifest["documents"]
            assert "IDENTITY" in manifest["documents"]


class TestConfigContent:
    def test_config_content(self, client, sample_super_agent):
        """Verify config.json has correct fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            resp = client.post(
                "/admin/super-agent-exports/export",
                json={
                    "super_agent_id": sample_super_agent,
                    "export_format": "directory",
                    "output_dir": tmpdir,
                },
            )
            assert resp.status_code == 200
            export_path = resp.get_json()["export_path"]

            with open(os.path.join(export_path, "config.json")) as f:
                config = json.load(f)

            assert config["name"] == "Test Agent"
            assert config["description"] == "A test super agent"
            assert config["backend_type"] == "claude"
            assert config["max_concurrent_sessions"] == 5


class TestImportFromDirectory:
    def test_import_from_directory(self, client, sample_super_agent):
        """Export then import from directory creates new agent with documents."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Export first
            export_resp = client.post(
                "/admin/super-agent-exports/export",
                json={
                    "super_agent_id": sample_super_agent,
                    "export_format": "directory",
                    "output_dir": tmpdir,
                },
            )
            assert export_resp.status_code == 200
            export_path = export_resp.get_json()["export_path"]

            # Import
            import_resp = client.post(
                "/admin/super-agent-exports/import",
                json={"source_path": export_path},
            )
            assert import_resp.status_code == 201
            body = import_resp.get_json()
            assert body["super_agent_id"].startswith("super-")
            assert body["documents_imported"] == 2
            # Name should be modified to avoid collision
            assert "imported" in body["name"]

            # Verify the imported agent exists
            sa = get_super_agent(body["super_agent_id"])
            assert sa is not None
            assert sa["backend_type"] == "claude"


class TestImportFromZip:
    def test_import_from_zip(self, client, sample_super_agent):
        """Export as ZIP then import from ZIP verifies round-trip data integrity."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Export as ZIP
            export_resp = client.post(
                "/admin/super-agent-exports/export",
                json={
                    "super_agent_id": sample_super_agent,
                    "export_format": "zip",
                    "output_dir": tmpdir,
                },
            )
            assert export_resp.status_code == 200
            zip_path = export_resp.get_json()["export_path"]

            # Import from ZIP
            import_resp = client.post(
                "/admin/super-agent-exports/import",
                json={"source_path": zip_path},
            )
            assert import_resp.status_code == 201
            body = import_resp.get_json()
            assert body["super_agent_id"].startswith("super-")
            assert body["documents_imported"] == 2

            # Verify round-trip integrity
            sa = get_super_agent(body["super_agent_id"])
            assert sa is not None
            assert sa["description"] == "A test super agent"
            assert sa["backend_type"] == "claude"
            assert sa["max_concurrent_sessions"] == 5


class TestImportValidationMissingBackend:
    def test_import_validation_missing_backend(self, client):
        """Import with manifest declaring non-existent backend returns validation error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a fake package with a non-existent backend
            pkg_dir = os.path.join(tmpdir, "super_agents", "fake-agent")
            os.makedirs(pkg_dir)

            manifest = {
                "name": "Fake Agent",
                "version": "1.0.0",
                "type": "super_agent",
                "dependencies": {
                    "backends": ["nonexistent_backend"],
                    "skills": [],
                    "mcp_servers": [],
                },
                "documents": [],
            }
            with open(os.path.join(pkg_dir, "manifest.json"), "w") as f:
                json.dump(manifest, f)

            config = {
                "name": "Fake Agent",
                "description": "Test",
                "backend_type": "nonexistent_backend",
                "preferred_model": None,
                "max_concurrent_sessions": 10,
                "config_json": None,
            }
            with open(os.path.join(pkg_dir, "config.json"), "w") as f:
                json.dump(config, f)

            import_resp = client.post(
                "/admin/super-agent-exports/import",
                json={"source_path": pkg_dir},
            )
            assert import_resp.status_code == 400
            body = import_resp.get_json()
            assert body["error"] == "Validation failed"
            assert any("nonexistent_backend" in e for e in body["errors"])


class TestImportMissingManifest:
    def test_import_missing_manifest(self, client):
        """Import from directory without manifest.json returns error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            resp = client.post(
                "/admin/super-agent-exports/import",
                json={"source_path": tmpdir},
            )
            assert resp.status_code == 400
            assert "manifest.json" in resp.get_json()["error"].lower()


class TestSlugifySpecialCharacters:
    def test_slugify_special_characters(self, client):
        """Export agent with special chars in name produces safe path."""
        sa_id = add_super_agent(
            name="My Agent!!! @#$% v2.0",
            description="Special chars test",
            backend_type="claude",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            resp = client.post(
                "/admin/super-agent-exports/export",
                json={
                    "super_agent_id": sa_id,
                    "export_format": "directory",
                    "output_dir": tmpdir,
                },
            )
            assert resp.status_code == 200
            body = resp.get_json()
            # Slugified name should be safe
            assert ".." not in body["name"]
            assert "/" not in body["name"]
            assert body["name"] == "my-agent-v2-0"


class TestExportNoDocuments:
    def test_export_no_documents(self, client, sample_agent_no_docs):
        """Export agent with 0 documents produces empty documents list in manifest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            resp = client.post(
                "/admin/super-agent-exports/export",
                json={
                    "super_agent_id": sample_agent_no_docs,
                    "export_format": "directory",
                    "output_dir": tmpdir,
                },
            )
            assert resp.status_code == 200
            body = resp.get_json()
            assert body["documents"] == 0

            export_path = body["export_path"]
            with open(os.path.join(export_path, "manifest.json")) as f:
                manifest = json.load(f)
            assert manifest["documents"] == []
