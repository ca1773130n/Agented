"""discovery_ranker — pure, deterministic blend of similarity signals (Phase 24).

The discovery brain's *scoring* half. The similarity client
(``github_similarity_client.py``) produces raw candidate signal counts; this
module turns each candidate into a bounded ``[0,1]`` relevance score and a
human-readable "why" string — with NO LLM, NO I/O, and NO randomness (same input
→ same output, mirroring ``signal_summarizer_service.score_signal`` :307).

Score formula (``discovery-engine-design-phase24.md`` §2.3 "weighted, bounded,
explainable"):

    score = w_topic  * min(shared_topics, 5) / 5
          + w_star   * min(shared_stargazers, STAR_CAP) / STAR_CAP   # STAR_CAP=10
          + w_dep    * is_dependent
          + w_readme * readme_similarity        # 0 / absent when S5 disabled
          + w_prior  * (0.5*same_language + 0.5*multi_seed_bonus)

Default weights sum to 1 with the README lens (S5) on. The KEY property: the
blend is **renormalized over only the active signals**, so disabling
README/dependents NEVER penalizes a candidate — we divide by the sum of the
active weights, not the full weight set. A candidate scored with README *off* is
identical to the same candidate scored with README *active-but-zero*.

``render_reason`` renders the highest-contributing fired clauses (§2.4): only
signals that actually fired appear, each pluralized, topics listed up to 3, and
a "surfaced by N of your seeds" clause when ``multi_seed_bonus`` is set.
"""

from __future__ import annotations

# --- weights (design §2.3, S5-on totals; renormalized over active) -----------
W_STAR = 0.40  # S2 stargazer overlap
W_TOPIC = 0.30  # S1 shared topics
W_README = 0.20  # S5 README similarity (optional lens — 24-03)
W_DEP = 0.07  # S3 dependents (deferred)
W_PRIOR = 0.03  # S4 prior (same_language + multi_seed_bonus)

# Saturating cap for the stargazer-overlap signal: 10 co-stars saturates to 1.0.
STAR_CAP = 10
# Saturating cap for the shared-topic count: 5 shared topics saturates to 1.0.
TOPIC_CAP = 5

# The canonical signal keys, mapped to their weights. ``active_signals`` is a set
# of these keys; a signal not in the set is dropped from BOTH the numerator and
# the renormalizing denominator.
_SIGNAL_WEIGHTS = {
    "star": W_STAR,
    "topic": W_TOPIC,
    "readme": W_README,
    "dep": W_DEP,
    "prior": W_PRIOR,
}

# When a caller does not constrain the active set, score over every signal whose
# evidence is present (README only counts when a non-null readme_similarity is
# supplied — see ``_default_active_signals``).
ALL_SIGNALS = frozenset(_SIGNAL_WEIGHTS)

# Final score gating (design §2.3) — exposed for 24-03's persistence layer.
MIN_SCORE = 0.15
TOP_N = 25


def _saturate(value: float, cap: int) -> float:
    """``min(value, cap) / cap`` clamped to ``[0,1]`` (the saturating curve)."""
    if cap <= 0:
        return 0.0
    return max(0.0, min(float(value), cap)) / cap


# The cheap MVP-core signals that are ALWAYS active for every candidate (a zero
# count just contributes 0, never a penalty). The optional lenses (``readme`` /
# ``dep``) are active PER-CANDIDATE — only when that candidate's own evidence
# carries the signal — so a candidate missing a README is renormalized over the
# core set rather than carrying README's weight as a 0.0 penalty.
_CORE_SIGNALS = frozenset({"star", "topic", "prior"})


def _default_active_signals(evidence: dict) -> set[str]:
    """Infer which signals are active from THIS candidate's evidence.

    ``star``/``topic``/``prior`` are always considered active (cheap MVP-core
    signals — a zero count just contributes 0). ``readme`` is active only when a
    non-null ``readme_similarity`` is present; ``dep`` only when ``is_dependent``
    is present. This keeps a candidate WITHOUT a README from carrying README's
    weight in the denominator (an absent optional signal must never lower the
    score — the design's renormalize-over-active contract).
    """
    active = set(_CORE_SIGNALS)
    if evidence.get("readme_similarity") is not None:
        active.add("readme")
    if evidence.get("is_dependent") is not None:
        active.add("dep")
    return active


