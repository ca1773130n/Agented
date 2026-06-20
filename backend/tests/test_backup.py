"""v0.5.15: backup script tests."""

import json
import sqlite3
import threading
import time
from pathlib import Path

import pytest


def _seed_db(path: Path, rows: int = 5) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY, name TEXT)")
    conn.executemany("INSERT INTO t (name) VALUES (?)", [(f"r-{i}",) for i in range(rows)])
    conn.commit()
    conn.close()


class TestSnapshotOne:
    def test_produces_readable_copy(self, tmp_path):
        from scripts.backup import snapshot_one

        src = tmp_path / "src.db"
        _seed_db(src, rows=10)
        dest_dir = tmp_path / "snaps"
        result = snapshot_one("test", src, dest_dir, timestamp="2026-01-01T00-00-00Z")
        assert result.exists()
        assert result.name == "test-2026-01-01T00-00-00Z.db"
        # Snapshot is a real DB with the same data.
        conn = sqlite3.connect(str(result))
        cursor = conn.execute("SELECT COUNT(*) FROM t")
        assert cursor.fetchone()[0] == 10
        conn.close()

    def test_partial_file_cleaned_on_failure(self, tmp_path):
        from scripts.backup import snapshot_one

        # Source doesn't exist → sqlite3.connect creates it empty (so no
        # natural failure). Simulate failure by passing a directory as source.
        bad_src = tmp_path  # a directory, not a DB file
        dest_dir = tmp_path / "snaps"
        with pytest.raises((sqlite3.Error, sqlite3.OperationalError, OSError)):
            snapshot_one("test", bad_src, dest_dir, timestamp="2026-01-01T00-00-00Z")
        # The target file must not be left behind in a half-state.
        assert not (dest_dir / "test-2026-01-01T00-00-00Z.db").exists()


class TestApplyRetention:
    def test_removes_old_files(self, tmp_path):
        from scripts.backup import apply_retention

        old_file = tmp_path / "test-2025-01-01T00-00-00Z.db"
        old_file.write_text("x")
        # Backdate the file to 100 days ago.
        old_mtime = time.time() - 100 * 86400
        import os

        os.utime(old_file, (old_mtime, old_mtime))
        new_file = tmp_path / "test-2026-05-04T00-00-00Z.db"
        new_file.write_text("y")
        removed = apply_retention(tmp_path, retention_days=30, label="test")
        assert removed == 1
        assert not old_file.exists()
        assert new_file.exists()

    def test_zero_or_negative_retention_is_a_noop(self, tmp_path):
        from scripts.backup import apply_retention

        f = tmp_path / "test-x.db"
        f.write_text("x")
        assert apply_retention(tmp_path, retention_days=0, label="test") == 0
        assert apply_retention(tmp_path, retention_days=-1, label="test") == 0
        assert f.exists()

    def test_only_matches_label_prefix(self, tmp_path):
        from scripts.backup import apply_retention

        old = tmp_path / "agented-old.db"
        old.write_text("x")
        import os

        old_mtime = time.time() - 100 * 86400
        os.utime(old, (old_mtime, old_mtime))
        # Different-label file with same age — must NOT be removed.
        other = tmp_path / "ai_accounts-old.db"
        other.write_text("y")
        os.utime(other, (old_mtime, old_mtime))
        removed = apply_retention(tmp_path, retention_days=30, label="agented")
        assert removed == 1
        assert other.exists()

    def test_excludes_pre_restore_safety_snapshots(self, tmp_path):
        """Codex round-1 Issue 2: pre-restore files match the {label}-*.db
        glob. Retention must NOT delete them."""
        import os

        from scripts.backup import apply_retention

        normal = tmp_path / "agented-2025-01-01T00-00-00Z.db"
        safety = tmp_path / "agented-pre-restore-2025-01-01T00-00-00Z.db"
        normal.write_text("x")
        safety.write_text("y")
        old = time.time() - 100 * 86400
        os.utime(normal, (old, old))
        os.utime(safety, (old, old))
        removed = apply_retention(tmp_path, retention_days=30, label="agented")
        assert removed == 1
        assert not normal.exists()
        assert safety.exists(), "safety snapshot must survive normal retention"


class TestSyncRemote:
    def test_substitutes_file_token_and_returns_true_on_exit_0(self, tmp_path):
        from scripts.backup import sync_remote

        snap = tmp_path / "snap.db"
        snap.write_text("x")
        marker = tmp_path / "ran"
        cmd = f"echo {{file}} > {marker}"
        assert sync_remote(snap, cmd) is True
        # Note: shlex.quote may add quotes around the path on echo's
        # output; just check the path is present.
        assert str(snap) in marker.read_text()

    def test_returns_false_on_nonzero_exit(self, tmp_path):
        from scripts.backup import sync_remote

        snap = tmp_path / "snap.db"
        snap.write_text("x")
        assert sync_remote(snap, "false") is False

    def test_handles_path_with_spaces_via_shlex_quote(self, tmp_path):
        """Codex round-1 Issue 3: paths with spaces must work."""
        from scripts.backup import sync_remote

        spacey_dir = tmp_path / "with spaces"
        spacey_dir.mkdir()
        snap = spacey_dir / "snap.db"
        snap.write_text("x")
        marker = tmp_path / "ran"
        # Without shlex.quote, this would break because the path has a space.
        cmd = f"cat {{file}} > {marker}"
        assert sync_remote(snap, cmd) is True
        assert marker.read_text() == "x"


