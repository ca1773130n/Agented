"""Session collection service — find, parse, and record session usage data."""

import json
import logging
import os
from pathlib import Path
from typing import Optional

from .session_cost_service import _compute_cost

logger = logging.getLogger(__name__)

_SETTINGS_KEY = "session_usage_imported"


class SessionCollectionService:
    """Collects token usage from local CLI session files."""

    @classmethod
    def collect_all(cls) -> dict:
        """Run full collection. Returns summary of imported data.

        Re-parses already-imported sessions to pick up token growth from
        active/in-progress sessions. Updates existing DB records when
        token counts have increased.
        """
        imported_set = cls._get_imported_sessions()
        results = {
            "claude": {"sessions": 0, "updated": 0, "cost": 0.0},
            "codex": {"sessions": 0, "updated": 0, "cost": 0.0},
        }

        # Claude Code sessions
        claude_dirs = cls._find_claude_project_dirs()
        for proj_dir in claude_dirs:
            for jsonl_file in proj_dir.glob("*.jsonl"):
                session_id = jsonl_file.stem
                usage = cls._parse_claude_session(jsonl_file)
                if not usage or (usage["input_tokens"] == 0 and usage["output_tokens"] == 0):
                    continue
                if session_id in imported_set:
                    # Re-imported: update if tokens grew
                    if cls._update_usage_if_changed(session_id, "claude", usage):
                        results["claude"]["updated"] += 1
                else:
                    cls._record_usage(
                        session_id=session_id,
                        backend_type="claude",
                        usage=usage,
                    )
                    imported_set.add(session_id)
                    results["claude"]["sessions"] += 1
                    results["claude"]["cost"] += usage.get("total_cost_usd", 0.0)

        # Codex CLI sessions
        codex_dir = cls._find_codex_session_dir()
        if codex_dir and codex_dir.exists():
            for jsonl_file in codex_dir.glob("*.jsonl"):
                session_id = jsonl_file.stem
                usage = cls._parse_codex_session(jsonl_file)
                if not usage or (usage["input_tokens"] == 0 and usage["output_tokens"] == 0):
                    continue
                if session_id in imported_set:
                    if cls._update_usage_if_changed(session_id, "codex", usage):
                        results["codex"]["updated"] += 1
                else:
                    cls._record_usage(
                        session_id=session_id,
                        backend_type="codex",
                        usage=usage,
                    )
                    imported_set.add(session_id)
                    results["codex"]["sessions"] += 1
                    results["codex"]["cost"] += usage.get("total_cost_usd", 0.0)

        cls._save_imported_sessions(imported_set)
        return results

    @classmethod
    def get_stats_cache_summary(cls) -> Optional[dict]:
        """Read Claude Code's aggregated stats-cache.json from all account config dirs."""
        bases = [Path.home() / ".claude", Path.home() / ".config" / "claude"]

        # Add per-account config dirs from DB
        try:
            from ..database import get_connection

            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT config_path FROM backend_accounts WHERE config_path IS NOT NULL"
                ).fetchall()
                for row in rows:
                    if row["config_path"]:
                        expanded = Path(os.path.expanduser(row["config_path"]))
                        if expanded not in bases:
                            bases.append(expanded)
        except Exception as e:
            logger.warning("Failed to load config paths from DB: %s", e)

        # Merge all stats-cache.json files
        merged: Optional[dict] = None
        for base in bases:
            stats_file = base / "stats-cache.json"
            if stats_file.exists():
                try:
                    data = json.loads(stats_file.read_text())
                    if merged is None:
                        merged = data
                    else:
                        # Merge totals
                        merged["totalSessions"] = merged.get("totalSessions", 0) + data.get(
                            "totalSessions", 0
                        )
                        merged["totalMessages"] = merged.get("totalMessages", 0) + data.get(
                            "totalMessages", 0
                        )
                        # Keep earliest first session date
                        existing_date = merged.get("firstSessionDate")
                        new_date = data.get("firstSessionDate")
                        if new_date and (not existing_date or new_date < existing_date):
                            merged["firstSessionDate"] = new_date
                        # Merge model usage
                        for model_id, usage in data.get("modelUsage", {}).items():
                            if model_id in merged.get("modelUsage", {}):
                                for k in [
                                    "inputTokens",
                                    "outputTokens",
                                    "cacheReadInputTokens",
                                    "cacheCreationInputTokens",
                                ]:
                                    merged["modelUsage"][model_id][k] = merged["modelUsage"][
                                        model_id
                                    ].get(k, 0) + usage.get(k, 0)
                            else:
                                merged.setdefault("modelUsage", {})[model_id] = usage
                except (json.JSONDecodeError, OSError) as e:
                    logger.debug(f"Failed to read stats-cache.json from {base}: {e}")

        if merged is None:
            return None
        return cls._format_stats_cache(merged)

    @classmethod
    def _format_stats_cache(cls, data: dict) -> dict:
        """Format stats-cache.json data into a summary."""
        model_usage = data.get("modelUsage", {})
        total_input = 0
        total_output = 0
        total_cache_read = 0
        total_cache_create = 0
        total_cost = 0.0
        models = {}

        for model_id, usage in model_usage.items():
            inp = usage.get("inputTokens", 0)
            out = usage.get("outputTokens", 0)
            cr = usage.get("cacheReadInputTokens", 0)
            cc = usage.get("cacheCreationInputTokens", 0)
            cost = _compute_cost(inp, out, cr, cc, model_id)

            total_input += inp
            total_output += out
            total_cache_read += cr
            total_cache_create += cc
            total_cost += cost

            models[model_id] = {
                "input_tokens": inp,
                "output_tokens": out,
                "cache_read_tokens": cr,
                "cache_creation_tokens": cc,
                "cost_usd": round(cost, 4),
            }

        return {
            "source": "stats-cache.json",
            "total_sessions": data.get("totalSessions", 0),
            "total_messages": data.get("totalMessages", 0),
            "first_session_date": data.get("firstSessionDate"),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_cache_read_tokens": total_cache_read,
            "total_cache_creation_tokens": total_cache_create,
            "total_cost_usd": round(total_cost, 4),
            "models": models,
            "daily_activity": data.get("dailyActivity", []),
        }

    # ----- Claude Code parsing -----

    @classmethod
    def _find_claude_project_dirs(cls) -> list[Path]:
        """Find all Claude Code project directories.

        Scans both default locations and per-account config directories
        from the backend_accounts table.
        """
        seen = set()
        dirs = []

        # Default locations
        bases = [Path.home() / ".claude", Path.home() / ".config" / "claude"]

        # Add per-account config directories from DB
        try:
            from ..database import get_connection

            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT config_path FROM backend_accounts WHERE config_path IS NOT NULL"
                ).fetchall()
                for row in rows:
                    config_path = row["config_path"]
                    if config_path:
                        expanded = Path(os.path.expanduser(config_path))
                        if expanded not in seen:
                            bases.append(expanded)
                            seen.add(expanded)
        except Exception as e:
            logger.debug("Failed to load account config paths: %s", e)

        for base in bases:
            projects_dir = base / "projects"
            if projects_dir.exists():
                for proj_dir in projects_dir.iterdir():
                    if proj_dir.is_dir() and proj_dir not in seen:
                        dirs.append(proj_dir)
                        seen.add(proj_dir)
        return dirs

    @classmethod
    def _parse_claude_session(cls, jsonl_path: Path) -> Optional[dict]:
        """Parse a Claude Code JSONL session file and aggregate token usage.

        Computes cost per-message using each turn's actual model, so multi-model
        sessions get accurate pricing instead of using a single model for all tokens.
        """
        total_input = 0
        total_output = 0
        total_cache_read = 0
        total_cache_create = 0
        total_cost = 0.0
        num_turns = 0
        model = ""
        first_ts = None
        last_ts = None

        try:
            with open(jsonl_path, "r", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if entry.get("type") != "assistant":
                        continue
                    if entry.get("isApiErrorMessage"):
                        continue

                    msg = entry.get("message", {})
                    usage = msg.get("usage", {})
                    if not usage:
                        continue

                    turn_input = usage.get("input_tokens", 0)
                    turn_output = usage.get("output_tokens", 0)
                    turn_cache_read = usage.get("cache_read_input_tokens", 0)
                    turn_cache_create = usage.get("cache_creation_input_tokens", 0)
                    turn_model = msg.get("model", "") or model

                    total_input += turn_input
                    total_output += turn_output
                    total_cache_read += turn_cache_read
                    total_cache_create += turn_cache_create
                    total_cost += _compute_cost(
                        turn_input, turn_output, turn_cache_read, turn_cache_create, turn_model
                    )
                    num_turns += 1

                    if msg.get("model"):
                        model = msg["model"]

                    ts = entry.get("timestamp")
                    if ts:
                        if first_ts is None:
                            first_ts = ts
                        last_ts = ts

        except (OSError, IOError) as e:
            logger.debug(f"Failed to parse Claude session {jsonl_path}: {e}")
            return None

        if num_turns == 0:
            return None

        return {
            "input_tokens": total_input,
            "output_tokens": total_output,
            "cache_read_tokens": total_cache_read,
            "cache_creation_tokens": total_cache_create,
            "total_cost_usd": round(total_cost, 6),
            "num_turns": num_turns,
            "model": model,
            "first_timestamp": first_ts,
            "last_timestamp": last_ts,
        }

    # ----- Codex CLI parsing -----

    @classmethod
    def _find_codex_session_dir(cls) -> Optional[Path]:
        """Find the Codex CLI sessions directory."""
        codex_home = os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))
        sessions_dir = Path(codex_home) / "sessions"
        return sessions_dir if sessions_dir.exists() else None

    @classmethod
    def _parse_codex_session(cls, jsonl_path: Path) -> Optional[dict]:
        """Parse a Codex CLI JSONL session file and aggregate token usage."""
        total_input = 0
        total_output = 0
        total_cached = 0
        num_turns = 0
        model = ""
        first_ts = None
        last_ts = None

        # Codex reports cumulative tokens; we need final totals
        last_input = 0
        last_output = 0
        last_cached = 0

        try:
            with open(jsonl_path, "r", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    # Look for turn.completed events with usage
                    if entry.get("type") == "turn.completed":
                        usage = entry.get("usage", {})
                        if usage:
                            cur_input = usage.get("input_tokens", 0)
                            cur_output = usage.get("output_tokens", 0)
                            cur_cached = usage.get("cached_input_tokens", 0)
                            # Use the maximum values (cumulative)
                            if cur_input > last_input:
                                last_input = cur_input
                            if cur_output > last_output:
                                last_output = cur_output
                            if cur_cached > last_cached:
                                last_cached = cur_cached
                            num_turns += 1

                    # Try to extract model from turn context
                    if entry.get("turn_context", {}).get("model"):
                        model = entry["turn_context"]["model"]

                    ts = entry.get("timestamp") or entry.get("created_at")
                    if ts:
                        if first_ts is None:
                            first_ts = ts
                        last_ts = ts

        except (OSError, IOError) as e:
            logger.debug(f"Failed to parse Codex session {jsonl_path}: {e}")
            return None

        total_input = last_input
        total_output = last_output
        total_cached = last_cached

        if num_turns == 0 and total_input == 0:
            return None

        cost = _compute_cost(total_input, total_output, total_cached, 0, model)

        return {
            "input_tokens": total_input,
            "output_tokens": total_output,
            "cache_read_tokens": total_cached,
            "cache_creation_tokens": 0,
            "total_cost_usd": cost,
            "num_turns": num_turns,
            "model": model,
            "first_timestamp": first_ts,
            "last_timestamp": last_ts,
        }

    # ----- Database -----

    @classmethod
    def _record_usage(cls, session_id: str, backend_type: str, usage: dict):
        """Record session usage into the token_usage table."""
        from ..database import create_token_usage_record

        execution_id = f"session-{session_id}"
        # Use the session's actual timestamp (last message time), not import time
        session_ts = usage.get("last_timestamp") or usage.get("first_timestamp")
        create_token_usage_record(
            execution_id=execution_id,
            entity_type="session",
            entity_id=backend_type,
            backend_type=backend_type,
            account_id=None,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cache_read_tokens=usage.get("cache_read_tokens", 0),
            cache_creation_tokens=usage.get("cache_creation_tokens", 0),
            total_cost_usd=usage.get("total_cost_usd", 0.0),
            num_turns=usage.get("num_turns", 0),
            session_id=session_id,
            recorded_at=session_ts,
        )

    @classmethod
    def _update_usage_if_changed(cls, session_id: str, backend_type: str, usage: dict) -> bool:
        """Update an existing token_usage record if the session's tokens have grown.

        Returns True if a record was updated, False if unchanged or not found.
        """
        from ..database import get_connection

        execution_id = f"session-{session_id}"
        try:
            with get_connection() as conn:
                cursor = conn.execute(
                    """SELECT input_tokens, output_tokens, cache_read_tokens,
                              cache_creation_tokens
                       FROM token_usage WHERE execution_id = ?""",
                    (execution_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return False

                new_input = usage.get("input_tokens", 0)
                new_output = usage.get("output_tokens", 0)
                new_cache_read = usage.get("cache_read_tokens", 0)
                new_cache_create = usage.get("cache_creation_tokens", 0)

                if (
                    new_input <= row["input_tokens"]
                    and new_output <= row["output_tokens"]
                    and new_cache_read <= row["cache_read_tokens"]
                    and new_cache_create <= row["cache_creation_tokens"]
                ):
                    return False  # No growth

                # Use the session's actual timestamp, preserve original if not available
                session_ts = usage.get("last_timestamp") or usage.get("first_timestamp")
                if session_ts:
                    conn.execute(
                        """UPDATE token_usage
                           SET input_tokens = ?, output_tokens = ?,
                               cache_read_tokens = ?, cache_creation_tokens = ?,
                               total_cost_usd = ?, num_turns = ?,
                               recorded_at = ?
                           WHERE execution_id = ?""",
                        (
                            new_input,
                            new_output,
                            new_cache_read,
                            new_cache_create,
                            usage.get("total_cost_usd", 0.0),
                            usage.get("num_turns", 0),
                            session_ts,
                            execution_id,
                        ),
                    )
                else:
                    conn.execute(
                        """UPDATE token_usage
                           SET input_tokens = ?, output_tokens = ?,
                               cache_read_tokens = ?, cache_creation_tokens = ?,
                               total_cost_usd = ?, num_turns = ?
                           WHERE execution_id = ?""",
                        (
                            new_input,
                            new_output,
                            new_cache_read,
                            new_cache_create,
                            usage.get("total_cost_usd", 0.0),
                            usage.get("num_turns", 0),
                            execution_id,
                        ),
                    )
                conn.commit()
                return True
        except Exception as e:
            logger.debug(f"Failed to update session {session_id}: {e}")
            return False

    @classmethod
    def _get_imported_sessions(cls) -> set[str]:
        """Get set of already-imported session IDs from DB settings."""
        try:
            from ..database import get_connection

            with get_connection() as conn:
                cursor = conn.execute("SELECT value FROM settings WHERE key = ?", (_SETTINGS_KEY,))
                row = cursor.fetchone()
                if row and row["value"]:
                    return set(json.loads(row["value"]))
        except Exception as e:
            logger.warning("Failed to load imported session IDs from DB: %s", e, exc_info=True)
        return set()

    @classmethod
    def _save_imported_sessions(cls, sessions: set[str]):
        """Save set of imported session IDs to DB settings."""
        try:
            from ..database import get_connection

            with get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO settings (key, value, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (_SETTINGS_KEY, json.dumps(sorted(sessions))),
                )
                conn.commit()
        except Exception as e:
            logger.debug(f"Failed to save imported sessions: {e}")
