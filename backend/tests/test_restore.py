"""v0.5.15: restore script tests."""
import sqlite3
import time
from pathlib import Path

import pytest


def _seed_db(path: Path, marker: str) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE IF NOT EXISTS m (k TEXT)")
    conn.execute("INSERT INTO m (k) VALUES (?)", (marker,))
    conn.commit()
    conn.close()


def _read_marker(path: Path) -> str:
    conn = sqlite3.connect(str(path))
    row = conn.execute("SELECT k FROM m LIMIT 1").fetchone()
    conn.close()
    return row[0] if row else ""


class TestListSnapshots:
    def test_returns_newest_first(self, tmp_path):
        from scripts.restore import list_snapshots
        # Create three files with controlled mtimes.
        old = tmp_path / "agented-2025-01-01T00-00-00Z.db"
        mid = tmp_path / "agented-2025-06-01T00-00-00Z.db"
        new = tmp_path / "agented-2026-05-04T00-00-00Z.db"
        for p in (old, mid, new):
            p.write_text("x")
        import os
        now = time.time()
        os.utime(old, (now - 100 * 86400, now - 100 * 86400))
        os.utime(mid, (now - 50 * 86400, now - 50 * 86400))
        os.utime(new, (now, now))
        result = list_snapshots(tmp_path, "agented")
        assert [p.name for p in result] == [new.name, mid.name, old.name]

    def test_filters_by_label(self, tmp_path):
        from scripts.restore import list_snapshots
        (tmp_path / "agented-x.db").write_text("a")
        (tmp_path / "ai_accounts-y.db").write_text("b")
        result = list_snapshots(tmp_path, "agented")
        assert len(result) == 1
        assert result[0].name == "agented-x.db"


class TestRestoreOne:
    def test_overwrites_target_with_snapshot_contents(self, tmp_path):
        from scripts.restore import restore_one
        snap = tmp_path / "agented-snap.db"
        target = tmp_path / "agented.db"
        _seed_db(snap, "from-snapshot")
        _seed_db(target, "current-state")
        safety = restore_one("agented", snap, target,
                             safety_dir=tmp_path / "safety",
                             take_safety_snapshot=True)
        assert _read_marker(target) == "from-snapshot"
        assert safety is not None
        assert safety.exists()
        assert _read_marker(safety) == "current-state"

    def test_no_safety_snapshot_when_disabled(self, tmp_path):
        from scripts.restore import restore_one
        snap = tmp_path / "agented-snap.db"
        target = tmp_path / "agented.db"
        _seed_db(snap, "from-snapshot")
        _seed_db(target, "current-state")
        safety = restore_one("agented", snap, target,
                             safety_dir=tmp_path / "safety",
                             take_safety_snapshot=False)
        assert safety is None
        assert _read_marker(target) == "from-snapshot"

    def test_clears_stale_wal_shm(self, tmp_path):
        from scripts.restore import restore_one
        snap = tmp_path / "agented-snap.db"
        target = tmp_path / "agented.db"
        _seed_db(snap, "x")
        _seed_db(target, "y")
        wal = target.with_suffix(target.suffix + "-wal")
        shm = target.with_suffix(target.suffix + "-shm")
        wal.write_text("stale-wal")
        shm.write_text("stale-shm")
        restore_one("agented", snap, target,
                    safety_dir=tmp_path / "safety",
                    take_safety_snapshot=False)
        assert not wal.exists()
        assert not shm.exists()


class TestLiveDBGuard:
    def test_main_refuses_when_wal_is_recent(self, tmp_path, monkeypatch, capsys):
        from scripts import restore
        target = tmp_path / "agented.db"
        _seed_db(target, "live")
        wal = target.with_suffix(target.suffix + "-wal")
        wal.write_text("live")  # mtime = now → within 60s guard
        snap = tmp_path / "agented-snap.db"
        _seed_db(snap, "from-snap")
        monkeypatch.setattr(restore, "_default_agented_db_path", lambda: target)
        rc = restore.main([
            "--target", "agented",
            "--snapshot", str(snap),
            "--yes",
            "--no-safety-snapshot",
        ])
        assert rc == 2
        # Target was NOT overwritten.
        assert _read_marker(target) == "live"

    def test_force_flag_overrides_live_guard(self, tmp_path, monkeypatch):
        """Codex round-1 Issue 4: --force lets the operator override
        when they've manually verified the service is stopped."""
        from scripts import restore
        target = tmp_path / "agented.db"
        _seed_db(target, "live")
        wal = target.with_suffix(target.suffix + "-wal")
        wal.write_text("live")  # fresh WAL → guard would normally fire
        snap = tmp_path / "agented-snap.db"
        _seed_db(snap, "from-snap")
        monkeypatch.setattr(restore, "_default_agented_db_path", lambda: target)
        rc = restore.main([
            "--target", "agented",
            "--snapshot", str(snap),
            "--yes",
            "--no-safety-snapshot",
            "--force",
        ])
        assert rc == 0
        assert _read_marker(target) == "from-snap"
