"""Prompt snippet resolution service.

Resolves {{snippet_name}} references in prompt templates by looking up
named snippets from the database. Supports nested snippets with circular
reference detection (max depth 5).
"""

import logging
import re

from ..db.prompt_snippets import get_snippet_by_name

logger = logging.getLogger(__name__)


class SnippetService:
    """Resolves {{snippet_name}} references in prompt text."""

    MAX_DEPTH = 5

    @classmethod
    def resolve_snippets(cls, text: str, depth: int = 0, visited: set = None) -> str:
        """Resolve all {{snippet_name}} references in the given text.

        Args:
            text: The text containing {{snippet}} references.
            depth: Current recursion depth (for nested snippets).
            visited: Set of snippet names already being resolved (cycle detection).

        Returns:
            Text with all resolvable {{snippet}} references expanded.
            Missing or circular references are left intact.
        """
        if depth >= cls.MAX_DEPTH:
            return text

        if visited is None:
            visited = set()

        def replacer(match) -> str:
            name = match.group(1)
            if name in visited:
                # Circular reference -- leave unresolved
                return match.group(0)
            snippet = get_snippet_by_name(name)
            if snippet is None:
                # Missing snippet -- leave unresolved
                return match.group(0)
            # Recursively resolve nested snippets
            new_visited = visited | {name}
            return cls.resolve_snippets(snippet["content"], depth + 1, new_visited)

        return re.sub(r"\{\{(\w[\w\-]*)\}\}", replacer, text)
