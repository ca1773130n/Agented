"""v0.5.15: SQLite backup + retention + optional remote sync.

Snapshots both `agented.db` and `ai_accounts.db` via the SQLite online
backup API (`Connection.backup`), writes timestamped files to
`AGENTED_BACKUP_DIR`, optionally pipes each through `BACKUP_REMOTE_CMD`,
and applies `BACKUP_RETENTION_DAYS` retention.

CLI: `python -m scripts.backup [--target {agented|ai_accounts|all}]
[--retention-days N] [--remote-cmd CMD] [--no-remote]
[--dest-dir PATH] [--quiet]`

Emits a JSON summary on stdout for scripted callers.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shlex
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from app.utils.timezone import utcnow as _utcnow

logger = logging.getLogger(__name__)


def _default_agented_db_path() -> Path:
    """Mirror app/config.py:DB_PATH resolution without importing the app."""
    explicit = os.environ.get("AGENTED_DB_PATH")
    if explicit:
        return Path(explicit)
    here = Path(__file__).resolve().parent.parent  # backend/
    return here / "agented.db"


def _default_ai_accounts_db_path() -> Path:
    """Sidecar runs from backend/ with `./ai_accounts.db`."""
    here = Path(__file__).resolve().parent.parent  # backend/
    return here / "ai_accounts.db"


def _default_dest_dir() -> Path:
    explicit = os.environ.get("AGENTED_BACKUP_DIR")
    if explicit:
        # Resolve relative env values against an absolute path so the
        # destination doesn't drift with the launcher's cwd.
        return Path(explicit).expanduser().resolve()
    here = Path(__file__).resolve().parent.parent  # backend/
    return here / "backups"


def _utc_timestamp() -> str:
    """ISO-8601 UTC with colons → hyphens for filename safety."""
    now = _utcnow().replace(microsecond=0)
    return now.isoformat().replace(":", "-") + "Z"


def snapshot_one(
    label: str,
    source: Path,
    dest_dir: Path,
    *,
    timestamp: str,
    pages_per_step: int = 100,
) -> Path:
    """Atomic online snapshot via sqlite3.Connection.backup. Returns
    the destination path on success; raises on failure (and removes
    any partial dest file).

    `pages_per_step` controls SQLite's chunked copy: each call holds
    the source's read lock briefly, releases, and resumes — letting
    concurrent WAL writers proceed instead of starving on a single
    big lock. 100 pages = ~400KB per chunk at the default 4KB page,
    which is a reasonable balance between progress and lock fairness.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{label}-{timestamp}.db"
    src_conn = sqlite3.connect(str(source))
    dst_conn = sqlite3.connect(str(dest))
    try:
        # pages > 0 enables chunked copying; the API still produces
        # an internally-consistent snapshot under concurrent writers
        # because each chunk runs inside a sqlite read transaction.
        src_conn.backup(dst_conn, pages=pages_per_step)
        dst_conn.commit()
    except Exception:
        try:
            dst_conn.close()
        finally:
            if dest.exists():
                dest.unlink()
        raise
    finally:
        src_conn.close()
        try:
            dst_conn.close()
        except Exception:  # noqa: BLE001
            pass
    return dest


def apply_retention(dest_dir: Path, retention_days: int, *, label: str) -> int:
    """Remove `{label}-*.db` files older than `retention_days`. Returns
    count removed. Per-file errors are logged at WARN and skipped.

    Pre-restore safety snapshots (`{label}-pre-restore-*.db`) are
    excluded — those are operator safety nets from a restore event
    and should outlive normal-rhythm retention.
    """
    if retention_days <= 0:
        return 0
    cutoff = time.time() - retention_days * 86400
    removed = 0
    for entry in dest_dir.glob(f"{label}-*.db"):
        if entry.stem.startswith(f"{label}-pre-restore-"):
            continue
        try:
            if entry.stat().st_mtime < cutoff:
                entry.unlink()
                removed += 1
        except OSError as exc:
            logger.warning("backup: could not remove %s: %s", entry, exc)
    return removed


