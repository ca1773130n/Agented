"""Tests for BackendDetectionService, multi-backend token extraction, command building, and rate limits."""

import json
import subprocess
from unittest.mock import MagicMock, patch

from app.services.backend_detection_service import (
    detect_backend,
    get_all_backends_status,
    get_capabilities,
)
from app.services.budget_service import BudgetService
from app.services.execution_service import ExecutionService
from app.services.rate_limit_service import RateLimitService

# =============================================================================
# BackendDetectionService.detect_backend() tests
# =============================================================================


class TestDetectBackend:
    """Tests for detect_backend()."""

    @patch("app.services.backend_detection_service.subprocess.run")
    @patch("app.services.backend_detection_service.shutil.which")
    def test_detect_installed_backend(self, mock_which, mock_run):
        """Installed backend returns (True, version, cli_path)."""
        mock_which.return_value = "/usr/bin/claude"
        mock_run.return_value = MagicMock(stdout="2.1.39 (Claude Code)\n", stderr="")

        installed, version, cli_path = detect_backend("claude")

        assert installed is True
        assert version == "2.1.39 (Claude Code)"
        assert cli_path == "/usr/bin/claude"
        mock_which.assert_called_once_with("claude")

    @patch("app.services.backend_detection_service.shutil.which")
    def test_detect_uninstalled_backend(self, mock_which):
        """Uninstalled backend returns (False, None, None)."""
        mock_which.return_value = None

        installed, version, cli_path = detect_backend("nonexistent")

        assert installed is False
        assert version is None
        assert cli_path is None

    @patch("app.services.backend_detection_service.subprocess.run")
    @patch("app.services.backend_detection_service.shutil.which")
    def test_detect_backend_timeout(self, mock_which, mock_run):
        """Timeout returns (True, 'unknown (timeout)', cli_path)."""
        mock_which.return_value = "/usr/bin/codex"
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="codex --version", timeout=5)

        installed, version, cli_path = detect_backend("codex")

        assert installed is True
        assert version == "unknown (timeout)"
        assert cli_path == "/usr/bin/codex"

    @patch("app.services.backend_detection_service.subprocess.run")
    @patch("app.services.backend_detection_service.shutil.which")
    def test_detect_backend_error(self, mock_which, mock_run):
        """Generic error returns (True, 'unknown', cli_path)."""
        mock_which.return_value = "/usr/local/bin/gemini"
        mock_run.side_effect = OSError("Permission denied")

        installed, version, cli_path = detect_backend("gemini")

        assert installed is True
        assert version == "unknown"
        assert cli_path == "/usr/local/bin/gemini"

    @patch("app.services.backend_detection_service.subprocess.run")
    @patch("app.services.backend_detection_service.shutil.which")
    def test_detect_backend_empty_stdout_uses_stderr(self, mock_which, mock_run):
        """When stdout is empty, version is extracted from stderr."""
        mock_which.return_value = "/usr/bin/opencode"
        mock_run.return_value = MagicMock(stdout="", stderr="opencode v1.2.3\n")

        installed, version, cli_path = detect_backend("opencode")

        assert installed is True
        assert version == "opencode v1.2.3"
        assert cli_path == "/usr/bin/opencode"


# =============================================================================
# BackendDetectionService.get_capabilities() tests
# =============================================================================


class TestGetCapabilities:
    """Tests for get_capabilities()."""

    def test_capabilities_claude(self):
        caps = get_capabilities("claude")
        assert caps is not None
        assert caps.supports_json_output is True
        assert caps.supports_token_usage is True
        assert caps.supports_streaming is True
        assert caps.supports_non_interactive is True
        assert caps.json_output_flag == "--output-format json"
        assert caps.non_interactive_flag == "-p"

    def test_capabilities_opencode(self):
        caps = get_capabilities("opencode")
        assert caps is not None
        assert caps.supports_json_output is True
        assert caps.json_output_flag == "--format json"
        assert caps.non_interactive_flag == "run"

    def test_capabilities_gemini(self):
        caps = get_capabilities("gemini")
        assert caps is not None
        assert caps.supports_json_output is True
        assert caps.supports_token_usage is True
        assert caps.json_output_flag == "--output-format json"
        assert caps.non_interactive_flag == "-p"

    def test_capabilities_codex(self):
        caps = get_capabilities("codex")
        assert caps is not None
        assert caps.supports_json_output is True
        assert caps.supports_token_usage is True
        assert caps.json_output_flag == "--json"
        assert caps.non_interactive_flag == "exec"

    def test_capabilities_unknown(self):
        caps = get_capabilities("unknown_backend")
        assert caps is None


