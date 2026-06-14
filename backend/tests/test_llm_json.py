"""Tests for the shared LLM-JSON extraction helper.

Reproduces err-h1xhkn: ``json.loads`` on an empty or markdown-fenced LLM
completion raises ``Expecting value: line 1 column 1 (char 0)``. The helper
must absorb those realities and return ``None`` instead of raising.
"""

from app.utils.llm_json import extract_json_object


class TestExtractJsonObject:
    def test_plain_json_object(self):
        assert extract_json_object('{"phase": "execution", "confidence": 0.9}') == {
            "phase": "execution",
            "confidence": 0.9,
        }

    def test_empty_string_returns_none(self):
        # err-h1xhkn root cause: empty content -> json.loads("") used to raise.
        assert extract_json_object("") is None

    def test_whitespace_only_returns_none(self):
        assert extract_json_object("   \n\t ") is None

    def test_none_returns_none(self):
        assert extract_json_object(None) is None

    def test_markdown_json_fence(self):
        fenced = '```json\n{"phase": "review", "confidence": 0.5}\n```'
        assert extract_json_object(fenced) == {"phase": "review", "confidence": 0.5}

    def test_bare_markdown_fence(self):
        fenced = '```\n{"shape": "task", "intent": "plan"}\n```'
        assert extract_json_object(fenced) == {"shape": "task", "intent": "plan"}

    def test_prose_preamble_and_suffix(self):
        noisy = 'Sure! Here is the classification:\n{"phase": "planning"}\nHope that helps.'
        assert extract_json_object(noisy) == {"phase": "planning"}

    def test_unparseable_returns_none(self):
        assert extract_json_object("not json at all, no braces") is None

    def test_non_object_json_returns_none(self):
        # A JSON array/scalar is valid JSON but not the object the callers expect.
        assert extract_json_object("[1, 2, 3]") is None
        assert extract_json_object("42") is None
