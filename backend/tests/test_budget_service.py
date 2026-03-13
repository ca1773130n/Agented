"""Tests for BudgetService — token extraction, cost estimation, and budget checks."""

import json

import pytest

from app.services.budget_service import BudgetService


class TestExtractTokenUsage:
    """Tests for extract_token_usage dispatcher and backend-specific parsers."""

    def test_empty_stdout_returns_none(self):
        assert BudgetService.extract_token_usage("", "claude") is None
        assert BudgetService.extract_token_usage("  ", "claude") is None
        assert BudgetService.extract_token_usage(None, "claude") is None

    def test_unknown_backend_returns_none(self):
        assert BudgetService.extract_token_usage('{"usage":{}}', "unknown_backend") is None

    # --- Claude ---

    def test_claude_json_output(self):
        data = json.dumps(
            {
                "usage": {
                    "input_tokens": 1000,
                    "output_tokens": 500,
                    "cache_read_input_tokens": 200,
                    "cache_creation_input_tokens": 50,
                },
                "total_cost_usd": 0.0325,
                "num_turns": 3,
                "duration_api_ms": 12000,
                "session_id": "sess-123",
            }
        )
        result = BudgetService.extract_token_usage(data, "claude")
        assert result is not None
        assert result["input_tokens"] == 1000
        assert result["output_tokens"] == 500
        assert result["cache_read_tokens"] == 200
        assert result["cache_creation_tokens"] == 50
        assert result["total_cost_usd"] == 0.0325
        assert result["num_turns"] == 3
        assert result["session_id"] == "sess-123"
        assert result["source"] == "cli_output"

    def test_claude_json_embedded_in_text(self):
        stdout = 'Some debug output\n{"usage": {"input_tokens": 100, "output_tokens": 50}}\n'
        result = BudgetService.extract_token_usage(stdout, "claude")
        assert result is not None
        assert result["input_tokens"] == 100
        assert result["output_tokens"] == 50

    def test_claude_no_json_returns_none(self):
        assert BudgetService.extract_token_usage("just plain text", "claude") is None

    # --- Gemini ---

    def test_gemini_json_output(self):
        data = json.dumps(
            {
                "stats": {
                    "models": {
                        "gemini-2.5-pro": {
                            "tokens": {
                                "prompt": 800,
                                "candidates": 400,
                                "cached": 100,
                            }
                        }
                    }
                }
            }
        )
        result = BudgetService.extract_token_usage(data, "gemini")
        assert result is not None
        assert result["input_tokens"] == 800
        assert result["output_tokens"] == 400
        assert result["cache_read_tokens"] == 100

    def test_gemini_multi_model_sums(self):
        data = json.dumps(
            {
                "stats": {
                    "models": {
                        "model-a": {"tokens": {"prompt": 100, "candidates": 50, "cached": 10}},
                        "model-b": {"tokens": {"prompt": 200, "candidates": 100, "cached": 20}},
                    }
                }
            }
        )
        result = BudgetService.extract_token_usage(data, "gemini")
        assert result["input_tokens"] == 300
        assert result["output_tokens"] == 150
        assert result["cache_read_tokens"] == 30

    def test_gemini_zero_tokens_returns_none(self):
        data = json.dumps({"stats": {"models": {"m": {"tokens": {"prompt": 0, "candidates": 0}}}}})
        assert BudgetService.extract_token_usage(data, "gemini") is None

    # --- Codex ---

    def test_codex_jsonl_output(self):
        lines = [
            json.dumps({"type": "message.start", "data": "hello"}),
            json.dumps(
                {
                    "type": "turn.completed",
                    "usage": {
                        "input_tokens": 500,
                        "output_tokens": 250,
                        "cached_input_tokens": 100,
                    },
                }
            ),
        ]
        result = BudgetService.extract_token_usage("\n".join(lines), "codex")
        assert result is not None
        assert result["input_tokens"] == 500
        assert result["output_tokens"] == 250
        assert result["cache_read_tokens"] == 100

    def test_codex_uses_last_turn_completed(self):
        lines = [
            json.dumps(
                {"type": "turn.completed", "usage": {"input_tokens": 100, "output_tokens": 50}}
            ),
            json.dumps(
                {"type": "turn.completed", "usage": {"input_tokens": 200, "output_tokens": 100}}
            ),
        ]
        result = BudgetService.extract_token_usage("\n".join(lines), "codex")
        assert result["input_tokens"] == 200
        assert result["output_tokens"] == 100

    def test_codex_no_turn_completed_returns_none(self):
        lines = [json.dumps({"type": "message.start"})]
        assert BudgetService.extract_token_usage("\n".join(lines), "codex") is None

    # --- OpenCode ---

    def test_opencode_usage_key(self):
        data = json.dumps({"usage": {"input_tokens": 300, "output_tokens": 150}})
        result = BudgetService.extract_token_usage(data, "opencode")
        assert result is not None
        assert result["input_tokens"] == 300
        assert result["output_tokens"] == 150

    def test_opencode_stats_key(self):
        data = json.dumps({"stats": {"input_tokens": 400, "output_tokens": 200}})
        result = BudgetService.extract_token_usage(data, "opencode")
        assert result is not None
        assert result["input_tokens"] == 400

    def test_opencode_no_tokens_returns_none(self):
        data = json.dumps({"some_other": "data"})
        assert BudgetService.extract_token_usage(data, "opencode") is None


