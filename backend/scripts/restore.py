"""v0.5.15: SQLite restore from a backup snapshot.

Picks a snapshot (interactively or via `--snapshot PATH`), takes a
pre-restore safety snapshot of the current DB, then overwrites.
Refuses to overwrite a DB whose `*.db-wal` is newer than 60 seconds
(implies the app is still running).

CLI: `python -m scripts.restore [--target {agented|ai_accounts}]
[--snapshot PATH] [--yes] [--no-safety-snapshot] [--dest-dir PATH]`
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import shutil
import sqlite3
import sys
import time
from pathlib import Path
from typing import Optional

from scripts.backup import (
    _default_agented_db_path,
    _default_ai_accounts_db_path,
    _default_dest_dir,
    _utc_timestamp,
)


logger = logging.getLogger(__name__)
LIVE_DB_GUARD_SECONDS = 60


def list_snapshots(dest_dir: Path, label: str) -> list[Path]:
    """Return snapshot files for `label`, newest first by mtime."""
    items = sorted(
        dest_dir.glob(f"{label}-*.db"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return items


def _is_live_db(target: Path) -> bool:
    """True if a *.db-wal companion exists and was modified in the
    last LIVE_DB_GUARD_SECONDS — which implies the app may still be
    writing to the DB."""
    wal = target.with_suffix(target.suffix + "-wal")
    if not wal.exists():
        return False
    age = time.time() - wal.stat().st_mtime
    return age < LIVE_DB_GUARD_SECONDS


def restore_one(
    label: str,
    snapshot_path: Path,
    target_path: Path,
    *,
    safety_dir: Optional[Path] = None,
    take_safety_snapshot: bool = True,
) -> Optional[Path]:
    """Overwrite `target_path` with `snapshot_path`. Returns the path
    of the safety snapshot taken (or None if `take_safety_snapshot`
    is False / target didn't exist)."""
    if not snapshot_path.exists():
        raise FileNotFoundError(f"snapshot not found: {snapshot_path}")
    safety_path: Optional[Path] = None
    if take_safety_snapshot and target_path.exists():
        if safety_dir is None:
            safety_dir = target_path.parent / "backups"
        safety_dir.mkdir(parents=True, exist_ok=True)
        safety_path = safety_dir / f"{label}-pre-restore-{_utc_timestamp()}.db"
        # Use sqlite3 backup so we still get a consistent copy even if
        # the operator forgot to stop the app (the live-DB guard above
        # is a best-effort warning, not a hard interlock).
        try:
            src_conn = sqlite3.connect(str(target_path))
            dst_conn = sqlite3.connect(str(safety_path))
            try:
                src_conn.backup(dst_conn)
                dst_conn.commit()
            finally:
                src_conn.close()
                dst_conn.close()
        except Exception:
            if safety_path.exists():
                safety_path.unlink()
            raise
    # Overwrite the target.
    shutil.copy2(snapshot_path, target_path)
    # Clear stale WAL so the restored DB starts fresh.
    for suffix in ("-wal", "-shm"):
        sidecar = target_path.with_suffix(target_path.suffix + suffix)
        if sidecar.exists():
            try:
                sidecar.unlink()
            except OSError as exc:
                logger.warning("restore: could not remove %s: %s", sidecar, exc)
    return safety_path


def _resolve_target(label: str) -> Path:
    if label == "agented":
        return _default_agented_db_path()
    if label == "ai_accounts":
        return _default_ai_accounts_db_path()
    raise ValueError(f"unknown target: {label!r}")


def _interactive_pick(snapshots: list[Path]) -> Optional[Path]:
    if not snapshots:
        print("No snapshots found.", file=sys.stderr)
        return None
    visible = snapshots[:10]
    print("Available snapshots (newest first):", file=sys.stderr)
    for i, s in enumerate(visible, start=1):
        size_kb = s.stat().st_size // 1024
        mtime = dt.datetime.fromtimestamp(s.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        print(f"  [{i:2d}] {s.name}  ({size_kb} KB, modified {mtime})", file=sys.stderr)
    try:
        raw = input(f"Select [1-{len(visible)}] or 'q' to abort: ").strip()
    except EOFError:
        return None
    if raw.lower() in ("q", "quit", "exit", ""):
        return None
    try:
        idx = int(raw)
    except ValueError:
        print(f"Invalid selection: {raw!r}", file=sys.stderr)
        return None
    if not (1 <= idx <= len(visible)):
        print(f"Out of range: {idx}", file=sys.stderr)
        return None
    return visible[idx - 1]


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Restore an Agented SQLite DB from a snapshot.")
    parser.add_argument("--target", choices=["agented", "ai_accounts"], default=None)
    parser.add_argument("--snapshot", default=None)
    parser.add_argument("--yes", action="store_true",
                        help="Skip the confirmation prompt.")
    parser.add_argument("--no-safety-snapshot", action="store_true")
    parser.add_argument("--dest-dir", default=None)
    args = parser.parse_args(argv)

    dest_dir = Path(args.dest_dir) if args.dest_dir else _default_dest_dir()

    snapshot_path: Optional[Path] = None
    label: Optional[str] = args.target

    if args.snapshot:
        snapshot_path = Path(args.snapshot)
        if not snapshot_path.is_file():
            print(f"ERROR: snapshot not found: {snapshot_path}", file=sys.stderr)
            return 1
        if label is None:
            # Infer from filename prefix.
            stem = snapshot_path.stem
            if stem.startswith("agented-"):
                label = "agented"
            elif stem.startswith("ai_accounts-"):
                label = "ai_accounts"
            else:
                print("ERROR: could not infer --target from snapshot filename; pass --target.",
                      file=sys.stderr)
                return 1
    else:
        if label is None:
            print("ERROR: pass --target {agented|ai_accounts} or --snapshot PATH.",
                  file=sys.stderr)
            return 1
        snapshots = list_snapshots(dest_dir, label)
        snapshot_path = _interactive_pick(snapshots)
        if snapshot_path is None:
            return 2

    target_path = _resolve_target(label)
    if _is_live_db(target_path):
        print(
            f"ERROR: {target_path} appears to be in active use "
            f"(*.db-wal modified within last {LIVE_DB_GUARD_SECONDS}s).\n"
            f"Stop the service first (e.g., `just kill` or "
            f"`systemctl --user stop agented-backend`).",
            file=sys.stderr,
        )
        return 2

    if not args.yes:
        try:
            confirm = input(
                f"Overwrite {target_path} with {snapshot_path.name}? [y/N]: "
            ).strip().lower()
        except EOFError:
            confirm = ""
        if confirm not in ("y", "yes"):
            print("Aborted.", file=sys.stderr)
            return 2

    safety_path = restore_one(
        label, snapshot_path, target_path,
        safety_dir=dest_dir,
        take_safety_snapshot=not args.no_safety_snapshot,
    )

    print(f"Restored {target_path} from {snapshot_path}")
    if safety_path:
        print(f"Pre-restore safety snapshot: {safety_path}")
    print("Restart the service to pick up the restored DB.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
