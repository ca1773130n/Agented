#!/usr/bin/env python3
"""Run one Life-Harness evolution round from the command line (T3).

Usage::

    uv run python scripts/run_harness_evolution.py <bot_id> [--since ISO]
                                                  [--until ISO] [--limit N]

The operator's environment must have Codex CLI on PATH (or
``AGENTED_CODEX_CMD`` set). Exits 0 on success, non-zero on failure.
"""

from __future__ import annotations

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one Life-Harness evolution round.",
    )
    parser.add_argument("bot_id")
    parser.add_argument("--since", default=None,
                        help="ISO-8601 lower bound on snapshot.created_at")
    parser.add_argument("--until", default=None,
                        help="ISO-8601 upper bound on snapshot.created_at")
    parser.add_argument("--limit", type=int, default=25,
                        help="Max recent executions to include (default 25)")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Stop after validating Codex's patch; round transitions to "
             "'awaiting_approval' for human review.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Bypass the 24h-default rate-limit guard.",
    )
    args = parser.parse_args()

    from app.services.harness_evolver import run_evolution_round

    result = run_evolution_round(
        args.bot_id,
        since=args.since,
        until=args.until,
        limit=args.limit,
        dry_run=args.dry_run,
        force=args.force,
    )

    json.dump(
        {
            "round_id": result.round_id,
            "status": result.status,
            "applied_layer_ids": result.applied_layer_ids,
            "error": result.error,
            "notes": result.notes,
        },
        sys.stdout,
        indent=2,
    )
    sys.stdout.write("\n")
    return 0 if result.status in ("applied", "awaiting_approval") else 1


if __name__ == "__main__":
    sys.exit(main())