class TestTryParseJson:
    def test_valid_json(self):
        assert BudgetService._try_parse_json('{"a": 1}') == {"a": 1}

    def test_invalid_json(self):
        assert BudgetService._try_parse_json("not json") is None

    def test_non_dict_json(self):
        assert BudgetService._try_parse_json("[1,2,3]") is None


class TestFindLastJsonObject:
    def test_finds_json_in_mixed_text(self):
        text = 'Debug line\nMore debug\n{"key": "value"}\ntrailing'
        result = BudgetService._find_last_json_object(text)
        assert result == {"key": "value"}

    def test_no_json_returns_none(self):
        assert BudgetService._find_last_json_object("no json here") is None

    def test_nested_json(self):
        text = '{"outer": {"inner": 1}}'
        result = BudgetService._find_last_json_object(text)
        assert result == {"outer": {"inner": 1}}


class TestEstimateCost:
    def test_basic_estimate(self, isolated_db):
        result = BudgetService.estimate_cost("Hello world", model="claude-sonnet-4")
        assert result["estimated_input_tokens"] > 0
        assert result["estimated_output_tokens"] == 2000  # default
        assert result["confidence"] == "low"
        assert result["model"] == "claude-sonnet-4"
        assert result["estimated_cost_usd"] > 0

    def test_estimate_with_opus_model(self, isolated_db):
        prompt = "x" * 400  # ~100 tokens
        result_opus = BudgetService.estimate_cost(prompt, model="claude-opus-4-6")
        result_sonnet = BudgetService.estimate_cost(prompt, model="claude-sonnet-4")
        # Opus should be more expensive
        assert result_opus["estimated_cost_usd"] > result_sonnet["estimated_cost_usd"]


class TestCheckBudget:
    def test_no_limits_configured(self, isolated_db):
        result = BudgetService.check_budget("trigger", "trig-nonexistent")
        assert result["allowed"] is True
        assert result["reason"] == "no_limits"

    def test_check_execution_time_no_limit(self, isolated_db):
        assert BudgetService.check_execution_time_limit("trigger", "trig-none", 9999) is False


class TestModelPricing:
    def test_all_models_have_required_keys(self):
        for model, pricing in BudgetService.MODEL_PRICING.items():
            assert "input" in pricing, f"{model} missing input price"
            assert "output" in pricing, f"{model} missing output price"
            assert "cache_read" in pricing, f"{model} missing cache_read price"
            assert pricing["input"] > 0
            assert pricing["output"] > 0
