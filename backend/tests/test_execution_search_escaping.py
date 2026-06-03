"""Regression: FTS snippet output must be HTML-escaped (XSS, C1).

The frontend renders stdout_match/stderr_match via v-html, so agent-controlled
log text must never reach the DOM as live markup — only the <mark> highlight
delimiters survive escaping.
"""

from app.services.execution_search_service import ExecutionSearchService as S


def test_escape_neutralizes_html_keeps_marks():
    row = {
        "stdout_match": f"before {S._MARK_OPEN}<img src=x onerror=alert(1)>{S._MARK_CLOSE} after",
        "stderr_match": None,
    }
    out = S._escape_snippets(row)
    val = out["stdout_match"]
    # The injected tag is escaped, not live.
    assert "<img" not in val
    assert "&lt;img" in val
    assert "onerror" in val  # text preserved, just inert
    # The highlight delimiters are restored to real <mark> tags.
    assert "<mark>" in val and "</mark>" in val
    assert S._MARK_OPEN not in val and S._MARK_CLOSE not in val


def test_escape_handles_ampersand_and_none():
    row = {"stdout_match": "a & b < c > d", "stderr_match": None}
    out = S._escape_snippets(row)
    assert out["stdout_match"] == "a &amp; b &lt; c &gt; d"
    assert out["stderr_match"] is None
