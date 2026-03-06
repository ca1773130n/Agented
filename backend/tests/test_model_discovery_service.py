"""Tests for ModelDiscoveryService."""

import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.model_discovery_service import ModelDiscoveryService


# ---------------------------------------------------------------------------
# _group_claude_models (normalization)
# ---------------------------------------------------------------------------


class TestGroupClaudeModels:
    def test_groups_by_family_keeps_latest(self):
        raw = ["claude-opus-4-6-20250514", "claude-opus-4-5-20250101", "claude-sonnet-4-5-20250514"]
        result = ModelDiscoveryService._group_claude_models(raw)
        assert result == ["Opus 4.6", "Sonnet 4.5"]

    def test_all_three_families(self):
        raw = [
            "claude-opus-4-6-20250514",
            "claude-sonnet-4-5-20250514",
            "claude-haiku-3-5-20250101",
        ]
        result = ModelDiscoveryService._group_claude_models(raw)
        assert result == ["Opus 4.6", "Sonnet 4.5", "Haiku 3.5"]

    def test_returns_originals_when_no_match(self):
        raw = ["some-unknown-model"]
        result = ModelDiscoveryService._group_claude_models(raw)
        assert result == ["some-unknown-model"]

    def test_single_model(self):
        raw = ["claude-sonnet-4-5-20250514"]
        result = ModelDiscoveryService._group_claude_models(raw)
        assert result == ["Sonnet 4.5"]


# ---------------------------------------------------------------------------
# _filter_codex_models (normalization)
# ---------------------------------------------------------------------------


class TestFilterCodexModels:
    def test_keeps_latest_per_variant(self):
        raw = ["gpt-5-codex", "gpt-5.1-codex", "gpt-5.3-codex", "gpt-5.3-codex-spark"]
        result = ModelDiscoveryService._filter_codex_models(raw)
        assert "gpt-5.3-codex" in result
        assert "gpt-5.3-codex-spark" in result
        assert "gpt-5-codex" not in result

    def test_no_codex_models_returns_originals(self):
        raw = ["gpt-4o", "gpt-4-turbo"]
        result = ModelDiscoveryService._filter_codex_models(raw)
        assert result == raw

    def test_non_gpt_codex_models_preserved(self):
        raw = ["codex-mini-latest", "gpt-5.3-codex"]
        result = ModelDiscoveryService._filter_codex_models(raw)
        assert "codex-mini-latest" in result
        assert "gpt-5.3-codex" in result


# ---------------------------------------------------------------------------
# _filter_gemini_models (normalization)
# ---------------------------------------------------------------------------


class TestFilterGeminiModels:
    def test_keeps_latest_major_per_variant(self):
        raw = ["gemini-1.5-pro", "gemini-2.5-pro", "gemini-3-pro"]
        result = ModelDiscoveryService._filter_gemini_models(raw)
        assert result == ["gemini-3-pro"]

    def test_different_variants_kept(self):
        raw = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-3-flash-lite"]
        result = ModelDiscoveryService._filter_gemini_models(raw)
        assert len(result) == 3

    def test_non_matching_preserved(self):
        raw = ["some-other-model"]
        result = ModelDiscoveryService._filter_gemini_models(raw)
        assert result == ["some-other-model"]


# ---------------------------------------------------------------------------
# _normalize_opencode_models
# ---------------------------------------------------------------------------


class TestNormalizeOpencodeModels:
    def test_strips_proxy_providers(self):
        raw = ["anthropic/claude-sonnet-4-5", "openai/gpt-4o", "zhipu/glm-4.7-free"]
        result = ModelDiscoveryService._normalize_opencode_models(raw)
        # anthropic and openai are proxy providers, should be filtered out
        # zhipu is native, only free models kept
        assert "glm-4.7-free" in result
        assert "claude-sonnet-4-5" not in result
        assert "gpt-4o" not in result

    def test_prefers_free_models(self):
        raw = ["zhipu/glm-4.7-free", "zhipu/glm-4.7-premium"]
        result = ModelDiscoveryService._normalize_opencode_models(raw)
        assert result == ["glm-4.7-free"]

    def test_falls_back_to_native_when_no_free(self):
        raw = ["zhipu/glm-4.7-premium"]
        result = ModelDiscoveryService._normalize_opencode_models(raw)
        assert result == ["glm-4.7-premium"]