def _candidate_active_signals(evidence: dict, active_signals: set[str] | None) -> set[str]:
    """Resolve the active signal set for ONE candidate (per-candidate, not global).

    The caller's ``active_signals`` (when supplied) constrains which OPTIONAL
    lenses may ever count this scan (e.g. README was never fetched → don't let
    any candidate claim it). But within that ceiling each candidate only counts a
    lens its OWN evidence carries: a scan where README fired for *some*
    candidates must still renormalize a README-less candidate over only the core
    signals, never penalizing it with a 0.0 README contribution. Core signals are
    always active. When ``active_signals`` is None we infer purely from evidence.
    """
    present = _default_active_signals(evidence)
    if active_signals is None:
        return present
    allowed = {s for s in active_signals if s in _SIGNAL_WEIGHTS}
    # Core signals stay on regardless; optional lenses count only when BOTH the
    # caller allows them AND this candidate's evidence actually carries them.
    return (present & allowed) | (present & _CORE_SIGNALS)


def _signal_contributions(evidence: dict) -> dict[str, float]:
    """Per-signal normalized contribution in ``[0,1]`` (pre-weight, pre-renorm)."""
    shared_topics = evidence.get("shared_topics") or []
    same_language = 1.0 if evidence.get("same_language") else 0.0
    multi_seed = 1.0 if evidence.get("multi_seed_bonus") else 0.0
    readme = evidence.get("readme_similarity")
    return {
        "star": _saturate(evidence.get("shared_stargazers") or 0, STAR_CAP),
        "topic": _saturate(len(shared_topics), TOPIC_CAP),
        "readme": max(0.0, min(float(readme), 1.0)) if readme is not None else 0.0,
        "dep": 1.0 if evidence.get("is_dependent") else 0.0,
        "prior": 0.5 * same_language + 0.5 * multi_seed,
    }


def score_candidate(evidence: dict, *, active_signals: set[str] | None = None) -> float:
    """Bounded ``[0,1]`` relevance score for one candidate's evidence.

    Renormalizes the weighted blend over only ``active_signals`` (the design's
    "never penalize for a disabled signal"): divide by the summed weight of the
    active set, not the full set. Deterministic — same evidence → same score,
    rounded to 3 dp.
    """
    if active_signals is None:
        active_signals = _default_active_signals(evidence)
    active = {s for s in active_signals if s in _SIGNAL_WEIGHTS}
    if not active:
        return 0.0

    contributions = _signal_contributions(evidence)
    active_weight = sum(_SIGNAL_WEIGHTS[s] for s in active)
    if active_weight <= 0:
        return 0.0

    blended = sum(_SIGNAL_WEIGHTS[s] * contributions[s] for s in active)
    return round(max(0.0, min(blended / active_weight, 1.0)), 3)


def _pluralize(count: int, noun: str) -> str:
    """``"1 shared topic"`` / ``"5 shared stargazers"`` — deterministic."""
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def render_reason(evidence: dict) -> str:
    """Deterministic human "why" string from the evidence — NO LLM.

    Lists ONLY the signals that fired, ordered by descending score contribution
    (matching ``score_candidate``'s weighting), e.g.:

        "7 shared stargazers · 3 shared topics (agents, llm, orchestration)"

    A zero/absent signal is omitted. ``multi_seed_bonus`` renders as
    "surfaced by N of your seeds" when ``seed_hits`` carries the count, else a
    generic "used by your other competitors".
    """
    contributions = _signal_contributions(evidence)
    clauses: list[tuple[float, str]] = []

    shared_stargazers = int(evidence.get("shared_stargazers") or 0)
    if shared_stargazers > 0:
        clauses.append(
            (W_STAR * contributions["star"], _pluralize(shared_stargazers, "shared stargazer"))
        )

    shared_topics = [t for t in (evidence.get("shared_topics") or []) if t]
    if shared_topics:
        shown = ", ".join(shared_topics[:3])
        label = _pluralize(len(shared_topics), "shared topic")
        clauses.append((W_TOPIC * contributions["topic"], f"{label} ({shown})"))

    readme = evidence.get("readme_similarity")
    if readme is not None and float(readme) > 0:
        clauses.append((W_README * contributions["readme"], "similar README"))

    if evidence.get("is_dependent"):
        clauses.append((W_DEP, "depends on your repo"))

    if evidence.get("multi_seed_bonus"):
        seed_hits = evidence.get("seed_hits") or []
        if seed_hits:
            phrase = f"surfaced by {len(seed_hits)} of your seeds"
        else:
            phrase = "used by your other competitors"
        # Prior is the lowest-weight signal — render it last.
        clauses.append((W_PRIOR * 0.5, phrase))

    if not clauses:
        return ""
    clauses.sort(key=lambda c: c[0], reverse=True)
    return " · ".join(text for _, text in clauses)


