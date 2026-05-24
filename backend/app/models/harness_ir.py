"""Harness-layer payload IR (T2).

Strongly-typed views of the ``harness_layers.payload_json`` blob for each
of the four Life-Harness layers. Used by ``HarnessCompiler`` to produce a
harness-agnostic ``HarnessBuildArtifact``.

Validation philosophy:
    Parse, don't validate. ``parse_payload(layer, payload)`` returns ``None``
    when the blob is malformed — the compiler logs and skips. We never block
    bot startup on a half-typed manual edit.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import msgspec

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# H3 — Environment Contract
# ---------------------------------------------------------------------------

class H3ToolOverride(msgspec.Struct, kw_only=True):
    tool: str
    append_description: str = ""
    replace_description: Optional[str] = None


class H3RuleIR(msgspec.Struct, kw_only=True):
    """Static contract overlay injected before interaction."""

    title: str
    rule_text: str = ""
    tool_overrides: list[H3ToolOverride] = []
    applies_when: dict[str, list[str]] = {}


# ---------------------------------------------------------------------------
# H5 — Procedural Skill
# ---------------------------------------------------------------------------

class H5SkillIR(msgspec.Struct, kw_only=True):
    """Compact recipe distilled from past trajectories. Retrieval-ready."""

    title: str
    when: str = ""
    recipe: str
    tags: list[str] = []


# ---------------------------------------------------------------------------
# H2 — Action Realization
# ---------------------------------------------------------------------------

class H2MatchIR(msgspec.Struct, kw_only=True):
    """Pre-execution match predicate. All present fields must match."""

    tool: Optional[str] = None
    arg_regex: dict[str, str] = {}
    content_regex: Optional[str] = None


class H2ActionIR(msgspec.Struct, kw_only=True):
    """Discriminated by ``kind``. ``params`` is action-specific.

    Known kinds:
        block        — refuse to execute; surface ``message`` as feedback
        canonicalize — rewrite args / tool name before execution
        rescue       — lift a malformed in-content action into a real tool call
    """

    kind: str
    params: dict[str, Any] = {}


class H2RuleIR(msgspec.Struct, kw_only=True):
    title: str
    match: H2MatchIR
    action: H2ActionIR
    message: Optional[str] = None


# ---------------------------------------------------------------------------
# H4 — Trajectory Regulation
# ---------------------------------------------------------------------------

class H4DetectorIR(msgspec.Struct, kw_only=True):
    """Discriminated by ``kind``. Known kinds:

        repeat_action — same (tool, args) repeated ``k`` times in ``window``
        stagnation    — ``k`` consecutive assistant turns without a tool call
        budget        — fire when remaining step budget < ``threshold``
        regex_count   — ``pattern`` matched in trajectory ``k`` times
    """

    kind: str
    params: dict[str, Any] = {}


class H4ResponseIR(msgspec.Struct, kw_only=True):
    """Discriminated by ``kind``. Known kinds:

        inject_hint  — append ``text`` to the next assistant turn's context
        abort        — terminate the trajectory with ``reason``
        suppress_dup — silently drop further matching tool calls
    """

    kind: str
    params: dict[str, Any] = {}


class H4RuleIR(msgspec.Struct, kw_only=True):
    title: str
    detector: H4DetectorIR
    response: H4ResponseIR


# ---------------------------------------------------------------------------
# Parse dispatch
# ---------------------------------------------------------------------------

_PARSERS: dict[str, type[msgspec.Struct]] = {
    "h2": H2RuleIR,
    "h3": H3RuleIR,
    "h4": H4RuleIR,
    "h5": H5SkillIR,
}


def parse_payload(layer: str, payload: dict[str, Any]) -> Optional[msgspec.Struct]:
    """Parse a raw payload dict into the layer's typed IR.

    Returns ``None`` on malformed input — the compiler skips and logs. Never
    raises so a single bad row can't block ``HarnessBuildService.build_for``.
    """
    cls = _PARSERS.get(layer)
    if cls is None:
        logger.warning("parse_payload: unknown layer %r", layer)
        return None
    try:
        return msgspec.convert(payload, cls)
    except msgspec.ValidationError as exc:
        logger.warning("parse_payload: %s payload invalid: %s", layer, exc)
        return None