class TestCLI:
    def test_main_exits_0_on_full_run(self, tmp_path, monkeypatch, capsys):
        from scripts import backup

        # Stub the default DB paths to point at temp DBs.
        agented = tmp_path / "agented.db"
        ai_accounts = tmp_path / "ai_accounts.db"
        _seed_db(agented, rows=3)
        _seed_db(ai_accounts, rows=2)
        monkeypatch.setattr(backup, "_default_agented_db_path", lambda: agented)
        monkeypatch.setattr(backup, "_default_ai_accounts_db_path", lambda: ai_accounts)
        dest = tmp_path / "snaps"
        rc = backup.main(["--dest-dir", str(dest), "--no-remote"])
        assert rc == 0
        captured = capsys.readouterr()
        summary = json.loads(captured.out)
        assert len(summary["targets"]) == 2
        assert all(t["ok"] for t in summary["targets"])
        # Both snapshots exist.
        assert any(p.name.startswith("agented-") for p in dest.iterdir())
        assert any(p.name.startswith("ai_accounts-") for p in dest.iterdir())

    def test_main_exits_1_when_source_missing(self, tmp_path, monkeypatch, capsys):
        from scripts import backup

        missing = tmp_path / "nope.db"
        present = tmp_path / "ai_accounts.db"
        _seed_db(present)
        monkeypatch.setattr(backup, "_default_agented_db_path", lambda: missing)
        monkeypatch.setattr(backup, "_default_ai_accounts_db_path", lambda: present)
        dest = tmp_path / "snaps"
        rc = backup.main(["--dest-dir", str(dest), "--no-remote", "--quiet"])
        assert rc == 1

    def test_main_emits_stable_schema_for_failed_targets(self, tmp_path, monkeypatch, capsys):
        """Codex round-1 Issue 7: failed-target entries must include the
        same keys as success entries (with None where applicable)."""
        from scripts import backup

        missing = tmp_path / "nope.db"
        present = tmp_path / "ai_accounts.db"
        _seed_db(present)
        monkeypatch.setattr(backup, "_default_agented_db_path", lambda: missing)
        monkeypatch.setattr(backup, "_default_ai_accounts_db_path", lambda: present)
        dest = tmp_path / "snaps"
        backup.main(["--dest-dir", str(dest), "--no-remote"])
        out = capsys.readouterr().out
        summary = json.loads(out)
        expected_keys = {
            "label",
            "source",
            "ok",
            "snapshot",
            "size_bytes",
            "remote_synced",
            "retained_removed",
            "error",
        }
        for entry in summary["targets"]:
            assert set(entry.keys()) == expected_keys, (
                f"target entry missing/extra keys: {set(entry.keys())} != {expected_keys}"
            )


class TestConcurrentWriter:
    """Codex round-1 Issue 8: snapshot must be internally consistent
    while another writer is active (WAL mode)."""

    def test_snapshot_under_concurrent_writer_is_consistent(self, tmp_path):
        from scripts.backup import snapshot_one

        src = tmp_path / "live.db"
        # Enable WAL mode + seed a counter table.
        conn = sqlite3.connect(str(src))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE counter (id INTEGER PRIMARY KEY, n INTEGER)")
        conn.execute("INSERT INTO counter (n) VALUES (0)")
        conn.commit()
        conn.close()

        stop = threading.Event()

        def writer():
            wconn = sqlite3.connect(str(src), timeout=5.0)
            try:
                while not stop.is_set():
                    wconn.execute("UPDATE counter SET n = n + 1")
                    wconn.commit()
            finally:
                wconn.close()

        wt = threading.Thread(target=writer, daemon=True)
        wt.start()
        try:
            time.sleep(0.05)  # let the writer get going
            dest_dir = tmp_path / "snaps"
            snap = snapshot_one(
                "live",
                src,
                dest_dir,
                timestamp="2026-01-01T00-00-00Z",
            )
        finally:
            stop.set()
            wt.join(timeout=5.0)

        # The snapshot must be a valid SQLite DB with consistent state.
        sconn = sqlite3.connect(str(snap))
        try:
            integrity = sconn.execute("PRAGMA integrity_check").fetchone()[0]
            assert integrity == "ok", f"integrity_check failed: {integrity}"
            # Counter must be a non-negative int (snapshot has SOME consistent value).
            n = sconn.execute("SELECT n FROM counter").fetchone()[0]
            assert isinstance(n, int) and n >= 0
        finally:
            sconn.close()
