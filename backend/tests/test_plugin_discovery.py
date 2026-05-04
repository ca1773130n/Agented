"""v0.6.4: plugin discovery service tests."""
import json
from pathlib import Path

import pytest


@pytest.fixture
def plugin_root(tmp_path, monkeypatch):
    """Set AGENTED_PLUGIN_PATHS to a tmp dir + return it."""
    monkeypatch.setenv("AGENTED_PLUGIN_PATHS", str(tmp_path))
    # Disable the home-dir fallbacks so the test sees only what we
    # planted in tmp_path.
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "_unset_home"))
    return tmp_path


def _seed_directory_plugin(root: Path, name: str, manifest: dict) -> Path:
    plugin_dir = root / name
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "plugin.json").write_text(json.dumps(manifest))
    return plugin_dir


def _seed_single_file_plugin(root: Path, name: str) -> Path:
    p = root / f"{name}.plugin.py"
    p.write_text("# noop\n")
    return p


class TestDiscover:
    def test_returns_empty_when_no_plugins_present(self, plugin_root):
        from app.services.plugin_discovery_service import discover
        assert discover() == []

    def test_finds_directory_plugin(self, plugin_root):
        from app.services.plugin_discovery_service import discover
        _seed_directory_plugin(
            plugin_root, "my-plugin",
            {"name": "my-plugin", "version": "1.0.0",
             "description": "test", "type": "skill-bundle"},
        )
        result = discover()
        assert len(result) == 1
        assert result[0]["name"] == "my-plugin"
        assert result[0]["version"] == "1.0.0"
        assert result[0]["type"] == "skill-bundle"
        assert result[0]["source"] == "directory"

    def test_finds_single_file_plugin(self, plugin_root):
        from app.services.plugin_discovery_service import discover
        _seed_single_file_plugin(plugin_root, "shimmer")
        result = discover()
        assert len(result) == 1
        assert result[0]["name"] == "shimmer"
        assert result[0]["type"] == "single-file-plugin"
        assert result[0]["source"] == "single-file"

    def test_skips_dotfiles_and_unmarked_dirs(self, plugin_root):
        from app.services.plugin_discovery_service import discover
        # A directory without plugin.json should not be picked up.
        (plugin_root / "not-a-plugin").mkdir()
        (plugin_root / "not-a-plugin" / "README.md").write_text("just docs")
        # A dotfile directory.
        (plugin_root / ".hidden-plugin").mkdir()
        (plugin_root / ".hidden-plugin" / "plugin.json").write_text("{}")
        # A real plugin.
        _seed_directory_plugin(plugin_root, "real", {"name": "real"})
        result = discover()
        names = [p["name"] for p in result]
        assert names == ["real"]

    def test_stable_sort(self, plugin_root):
        from app.services.plugin_discovery_service import discover
        _seed_directory_plugin(plugin_root, "zeta", {"name": "zeta"})
        _seed_directory_plugin(plugin_root, "alpha", {"name": "alpha"})
        _seed_single_file_plugin(plugin_root, "mid")
        names = [p["name"] for p in discover()]
        assert names == ["alpha", "mid", "zeta"]

    def test_corrupt_manifest_is_silently_skipped(self, plugin_root):
        from app.services.plugin_discovery_service import discover
        bad = plugin_root / "broken"
        bad.mkdir()
        (bad / "plugin.json").write_text("{not valid json")
        # Corrupt manifest → manifest read returns {} but
        # _describe_directory_plugin still emits an entry with the
        # directory's name and `type` defaulting to 'directory-plugin'.
        result = discover()
        assert len(result) == 1
        assert result[0]["name"] == "broken"
        assert result[0]["type"] == "directory-plugin"


class TestEnvVarPath:
    def test_AGENTED_PLUGIN_PATHS_is_colon_separated(self, tmp_path, monkeypatch):
        from app.services.plugin_discovery_service import discover
        a = tmp_path / "first"
        b = tmp_path / "second"
        a.mkdir()
        b.mkdir()
        _seed_directory_plugin(a, "p-a", {"name": "p-a"})
        _seed_directory_plugin(b, "p-b", {"name": "p-b"})
        monkeypatch.setenv("AGENTED_PLUGIN_PATHS", f"{a}:{b}")
        # Disable home fallbacks.
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "_unset"))
        names = [p["name"] for p in discover()]
        assert "p-a" in names
        assert "p-b" in names