# =============================================================================
# BackendDetectionService.get_all_backends_status() tests
# =============================================================================


class TestGetAllBackendsStatus:
    """Tests for get_all_backends_status()."""

    @patch("app.services.backend_detection_service.detect_backend")
    def test_returns_all_four_backends(self, mock_detect):
        mock_detect.return_value = (False, None, None)

        results = get_all_backends_status()

        assert len(results) == 4
        types = [r["type"] for r in results]
        assert "claude" in types
        assert "opencode" in types
        assert "gemini" in types
        assert "codex" in types

    @patch("app.services.backend_detection_service.detect_backend")
    def test_includes_capabilities(self, mock_detect):
        mock_detect.return_value = (True, "1.0.0", "/usr/bin/test")

        results = get_all_backends_status()
        for result in results:
            assert "capabilities" in result
            assert "supports_json_output" in result["capabilities"]


# =============================================================================
# BudgetService token extraction tests
# =============================================================================


class TestBudgetServiceTokenExtraction:
    """Tests for multi-backend token extraction in BudgetService."""

    def test_extract_claude_usage(self):
        """Claude JSON output with usage section extracts correctly."""
        claude_json = json.dumps(
            {
                "usage": {
                    "input_tokens": 500,
                    "output_tokens": 200,
                    "cache_read_input_tokens": 100,
                    "cache_creation_input_tokens": 50,
                },
                "total_cost_usd": 0.0123,
                "num_turns": 1,
                "duration_api_ms": 3000,
                "session_id": "sess-123",
            }
        )

        result = BudgetService.extract_token_usage(claude_json, "claude")

        assert result is not None
        assert result["input_tokens"] == 500
        assert result["output_tokens"] == 200
        assert result["cache_read_tokens"] == 100
        assert result["cache_creation_tokens"] == 50
        assert result["total_cost_usd"] == 0.0123
        assert result["source"] == "cli_output"

    def test_extract_gemini_usage(self):
        """Gemini JSON output with stats.models.*.tokens extracts correctly."""
        gemini_json = json.dumps(
            {
                "stats": {
                    "models": {
                        "gemini-2.0-flash": {
                            "tokens": {
                                "prompt": 100,
                                "candidates": 50,
                                "total": 150,
                                "cached": 10,
                                "thoughts": 5,
                                "tool": 0,
                            }
                        }
                    }
                }
            }
        )

        result = BudgetService.extract_token_usage(gemini_json, "gemini")

        assert result is not None
        assert result["input_tokens"] == 100
        assert result["output_tokens"] == 50
        assert result["cache_read_tokens"] == 10
        assert result["cache_creation_tokens"] == 0
        assert result["total_cost_usd"] == 0.0
        assert result["source"] == "cli_output"

    def test_extract_gemini_usage_multi_model(self):
        """Gemini output with multiple models sums token counts."""
        gemini_json = json.dumps(
            {
                "stats": {
                    "models": {
                        "gemini-2.0-flash": {
                            "tokens": {"prompt": 100, "candidates": 50, "cached": 10}
                        },
                        "gemini-1.5-pro": {
                            "tokens": {"prompt": 200, "candidates": 100, "cached": 20}
                        },
                    }
                }
            }
        )

        result = BudgetService.extract_token_usage(gemini_json, "gemini")

        assert result is not None
        assert result["input_tokens"] == 300
        assert result["output_tokens"] == 150
        assert result["cache_read_tokens"] == 30

    def test_extract_codex_usage(self):
        """Codex JSONL output with turn.completed event extracts correctly."""
        codex_jsonl = "\n".join(
            [
                json.dumps({"type": "message.start"}),
                json.dumps({"type": "message.delta", "content": "Hello"}),
                json.dumps(
                    {
                        "type": "turn.completed",
                        "usage": {
                            "input_tokens": 1000,
                            "output_tokens": 200,
                            "cached_input_tokens": 500,
                        },
                    }
                ),
            ]
        )

        result = BudgetService.extract_token_usage(codex_jsonl, "codex")

        assert result is not None
        assert result["input_tokens"] == 1000
        assert result["output_tokens"] == 200
        assert result["cache_read_tokens"] == 500
        assert result["cache_creation_tokens"] == 0
        assert result["source"] == "cli_output"

    def test_extract_codex_usage_last_event_wins(self):
        """Codex extraction uses the LAST turn.completed event."""
        codex_jsonl = "\n".join(
            [
                json.dumps(
                    {
                        "type": "turn.completed",
                        "usage": {
                            "input_tokens": 100,
                            "output_tokens": 50,
                            "cached_input_tokens": 0,
                        },
                    }
                ),
                json.dumps({"type": "message.delta"}),
                json.dumps(
                    {
                        "type": "turn.completed",
                        "usage": {
                            "input_tokens": 500,
                            "output_tokens": 150,
                            "cached_input_tokens": 200,
                        },
                    }
                ),
            ]
        )

        result = BudgetService.extract_token_usage(codex_jsonl, "codex")

        assert result is not None
        assert result["input_tokens"] == 500
        assert result["output_tokens"] == 150
        assert result["cache_read_tokens"] == 200

    def test_extract_opencode_usage_returns_none_for_unknown_format(self):
        """OpenCode parser returns None for unrecognized JSON format."""
        opencode_json = json.dumps({"some_unknown_key": "value"})

        result = BudgetService.extract_token_usage(opencode_json, "opencode")

        # MEDIUM confidence parser -- returns None if format not recognized
        assert result is None

    def test_extract_opencode_usage_with_usage_key(self):
        """OpenCode parser extracts from usage key if present."""
        opencode_json = json.dumps(
            {
                "usage": {
                    "input_tokens": 300,
                    "output_tokens": 100,
                    "cache_read_tokens": 50,
                }
            }
        )

        result = BudgetService.extract_token_usage(opencode_json, "opencode")

        assert result is not None
        assert result["input_tokens"] == 300
        assert result["output_tokens"] == 100

    def test_extract_unknown_backend_returns_none(self):
        """Unknown backend type returns None."""
        result = BudgetService.extract_token_usage('{"data": 1}', "unknown_backend")
        assert result is None

    def test_extract_empty_log(self):
        """Empty log returns None for all backends."""
        assert BudgetService.extract_token_usage("", "claude") is None
        assert BudgetService.extract_token_usage("", "gemini") is None
        assert BudgetService.extract_token_usage("", "codex") is None
        assert BudgetService.extract_token_usage("", "opencode") is None

    def test_extract_whitespace_only_log(self):
        """Whitespace-only log returns None."""
        assert BudgetService.extract_token_usage("   \n  ", "claude") is None

    def test_extract_gemini_zero_tokens_returns_none(self):
        """Gemini output with all zero tokens returns None."""
        gemini_json = json.dumps(
            {
                "stats": {
                    "models": {
                        "gemini-2.0-flash": {"tokens": {"prompt": 0, "candidates": 0, "cached": 0}}
                    }
                }
            }
        )

        result = BudgetService.extract_token_usage(gemini_json, "gemini")
        assert result is None

    def test_extract_codex_no_turn_completed_returns_none(self):
        """Codex JSONL without turn.completed event returns None."""
        codex_jsonl = "\n".join(
            [
                json.dumps({"type": "message.start"}),
                json.dumps({"type": "message.delta", "content": "Hello"}),
            ]
        )

        result = BudgetService.extract_token_usage(codex_jsonl, "codex")
        assert result is None


