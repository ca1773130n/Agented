"""Tests for the Life-Harness T2 compiler + IR.

Covers:
    - Layer payload parsing (good + malformed)
    - ClaudeCodeTranslator folds H3/H5/H2/H4 into the build artifact
    - Disabled layers are excluded
    - Unknown harness_kind raises NotImplementedError
    - Version snapshot reflects max active version per layer
    - Malformed payloads land in ``skipped_layers`` instead of blowing up
"""

from __future__ import annotations

import pytest

from app.db import harness_layers as repo
from app.models.harness_ir import H2RuleIR, H3RuleIR, parse_payload
from app.services.harness_compiler import (
    ClaudeCodeTranslator,
    HarnessBuildService,
    get_translator,
)


@pytest.fixture
def fresh_db(isolated_db):
    return isolated_db


# ---------- IR parse ------------------------------------------------------

def test_parse_h3_payload_returns_typed_ir():
    payload = {
        "title": "Quote spaced column names",
        "rule_text": "Wrap any column name containing a space in double quotes.",
        "tool_overrides": [
            {"tool": "execute_sql", "append_description": "Always quote spaces."}
        ],
    }
    ir = parse_payload("h3", payload)
    assert isinstance(ir, H3RuleIR)
    assert ir.tool_overrides[0].tool == "execute_sql"


def test_parse_returns_none_on_malformed_payload():
    # Missing required title field.
    assert parse_payload("h3", {"rule_text": "no title"}) is None
    assert parse_payload("zz", {}) is None


# ---------- Compiler: H3 overlay + tool overrides ------------------------

def test_h3_rules_fold_into_overlay_and_tool_overrides(fresh_db):
    bot = "bot-test"
    repo.create_layer(
        bot_id=bot, layer="h3", name="quote-cols",
        payload={
            "title": "Quote spaced column names",
            "rule_text": "Wrap any spaced column in double quotes.",
            "tool_overrides": [
                {"tool": "execute_sql",
                 "append_description": "PostgreSQL dialect; quote spaces."}
            ],
        },
    )
    art = HarnessBuildService.build_for(bot, "claude")

    assert "Quote spaced column names" in art.system_prompt_overlay
    assert "Wrap any spaced column" in art.system_prompt_overlay
    assert "execute_sql" in art.tool_description_overrides
    assert "PostgreSQL" in art.tool_description_overrides["execute_sql"]
    assert art.layer_versions["h3"] == 1


# ---------- Compiler: H5 cards appended to overlay -----------------------

def test_h5_skills_become_cards_and_overlay_section(fresh_db):
    bot = "bot-test"
    repo.create_layer(
        bot_id=bot, layer="h5", name="refund-recipe",
        payload={
            "title": "Refunding a digital order",
            "when": "user asks for a refund",
            "recipe": "1) lookup_order  2) check_refund_eligibility  3) refund",
            "tags": ["refund", "retail"],
        },
    )
    art = HarnessBuildService.build_for(bot, "claude")

    assert len(art.skill_cards) == 1
    assert art.skill_cards[0]["title"] == "Refunding a digital order"
    assert "Procedural skills" in art.system_prompt_overlay
    assert "lookup_order" in art.system_prompt_overlay


# ---------- Compiler: H2 produces pre-tool-use HookSpec ------------------

def test_h2_block_rule_produces_pre_tool_use_hook(fresh_db):
    bot = "bot-test"
    repo.create_layer(
        bot_id=bot, layer="h2", name="block-rm-rf",
        payload={
            "title": "Block destructive rm -rf",
            "match": {"tool": "Bash", "arg_regex": {"command": "\\brm\\s+-rf\\b"}},
            "action": {"kind": "block", "params": {}},
            "message": "Refused: destructive command needs explicit approval.",
        },
    )
    art = HarnessBuildService.build_for(bot, "claude")

    assert len(art.hook_specs) == 1
    hook = art.hook_specs[0]
    assert hook.layer == "h2"
    assert hook.spec["trigger"] == "pre_tool_use"
    assert hook.spec["match"]["tool"] == "Bash"
    assert hook.spec["action"]["kind"] == "block"
    assert "Refused" in hook.spec["message"]


# ---------- Compiler: H4 produces post-tool-use HookSpec -----------------

def test_h4_repeat_detector_produces_post_hook(fresh_db):
    bot = "bot-test"
    repo.create_layer(
        bot_id=bot, layer="h4", name="stop-repeats",
        payload={
            "title": "Hint after 3 repeated calls",
            "detector": {"kind": "repeat_action", "params": {"k": 3, "window": 5}},
            "response": {"kind": "inject_hint",
                         "params": {"text": "You've repeated this — try differently."}},
        },
    )
    art = HarnessBuildService.build_for(bot, "claude")

    assert len(art.hook_specs) == 1
    hook = art.hook_specs[0]
    assert hook.layer == "h4"
    assert hook.spec["trigger"] == "post_tool_use"
    assert hook.spec["detector"]["params"]["k"] == 3
    assert hook.spec["response"]["kind"] == "inject_hint"


