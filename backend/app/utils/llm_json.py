"""Robust JSON extraction from LLM completions.

LLMs are instructed to "respond with ONLY a JSON object", but in practice
they return realities that ``json.loads`` chokes on at char 0:

- empty / whitespace-only content (``json.loads("")`` ->
  ``Expecting value: line 1 column 1 (char 0)`` — this was err-h1xhkn)
- markdown code fences (```` ```json\n{...}\n``` ````)
- a prose preamble before the object ("Sure! Here is the classification: {...}")

``extract_json_object`` absorbs all of those and returns the parsed ``dict``,
or ``None`` when nothing object-shaped can be recovered. Callers that expect a
JSON object back from a model should use this instead of bare ``json.loads``.
"""

import json
import re
from typing import Optional

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def extract_json_object(content: Optional[str]) -> Optional[dict]:
    """Best-effort parse of an LLM completion into a JSON object.

    Returns the parsed ``dict`` on success, or ``None`` for empty input,
    unparseable text, or valid JSON that is not an object (arrays/scalars).
    Never raises on malformed model output.
    """
    if not content:
        return None

    text = content.strip()
    if not text:
        return None

    # Unwrap a ```json ... ``` / ``` ... ``` markdown fence if present.
    fence = _FENCE_RE.search(text)
    if fence:
        text = fence.group(1).strip()

    candidates = [text]

    # Fall back to slicing the first ``{`` to the last ``}`` so a prose
    # preamble/suffix around the object does not defeat parsing.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        sliced = text[start : end + 1]
        if sliced != text:
            candidates.append(sliced)

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        if isinstance(parsed, dict):
            return parsed

    return None