# =============================================================================
# ExecutionService.build_command() tests
# =============================================================================


class TestBuildCommand:
    """Tests for ExecutionService.build_command()."""

    def test_build_command_claude(self):
        """Claude command uses -p with --output-format json."""
        cmd = ExecutionService.build_command("claude", "test prompt")

        assert cmd[0] == "claude"
        assert "-p" in cmd
        assert "test prompt" in cmd
        assert "--output-format" in cmd
        idx = cmd.index("--output-format")
        assert cmd[idx + 1] == "json"

    def test_build_command_opencode(self):
        """OpenCode command uses run with positional message and --format json."""
        cmd = ExecutionService.build_command("opencode", "test prompt")

        assert cmd == ["opencode", "run", "--format", "json", "test prompt"]

    def test_build_command_gemini(self):
        """Gemini command uses -p with --output-format json."""
        cmd = ExecutionService.build_command("gemini", "test prompt")

        assert cmd == ["gemini", "-p", "test prompt", "--output-format", "json"]

    def test_build_command_gemini_with_model(self):
        """Gemini command includes --model flag when model provided."""
        cmd = ExecutionService.build_command("gemini", "test prompt", model="gemini-2.0-flash")

        assert "--model" in cmd
        assert "gemini-2.0-flash" in cmd
        assert cmd[0] == "gemini"
        assert "-p" in cmd

    def test_build_command_codex(self):
        """Codex command uses exec --json --full-auto with prompt at end."""
        cmd = ExecutionService.build_command("codex", "test prompt")

        assert cmd[0] == "codex"
        assert "exec" in cmd
        assert "--json" in cmd
        assert "--full-auto" in cmd
        # Prompt should be at the end
        assert cmd[-1] == "test prompt"

    def test_build_command_codex_with_model(self):
        """Codex command includes --model flag when model provided."""
        cmd = ExecutionService.build_command("codex", "test prompt", model="o4-mini")

        assert "--model" in cmd
        assert "o4-mini" in cmd
        # Prompt is still at the end
        assert cmd[-1] == "test prompt"

    def test_build_command_claude_with_paths(self):
        """Claude command includes --add-dir for allowed_paths."""
        cmd = ExecutionService.build_command(
            "claude", "test prompt", allowed_paths=["/project/a", "/project/b"]
        )

        assert "--add-dir" in cmd
        assert "/project/a" in cmd
        assert "/project/b" in cmd


