"""Budget enforcement service with pre-check, post-record, and cost estimation."""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from ..database import (
    create_token_usage_record,
    get_average_output_tokens,
    get_budget_limit,
    get_current_period_spend,
    get_window_token_usage,
    update_execution_token_data,
)

logger = logging.getLogger(__name__)

# Default rate limit window token limits (conservative Tier 1 Anthropic estimates)
DEFAULT_5H_TOKEN_LIMIT = 300_000
DEFAULT_WEEKLY_TOKEN_LIMIT = 1_000_000


class BudgetService:
    """Service for budget enforcement, token usage tracking, and cost estimation."""

    # Model pricing: price per million tokens (USD)
    # Source: Anthropic pricing as of 2025
    MODEL_PRICING = {
        "claude-opus-4-6": {
            "input": 15.0,
            "output": 75.0,
            "cache_read": 1.5,
        },
        "claude-opus-4-5": {
            "input": 15.0,
            "output": 75.0,
            "cache_read": 1.5,
        },
        "claude-opus-4": {
            "input": 15.0,
            "output": 75.0,
            "cache_read": 1.5,
        },
        "claude-sonnet-4-5": {
            "input": 3.0,
            "output": 15.0,
            "cache_read": 0.3,
        },
        "claude-sonnet-4": {
            "input": 3.0,
            "output": 15.0,
            "cache_read": 0.3,
        },
        "claude-haiku-4.5": {
            "input": 0.80,
            "output": 4.0,
            "cache_read": 0.08,
        },
        "claude-haiku-3.5": {
            "input": 0.80,
            "output": 4.0,
            "cache_read": 0.08,
        },
    }

    @classmethod
    def extract_token_usage(cls, stdout_log: str, backend_type: str) -> Optional[dict]:
        """Extract token usage from CLI output.

        Dispatches to backend-specific parsers:
        - claude: parses JSON result from --output-format json
        - gemini: parses JSON with stats.models.*.tokens structure
        - codex: parses JSONL with turn.completed events
        - opencode: best-effort JSON parsing (MEDIUM confidence)
        """
        if not stdout_log or not stdout_log.strip():
            return None

        if backend_type == "claude":
            return cls._extract_claude_usage(stdout_log)
        elif backend_type == "gemini":
            return cls._extract_gemini_usage(stdout_log)
        elif backend_type == "codex":
            return cls._extract_codex_usage(stdout_log)
        elif backend_type == "opencode":
            return cls._extract_opencode_usage(stdout_log)
        else:
            return None

    @classmethod
    def _extract_claude_usage(cls, stdout_log: str) -> Optional[dict]:
        """Parse Claude CLI JSON output for token usage."""
        parsed = cls._try_parse_json(stdout_log.strip())

        if parsed is None:
            parsed = cls._find_last_json_object(stdout_log)

        if parsed is None:
            return None

        usage = parsed.get("usage", {})

        return {
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "cache_read_tokens": usage.get("cache_read_input_tokens", 0),
            "cache_creation_tokens": usage.get("cache_creation_input_tokens", 0),
            "total_cost_usd": parsed.get("total_cost_usd", 0.0),
            "num_turns": parsed.get("num_turns", 0),
            "duration_api_ms": parsed.get("duration_api_ms", 0),
            "session_id": parsed.get("session_id"),
            "source": "cli_output",
        }

    @classmethod
    def _extract_gemini_usage(cls, stdout_log: str) -> Optional[dict]:
        """Parse Gemini CLI JSON output for token usage.

        Gemini --output-format json returns stats.models.<model>.tokens with
        prompt, candidates, total, cached, thoughts, tool fields.
        Sums across all models.
        """
        parsed = cls._try_parse_json(stdout_log.strip())
        if parsed is None:
            parsed = cls._find_last_json_object(stdout_log)
        if parsed is None:
            return None

        stats = parsed.get("stats", {})
        models = stats.get("models", {})

        total_input = 0
        total_output = 0
        total_cached = 0

        for model_data in models.values():
            tokens = model_data.get("tokens", {})
            total_input += tokens.get("prompt", 0)
            total_output += tokens.get("candidates", 0)
            total_cached += tokens.get("cached", 0)

        if total_input == 0 and total_output == 0:
            return None

        return {
            "input_tokens": total_input,
            "output_tokens": total_output,
            "cache_read_tokens": total_cached,
            "cache_creation_tokens": 0,
            "total_cost_usd": 0.0,
            "source": "cli_output",
        }

    @classmethod
    def _extract_codex_usage(cls, stdout_log: str) -> Optional[dict]:
        """Parse Codex CLI JSONL output for token usage.

        Codex --json outputs JSONL events. The last turn.completed event contains:
        {"type":"turn.completed","usage":{"input_tokens":N,"cached_input_tokens":N,"output_tokens":N}}
        """
        last_usage = None

        for line in stdout_log.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                if event.get("type") == "turn.completed" and "usage" in event:
                    last_usage = event["usage"]
            except (json.JSONDecodeError, ValueError):
                continue

        if not last_usage:
            return None

        return {
            "input_tokens": last_usage.get("input_tokens", 0),
            "output_tokens": last_usage.get("output_tokens", 0),
            "cache_read_tokens": last_usage.get("cached_input_tokens", 0),
            "cache_creation_tokens": 0,
            "total_cost_usd": 0.0,
            "source": "cli_output",
        }

    @classmethod
    def _extract_opencode_usage(cls, stdout_log: str) -> Optional[dict]:
        """Parse OpenCode CLI JSON output for token usage.

        MEDIUM confidence parser -- OpenCode's JSON event format is less documented.
        Tries to find usage or stats keys with token counts.
        Returns None if structure doesn't match expected format.
        """
        parsed = cls._try_parse_json(stdout_log.strip())
        if parsed is None:
            parsed = cls._find_last_json_object(stdout_log)
        if parsed is None:
            return None

        # Try direct usage key
        usage = parsed.get("usage", {})
        if usage and (usage.get("input_tokens") or usage.get("output_tokens")):
            return {
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "cache_read_tokens": usage.get("cache_read_tokens", 0),
                "cache_creation_tokens": 0,
                "total_cost_usd": 0.0,
                "source": "cli_output",
            }

        # Try stats key
        stats = parsed.get("stats", {})
        if stats and (stats.get("input_tokens") or stats.get("output_tokens")):
            return {
                "input_tokens": stats.get("input_tokens", 0),
                "output_tokens": stats.get("output_tokens", 0),
                "cache_read_tokens": stats.get("cache_read_tokens", 0),
                "cache_creation_tokens": 0,
                "total_cost_usd": 0.0,
                "source": "cli_output",
            }

        return None

    @classmethod
    def _try_parse_json(cls, text: str) -> Optional[dict]:
        """Try to parse text as JSON. Returns dict or None."""
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, ValueError):
            pass
        return None

    @classmethod
    def _find_last_json_object(cls, text: str) -> Optional[dict]:
        """Find the last JSON object in mixed text content.

        Scans from the end of the text looking for a matching { }.
        """
        # Find the last closing brace
        last_close = text.rfind("}")
        if last_close == -1:
            return None

        # Find the matching opening brace by counting
        depth = 0
        for i in range(last_close, -1, -1):
            if text[i] == "}":
                depth += 1
            elif text[i] == "{":
                depth -= 1
                if depth == 0:
                    # Try to parse this substring
                    candidate = text[i : last_close + 1]
                    parsed = cls._try_parse_json(candidate)
                    if parsed is not None:
                        return parsed
                    break
        return None

    @classmethod
    def estimate_cost(
        cls,
        prompt: str,
        model: str = "claude-sonnet-4",
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
    ) -> dict:
        """Estimate execution cost based on prompt length and historical averages.

        Returns dict with estimated_input_tokens, estimated_output_tokens,
        estimated_cost_usd, model, confidence.
        """
        # Estimate input tokens from prompt length (rough heuristic: ~4 chars per token)
        estimated_input_tokens = max(1, len(prompt) // 4)

        # Look up historical average output tokens if entity provided
        estimated_output_tokens = 2000  # default
        confidence = "low"

        if entity_type and entity_id:
            avg_output = get_average_output_tokens(entity_type, entity_id)
            if avg_output is not None:
                estimated_output_tokens = int(avg_output)
                confidence = "medium"

        # Look up model pricing
        pricing = cls.MODEL_PRICING.get(model, cls.MODEL_PRICING["claude-sonnet-4"])

        # Calculate estimated cost
        estimated_cost_usd = (estimated_input_tokens * pricing["input"] / 1_000_000) + (
            estimated_output_tokens * pricing["output"] / 1_000_000
        )

        return {
            "estimated_input_tokens": estimated_input_tokens,
            "estimated_output_tokens": estimated_output_tokens,
            "estimated_cost_usd": round(estimated_cost_usd, 6),
            "model": model,
            "confidence": confidence,
        }

    @classmethod
    def check_budget(cls, entity_type: str, entity_id: str) -> dict:
        """Pre-execution budget check.

        Returns dict with allowed, reason, remaining_usd, current_spend, limit.
        """
        limits = get_budget_limit(entity_type, entity_id)

        if not limits:
            return {
                "allowed": True,
                "reason": "no_limits",
                "remaining_usd": None,
                "current_spend": None,
            }

        period = limits.get("period", "monthly")
        current_spend = get_current_period_spend(entity_type, entity_id, period)

        hard_limit = limits.get("hard_limit_usd")
        soft_limit = limits.get("soft_limit_usd")

        # Check hard limit first
        if hard_limit is not None and current_spend >= hard_limit:
            return {
                "allowed": False,
                "reason": f"hard_limit_reached: spent ${current_spend:.2f} of ${hard_limit:.2f} {period} limit",
                "remaining_usd": 0,
                "current_spend": current_spend,
                "limit": limits,
            }

        # Check soft limit
        if soft_limit is not None and current_spend >= soft_limit:
            remaining = (hard_limit if hard_limit is not None else float("inf")) - current_spend
            return {
                "allowed": True,
                "reason": "soft_limit_warning",
                "remaining_usd": remaining if remaining != float("inf") else None,
                "current_spend": current_spend,
                "limit": limits,
            }

        # Within budget
        cap = hard_limit if hard_limit is not None else soft_limit
        remaining = (cap - current_spend) if cap is not None else None

        return {
            "allowed": True,
            "reason": "within_budget",
            "remaining_usd": remaining,
            "current_spend": current_spend,
            "limit": limits,
        }

    @classmethod
    def get_window_usage(cls) -> dict:
        """Calculate approximate rate limit window usage.

        Returns token usage within:
        - Current 5-hour window (rolling: now minus 5 hours)
        - Current weekly window (from Monday 00:00 UTC to end of Sunday)

        Limits are configurable defaults per tier; later can be per-account.
        """
        now = datetime.now(timezone.utc)

        # 5-hour rolling window
        five_h_start = now - timedelta(hours=5)
        five_h_start_str = five_h_start.strftime("%Y-%m-%dT%H:%M:%SZ")
        five_h_end_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        five_h_tokens = get_window_token_usage(five_h_start_str)
        five_h_limit = DEFAULT_5H_TOKEN_LIMIT
        five_h_pct = (
            min(round((five_h_tokens / five_h_limit) * 100, 1), 100.0) if five_h_limit > 0 else 0.0
        )

        # Weekly window: Monday 00:00 UTC to Sunday 23:59:59 UTC
        days_since_monday = now.weekday()  # Monday=0
        week_start = (now - timedelta(days=days_since_monday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        week_end = week_start + timedelta(days=6, hours=23, minutes=59, seconds=59)
        week_start_str = week_start.strftime("%Y-%m-%dT%H:%M:%SZ")
        week_end_str = week_end.strftime("%Y-%m-%dT%H:%M:%SZ")
        weekly_tokens = get_window_token_usage(week_start_str)
        weekly_limit = DEFAULT_WEEKLY_TOKEN_LIMIT
        weekly_pct = (
            min(round((weekly_tokens / weekly_limit) * 100, 1), 100.0) if weekly_limit > 0 else 0.0
        )

        return {
            "five_hour_window": {
                "start": five_h_start_str,
                "end": five_h_end_str,
                "tokens_used": five_h_tokens,
                "limit": five_h_limit,
                "percentage": five_h_pct,
            },
            "weekly_window": {
                "start": week_start_str,
                "end": week_end_str,
                "tokens_used": weekly_tokens,
                "limit": weekly_limit,
                "percentage": weekly_pct,
            },
        }

    @classmethod
    def record_usage(
        cls,
        execution_id: str,
        entity_type: str,
        entity_id: str,
        backend_type: str,
        account_id: Optional[int],
        usage_data: dict,
    ) -> Optional[int]:
        """Record token usage for a completed execution.

        Persists to token_usage table and caches on execution_logs.
        Returns the token_usage record ID.
        """
        record_id = create_token_usage_record(
            execution_id=execution_id,
            entity_type=entity_type,
            entity_id=entity_id,
            backend_type=backend_type,
            account_id=account_id,
            input_tokens=usage_data.get("input_tokens", 0),
            output_tokens=usage_data.get("output_tokens", 0),
            cache_read_tokens=usage_data.get("cache_read_tokens", 0),
            cache_creation_tokens=usage_data.get("cache_creation_tokens", 0),
            total_cost_usd=usage_data.get("total_cost_usd", 0.0),
            num_turns=usage_data.get("num_turns", 0),
            duration_api_ms=usage_data.get("duration_api_ms", 0),
            session_id=usage_data.get("session_id"),
        )

        # Cache token data on execution_logs for quick access
        update_execution_token_data(
            execution_id=execution_id,
            input_tokens=usage_data.get("input_tokens", 0),
            output_tokens=usage_data.get("output_tokens", 0),
            total_cost_usd=usage_data.get("total_cost_usd", 0.0),
        )

        if record_id:
            logger.info(
                f"Recorded token usage for {execution_id}: "
                f"${usage_data.get('total_cost_usd', 0):.4f}"
            )
        else:
            logger.warning(f"Failed to record token usage for {execution_id}")

        return record_id
