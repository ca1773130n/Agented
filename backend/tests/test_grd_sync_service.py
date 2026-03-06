"""Tests for GrdSyncService — SHA256 hashing, safe encoding, and sync logic."""

import datetime
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.grd_sync_service import GrdSyncService, _SafeEncoder, _sha256


class TestSha256:
    def test_deterministic(self):
        assert _sha256("hello") == _sha256("hello")

    def test_different_inputs(self):
        assert _sha256("hello") != _sha256("world")

    def test_empty_string(self):
        result = _sha256("")
        assert len(result) == 64  # SHA256 hex length

    def test_unicode(self):
        result = _sha256("héllo wörld")
        assert len(result) == 64


class TestSafeEncoder:
    def test_date_serialization(self):
        d = datetime.date(2025, 1, 15)
        result = json.dumps({"date": d}, cls=_SafeEncoder)
        assert "2025-01-15" in result

    def test_datetime_serialization(self):
        dt = datetime.datetime(2025, 1, 15, 10, 30, 0)
        result = json.dumps({"dt": dt}, cls=_SafeEncoder)
        assert "2025-01-15" in result

    def test_normal_types_passthrough(self):
        data = {"str": "hello", "num": 42, "list": [1, 2]}
        result = json.dumps(data, cls=_SafeEncoder)
        assert json.loads(result) == data

    def test_unsupported_type_raises(self):
        with pytest.raises(TypeError):
            json.dumps({"obj": object()}, cls=_SafeEncoder)


class TestSyncProject:
    def test_nonexistent_directory(self, isolated_db):
        result = GrdSyncService.sync_project("proj-test", "/nonexistent/path")
        assert result["synced"] == 0
        assert result["skipped"] == 0
        assert len(result["errors"]) == 1
        assert "not found" in result["errors"][0]

    def test_empty_planning_dir(self, isolated_db, tmp_path):
        planning_dir = tmp_path / ".planning"
        planning_dir.mkdir()
        result = GrdSyncService.sync_project("proj-test", str(planning_dir))
        assert result["synced"] == 0
        assert result["skipped"] == 0
        assert result["errors"] == []

    def test_roadmap_sync_error_recorded(self, isolated_db, tmp_path):
        """Errors during roadmap sync are recorded, not raised."""
        planning_dir = tmp_path / ".planning"
        planning_dir.mkdir()
        roadmap = planning_dir / "ROADMAP.md"
        roadmap.write_text("# Roadmap — v1.0.0\n\n## Phase 1: Init\nSetup stuff\n")

        with patch(
            "app.services.grd_sync_service.get_project_sync_state", return_value=None
        ), patch(
            "app.services.grd_sync_service.GrdSyncService._sync_roadmap",
            side_effect=ValueError("test error"),
        ):
            result = GrdSyncService.sync_project("proj-test", str(planning_dir))
            assert len(result["errors"]) == 1
            assert "test error" in result["errors"][0]

    def test_roadmap_incremental_skip(self, isolated_db, tmp_path):
        """Cached content hash match causes skip."""
        planning_dir = tmp_path / ".planning"
        planning_dir.mkdir()
        roadmap = planning_dir / "ROADMAP.md"
        content = "# Roadmap — v1.0.0\n\nSimple roadmap\n"
        roadmap.write_text(content)

        cached = {"content_hash": _sha256(content), "entity_id": "ms-123"}
        with patch(
            "app.services.grd_sync_service.get_project_sync_state", return_value=cached
        ), patch(
            "app.services.grd_sync_service.get_milestones_by_project", return_value=[]
        ):
            result = GrdSyncService.sync_project("proj-test2", str(planning_dir))
            assert result["skipped"] >= 1
            assert result["synced"] == 0
