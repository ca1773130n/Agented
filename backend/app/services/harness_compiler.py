"""Harness-agnostic compiler that turns ``harness_layers`` rows into a
``HarnessBuildArtifact`` (T2).

Pipeline::

    harness_layers (DB)
        ↓ list_enabled_for_bot
    [LayerRow] rows
        ↓ parse_payload → IR Structs
    [H2RuleIR, H3RuleIR, H4RuleIR, H5SkillIR]
        ↓ HarnessTranslator.compile
    HarnessBuildArtifact
        ↓ (future) consumed by ExecutionService when spawning subprocess
    .claude/CLAUDE.md + .claude/hooks.json + argv extras

This module deliberately stops at ``HarnessBuildArtifact``. Writing the
artifact to disk (per-harness materializer) is the integration step and
lives in a separate follow-up so this PR doesn't silently change how
every execution is spawned.
"""

from __future__ import annotations

import logging
from typing import ClassVar, Optional, Protocol, runtime_checkable

import msgspec

from app.db import harness_layers as repo
from app.db import harness_skill_index as skill_index
from app.models.harness_ir import (
    H2RuleIR,
    H3RuleIR,
    H4RuleIR,
    H5SkillIR,
    parse_payload,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Build artifact — what every translator emits
# ---------------------------------------------------------------------------

class HookSpec(msgspec.Struct, kw_only=True):
    """Harness-agnostic description of a runtime hook. A per-harness writer
    turns this into native config (Claude Code hooks.json, Codex AGENTS.md
    hook table, etc.)."""

    layer: str           # "h2" | "h4"
    layer_id: str        # source harness_layers.id
    name: str
    spec: dict           # flattened, already-normalized; runtime-ready


class HarnessBuildArtifact(msgspec.Struct, kw_only=True):
    """Output of ``HarnessTranslator.compile``.

    Carries everything the bot's runtime needs to apply this bot's harness.
    The shape is intentionally narrow — adding fields is cheap, removing is
    expensive — so we ship the minimum useful for T2.
    """

    bot_id: str
    harness_kind: str
    system_prompt_overlay: str = ""
    tool_description_overrides: dict[str, str] = {}
    hook_specs: list[HookSpec] = []
    skill_cards: list[dict] = []
    layer_versions: dict[str, int] = {}     # layer → max active version
    skipped_layers: list[dict] = []         # rows the compiler couldn't parse


# ---------------------------------------------------------------------------
# Translator protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class HarnessTranslator(Protocol):
    """Per-harness compiler. T2 ships ``ClaudeCodeTranslator`` plus
    overlay-only translators for codex/gemini/opencode."""

    harness_kind: ClassVar[str]

    def compile(
        self,
        bot_id: str,
        layer_rows: list[dict],
        *,
        task_description: Optional[str] = None,
        h5_top_k: int = 3,
    ) -> HarnessBuildArtifact: ...


_REGISTRY: dict[str, HarnessTranslator] = {}


def register_translator(translator: HarnessTranslator) -> None:
    _REGISTRY[translator.harness_kind] = translator


def get_translator(harness_kind: str) -> HarnessTranslator:
    try:
        return _REGISTRY[harness_kind]
    except KeyError as exc:
        raise NotImplementedError(
            f"no HarnessTranslator registered for harness_kind={harness_kind!r}"
        ) from exc


# ---------------------------------------------------------------------------
# Claude Code translator
# ---------------------------------------------------------------------------

class ClaudeCodeTranslator:
    """T2 translator for Claude Code.

    H3 → CLAUDE.md overlay text + tool_description_overrides
    H5 → skill cards appended to the overlay (no BM25 retrieval yet — see
         ``skill_cards`` field; future retrieval ranks them per task)
    H2 → PreToolUse HookSpec entries
    H4 → PostToolUse / Stop HookSpec entries
    """

    harness_kind: ClassVar[str] = "claude"

    def compile(
        self,
        bot_id: str,
        layer_rows: list[dict],
        *,
        task_description: Optional[str] = None,
        h5_top_k: int = 3,
    ) -> HarnessBuildArtifact:
        overlay_chunks: list[str] = []
        tool_overrides: dict[str, list[str]] = {}
        hooks: list[HookSpec] = []
        skipped: list[dict] = []
        versions: dict[str, int] = {}

        # Stash H5 rows on the side so we can apply BM25 retrieval after
        # everything else has been collected.
        all_skills: list[tuple[dict, H5SkillIR]] = []

        for row in layer_rows:
            layer = row["layer"]
            ir = parse_payload(layer, row.get("payload", {}))
            if ir is None:
                skipped.append({"id": row["id"], "layer": layer, "name": row["name"]})
                continue
            versions[layer] = max(versions.get(layer, 0), row.get("version", 1))

            if isinstance(ir, H3RuleIR):
                self._fold_h3(ir, row, overlay_chunks, tool_overrides)
            elif isinstance(ir, H5SkillIR):
                all_skills.append((row, ir))
            elif isinstance(ir, H2RuleIR):
                hooks.append(self._fold_h2(ir, row))
            elif isinstance(ir, H4RuleIR):
                hooks.append(self._fold_h4(ir, row))

        skill_cards = _retrieve_top_k_skills(
            bot_id, all_skills,
            task_description=task_description, k=h5_top_k,
        )

        # Skill cards land at the end of the overlay so the operator-authored
        # H3 contract appears first (more authoritative).
        if skill_cards:
            overlay_chunks.append("## Procedural skills\n")
            for card in skill_cards:
                overlay_chunks.append(_format_skill_card(card))

        return HarnessBuildArtifact(
            bot_id=bot_id,
            harness_kind=self.harness_kind,
            system_prompt_overlay="\n\n".join(c.rstrip() for c in overlay_chunks),
            tool_description_overrides={
                tool: "\n".join(parts) for tool, parts in tool_overrides.items()
            },
            hook_specs=hooks,
            skill_cards=skill_cards,
            layer_versions=versions,
            skipped_layers=skipped,
        )

    # --- per-layer folders ----------------------------------------------

    @staticmethod
    def _fold_h3(
        ir: H3RuleIR,
        row: dict,
        overlay: list[str],
        tool_overrides: dict[str, list[str]],
    ) -> None:
        if ir.rule_text:
            overlay.append(f"### {ir.title}\n\n{ir.rule_text}")
        for ov in ir.tool_overrides:
            if ov.replace_description is not None:
                tool_overrides.setdefault(ov.tool, []).append(ov.replace_description)
            elif ov.append_description:
                tool_overrides.setdefault(ov.tool, []).append(ov.append_description)

    @staticmethod
    def _fold_h2(ir: H2RuleIR, row: dict) -> HookSpec:
        return HookSpec(
            layer="h2",
            layer_id=row["id"],
            name=ir.title,
            spec={
                "trigger": "pre_tool_use",
                "match": msgspec.to_builtins(ir.match),
                "action": msgspec.to_builtins(ir.action),
                "message": ir.message,
            },
        )

    @staticmethod
    def _fold_h4(ir: H4RuleIR, row: dict) -> HookSpec:
        return HookSpec(
            layer="h4",
            layer_id=row["id"],
            name=ir.title,
            spec={
                "trigger": "post_tool_use",
                "detector": msgspec.to_builtins(ir.detector),
                "response": msgspec.to_builtins(ir.response),
            },
        )


register_translator(ClaudeCodeTranslator())


# ---------------------------------------------------------------------------
# Translators for non-Claude harnesses
#
# These produce the H3-overlay + H5-skill-cards into ``system_prompt_overlay``
# and ``tool_description_overrides`` — the universal pieces of the IR. Hook
# specs (H2/H4) are not yet wired for these harnesses because they don't
# expose a Claude-Code-style PreToolUse/PostToolUse hook contract. The IR
# is recorded on the artifact (``hook_specs`` field) so a future, harness-
# specific runtime can pick it up; today's injector simply doesn't fire it.
#
# The runtime injector (``harness_injector.inject_artifact_into_cmd``) only
# wires ``--append-system-prompt`` for Claude today, so ``injected_components``
# will honestly report ``system_prompt: False`` for these harnesses until an
# operator builds the corresponding wiring. The translators are useful even
# without injector support because:
#   - the snapshot table records what *would* have been used
#   - the evolution loop can read these snapshots
#   - cross-harness transfer studies become possible
# ---------------------------------------------------------------------------


class _OverlayOnlyTranslator(ClaudeCodeTranslator):
    """Translator that produces overlay text + skill cards but never wires
    hooks. Concrete subclasses override ``harness_kind``."""

    def compile(
        self,
        bot_id: str,
        layer_rows: list[dict],
        *,
        task_description: Optional[str] = None,
        h5_top_k: int = 3,
    ) -> HarnessBuildArtifact:
        artifact = super().compile(
            bot_id, layer_rows,
            task_description=task_description, h5_top_k=h5_top_k,
        )
        # Hook specs stay on the artifact for audit, but mark them as
        # belonging to the IR (not the live wiring) by leaving them as-is;
        # the snapshot service will record `injected_components: {hooks: False}`
        # for non-Claude harnesses regardless.
        artifact.harness_kind = self.harness_kind
        return artifact


class CodexTranslator(_OverlayOnlyTranslator):
    harness_kind: ClassVar[str] = "codex"


class GeminiTranslator(_OverlayOnlyTranslator):
    harness_kind: ClassVar[str] = "gemini"


class OpenCodeTranslator(_OverlayOnlyTranslator):
    harness_kind: ClassVar[str] = "opencode"


register_translator(CodexTranslator())
register_translator(GeminiTranslator())
register_translator(OpenCodeTranslator())


# ---------------------------------------------------------------------------
# Public service
# ---------------------------------------------------------------------------

class HarnessBuildService:
    """Orchestrates load → compile → artifact. Stateless."""

    @staticmethod
    def build_for(
        bot_id: str,
        harness_kind: str,
        *,
        trigger_id: Optional[str] = None,
        task_description: Optional[str] = None,
        h5_top_k: int = 3,
    ) -> HarnessBuildArtifact:
        translator = get_translator(harness_kind)
        layer_rows = repo.list_enabled_for_bot(bot_id, trigger_id=trigger_id)
        return translator.compile(
            bot_id, layer_rows,
            task_description=task_description, h5_top_k=h5_top_k,
        )


def _retrieve_top_k_skills(
    bot_id: str,
    skills: list[tuple[dict, H5SkillIR]],
    *,
    task_description: Optional[str],
    k: int,
) -> list[dict]:
    """Pick the top-K H5 skill cards for this task.

    When ``task_description`` is provided AND we have more skills than K,
    use the FTS5 BM25 index to rank. Falls back to "all skills" when the
    index returns nothing (empty query, malformed FTS5 grammar, etc.) so
    the operator always sees their procedural library — retrieval is an
    optimization, not a gate.
    """
    if not skills:
        return []
    cards_by_id = {row["id"]: _claude_skill_card(row, ir) for row, ir in skills}

    if task_description and len(skills) > k:
        ranked_ids = skill_index.top_k(bot_id, task_description, k=k)
        if ranked_ids:
            return [cards_by_id[lid] for lid in ranked_ids if lid in cards_by_id]

    return list(cards_by_id.values())[:k] if len(skills) > k else list(cards_by_id.values())


def _claude_skill_card(row: dict, ir: H5SkillIR) -> dict:
    return {
        "id": row["id"],
        "title": ir.title,
        "when": ir.when,
        "recipe": ir.recipe,
        "tags": ir.tags,
    }


def _format_skill_card(card: dict) -> str:
    when = f" (when: {card['when']})" if card.get("when") else ""
    tags = f"  _tags: {', '.join(card['tags'])}_" if card.get("tags") else ""
    return f"- **{card['title']}**{when}\n\n  {card['recipe']}\n{tags}"
