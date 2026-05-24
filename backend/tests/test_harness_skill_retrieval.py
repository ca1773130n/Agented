"""Tests for FTS5 BM25 top-K retrieval of H5 procedural skills."""

from __future__ import annotations

import pytest

from app.db import harness_layers as repo
from app.db import harness_skill_index as skill_index
from app.services.harness_compiler import HarnessBuildService


def _seed(bot: str, *,
          title: str, when: str = "", recipe: str = "",
          tags: list[str] | None = None) -> str:
    return repo.create_layer(
        bot_id=bot, layer="h5", name=title.lower().replace(" ", "-"),
        payload={
            "title": title, "when": when, "recipe": recipe,
            "tags": tags or [],
        },
    )


def test_index_maintained_on_create_and_supersede(isolated_db):
    bot = "bot-h5-a"
    v1 = _seed(bot, title="Refund a digital order", when="user wants refund",
               recipe="lookup_order then refund")
    # Index entry exists for v1; query for "refund" surfaces it.
    hits = skill_index.top_k(bot, "refund digital order", k=5)
    assert v1 in hits

    # supersede swaps the index entry: parent removed, child indexed.
    v2 = repo.supersede_layer(v1, new_payload={
        "title": "Refund a digital order v2",
        "when": "user wants refund",
        "recipe": "lookup_order then check_eligibility then refund",
        "tags": ["refund"],
    })
    hits_after = skill_index.top_k(bot, "refund digital order", k=5)
    assert v1 not in hits_after
    assert v2 in hits_after


def test_index_removed_on_disable(isolated_db):
    bot = "bot-h5-b"
    sid = _seed(bot, title="Quote spaced names")
    assert skill_index.top_k(bot, "spaced names", k=5) == [sid]
    repo.set_enabled(sid, False)
    assert skill_index.top_k(bot, "spaced names", k=5) == []


def test_top_k_empty_query_returns_empty(isolated_db):
    bot = "bot-h5-c"
    _seed(bot, title="x")
    assert skill_index.top_k(bot, "", k=5) == []
    assert skill_index.top_k(bot, "   ", k=5) == []


def test_compiler_uses_retrieval_when_more_skills_than_k(isolated_db):
    """With 5 skills and h5_top_k=2, only the 2 most relevant land in the
    overlay."""
    bot = "bot-h5-d"
    _seed(bot, title="Refund digital order",
          when="refund", recipe="A")
    _seed(bot, title="Cancel scheduled meeting",
          when="cancel", recipe="B")
    _seed(bot, title="Issue store credit",
          when="store credit", recipe="C")
    _seed(bot, title="Reschedule appointment",
          when="reschedule", recipe="D")
    _seed(bot, title="Send a follow-up email",
          when="email", recipe="E")

    art = HarnessBuildService.build_for(
        bot, "claude",
        task_description="customer wants to refund their order",
        h5_top_k=2,
    )
    assert len(art.skill_cards) <= 2
    # The refund skill ranks above unrelated ones.
    titles = [c["title"] for c in art.skill_cards]
    assert "Refund digital order" in titles


def test_compiler_falls_back_to_all_when_no_task_description(isolated_db):
    """Without a task description, retrieval is skipped and all skills
    (up to k) are returned — operator sees their full library."""
    bot = "bot-h5-e"
    _seed(bot, title="Skill A")
    _seed(bot, title="Skill B")

    art = HarnessBuildService.build_for(bot, "claude", h5_top_k=10)
    assert len(art.skill_cards) == 2


def test_compiler_resilient_to_malformed_fts5_query(isolated_db):
    """FTS5 has a strict query grammar. The retrieval helper must not
    propagate parse errors back to the compiler."""
    bot = "bot-h5-f"
    sid = _seed(bot, title="x")
    art = HarnessBuildService.build_for(
        bot, "claude",
        task_description="((bad query :( ",
        h5_top_k=5,
    )
    # Compiler should still produce an overlay — fallback is "all skills".
    assert any(c["id"] == sid for c in art.skill_cards)
