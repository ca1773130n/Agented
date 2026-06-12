"""Renderer interface shared by all backend-specific renderers."""

from __future__ import annotations

from typing import Protocol

from ..context_compiler_service import ContextBundle


class Renderer(Protocol):
    """Translate a ``ContextBundle`` into backend-specific mutations.

    ``apply`` returns the (possibly modified) cmd list and env dict.
    Returning the inputs unchanged is a valid no-op for empty
    bundles.
    """

    def apply(
        self,
        cmd: list[str],
        env: dict,
        bundle: ContextBundle,
        session_id: str,
    ) -> tuple[list[str], dict]: ...


def subagent_prompt_block(bundle: ContextBundle) -> str:
    """Build the degrade-path sub-agent block for backends with no native
    sub-agent concept (codex/gemini/opencode).

    claude does NOT use this — it discovers sub-agents natively from the
    overlay's ``agents/`` dir, so inlining the body in its system prompt would
    duplicate it. The block is deterministic: sub-agents are emitted in the
    order they were resolved, each as a named ``--- Sub-agent: <name> ---``
    section. Returns ``""`` when no sub-agents are bound.
    """
    if not bundle.subagents:
        return ""
    parts: list[str] = ["=== Sub-agents ==="]
    for sa in bundle.subagents:
        name = sa.get("name") or "unnamed"
        body = (sa.get("body") or "").strip()
        parts.append(f"--- Sub-agent: {name} ---\n{body}")
    return "\n\n".join(parts)


def prepend_to_trailing_prompt(cmd: list[str], text: str) -> list[str]:
    """Splice ``text`` above the trailing positional prompt arg. Shared by
    codex/opencode (trailing-arg backends).

    Returns cmd unchanged when there is nothing to add or the tail isn't a
    free-form prompt arg.
    """
    if not text or not cmd:
        return cmd
    last = cmd[-1]
    if not isinstance(last, str) or last.startswith("-"):
        return cmd
    return [*cmd[:-1], f"{text}\n\n{last}"]


def universal_prompt_prepend(cmd: list[str], bundle: ContextBundle) -> list[str]:
    """Splice ``bundle.prompt_prepend`` into the last argument of cmd
    when that argument looks like a free-form prompt.

    Recognised shapes:
      * ``[..., "-p", "<prompt>"]`` — the universal short-form
      * ``[..., "exec", ..., "<prompt>"]`` (codex) — last arg is the prompt
      * any cmd whose last element is a non-flag string

    Returns the (possibly mutated) cmd. If no plausible prompt arg
    exists (e.g. ``claude --print --input-format stream-json``
    where the prompt arrives over stdin), returns cmd unchanged —
    the caller is expected to splice into stdin instead.
    """
    return prepend_to_trailing_prompt(cmd, bundle.prompt_prepend)
