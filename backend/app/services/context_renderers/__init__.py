"""Backend-specific renderers for ``ContextBundle``.

Each renderer takes a (cmd, env, bundle, session_id) tuple and
returns mutated (cmd, env). Backends not yet wired return the
inputs unchanged so the harness keeps spawning as before.
"""

from __future__ import annotations

from typing import Optional

from ..context_compiler_service import ContextBundle
from .base import Renderer
from .claude import ClaudeRenderer
from .codex import CodexRenderer
from .gemini import GeminiRenderer
from .opencode import OpencodeRenderer

_REGISTRY: dict[str, Renderer] = {
    "claude": ClaudeRenderer(),
    "codex": CodexRenderer(),
    "gemini": GeminiRenderer(),
    "opencode": OpencodeRenderer(),
}


def renderer_for(backend: str) -> Optional[Renderer]:
    return _REGISTRY.get((backend or "").lower())


__all__ = [
    "ContextBundle",
    "Renderer",
    "ClaudeRenderer",
    "CodexRenderer",
    "GeminiRenderer",
    "OpencodeRenderer",
    "renderer_for",
]