def sync_remote(snapshot_path: Path, remote_cmd_template: str) -> bool:
    """Substitute `{file}` and shell out. Returns True on exit code 0.

    The substituted path is shlex-quoted before insertion so that
    paths containing spaces or shell metacharacters don't break the
    operator's command (or open an injection vector if the snapshot
    path is somehow attacker-influenced).
    """
    quoted = shlex.quote(str(snapshot_path))
    cmd = remote_cmd_template.replace("{file}", quoted)
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        logger.warning("backup: remote sync timed out for %s", snapshot_path)
        return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("backup: remote sync errored for %s: %s", snapshot_path, exc)
        return False
    if result.returncode != 0:
        logger.warning(
            "backup: remote sync exit=%d cmd=%r stderr=%r",
            result.returncode,
            cmd,
            result.stderr[:500],
        )
        return False
    return True


def _build_targets(target_arg: str) -> list[tuple[str, Path]]:
    all_targets = [
        ("agented", _default_agented_db_path()),
        ("ai_accounts", _default_ai_accounts_db_path()),
    ]
    if target_arg == "all":
        return all_targets
    return [t for t in all_targets if t[0] == target_arg]


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Snapshot Agented SQLite databases.")
    parser.add_argument("--target", choices=["agented", "ai_accounts", "all"], default="all")
    parser.add_argument("--retention-days", type=int, default=None)
    parser.add_argument("--remote-cmd", default=None)
    parser.add_argument("--no-remote", action="store_true")
    parser.add_argument("--dest-dir", default=None)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    if args.dest_dir:
        dest_dir = Path(args.dest_dir)
    else:
        dest_dir = _default_dest_dir()

    if args.retention_days is not None:
        retention_days = args.retention_days
    else:
        retention_days = int(os.environ.get("BACKUP_RETENTION_DAYS", "30"))

    if args.no_remote:
        remote_cmd = None
    else:
        remote_cmd = args.remote_cmd or os.environ.get("BACKUP_REMOTE_CMD")

    targets = _build_targets(args.target)
    if not targets:
        print(f"ERROR: no targets matched --target={args.target}", file=sys.stderr)
        return 1

    started = time.monotonic()
    timestamp = _utc_timestamp()
    summary = {
        "timestamp": timestamp,
        "dest_dir": str(dest_dir),
        "targets": [],
        "removed": 0,
        "elapsed_seconds": 0.0,
    }

    def _target_entry(
        *,
        label: str,
        source: Path,
        ok: bool,
        snapshot: Optional[Path] = None,
        size_bytes: Optional[int] = None,
        remote_synced: Optional[bool] = None,
        retained_removed: int = 0,
        error: Optional[str] = None,
    ) -> dict:
        # Stable schema — every entry has the same keys; failure
        # entries fill the data fields with None instead of omitting.
        return {
            "label": label,
            "source": str(source),
            "ok": ok,
            "snapshot": str(snapshot) if snapshot else None,
            "size_bytes": size_bytes,
            "remote_synced": remote_synced,
            "retained_removed": retained_removed,
            "error": error,
        }

    overall_ok = True
    for label, source in targets:
        if not source.exists():
            print(f"ERROR: source DB missing: {source}", file=sys.stderr)
            summary["targets"].append(
                _target_entry(
                    label=label,
                    source=source,
                    ok=False,
                    error="source missing",
                )
            )
            overall_ok = False
            continue
        try:
            dest = snapshot_one(label, source, dest_dir, timestamp=timestamp)
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR: snapshot failed for {label}: {exc}", file=sys.stderr)
            summary["targets"].append(
                _target_entry(
                    label=label,
                    source=source,
                    ok=False,
                    error=f"snapshot failed: {exc}",
                )
            )
            overall_ok = False
            continue

        size_bytes = dest.stat().st_size
        remote_synced: Optional[bool] = None
        if remote_cmd:
            remote_synced = sync_remote(dest, remote_cmd)

        removed = apply_retention(dest_dir, retention_days, label=label)
        summary["removed"] += removed
        summary["targets"].append(
            _target_entry(
                label=label,
                source=source,
                ok=True,
                snapshot=dest,
                size_bytes=size_bytes,
                remote_synced=remote_synced,
                retained_removed=removed,
            )
        )

    summary["elapsed_seconds"] = round(time.monotonic() - started, 3)
    if not args.quiet:
        print(json.dumps(summary, indent=2))
    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