# ---------------------------------------------------------------------------
# _parse_codex_model_ids
# ---------------------------------------------------------------------------


class TestParseCodexModelIds:
    def test_extracts_gpt_codex_ids(self):
        output = "Some text gpt-5.3-codex and gpt-5.3-codex-spark here"
        result = ModelDiscoveryService._parse_codex_model_ids(output)
        assert "gpt-5.3-codex" in result
        assert "gpt-5.3-codex-spark" in result

    def test_extracts_codex_mini(self):
        output = "Available: codex-mini-latest"
        result = ModelDiscoveryService._parse_codex_model_ids(output)
        assert "codex-mini-latest" in result

    def test_empty_output(self):
        result = ModelDiscoveryService._parse_codex_model_ids("")
        assert result == set()


# ---------------------------------------------------------------------------
# _parse_codex_model_list
# ---------------------------------------------------------------------------


class TestParseCodexModelList:
    def test_parses_numbered_list(self):
        output = (
            "  1. gpt-5.3-codex (current)  Latest frontier model.\n"
            "  2. gpt-5.3-codex-spark      Ultra-fast model.\n"
        )
        result = ModelDiscoveryService._parse_codex_model_list(output)
        assert result == ["gpt-5.3-codex", "gpt-5.3-codex-spark"]

    def test_returns_none_for_no_matches(self):
        result = ModelDiscoveryService._parse_codex_model_list("no models here")
        assert result is None


# ---------------------------------------------------------------------------
# _extract_models_from_claude_history
# ---------------------------------------------------------------------------


class TestExtractModelsFromClaudeHistory:
    def test_extracts_model_ids(self, tmp_path):
        history = tmp_path / "history.jsonl"
        history.write_text(
            '{"model":"claude-opus-4-6-20250514"}\n'
            '{"model":"claude-sonnet-4-5-20250514"}\n'
        )
        result = ModelDiscoveryService._extract_models_from_claude_history(history)
        assert "claude-opus-4-6-20250514" in result
        assert "claude-sonnet-4-5-20250514" in result

    def test_returns_none_for_no_matches(self, tmp_path):
        history = tmp_path / "history.jsonl"
        history.write_text('{"message":"hello"}\n')
        result = ModelDiscoveryService._extract_models_from_claude_history(history)
        assert result is None

    def test_handles_missing_file(self, tmp_path):
        missing = tmp_path / "nonexistent.jsonl"
        result = ModelDiscoveryService._extract_models_from_claude_history(missing)
        assert result is None


# ---------------------------------------------------------------------------
# discover_models (integration-level with mocked _discover_raw)
# ---------------------------------------------------------------------------


class TestDiscoverModels:
    @patch.object(ModelDiscoveryService, "_discover_raw", return_value=[])
    def test_returns_empty_list_when_nothing_found(self, mock_raw):
        result = ModelDiscoveryService.discover_models("claude")
        assert result == []

    @patch.object(
        ModelDiscoveryService,
        "_discover_raw",
        return_value=["claude-opus-4-6-20250514", "claude-sonnet-4-5-20250514"],
    )
    def test_normalizes_claude_models(self, mock_raw):
        result = ModelDiscoveryService.discover_models("claude")
        assert result == ["Opus 4.6", "Sonnet 4.5"]

    @patch.object(ModelDiscoveryService, "_discover_raw", return_value=["gpt-5.3-codex"])
    def test_normalizes_codex_models(self, mock_raw):
        result = ModelDiscoveryService.discover_models("codex")
        assert result == ["gpt-5.3-codex"]

    @patch.object(ModelDiscoveryService, "_discover_raw", return_value=[])
    def test_unknown_backend_returns_empty(self, mock_raw):
        result = ModelDiscoveryService.discover_models("unknown")
        assert result == []


# ---------------------------------------------------------------------------
# get_default_model_id
# ---------------------------------------------------------------------------


