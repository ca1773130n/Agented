"""Tests for PromptRenderer — placeholder substitution and unresolved warnings."""

import logging
from unittest.mock import patch

import pytest

from app.services.prompt_renderer import PromptRenderer


class TestRender:
    def _trigger(self, template, **kwargs):
        t = {"prompt_template": template}
        t.update(kwargs)
        return t

    def test_basic_substitution(self):
        trigger = self._trigger("Hello {trigger_id}, paths: {paths}, msg: {message}")
        result = PromptRenderer.render(trigger, "trg-001", "test msg", "/a,/b")
        assert result == "Hello trg-001, paths: /a,/b, msg: test msg"

    def test_bot_id_legacy_alias(self):
        trigger = self._trigger("Bot {bot_id} running")
        result = PromptRenderer.render(trigger, "trg-002", "", "")
        assert result == "Bot trg-002 running"

    def test_github_pr_placeholders(self):
        trigger = self._trigger("Review PR #{pr_number} by {pr_author}: {pr_url}")
        event = {
            "type": "github_pr",
            "pr_number": 42,
            "pr_author": "octocat",
            "pr_url": "https://github.com/org/repo/pull/42",
            "pr_title": "Fix bug",
            "repo_url": "https://github.com/org/repo.git",
            "repo_full_name": "org/repo",
        }
        result = PromptRenderer.render(trigger, "trg-003", "", "", event=event)
        assert "PR #42" in result
        assert "octocat" in result
        assert "https://github.com/org/repo/pull/42" in result

    def test_github_pr_missing_fields_default_empty(self):
        trigger = self._trigger("{pr_title} by {pr_author}")
        event = {"type": "github_pr"}  # No PR fields
        result = PromptRenderer.render(trigger, "trg-004", "", "", event=event)
        assert result == " by "

    def test_non_github_event_leaves_pr_placeholders(self):
        trigger = self._trigger("{pr_url} should remain")
        event = {"type": "webhook"}
        result = PromptRenderer.render(trigger, "trg-005", "", "", event=event)
        assert "{pr_url}" in result

    def test_no_event_leaves_pr_placeholders(self):
        trigger = self._trigger("{pr_url} untouched")
        result = PromptRenderer.render(trigger, "trg-006", "", "")
        assert "{pr_url}" in result

    def test_skill_command_prepended(self):
        trigger = self._trigger("do stuff", skill_command="/audit")
        result = PromptRenderer.render(trigger, "trg-007", "", "")
        assert result.startswith("/audit ")

    def test_skill_command_not_duplicated(self):
        trigger = self._trigger("/audit do stuff", skill_command="/audit")
        result = PromptRenderer.render(trigger, "trg-008", "", "")
        assert result == "/audit do stuff"
        assert result.count("/audit") == 1

    def test_empty_template(self):
        trigger = self._trigger("")
        result = PromptRenderer.render(trigger, "trg-009", "", "")
        assert result == ""

    def test_no_placeholders_passthrough(self):
        trigger = self._trigger("Static prompt with no variables")
        result = PromptRenderer.render(trigger, "trg-010", "msg", "/path")
        assert result == "Static prompt with no variables"

    def test_multiple_occurrences_of_same_placeholder(self):
        trigger = self._trigger("{message} then {message} again")
        result = PromptRenderer.render(trigger, "trg-011", "hello", "")
        assert result == "hello then hello again"

    @patch("app.services.prompt_renderer.SnippetService.resolve_snippets", return_value="resolved")
    def test_snippets_resolved_before_placeholders(self, mock_resolve):
        trigger = self._trigger("{{my_snippet}} {trigger_id}")
        result = PromptRenderer.render(trigger, "trg-012", "", "")
        mock_resolve.assert_called_once()

    def test_message_with_braces(self):
        """Message containing literal braces should not cause errors."""
        trigger = self._trigger("Input: {message}")
        result = PromptRenderer.render(trigger, "trg-013", "json: {key: value}", "")
        assert result == "Input: json: {key: value}"


