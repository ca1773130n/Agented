"""Tests for discovery_ranker — pure deterministic similarity blend (Phase 24-02).

No mocking (the module is pure: no I/O, no LLM, no randomness). Covers:

  * deterministic — same candidates → identical scores across two calls; every
    score in ``[0,1]``.
  * renormalization (the KEY invariant) — a candidate scored with the README
    signal DISABLED (``active_signals`` omits ``readme``) is NOT scored lower
    than the same candidate scored with README active-but-zero. Disabling a
    signal must renormalize, never penalize.
  * ``render_reason`` lists only the signals that fired (a zero/absent signal is
    omitted from the string).
"""

from __future__ import annotations

from app.services import discovery_ranker as dr
from app.services.discovery_ranker import (
    STAR_CAP,
    W_STAR,
    W_TOPIC,
    rank_candidates,
    render_reason,
    score_candidate,
)

# ---------------------------------------------------------------------------
# Determinism + bounds
# ---------------------------------------------------------------------------


def _candidates():
    return [
        {
            "owner": "rival",
            "repo": "agentkit",
            "url": "https://github.com/rival/agentkit",
            "shared_stargazers": 7,
            "shared_topics": ["agents", "llm"],
            "language": "Python",
        },
        {
            "owner": "other",
            "repo": "llmbox",
            "url": "https://github.com/other/llmbox",
            "shared_stargazers": 3,
            "shared_topics": ["llm"],
            "language": "Go",
        },
    ]


def test_rank_candidates_deterministic_and_bounded():
    seed = {"language": "Python"}
    a = rank_candidates(seed, _candidates())
    b = rank_candidates(seed, _candidates())
    assert [c["score"] for c in a] == [c["score"] for c in b]  # same input → same score
    assert [(c["owner"], c["repo"]) for c in a] == [(c["owner"], c["repo"]) for c in b]
    for c in a:
        assert 0.0 <= c["score"] <= 1.0
    # Sorted score DESC — the 7-stargazer + same-language candidate ranks first.
    assert a[0]["repo"] == "agentkit"
    assert a[0]["score"] >= a[1]["score"]


def test_score_candidate_in_unit_interval_extremes():
    # Maxed evidence saturates to 1.0; empty evidence is 0.0.
    maxed = {
        "shared_stargazers": 999,
        "shared_topics": ["a", "b", "c", "d", "e", "f"],
        "readme_similarity": 1.0,
        "is_dependent": True,
        "same_language": True,
        "multi_seed_bonus": True,
    }
    assert score_candidate(maxed) == 1.0
    assert score_candidate({}) == 0.0


def test_star_signal_saturates_at_cap():
    # shared_stargazers beyond STAR_CAP must not increase the contribution.
    at_cap = score_candidate({"shared_stargazers": STAR_CAP}, active_signals={"star"})
    over_cap = score_candidate({"shared_stargazers": STAR_CAP * 5}, active_signals={"star"})
    assert at_cap == over_cap == 1.0


# ---------------------------------------------------------------------------
# Renormalization invariant — disabling a signal never penalizes
# ---------------------------------------------------------------------------


def test_disabling_readme_does_not_penalize():
    # Same candidate, README signal carries ZERO value either way.
    cand = {"shared_stargazers": 7, "shared_topics": ["agents", "llm"]}

    # README ACTIVE but zero (readme in the active set, contribution 0).
    with_readme_zero = score_candidate(
        {**cand, "readme_similarity": 0.0},
        active_signals={"star", "topic", "readme", "prior"},
    )
    # README DISABLED (omitted from the active set → renormalized away).
    without_readme = score_candidate(cand, active_signals={"star", "topic", "prior"})

    # The disabled-README score must be STRICTLY HIGHER than the active-but-zero
    # score (renormalizing over fewer weights raises the others, never penalizes).
    assert without_readme > with_readme_zero


def test_renormalized_weight_math_matches_active_set():
    # Only star + topic active. shared_stargazers=10 → star contribution 1.0;
    # shared_topics has 5 → topic contribution 1.0. Renormalized over W_STAR+W_TOPIC
    # → (W_STAR*1 + W_TOPIC*1) / (W_STAR + W_TOPIC) == 1.0.
    ev = {"shared_stargazers": 10, "shared_topics": ["a", "b", "c", "d", "e"]}
    assert score_candidate(ev, active_signals={"star", "topic"}) == 1.0

    # Half the star signal, full topic signal, renormalized over the two.
    ev2 = {"shared_stargazers": 5, "shared_topics": ["a", "b", "c", "d", "e"]}
    expected = round((W_STAR * 0.5 + W_TOPIC * 1.0) / (W_STAR + W_TOPIC), 3)
    assert score_candidate(ev2, active_signals={"star", "topic"}) == expected


def test_default_active_signals_excludes_absent_readme():
    # With no readme key, the default active set must NOT include readme — so a
    # candidate is not silently penalized for the optional lens being off.
    ev = {"shared_stargazers": 7, "shared_topics": ["agents"]}
    explicit = score_candidate(ev, active_signals={"star", "topic", "prior"})
    inferred = score_candidate(ev)  # active_signals=None → inferred
    assert inferred == explicit