def rank_candidates(
    seed_meta: dict | None,
    candidates: list[dict],
    *,
    active_signals: set[str] | None = None,
    multi_seed_keys: set[tuple[str, str]] | None = None,
) -> list[dict]:
    """Score + explain every candidate; return them sorted by score DESC.

    Each input candidate is a raw signal dict from the similarity client
    (``shared_stargazers`` / ``shared_topics`` / optional ``readme_similarity``).
    For each, this builds an ``evidence`` dict (folding in ``same_language``
    against ``seed_meta`` and a ``multi_seed_bonus`` when the candidate's
    ``(owner, repo)`` is in ``multi_seed_keys``), scores it via
    :func:`score_candidate` renormalized over ``active_signals``, renders the
    "why" via :func:`render_reason`, and returns:

        {owner, repo, url, score, reason, evidence}

    Pure / deterministic: same inputs → identical output (including order; ties
    break by ``owner/repo`` so ordering is stable).
    """
    seed_language = (seed_meta or {}).get("language")
    multi_seed_keys = multi_seed_keys or set()

    ranked: list[dict] = []
    for cand in candidates:
        owner = cand.get("owner") or ""
        repo = cand.get("repo") or ""
        evidence = _build_evidence(
            cand, seed_language, (owner.lower(), repo.lower()), multi_seed_keys
        )
        # Resolve active signals PER-CANDIDATE: an optional lens (README /
        # dependents) only counts for a candidate whose own evidence carries it,
        # so a README-less candidate renormalizes over the core set and is never
        # penalized for a signal that fired only on its peers.
        cand_active = _candidate_active_signals(evidence, active_signals)
        score = score_candidate(evidence, active_signals=cand_active)
        ranked.append(
            {
                "owner": owner,
                "repo": repo,
                "url": cand.get("url") or f"https://github.com/{owner}/{repo}",
                "score": score,
                "reason": render_reason(evidence),
                "evidence": evidence,
            }
        )

    # Stable, deterministic ordering: score DESC, then owner/repo ASC for ties.
    ranked.sort(key=lambda c: (-c["score"], c["owner"].lower(), c["repo"].lower()))
    return ranked


def _build_evidence(
    cand: dict,
    seed_language: str | None,
    cand_key: tuple[str, str],
    multi_seed_keys: set[tuple[str, str]],
) -> dict:
    """Assemble the per-candidate evidence dict (design §2.2) from raw signals.

    Carries through whatever the client supplied (``shared_topics``,
    ``shared_stargazers``, ``shared_stargazer_logins``, optional
    ``readme_similarity`` / ``is_dependent`` / ``seed_hits``) and derives
    ``same_language`` + ``multi_seed_bonus``. Keys absent from the input stay
    absent so the renormalizer / "why" treat them as not-fired.
    """
    cand_language = cand.get("language")
    same_language = bool(seed_language and cand_language and seed_language == cand_language)

    seed_hits = cand.get("seed_hits") or []
    multi_seed = (
        bool(cand.get("multi_seed_bonus")) or len(seed_hits) >= 2 or cand_key in multi_seed_keys
    )

    evidence: dict = {
        "shared_topics": [t for t in (cand.get("shared_topics") or []) if t],
        "shared_stargazers": int(cand.get("shared_stargazers") or 0),
        "same_language": same_language,
        "multi_seed_bonus": multi_seed,
    }
    if cand.get("shared_stargazer_logins"):
        evidence["shared_stargazer_logins"] = list(cand["shared_stargazer_logins"])
    if seed_hits:
        evidence["seed_hits"] = list(seed_hits)
    # Optional lenses — present ONLY when the client supplied them, so the
    # renormalizer drops their weight from the denominator when absent.
    if cand.get("readme_similarity") is not None:
        evidence["readme_similarity"] = float(cand["readme_similarity"])
    if cand.get("is_dependent") is not None:
        evidence["is_dependent"] = bool(cand["is_dependent"])
    return evidence