class TestGetDefaultModelId:
    @patch.object(ModelDiscoveryService, "_discover_raw", return_value=[])
    def test_returns_none_when_no_models(self, mock_raw):
        result = ModelDiscoveryService.get_default_model_id("claude")
        assert result is None

    @patch.object(
        ModelDiscoveryService,
        "_discover_raw",
        return_value=["claude-opus-4-6-20250514", "claude-sonnet-4-5-20250514"],
    )
    def test_returns_first_for_claude(self, mock_raw):
        result = ModelDiscoveryService.get_default_model_id("claude")
        assert result == "claude-opus-4-6-20250514"

    @patch.object(
        ModelDiscoveryService,
        "_discover_raw",
        return_value=["anthropic/claude-sonnet-4-5", "zhipu/glm-4.7-free"],
    )
    def test_opencode_prefers_native_free(self, mock_raw):
        result = ModelDiscoveryService.get_default_model_id("opencode")
        assert result == "zhipu/glm-4.7-free"

    @patch.object(
        ModelDiscoveryService,
        "_discover_raw",
        return_value=["anthropic/claude-sonnet-4-5", "openai/gpt-4o"],
    )
    def test_opencode_falls_back_to_first_when_all_proxy(self, mock_raw):
        result = ModelDiscoveryService.get_default_model_id("opencode")
        assert result == "anthropic/claude-sonnet-4-5"

    @patch.object(
        ModelDiscoveryService,
        "_discover_raw",
        return_value=["zhipu/glm-4.7-premium", "zhipu/glm-4.7-free"],
    )
    def test_opencode_prefers_free_over_non_free(self, mock_raw):
        result = ModelDiscoveryService.get_default_model_id("opencode")
        assert result == "zhipu/glm-4.7-free"


# ---------------------------------------------------------------------------
# _discover_raw routing
# ---------------------------------------------------------------------------


class TestDiscoverRaw:
    @patch.object(ModelDiscoveryService, "_discover_claude_models_local", return_value=None)
    @patch.object(ModelDiscoveryService, "_discover_claude_models_pty", return_value=None)
    @patch.object(ModelDiscoveryService, "_discover_models_via_cliproxy", return_value=None)
    @patch.object(ModelDiscoveryService, "_discover_anthropic_models_via_opencode", return_value=None)
    def test_claude_returns_empty_when_all_fail(self, *mocks):
        result = ModelDiscoveryService._discover_raw("claude")
        assert result == []

    @patch.object(
        ModelDiscoveryService,
        "_discover_claude_models_local",
        return_value=["claude-opus-4-6-20250514"],
    )
    @patch.object(ModelDiscoveryService, "_discover_models_via_cliproxy", return_value=None)
    @patch.object(ModelDiscoveryService, "_discover_anthropic_models_via_opencode", return_value=None)
    def test_claude_uses_local_first(self, *mocks):
        result = ModelDiscoveryService._discover_raw("claude")
        assert "claude-opus-4-6-20250514" in result

    @patch.object(
        ModelDiscoveryService,
        "_discover_claude_models_local",
        return_value=["claude-opus-4-6-20250514"],
    )
    @patch.object(
        ModelDiscoveryService,
        "_discover_models_via_cliproxy",
        return_value=["claude-sonnet-4-5-20250514"],
    )
    @patch.object(ModelDiscoveryService, "_discover_anthropic_models_via_opencode", return_value=None)
    def test_claude_merges_extra_sources(self, *mocks):
        result = ModelDiscoveryService._discover_raw("claude")
        assert "claude-opus-4-6-20250514" in result
        assert "claude-sonnet-4-5-20250514" in result

    def test_unknown_backend_returns_empty(self):
        result = ModelDiscoveryService._discover_raw("nonexistent")
        assert result == []

    @patch.object(ModelDiscoveryService, "_discover_codex_models_binary", return_value=None)
    @patch.object(ModelDiscoveryService, "_discover_codex_models_pty", return_value=None)
    @patch.object(
        ModelDiscoveryService,
        "_discover_codex_models_local",
        return_value=["gpt-5.3-codex"],
    )
    @patch.object(ModelDiscoveryService, "_discover_models_via_cliproxy", return_value=None)
    def test_codex_fallback_chain(self, *mocks):
        result = ModelDiscoveryService._discover_raw("codex")
        assert result == ["gpt-5.3-codex"]


# ---------------------------------------------------------------------------
# _discover_claude_models_local (file-based)
# ---------------------------------------------------------------------------