# =============================================================================
# RateLimitService pattern tests
# =============================================================================


class TestRateLimitPatterns:
    """Tests for rate limit detection patterns for gemini and codex."""

    def test_gemini_rate_limit_patterns_exist(self):
        """Gemini patterns exist in RATE_LIMIT_PATTERNS."""
        assert "gemini" in RateLimitService.RATE_LIMIT_PATTERNS

    def test_codex_rate_limit_patterns_exist(self):
        """Codex patterns exist in RATE_LIMIT_PATTERNS."""
        assert "codex" in RateLimitService.RATE_LIMIT_PATTERNS

    def test_gemini_resource_exhausted_detection(self):
        """RESOURCE_EXHAUSTED triggers rate limit for gemini."""
        cooldown = RateLimitService.check_stderr_line(
            "Error: RESOURCE_EXHAUSTED: Quota exceeded", "gemini"
        )
        assert cooldown is not None
        assert cooldown > 0

    def test_gemini_429_detection(self):
        """HTTP 429 triggers rate limit for gemini."""
        cooldown = RateLimitService.check_stderr_line("HTTP Error 429: Too Many Requests", "gemini")
        assert cooldown is not None

    def test_codex_429_detection(self):
        """HTTP 429 triggers rate limit for codex."""
        cooldown = RateLimitService.check_stderr_line("429 Too Many Requests", "codex")
        assert cooldown is not None

    def test_codex_rate_limit_detection(self):
        """rate_limit keyword triggers rate limit for codex."""
        cooldown = RateLimitService.check_stderr_line("Error: rate_limit exceeded", "codex")
        assert cooldown is not None

    def test_no_false_positive_gemini(self):
        """Normal output does not trigger rate limit for gemini."""
        cooldown = RateLimitService.check_stderr_line(
            "Processing query with gemini-2.0-flash model", "gemini"
        )
        assert cooldown is None

    def test_no_false_positive_codex(self):
        """Normal output does not trigger rate limit for codex."""
        cooldown = RateLimitService.check_stderr_line(
            "Executing task in sandbox environment", "codex"
        )
        assert cooldown is None

    def test_gemini_quota_exceeded_detection(self):
        """Quota exceeded pattern triggers for gemini."""
        cooldown = RateLimitService.check_stderr_line(
            "Error: quota has been exceeded for this project", "gemini"
        )
        assert cooldown is not None


# =============================================================================
# VALID_BACKENDS test
# =============================================================================


class TestValidBackends:
    """Tests for VALID_BACKENDS constant."""

    def test_valid_backends_includes_four(self):
        """VALID_BACKENDS includes all 4 backend types."""
        from app.database import VALID_BACKENDS

        assert len(VALID_BACKENDS) == 4
        assert "claude" in VALID_BACKENDS
        assert "opencode" in VALID_BACKENDS
        assert "gemini" in VALID_BACKENDS
        assert "codex" in VALID_BACKENDS
