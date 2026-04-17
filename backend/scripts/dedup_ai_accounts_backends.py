"""One-shot cleanup: merge duplicate ai-accounts backend rows.

Matches the dedup key used by AccountService.create (ai-accounts >= 0.3.0):
  - (kind, config_path) if config_path is set
  - (kind, api_key_env) if api_key_env is set
  - (kind, email)       as a last resort

For each duplicate group the earliest-created row is kept; its config is
merged with all duplicates (latter rows win on per-key conflicts), and the
other rows are deleted.

Usage:
    uv run python scripts/dedup_ai_accounts_backends.py [--dry-run] [DB_PATH]

DB_PATH defaults to backend/ai_accounts.db.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path


def key_for(kind: str, cfg: dict) -> tuple[str, str, str] | None:
    cp = (cfg.get("config_path") or "").strip()
    env = (cfg.get("api_key_env") or "").strip()
    email = (cfg.get("email") or "").strip()
    if cp:
        return (kind, "config_path", cp)
    if env:
        return (kind, "api_key_env", env)
    if email:
        return (kind, "email", email)
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("db", nargs="?", default="backend/ai_accounts.db")
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    if not db_path.exists():
        print(f"DB not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, kind, display_name, status, config, created_at "
        "FROM backends ORDER BY created_at"
    ).fetchall()

    groups: dict[tuple[str, str, str], list[sqlite3.Row]] = defaultdict(list)
    for r in rows:
        try:
            cfg = json.loads(r["config"]) if r["config"] else {}
        except Exception:
            continue
        k = key_for(r["kind"], cfg)
        if k is None:
            continue
        groups[k].append(r)

    to_delete: list[str] = []
    updates: list[tuple[str, str]] = []  # (id, merged_config_json)

    for k, bucket in groups.items():
        if len(bucket) < 2:
            continue
        keeper = bucket[0]
        merged: dict = {}
        for r in bucket:
            try:
                merged.update(json.loads(r["config"]) if r["config"] else {})
            except Exception:
                pass
        updates.append((keeper["id"], json.dumps(merged)))
        for r in bucket[1:]:
            to_delete.append(r["id"])
        print(
            f"[{k[0]}] {k[1]}={k[2]}: keep {keeper['id']} ({keeper['display_name']}), "
            f"drop {', '.join(r['id'] for r in bucket[1:])}"
        )

    if not to_delete:
        print("No duplicates found.")
        return 0

    print(f"\n{len(to_delete)} duplicate row(s) to remove.")
    if args.dry_run:
        print("(dry run — no changes written)")
        return 0

    with conn:
        for bid, cfg_json in updates:
            conn.execute(
                "UPDATE backends SET config = ? WHERE id = ?",
                (cfg_json, bid),
            )
        conn.executemany(
            "DELETE FROM backends WHERE id = ?",
            [(bid,) for bid in to_delete],
        )
    print(f"Deleted {len(to_delete)} row(s), merged config into {len(updates)} keeper(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
