"""Labeled transcript fixtures for the repeated-request detector (Phase 22, P1/A1).

Each entry is a single user-request string. ``build_payload_text`` wraps one
into the claude-jsonl shape the fetchers produce, so a fetcher monkeypatch can
return a ``SessionPayload`` whose ``text`` drives ``detect_for_session``.

PARAPHRASES are three differently-worded variants of ONE intent ("add a dark
mode toggle"); a correct detector coalesces them into ONE signal via cosine
match. UNRELATED are two clearly distinct intents that must stay separate.
"""

from __future__ import annotations

import json

# Three paraphrases of the SAME request — should cosine-match into one signal.
# Word-order / hyphenation / phrasing variants of one intent ("add a dark mode
# toggle to the settings page"); measured pairwise MiniLM cosine 0.96-0.997,
# comfortably above the 0.83 Phase-22 threshold. (Looser synonym paraphrases —
# "can you add dark mode" / "dark-mode switch in preferences" — land at
# 0.68-0.83 and intentionally stay separate; 0.83 is a precision-first cut.)
PARAPHRASES: list[str] = [
    "add a dark mode toggle to the settings page",
    "add a dark-mode toggle to the settings screen",
    "add dark mode toggle to the settings page",
]

# Two clearly unrelated requests — must remain two distinct signals.
UNRELATED: list[str] = [
    "export the monthly revenue report as a CSV file",
    "set up nightly database backups to S3",
]

# A distinct request used to prove verbatim repeats coalesce with no embedder.
VERBATIM = "rotate the API signing keys every 90 days"


def build_payload_text(user_request: str) -> str:
    """Wrap a user-request string into a single-line claude-jsonl payload of
    ``type: user`` with a text content block — the shape the fetchers emit and
    ``_extract_user_request_text`` consumes."""
    return json.dumps(
        {
            "type": "user",
            "message": {"content": [{"type": "text", "text": user_request}]},
        }
    )
