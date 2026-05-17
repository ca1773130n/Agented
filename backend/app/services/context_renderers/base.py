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
    if not bundle.prompt_prepend or not cmd:
        return cmd
    last = cmd[-1]
    if not isinstance(last, str) or last.startswith("-"):
        return cmd
    # Avoid eating subcommands ("claude", "codex", "exec").
    if len(cmd) >= 2 and not cmd[-2].startswith("-"):
        # codex exec <prompt>: -2 is "exec" (a subcommand) — still
        # OK to prepend.
        pass
    new_last = f"{bundle.prompt_prepend}\n\n{last}"
    return [*cmd[:-1], new_last]
