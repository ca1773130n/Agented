import pytest

from app.services.provider_cli_map import (
    SUPPORTED_PROVIDER_KINDS,
    resolve_llm_cmd,
)


def test_supported_kinds_are_the_four_providers():
    assert set(SUPPORTED_PROVIDER_KINDS) == {"anthropic", "openai", "gemini", "ollama"}


@pytest.mark.parametrize(
    "kind, head",
    [("anthropic", "claude"), ("openai", "codex"), ("gemini", "gemini"), ("ollama", "ollama")],
)
def test_resolve_llm_cmd_head(kind, head):
    cmd = resolve_llm_cmd(kind)
    assert cmd[0] == head
    assert "{PROMPT}" in cmd


def test_resolve_llm_cmd_env_override(monkeypatch):
    monkeypatch.setenv("AGENTED_TAKEAWAY_ANTHROPIC_CMD", "claude --model opus -p {PROMPT}")
    cmd = resolve_llm_cmd("anthropic")
    assert cmd == ["claude", "--model", "opus", "-p", "{PROMPT}"]


def test_resolve_llm_cmd_unknown_raises():
    with pytest.raises(ValueError, match="unknown provider_kind"):
        resolve_llm_cmd("deepseek")