# ---------- Compiler: disabled rows are excluded -------------------------

def test_disabled_layer_is_excluded(fresh_db):
    bot = "bot-test"
    layer_id = repo.create_layer(
        bot_id=bot, layer="h3", name="dormant",
        payload={"title": "dormant", "rule_text": "should not appear"},
    )
    repo.set_enabled(layer_id, False)

    art = HarnessBuildService.build_for(bot, "claude")
    assert art.system_prompt_overlay == ""
    assert art.layer_versions == {}


# ---------- Compiler: malformed payloads skipped, not raised -------------

def test_malformed_payload_lands_in_skipped(fresh_db):
    bot = "bot-test"
    bad_id = repo.create_layer(
        bot_id=bot, layer="h3", name="broken",
        payload={"rule_text": "missing title field"},  # title is required
    )
    # Also include a good rule so we can confirm the compiler keeps going.
    repo.create_layer(
        bot_id=bot, layer="h3", name="good",
        payload={"title": "Real rule", "rule_text": "ok"},
    )
    art = HarnessBuildService.build_for(bot, "claude")

    assert any(s["id"] == bad_id for s in art.skipped_layers)
    assert "Real rule" in art.system_prompt_overlay


# ---------- supersede_layer audit trail ----------------------------------

def test_supersede_disables_parent_and_bumps_version(fresh_db):
    bot = "bot-test"
    v1_id = repo.create_layer(
        bot_id=bot, layer="h3", name="quote-cols",
        payload={"title": "v1", "rule_text": "v1 rule"},
    )
    v2_id = repo.supersede_layer(
        v1_id,
        new_payload={"title": "v2", "rule_text": "v2 rule"},
        source_kind="evolved",
    )

    v1 = repo.get_layer(v1_id)
    v2 = repo.get_layer(v2_id)
    assert v1["enabled"] is False
    assert v2["enabled"] is True
    assert v2["version"] == v1["version"] + 1
    assert v2["parent_layer_id"] == v1_id
    assert v2["source_kind"] == "evolved"

    # The compiler should now see only v2.
    art = HarnessBuildService.build_for(bot, "claude")
    assert "v2 rule" in art.system_prompt_overlay
    assert "v1 rule" not in art.system_prompt_overlay
    assert art.layer_versions["h3"] == 2


# ---------- registry ------------------------------------------------------

def test_unknown_harness_kind_raises():
    with pytest.raises(NotImplementedError):
        get_translator("totally-made-up")


def test_claude_translator_is_registered():
    t = get_translator("claude")
    assert isinstance(t, ClaudeCodeTranslator)


def test_codex_gemini_opencode_translators_registered():
    """All three secondary translators are registered and produce overlay
    artifacts. Hook injection is still claude-only at the injector layer,
    but the IR-level translator exists so snapshots + evolution can record
    these harnesses."""
    for kind in ("codex", "gemini", "opencode"):
        t = get_translator(kind)
        assert t.harness_kind == kind


def test_cross_harness_layer_transfer(fresh_db):
    """The IR is harness-agnostic: the same ``harness_layers`` rows compile
    to a useful overlay regardless of which translator runs them. This is
    the Life-Harness §5 "transfer" property: harnesses evolved against one
    backend should work as-is on another, modulo the per-harness wiring.
    """
    bot = "bot-transfer"
    repo.create_layer(
        bot_id=bot, layer="h3", name="r",
        payload={
            "title": "Quote spaced column names",
            "rule_text": "Wrap spaced cols in double quotes.",
        },
    )
    repo.create_layer(
        bot_id=bot, layer="h5", name="refund",
        payload={
            "title": "Refunding a digital order",
            "when": "user asks for refund",
            "recipe": "lookup_order then check_eligibility",
            "tags": ["refund"],
        },
    )

    overlays: dict[str, str] = {}
    for kind in ("claude", "codex", "gemini", "opencode"):
        art = HarnessBuildService.build_for(bot, kind)
        overlays[kind] = art.system_prompt_overlay
        assert "Quote spaced column names" in art.system_prompt_overlay
        assert "Refunding a digital order" in art.system_prompt_overlay
        assert art.harness_kind == kind

    # All four overlays carry the same H3 + H5 content (the IR is identical
    # and we don't yet diverge per-harness on overlay shape).
    assert len(set(overlays.values())) == 1