class TestDiscoverClaudeModelsLocal:
    @patch.object(
        ModelDiscoveryService,
        "_get_claude_config_dirs",
    )
    def test_reads_stats_cache(self, mock_dirs, tmp_path):
        stats = tmp_path / "stats-cache.json"
        stats.write_text(json.dumps({"modelUsage": {"claude-opus-4-6-20250514": {"count": 5}}}))
        mock_dirs.return_value = [tmp_path]
        result = ModelDiscoveryService._discover_claude_models_local()
        assert result == ["claude-opus-4-6-20250514"]

    @patch.object(ModelDiscoveryService, "_get_claude_config_dirs")
    def test_falls_back_to_history(self, mock_dirs, tmp_path):
        history = tmp_path / "history.jsonl"
        history.write_text('{"model":"claude-sonnet-4-5-20250514"}\n')
        mock_dirs.return_value = [tmp_path]
        result = ModelDiscoveryService._discover_claude_models_local()
        assert result is not None
        assert "claude-sonnet-4-5-20250514" in result

    @patch.object(ModelDiscoveryService, "_get_claude_config_dirs")
    def test_returns_none_when_no_files(self, mock_dirs, tmp_path):
        mock_dirs.return_value = [tmp_path]
        result = ModelDiscoveryService._discover_claude_models_local()
        assert result is None

    @patch.object(ModelDiscoveryService, "_get_claude_config_dirs")
    def test_handles_corrupt_json(self, mock_dirs, tmp_path):
        stats = tmp_path / "stats-cache.json"
        stats.write_text("not valid json{{{")
        mock_dirs.return_value = [tmp_path]
        result = ModelDiscoveryService._discover_claude_models_local()
        assert result is None


# ---------------------------------------------------------------------------
# _discover_codex_models_local (file-based)
# ---------------------------------------------------------------------------


class TestDiscoverCodexModelsLocal:
    @patch.object(ModelDiscoveryService, "_get_codex_config_dirs")
    def test_reads_models_cache_list_format(self, mock_dirs, tmp_path):
        cache = tmp_path / "models_cache.json"
        cache.write_text(
            json.dumps(
                [{"slug": "gpt-5.3-codex", "visibility": "list"}, {"slug": "internal", "visibility": "hidden"}]
            )
        )
        mock_dirs.return_value = [tmp_path]
        result = ModelDiscoveryService._discover_codex_models_local()
        assert result == ["gpt-5.3-codex"]

    @patch.object(ModelDiscoveryService, "_get_codex_config_dirs")
    def test_reads_config_toml_fallback(self, mock_dirs, tmp_path):
        config = tmp_path / "config.toml"
        config.write_text('model = "gpt-5.3-codex"\n')
        mock_dirs.return_value = [tmp_path]
        result = ModelDiscoveryService._discover_codex_models_local()
        assert result == ["gpt-5.3-codex"]


# ---------------------------------------------------------------------------
# _discover_opencode_models_local (file-based)
# ---------------------------------------------------------------------------


class TestDiscoverOpencodeModelsLocal:
    def test_reads_config_json(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENCODE_HOME", str(tmp_path))
        config = tmp_path / "config.json"
        config.write_text(json.dumps({"model": "some-model"}))
        result = ModelDiscoveryService._discover_opencode_models_local()
        assert result == ["some-model"]

    def test_reads_config_toml(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENCODE_HOME", str(tmp_path))
        config = tmp_path / "config.toml"
        config.write_text('model = "toml-model"\n')
        result = ModelDiscoveryService._discover_opencode_models_local()
        assert result == ["toml-model"]

    def test_returns_none_when_empty(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENCODE_HOME", str(tmp_path))
        result = ModelDiscoveryService._discover_opencode_models_local()
        assert result is None


# ---------------------------------------------------------------------------
# _discover_gemini_models_local (file-based)
# ---------------------------------------------------------------------------


class TestDiscoverGeminiModelsLocal:
    @patch.object(ModelDiscoveryService, "_get_gemini_config_dirs")
    def test_reads_settings_json(self, mock_dirs, tmp_path):
        settings = tmp_path / "settings.json"
        settings.write_text(json.dumps({"model": "gemini-2.5-pro"}))
        mock_dirs.return_value = [tmp_path]
        result = ModelDiscoveryService._discover_gemini_models_local()
        assert "gemini-2.5-pro" in result

    @patch.object(ModelDiscoveryService, "_get_gemini_config_dirs")
    def test_returns_none_when_no_files(self, mock_dirs, tmp_path):
        mock_dirs.return_value = [tmp_path]
        result = ModelDiscoveryService._discover_gemini_models_local()
        assert result is None
