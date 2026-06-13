"""Quality/safety guard for auto-forged skills (Phase 22, REQ-25).

Three guards the auto-skill gate (22-05) calls before any auto-apply:

- ``scan_skill_content(content)`` — FAIL-CLOSED scanner for prompt-injection,
  exfiltration, and invisible-Unicode (zero-width + bidi + word-join + tag
  chars). ANY match → unsafe. A pure function: no DB, no IO.
- ``find_duplicate_binding(name, content)`` — name-cosine dedup against bound
  skills (``user_skills``) so a near-duplicate becomes a patch-over-create.
- ``provenance_allows_overwrite(asset_id, kind, on_disk_path)`` — re-hash the
  on-disk SKILL.md and compare to the stored ``forge_origin.origin_hash``;
  divergence means the operator edited it → refuse overwrite.

Fail-closed is the contract: when in doubt, return unsafe / refuse overwrite.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

from app.db.forge_origin import get_origin
from app.db.skills import get_all_user_skills, get_user_skill_by_name
from app.utils.plugin_format import content_hash

# Hard ceiling on the size of untrusted content the scanner will regex-scan.
# Auto-forged skills are a few KB; oversized input fails closed (REQ-25).
_MAX_SCAN_LEN = 200_000


@dataclass
class ScanResult:
    """Outcome of a content safety scan. ``safe`` is True only when no
    category matched; ``reasons`` lists every triggered detector."""

    safe: bool
    reasons: list[str] = field(default_factory=list)


# --- prompt-injection: classic override directives ---------------------------
# Case-insensitive. Kept explicit and commented so the list is auditable.
_INJECTION_PATTERNS = [
    # "ignore/disregard ... (previous|prior|all|system) ... instructions"
    re.compile(
        r"\b(?:ignore|disregard|forget|override)\b[\s\S]{0,60}?"
        r"\b(?:previous|prior|earlier|all|above|system)\b[\s\S]{0,20}?"
        r"\b(?:instruction|instructions|prompt|prompts|rules?)\b",
        re.IGNORECASE,
    ),
    # "disregard the system prompt"
    re.compile(r"\b(?:ignore|disregard|bypass)\b[\s\S]{0,30}?\bsystem\s+prompt\b", re.IGNORECASE),
    # jailbreak persona toggles
    re.compile(r"\bdeveloper\s+mode\b", re.IGNORECASE),
    re.compile(r"\b(?:DAN|jailbreak|unrestricted\s+assistant)\b", re.IGNORECASE),
    # tool / hidden-prompt exfiltration directives
    re.compile(
        r"\b(?:reveal|print|output|show|dump|leak)\b[\s\S]{0,40}?"
        r"\b(?:system\s+prompt|hidden\s+(?:prompt|instructions?|tools?)|your\s+tools?)\b",
        re.IGNORECASE,
    ),
]

# --- exfiltration: send-secret-to-external-host ------------------------------
# A secret/credential reference combined with an outbound-send verb/host.
_SECRET_REF = (
    r"(?:\.env\b|env(?:ironment)?\s+(?:var|variable|secret)|"
    r"\$[A-Z_]*(?:KEY|TOKEN|SECRET|PASSWORD|CRED)[A-Z_]*|"
    r"process\.env\.[A-Za-z_]+|"
    r"\b(?:api[_\s-]?key|secret|token|password|credential)s?\b)"
)
_OUTBOUND_SEND = (
    r"(?:curl|wget|fetch\s*\(|requests\.(?:post|get)|http\.(?:post|get)|"
    r"\bPOST\b|--post-data|webhook|https?://)"
)
_EXFILTRATION_PATTERNS = [
    # send-verb / external host appearing near a secret reference, either order
    re.compile(_OUTBOUND_SEND + r"[\s\S]{0,80}?" + _SECRET_REF, re.IGNORECASE),
    re.compile(_SECRET_REF + r"[\s\S]{0,80}?" + _OUTBOUND_SEND, re.IGNORECASE),
    # explicit "send the contents of .env to <host>"
    re.compile(
        r"\bsend\b[\s\S]{0,40}?(?:\.env\b|secret|token|credential)[\s\S]{0,40}?"
        r"(?:to\b|https?://)",
        re.IGNORECASE,
    ),
]


def _invisible_unicode_reasons(content: str) -> list[str]:
    """Flag any codepoint in the invisible/format-control ranges. Fail-closed:
    a single match makes the whole content unsafe.

    Ranges:
      - U+200B–U+200F  zero-width chars + LTR/RTL marks
      - U+202A–U+202E  bidi embedding/override
      - U+2060–U+2064  word-joiner + invisible math operators
      - U+E0000–U+E007F tag characters
    """
    # category -> first offending codepoint, for an auditable reason string
    found: dict[str, int] = {}
    for ch in content:
        cp = ord(ch)
        if 0x200B <= cp <= 0x200F:
            cat = "zero-width/directional-mark"
        elif 0x202A <= cp <= 0x202E:
            cat = "bidi-control"
        elif 0x2060 <= cp <= 0x2064:
            cat = "word-joiner"
        elif 0xE0000 <= cp <= 0xE007F:
            cat = "tag-character"
        else:
            continue
        found.setdefault(cat, cp)
    return [f"invisible-unicode: {cat} (U+{cp:04X})" for cat, cp in sorted(found.items())]


def scan_skill_content(content: str) -> ScanResult:
    """Fail-closed safety scan. Returns ``ScanResult(safe=False, reasons=[...])``
    on ANY prompt-injection, exfiltration, or invisible-Unicode match; otherwise
    ``ScanResult(safe=True, reasons=[])``. Pure function — no DB, no IO."""
    reasons: list[str] = []

    # Bound the regex work on untrusted content. A legitimately auto-forged
    # skill is well under this; anything larger is refused rather than scanned.
    if len(content) > _MAX_SCAN_LEN:
        return ScanResult(
            safe=False, reasons=[f"oversized: {len(content)} > {_MAX_SCAN_LEN} chars"]
        )

    for pat in _INJECTION_PATTERNS:
        if pat.search(content):
            reasons.append(f"prompt-injection: matched /{pat.pattern[:48]}.../")
            break

    for pat in _EXFILTRATION_PATTERNS:
        if pat.search(content):
            reasons.append("exfiltration: secret reference combined with outbound send")
            break

    reasons.extend(_invisible_unicode_reasons(content))

    return ScanResult(safe=not reasons, reasons=reasons)


# --- dedup: patch-over-create -----------------------------------------------
# Phase-22 dedup threshold: a candidate name whose similarity to an existing
# bound skill name is >= this ratio is treated as the SAME skill (patch path).
_DEDUP_NAME_THRESHOLD = 0.9


def _name_similarity(a: str, b: str) -> float:
    """Normalized name-similarity ratio in [0, 1]. Case/whitespace-insensitive
    char-sequence ratio (difflib) — a documented stand-in for name cosine."""
    na = re.sub(r"[\s_-]+", " ", a.strip().lower())
    nb = re.sub(r"[\s_-]+", " ", b.strip().lower())
    return SequenceMatcher(None, na, nb).ratio()


def find_duplicate_binding(name: str, content: Optional[str] = None) -> Optional[dict]:
    """Return an existing bound user skill that the candidate ``name`` duplicates,
    or None. Exact match wins first; otherwise the highest name-similarity skill
    at or above the Phase-22 threshold (>= 0.9) is the patch target.

    ``content`` is accepted for a future content-aware tie-break; name similarity
    is authoritative today."""
    exact = get_user_skill_by_name(name)
    if exact is not None:
        return exact

    best: Optional[dict] = None
    best_score = 0.0
    for skill in get_all_user_skills():
        existing_name = skill.get("skill_name") or ""
        score = _name_similarity(name, existing_name)
        if score >= _DEDUP_NAME_THRESHOLD and score > best_score:
            best = skill
            best_score = score
    return best


def provenance_allows_overwrite(asset_id: str, kind: str, on_disk_path: str | Path) -> bool:
    """Return whether the auto path may overwrite the on-disk asset.

    - No origin row → nothing to protect → allow (True).
    - Origin row present → re-hash the on-disk file and compare to the stored
      ``origin_hash``. Match → operator left it as imported → allow (True).
      Divergence (or unreadable file) → operator modified it → refuse (False).

    Mirrors the get_origin→compare idiom in forge_session_import."""
    origin = get_origin(asset_id, kind)
    if origin is None:
        return True

    path = Path(on_disk_path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        # Can't verify → fail closed → refuse overwrite.
        return False

    return content_hash(text) == origin.get("origin_hash")
