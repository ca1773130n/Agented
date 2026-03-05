"""Smart context chunking with code-aware splitting and deduplication.

Splits large code contexts (>100KB) at semantic boundaries (class/function
definitions), runs bot against each chunk independently, and merges
deduplicated results.

Based on 08-RESEARCH.md Recommendation 3: Code-aware recursive character
splitting at 400-512 tokens per Pinecone/LangCopilot recommendations.
Deduplication uses normalized string matching per NAACL 2025 Findings.
"""

import logging
import re

logger = logging.getLogger(__name__)


class ChunkService:
    """Code-aware content chunking with merge and deduplication."""

    # Separators in priority order (most semantic -> least semantic)
    # Per 08-RESEARCH.md Recommendation 3 (Pinecone/LangCopilot)
    CODE_SEPARATORS = [
        "\nclass ",  # Class boundaries
        "\ndef ",  # Function boundaries
        "\nasync def ",  # Async function boundaries
        "\n\n\n",  # Triple newlines (major sections)
        "\n\n",  # Double newlines (paragraph/block boundaries)
        "\n",  # Single newlines (line boundaries)
    ]

    MAX_CHUNK_CHARS = 2000  # ~500 tokens at 4 chars/token
    OVERLAP_CHARS = 200  # ~10% overlap for context continuity
    SIZE_THRESHOLD = 102400  # 100KB threshold for triggering chunking

    @classmethod
    def chunk_code(cls, content: str, max_chars: int | None = None) -> list[str]:
        """Split content into semantically meaningful chunks at code boundaries.

        Args:
            content: The source code or text to chunk.
            max_chars: Maximum characters per chunk (default MAX_CHUNK_CHARS).

        Returns:
            List of chunk strings. Single-element list if content is small.
        """
        use_default = max_chars is None
        if max_chars is None:
            max_chars = cls.MAX_CHUNK_CHARS

        # Small content: no chunking needed (only when using default max_chars)
        if use_default and len(content) <= cls.SIZE_THRESHOLD:
            return [content]

        preamble = cls._extract_preamble(content)

        # Try each separator in priority order
        for separator in cls.CODE_SEPARATORS:
            chunks = cls._split_with_separator(content, separator, max_chars, preamble)
            if chunks is not None:
                return chunks

        # Fallback: character-limit splitting
        return cls._split_by_char_limit(content, max_chars, preamble)

    @classmethod
    def _extract_preamble(cls, content: str) -> str:
        """Extract import lines and module-level docstrings from the beginning.

        Per 08-RESEARCH.md Pitfall 2: Include import statements and file headers
        in chunk preambles for context continuity.

        Args:
            content: Full source code content.

        Returns:
            Preamble string to prepend to each chunk.
        """
        lines = content.split("\n")
        preamble_lines = []
        in_docstring = False

        for line in lines:
            stripped = line.strip()

            # Track module-level docstrings
            if not in_docstring and (stripped.startswith('"""') or stripped.startswith("'''")):
                preamble_lines.append(line)
                # Single-line docstring
                if stripped.count('"""') >= 2 or stripped.count("'''") >= 2:
                    continue
                in_docstring = True
                continue
            if in_docstring:
                preamble_lines.append(line)
                if '"""' in stripped or "'''" in stripped:
                    in_docstring = False
                continue

            # Import lines
            if stripped.startswith(("import ", "from ")):
                preamble_lines.append(line)
                continue

            # Comments at top of file
            if stripped.startswith("#") and not preamble_lines or (
                preamble_lines
                and all(
                    pl.strip().startswith(("#", "import ", "from ", '"""', "'''")) or not pl.strip()
                    for pl in preamble_lines
                )
                and stripped.startswith("#")
            ):
                preamble_lines.append(line)
                continue

            # Empty lines between imports
            if not stripped and preamble_lines:
                preamble_lines.append(line)
                continue

            # Stop at first non-import, non-comment, non-empty line
            if stripped and not stripped.startswith(("#", "import ", "from ")):
                break

        # Trim trailing empty lines from preamble
        while preamble_lines and not preamble_lines[-1].strip():
            preamble_lines.pop()

        return "\n".join(preamble_lines) if preamble_lines else ""

    @classmethod
    def _split_with_separator(
        cls, content: str, separator: str, max_chars: int, preamble: str
    ) -> list[str] | None:
        """Try splitting content using a specific separator.

        Returns None if any resulting chunk exceeds max_chars (need finer separator).
        """
        parts = content.split(separator)
        if len(parts) <= 1:
            return None

        # Re-attach the separator to each part (except the first)
        parts_with_sep = [parts[0]]
        for part in parts[1:]:
            parts_with_sep.append(separator.lstrip("\n") + part)

        # Merge small parts into chunks up to max_chars
        chunks = []
        current_chunk = ""

        for part in parts_with_sep:
            # If a single part exceeds max_chars, this separator is too coarse
            if len(part) > max_chars and separator != "\n":
                return None

            if not current_chunk:
                current_chunk = part
            elif len(current_chunk) + len(separator) + len(part) <= max_chars:
                current_chunk += "\n" + part
            else:
                chunks.append(current_chunk)
                current_chunk = part

        if current_chunk:
            chunks.append(current_chunk)

        if len(chunks) <= 1:
            return None

        # Add overlap and preamble
        return cls._add_overlap_and_preamble(chunks, preamble)

    @classmethod
    def _split_by_char_limit(
        cls, content: str, max_chars: int, preamble: str
    ) -> list[str]:
        """Fallback: split content at character boundaries."""
        preamble_len = len(preamble) + 1 if preamble else 0  # +1 for newline
        effective_max = max_chars - preamble_len

        if effective_max <= 0:
            effective_max = max_chars

        chunks = []
        start = 0
        while start < len(content):
            end = start + effective_max
            if end < len(content):
                # Try to break at a newline
                newline_pos = content.rfind("\n", start, end)
                if newline_pos > start:
                    end = newline_pos + 1
            chunk_text = content[start:end]
            if preamble and not chunk_text.startswith(preamble[:50]):
                chunk_text = preamble + "\n" + chunk_text
            chunks.append(chunk_text)
            start = end

        return chunks

    @classmethod
    def _add_overlap_and_preamble(cls, chunks: list[str], preamble: str) -> list[str]:
        """Add overlap between consecutive chunks and prepend preamble.

        Args:
            chunks: Raw split chunks.
            preamble: Import/header preamble to prepend.

        Returns:
            Chunks with overlap and preamble added.
        """
        result = []
        for i, chunk in enumerate(chunks):
            parts = []

            # Add preamble if chunk doesn't already contain it
            if preamble and not chunk.strip().startswith(preamble.strip()[:50]):
                parts.append(preamble)

            # Add overlap from end of previous chunk (except for first chunk)
            # Cap overlap at ~10% of chunk size to avoid excessive growth
            overlap_chars = min(cls.OVERLAP_CHARS, len(chunk) // 5)
            if i > 0 and overlap_chars > 0:
                prev = chunks[i - 1]
                overlap_text = prev[-overlap_chars:]
                # Try to start overlap at a line boundary
                newline_pos = overlap_text.find("\n")
                if newline_pos >= 0:
                    overlap_text = overlap_text[newline_pos + 1 :]
                if overlap_text.strip():
                    parts.append("# ... (context from previous chunk)")
                    parts.append(overlap_text)

            parts.append(chunk)
            result.append("\n".join(parts))

        return result

    @classmethod
    def deduplicate_findings(cls, findings: list[str]) -> list[str]:
        """Remove duplicate findings using normalized string matching.

        Normalization: lowercase, strip whitespace, replace line number
        references with a placeholder so 'line 42' and 'line 99' match.

        Per 08-RESEARCH.md Open Question 2: Start with normalized string
        matching. Add semantic dedup only if testing reveals significant
        paraphrased duplicates.

        Args:
            findings: List of finding strings from chunk outputs.

        Returns:
            Deduplicated list preserving first-occurrence order.
        """
        seen: set[str] = set()
        unique: list[str] = []

        for finding in findings:
            normalized = cls._normalize_finding(finding)
            if normalized not in seen:
                seen.add(normalized)
                unique.append(finding)

        return unique

    @classmethod
    def _normalize_finding(cls, finding: str) -> str:
        """Normalize a finding string for deduplication comparison."""
        text = finding.lower().strip()
        # Replace line number references: "line 42" -> "line N"
        text = re.sub(r"\bline \d+\b", "line N", text)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text)
        return text

    @classmethod
    def merge_chunk_results(cls, chunk_results: list[dict]) -> dict:
        """Merge and deduplicate results from multiple chunk executions.

        Args:
            chunk_results: List of dicts with 'bot_output' and 'chunk_index' keys.

        Returns:
            MergedChunkResults-shaped dict with stats and deduplicated findings.
        """
        all_findings: list[str] = []

        for result in sorted(chunk_results, key=lambda r: r.get("chunk_index", 0)):
            bot_output = result.get("bot_output", "")
            if not bot_output:
                continue
            # Split output into individual findings (non-empty lines)
            lines = [line.strip() for line in bot_output.split("\n") if line.strip()]
            all_findings.extend(lines)

        unique_findings = cls.deduplicate_findings(all_findings)
        duplicate_count = len(all_findings) - len(unique_findings)

        merged_output = "\n".join(unique_findings)

        return {
            "total_chunks": len(chunk_results),
            "unique_findings": unique_findings,
            "duplicate_count": duplicate_count,
            "merged_output": merged_output,
            "chunk_results": chunk_results,
        }