def test_rank_candidates_per_candidate_active_signals_no_readme_not_penalized():
    """The README fix (per-candidate active signals): when README fired for SOME
    candidate this scan (so the caller passes readme in the global active set), a
    candidate that has NO README must score IDENTICALLY to the same candidate
    scored without readme in the active set — never a 0.0-README penalty.

    Reproduces the original bug: a global ``active_signals`` containing ``readme``
    used to drag every README-less candidate down by README's full weight."""
    seed = {"language": "Python"}
    # One candidate HAS a README similarity (so the scan's global active set
    # legitimately includes 'readme'); the other has NONE.
    cands = [
        {
            "owner": "withreadme",
            "repo": "a",
            "shared_stargazers": 7,
            "shared_topics": ["agents", "llm"],
            "readme_similarity": 0.9,
        },
        {
            "owner": "noreadme",
            "repo": "b",
            "shared_stargazers": 7,
            "shared_topics": ["agents", "llm"],
        },
    ]
    # The scan surfaced a README for >=1 candidate → README is in the active set.
    global_active = {"star", "topic", "readme", "prior"}
    ranked = rank_candidates(seed, cands, active_signals=global_active)
    no_readme = next(c for c in ranked if c["owner"] == "noreadme")

    # The README-less candidate, scored under a global active set that includes
    # README, must equal its score under the README-OFF active set (renormalized
    # over its OWN present signals — star/topic/prior only).
    baseline = rank_candidates(seed, [cands[1]], active_signals={"star", "topic", "prior"})[0]
    assert no_readme["score"] == baseline["score"]

    # And it must NOT be lower than the same candidate scored with README treated
    # as active-but-absent under the global set (the exact penalty the bug caused).
    cand_b_evidence = {
        "shared_stargazers": 7,
        "shared_topics": ["agents", "llm"],
        "same_language": True,
        "multi_seed_bonus": False,
    }
    penalized = score_candidate(cand_b_evidence, active_signals=global_active)
    assert no_readme["score"] > penalized  # bug would have made them EQUAL (penalty)


# ---------------------------------------------------------------------------
# render_reason — only fired signals appear
# ---------------------------------------------------------------------------


def test_render_reason_lists_only_fired_signals():
    s = render_reason({"shared_stargazers": 7, "shared_topics": ["agents", "llm", "orchestration"]})
    assert "7 shared stargazers" in s
    assert "3 shared topics (agents, llm, orchestration)" in s
    # No README / dependents clause when those signals are absent.
    assert "README" not in s
    assert "depends on" not in s


def test_render_reason_omits_zero_and_absent_signals():
    # Zero stargazers + a single topic → only the topic clause appears, singular.
    s = render_reason({"shared_stargazers": 0, "shared_topics": ["agents"]})
    assert "stargazer" not in s
    assert s == "1 shared topic (agents)"


def test_render_reason_caps_topic_names_at_three():
    s = render_reason({"shared_topics": ["a", "b", "c", "d", "e"]})
    assert "(a, b, c)" in s
    assert "d" not in s.split("(")[1]  # only first 3 topics listed
    assert "5 shared topics" in s  # count still reflects the full set


def test_render_reason_multi_seed_clause():
    s = render_reason(
        {"shared_stargazers": 5, "multi_seed_bonus": True, "seed_hits": ["o/a", "o/b"]}
    )
    assert "surfaced by 2 of your seeds" in s


def test_render_reason_empty_evidence_is_empty_string():
    assert render_reason({}) == ""


# ---------------------------------------------------------------------------
# rank_candidates evidence + ordering
# ---------------------------------------------------------------------------


def test_rank_candidates_attaches_evidence_and_reason():
    seed = {"language": "Python"}
    out = rank_candidates(
        seed,
        [
            {
                "owner": "rival",
                "repo": "agentkit",
                "url": "https://github.com/rival/agentkit",
                "shared_stargazers": 7,
                "shared_topics": ["agents"],
                "language": "Python",
            }
        ],
    )
    row = out[0]
    assert set(row) == {"owner", "repo", "url", "score", "reason", "evidence"}
    assert row["evidence"]["shared_stargazers"] == 7
    assert row["evidence"]["same_language"] is True  # seed + candidate both Python
    assert "7 shared stargazers" in row["reason"]


def test_rank_candidates_multi_seed_keys_sets_bonus():
    seed = {"language": "Python"}
    out = rank_candidates(
        seed,
        [{"owner": "Rival", "repo": "AgentKit", "shared_stargazers": 4, "shared_topics": ["x"]}],
        multi_seed_keys={("rival", "agentkit")},  # lowercased key matches
    )
    assert out[0]["evidence"]["multi_seed_bonus"] is True


def test_rank_candidates_stable_tie_break():
    # Two candidates with identical evidence → identical score → tie broken by
    # owner/repo ASC (deterministic order).
    seed = {}
    cands = [
        {"owner": "zeta", "repo": "r", "shared_stargazers": 5, "shared_topics": ["x"]},
        {"owner": "alpha", "repo": "r", "shared_stargazers": 5, "shared_topics": ["x"]},
    ]
    out = rank_candidates(seed, cands)
    assert out[0]["score"] == out[1]["score"]
    assert [c["owner"] for c in out] == ["alpha", "zeta"]


def test_module_exposes_gating_constants():
    # 24-03's persistence layer consumes these thresholds.
    assert dr.MIN_SCORE == 0.15
    assert dr.TOP_N == 25
