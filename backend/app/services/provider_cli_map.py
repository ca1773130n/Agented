"""provider-kind → LLM CLI argv template.

Canonical taxonomy: provider-kind (anthropic/openai/gemini/ollama) — see
docs/superpowers/specs/2026-05-29-life-harness-completion-design.md
reconciliation #3. Phase A owns this; when Phase C ships, the same
``resolve_llm_cmd`` moves to harness_evolution_eval.py and callers update
their import only. Templates carry a ``{PROMPT}`` placeholder substituted by
the caller (same convention as the existing _llm_codex_cmd()).
"""
from __future__ import annotations

import os
import shlex

SUPPORTED_PROVIDER_KINDS = ("anthropic", "openai", "gemini", "ollama")

_DEFAULT_TEMPLATES: dict[str, list[str]] = {
    "anthropic": ["claude", "-p", "{PROMPT}"],
    "openai": ["codex", "exec", "--skip-git-repo-check", "{PROMPT}"],
    "gemini": ["gemini", "-p", "{PROMPT}"],
    "ollama": ["ollama", "run", "{MODEL}", "{PROMPT}"],
}

_DEFAULT_MODELS: dict[str, str] = {"ollama": "llama3"}


def resolve_llm_cmd(provider_kind: str, model_override: str | None = None) -> list[str]:
    """Return the argv template (with ``{PROMPT}``) for a provider kind.

    Per-provider override via ``AGENTED_TAKEAWAY_<PROVIDER>_CMD`` (e.g.
    ``AGENTED_TAKEAWAY_ANTHROPIC_CMD``). ``{MODEL}`` in a template is filled
    from ``model_override`` or the provider default.
    """
    if provider_kind not in _DEFAULT_TEMPLATES:
        raise ValueError(f"unknown provider_kind: {provider_kind!r}")

    override = os.environ.get(f"AGENTED_TAKEAWAY_{provider_kind.upper()}_CMD")
    if override:
        try:
            template = shlex.split(override)
        except ValueError:
            template = list(_DEFAULT_TEMPLATES[provider_kind])
    else:
        template = list(_DEFAULT_TEMPLATES[provider_kind])

    model = model_override or _DEFAULT_MODELS.get(provider_kind)
    if model is not None:
        template = [model if part == "{MODEL}" else part for part in template]
    return template