class TestSubagentRendererProjection:
    """4-backend golden parity for a bound sub-agent (success criterion #1,
    renderer half). claude discovers sub-agents natively (no inline body);
    codex/gemini/opencode emit a named prompt-prefix block. Deterministic."""

    def _bundle(self):
        from app.services.context_compiler_service import ContextBundle

        return ContextBundle(
            subagents=[{"name": "code-reviewer", "body": "Review code for bugs."}],
            overlay_files={"agents/code-reviewer.md": "Review code for bugs."},
        )

    def test_claude_does_not_inline_subagent_body(self):
        from app.services.context_renderers.claude import ClaudeRenderer

        cmd = ["claude", "-p", "do the task"]
        new_cmd, _ = ClaudeRenderer().apply(cmd, {}, self._bundle(), "sess-1")
        joined = "\n".join(new_cmd)
        # Native discovery: body must NOT be inlined into the system prompt.
        assert "Review code for bugs." not in joined
        # The native agents/ file rides in the overlay (overlay_files), not the cmd.
        assert "agents/code-reviewer.md" in self._bundle().overlay_files

    def test_codex_emits_named_block(self):
        from app.services.context_renderers.codex import CodexRenderer

        cmd = ["codex", "exec", "do the task"]
        new_cmd, _ = CodexRenderer().apply(cmd, {}, self._bundle(), "sess-1")
        last = new_cmd[-1]
        assert "=== Sub-agents ===" in last
        assert "Sub-agent: code-reviewer" in last
        assert "Review code for bugs." in last
        assert last.endswith("do the task")

    def test_opencode_emits_named_block(self):
        from app.services.context_renderers.opencode import OpencodeRenderer

        cmd = ["opencode", "run", "--format", "json", "do the task"]
        new_cmd, _ = OpencodeRenderer().apply(cmd, {}, self._bundle(), "sess-1")
        last = new_cmd[-1]
        assert "Sub-agent: code-reviewer" in last
        assert "Review code for bugs." in last

    def test_gemini_emits_named_block(self):
        from app.services.context_renderers.gemini import GeminiRenderer

        cmd = ["gemini", "-p", "do the task"]
        new_cmd, _ = GeminiRenderer().apply(cmd, {}, self._bundle(), "sess-1")
        idx = new_cmd.index("-p") + 1
        prompt = new_cmd[idx]
        assert "Sub-agent: code-reviewer" in prompt
        assert "Review code for bugs." in prompt

    @pytest.mark.parametrize(
        "renderer_path,cmd",
        [
            ("codex", ["codex", "exec", "task"]),
            ("opencode", ["opencode", "run", "task"]),
            ("gemini", ["gemini", "-p", "task"]),
            ("claude", ["claude", "-p", "task"]),
        ],
    )
    def test_subagent_projection_is_deterministic(self, renderer_path, cmd):
        import importlib

        mod = importlib.import_module(
            f"app.services.context_renderers.{renderer_path}"
        )
        cls = getattr(mod, f"{renderer_path.capitalize()}Renderer")
        out1, _ = cls().apply(list(cmd), {}, self._bundle(), "sess-1")
        out2, _ = cls().apply(list(cmd), {}, self._bundle(), "sess-1")
        assert out1 == out2


class TestWarnUnresolved:
    def test_no_warnings_when_fully_resolved(self):
        mock_logger = logging.getLogger("test.no_warn")
        with patch.object(mock_logger, "warning") as mock_warn:
            PromptRenderer.warn_unresolved("Fully resolved prompt", "test-trigger", mock_logger)
            mock_warn.assert_not_called()

    def test_warns_unknown_placeholders(self):
        mock_logger = logging.getLogger("test.unknown")
        with patch.object(mock_logger, "warning") as mock_warn:
            PromptRenderer.warn_unresolved(
                "Prompt with {custom_field}", "test-trigger", mock_logger
            )
            mock_warn.assert_called_once()
            assert "unknown" in mock_warn.call_args[0][0].lower()
            assert "custom_field" in str(mock_warn.call_args)

    def test_warns_known_unresolved(self):
        mock_logger = logging.getLogger("test.known")
        with patch.object(mock_logger, "warning") as mock_warn:
            PromptRenderer.warn_unresolved("Still has {message}", "test-trigger", mock_logger)
            mock_warn.assert_called_once()
            assert "known but unresolved" in mock_warn.call_args[0][0].lower()

    def test_separates_known_and_unknown(self):
        mock_logger = logging.getLogger("test.both")
        with patch.object(mock_logger, "warning") as mock_warn:
            PromptRenderer.warn_unresolved(
                "Has {message} and {custom_var}", "test-trigger", mock_logger
            )
            assert mock_warn.call_count == 2
