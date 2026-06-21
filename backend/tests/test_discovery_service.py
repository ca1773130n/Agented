"""DiscoveryService tests (Phase 24, 24-03) — scan orchestration + promote/dismiss.

The deterministic core: the GitHub similarity client is monkeypatched to return
canned candidates (no network), and ``embedding_service.is_available`` is forced
``False`` so the README lens resolves to the cheap ``text`` path (or ``off`` when
the caller opts out). Covers:

  * scan happy path → ranked ``discovery_suggestion`` rows (status ``suggested``),
    with a candidate already watched as a seed EXCLUDED;
  * idempotency → re-scan keeps the row count stable (UPSERT), refreshes scores;
  * dismissed-stickiness → a dismissed row stays ``dismissed`` across a re-scan;
  * no-candidate path (no PAT) → 0 rows written, no raise;
  * promote → ``add_source(origin='discovery')`` + status flips to ``added`` with a
    stamped ``source_id``;
  * README-mode → ``is_available()`` False yields a mode in ``{text, off}`` and the
    scan still completes (renormalization never blocks).
"""

from __future__ import annotations

import pytest

from app.db import discovery_suggestions
from app.db.projects import create_project
from app.services import discovery_ranker, embedding_service
from app.services import discovery_service as ds_module
from app.services.competitor_source_service import CompetitorSourceService
from app.services.discovery_service import DiscoveryService
from app.services.github_similarity_client import GitHubSimilarityClient

# A seed that yields strong S1+S2 signals so the candidate clears MIN_SCORE.
_STRONG_TOPICS = [
    {
        "owner": "acme",
        "repo": "rival",
        "url": "https://github.com/acme/rival",
        "stargazers_count": 900,
        "topics": ["agents", "llm", "orchestration"],
        "shared_topics": ["agents", "llm", "orchestration"],
        "archived": False,
        "fork": False,
    }
]
_STRONG_STARS = [
    {
        "owner": "acme",
        "repo": "rival",
        "url": "https://github.com/acme/rival",
        "shared_stargazers": 12,
        "shared_stargazer_logins": ["u1", "u2", "u3"],
    }
]


@pytest.fixture
def _no_embeddings(monkeypatch):
    """Force the text/off README path: no embedding backend, no real README GET."""
    monkeypatch.setattr(embedding_service, "is_available", lambda: False)
    # README fetch always reuses the auth seam; with no PAT it would return None
    # anyway, but stub it so the text path is exercised deterministically.
    monkeypatch.setattr(DiscoveryService, "_fetch_readme", staticmethod(lambda owner, repo: None))


@pytest.fixture
def _seeded_project(isolated_db):
    """A project with two ``github_repo`` seeds (one of which a candidate matches)."""
    project_id = create_project(name="Discovery CI")
    CompetitorSourceService.add_source(project_id, "https://github.com/me/seed")
    # ``already/watched`` is a watched seed → must be EXCLUDED from suggestions.
    CompetitorSourceService.add_source(project_id, "https://github.com/already/watched")
    return project_id


def _stub_client(monkeypatch, *, topics, stars, metadata=None):
    """Monkeypatch the similarity client's three read methods with canned data."""
    monkeypatch.setattr(
        GitHubSimilarityClient,
        "find_by_shared_topics",
        classmethod(lambda cls, o, r, **k: list(topics)),
    )
    monkeypatch.setattr(
        GitHubSimilarityClient,
        "find_by_stargazer_overlap",
        classmethod(lambda cls, o, r, **k: list(stars)),
    )
    monkeypatch.setattr(
        GitHubSimilarityClient, "repo_metadata", classmethod(lambda cls, o, r: metadata)
    )


# --------------------------------------------------------------------------- #
# README-mode resolver
# --------------------------------------------------------------------------- #


def test_resolve_readme_mode_text_when_no_embeddings(monkeypatch):
    monkeypatch.setattr(embedding_service, "is_available", lambda: False)
    assert DiscoveryService._resolve_readme_mode() == "text"


def test_resolve_readme_mode_embedding_when_available(monkeypatch):
    monkeypatch.setattr(embedding_service, "is_available", lambda: True)
    assert DiscoveryService._resolve_readme_mode() == "embedding"


def test_resolve_readme_mode_explicit_off_overrides(monkeypatch):
    monkeypatch.setattr(embedding_service, "is_available", lambda: True)
    assert DiscoveryService._resolve_readme_mode("off") == "off"


def test_resolve_readme_mode_never_raises_on_probe_failure(monkeypatch):
    def _boom():
        raise RuntimeError("model import exploded")

    monkeypatch.setattr(embedding_service, "is_available", _boom)
    # Degrades to text rather than propagating the probe failure.
    assert DiscoveryService._resolve_readme_mode() == "text"


# --------------------------------------------------------------------------- #
# scan_project
# --------------------------------------------------------------------------- #


def test_scan_writes_ranked_rows_and_excludes_watched(_seeded_project, _no_embeddings, monkeypatch):
    """Happy path: ranked suggestion rows written as 'suggested'; the candidate
    matching an already-watched seed is excluded."""
    project_id = _seeded_project
    # Two candidates: 'acme/rival' (strong, new) and 'already/watched' (watched seed).
    topics = _STRONG_TOPICS + [
        {
            "owner": "already",
            "repo": "watched",
            "url": "https://github.com/already/watched",
            "stargazers_count": 50,
            "topics": ["agents"],
            "shared_topics": ["agents"],
            "archived": False,
            "fork": False,
        }
    ]
    _stub_client(monkeypatch, topics=topics, stars=_STRONG_STARS)

    result = DiscoveryService.scan_project(project_id)

    assert result["scanned"] == 2  # two github_repo seeds
    assert result["suggestions"] >= 1
    assert result["readme_mode"] in {"text", "off"}

    rows = discovery_suggestions.list_suggestions(project_id)
    owners = {(r["candidate_owner"], r["candidate_repo"]) for r in rows}
    assert ("acme", "rival") in owners
    # The watched seed must NOT have been suggested.
    assert ("already", "watched") not in owners
    rival = next(r for r in rows if r["candidate_repo"] == "rival")
    assert rival["status"] == "suggested"
    assert rival["score"] is not None
    assert rival["score"] >= discovery_ranker.MIN_SCORE
    # evidence is parsed JSON carrying the raw signal counts.
    assert isinstance(rival["evidence"], dict)
    assert rival["evidence"]["shared_stargazers"] == 12
    assert "agents" in rival["evidence"]["shared_topics"]


def test_scan_is_idempotent(_seeded_project, _no_embeddings, monkeypatch):
    """A re-scan UPSERTs: row count stays stable, score refreshed not duplicated."""
    project_id = _seeded_project
    _stub_client(monkeypatch, topics=_STRONG_TOPICS, stars=_STRONG_STARS)

    first = DiscoveryService.scan_project(project_id)
    rows_after_first = discovery_suggestions.list_suggestions(project_id)

    # Re-scan with a weaker star signal → same row, refreshed (lower) score.
    weaker_stars = [{**_STRONG_STARS[0], "shared_stargazers": 4, "shared_stargazer_logins": ["u1"]}]
    _stub_client(monkeypatch, topics=_STRONG_TOPICS, stars=weaker_stars)
    second = DiscoveryService.scan_project(project_id)
    rows_after_second = discovery_suggestions.list_suggestions(project_id)

    assert len(rows_after_second) == len(rows_after_first)  # no duplication
    assert first["suggestions"] == second["suggestions"]
    rival_first = next(r for r in rows_after_first if r["candidate_repo"] == "rival")
    rival_second = next(r for r in rows_after_second if r["candidate_repo"] == "rival")
    assert rival_second["id"] == rival_first["id"]  # same row (UPSERT)
    assert rival_second["score"] != rival_first["score"]  # score refreshed


def test_dismissed_row_stays_dismissed_across_rescan(_seeded_project, _no_embeddings, monkeypatch):
    """An operator's dismiss verdict is sticky: a re-scan does not resurrect it."""
    project_id = _seeded_project
    _stub_client(monkeypatch, topics=_STRONG_TOPICS, stars=_STRONG_STARS)

    DiscoveryService.scan_project(project_id)
    rows = discovery_suggestions.list_suggestions(project_id)
    rival = next(r for r in rows if r["candidate_repo"] == "rival")

    DiscoveryService.dismiss_suggestion(project_id, rival["id"])
    assert discovery_suggestions.get_suggestion(rival["id"])["status"] == "dismissed"

    # Re-scan: the row must remain 'dismissed' (24-01 upsert invariant).
    DiscoveryService.scan_project(project_id)
    refreshed = discovery_suggestions.get_suggestion(rival["id"])
    assert refreshed["status"] == "dismissed"


def test_scan_no_candidates_writes_zero_and_does_not_raise(
    _seeded_project, _no_embeddings, monkeypatch
):
    """No PAT → client returns [] → 0 rows written, no exception."""
    project_id = _seeded_project
    _stub_client(monkeypatch, topics=[], stars=[])

    result = DiscoveryService.scan_project(project_id)

    assert result["suggestions"] == 0
    assert result["scanned"] == 2
    assert discovery_suggestions.list_suggestions(project_id) == []


def test_scan_no_github_seeds_returns_zero(isolated_db, _no_embeddings):
    """A project with no github_repo seeds yields 0 candidates, no error."""
    project_id = create_project(name="No github seeds")
    CompetitorSourceService.add_source(project_id, "https://arxiv.org/abs/2401.1")
    CompetitorSourceService.add_source(project_id, "https://acme.com/product")

    result = DiscoveryService.scan_project(project_id)
    assert result["scanned"] == 0
    assert result["suggestions"] == 0
    assert result["seeds_total"] == 0
    assert result["seeds_scanned"] == 0
    assert result["truncated"] is False
    assert result["readme_mode"] in {"text", "off"}


def test_scan_one_bad_seed_does_not_abort(_no_embeddings, isolated_db, monkeypatch):
    """A seed whose client call raises is isolated; other seeds still produce rows."""
    project_id = create_project(name="Mixed seeds")
    CompetitorSourceService.add_source(project_id, "https://github.com/good/seed")
    CompetitorSourceService.add_source(project_id, "https://github.com/bad/seed")

    def _topics(cls, owner, repo, **kwargs):
        if owner == "bad":
            raise RuntimeError("seed blew up")
        return list(_STRONG_TOPICS)

    monkeypatch.setattr(GitHubSimilarityClient, "find_by_shared_topics", classmethod(_topics))
    monkeypatch.setattr(
        GitHubSimilarityClient,
        "find_by_stargazer_overlap",
        classmethod(lambda cls, o, r, **k: list(_STRONG_STARS) if o == "good" else []),
    )
    monkeypatch.setattr(
        GitHubSimilarityClient, "repo_metadata", classmethod(lambda cls, o, r: None)
    )

    # Must not raise; the good seed's candidate is still written.
    result = DiscoveryService.scan_project(project_id)
    assert result["scanned"] == 2
    rows = discovery_suggestions.list_suggestions(project_id)
    assert any(r["candidate_repo"] == "rival" for r in rows)


def test_scan_readme_mode_reported_and_does_not_block(_seeded_project, _no_embeddings, monkeypatch):
    """is_available()->False: readme_mode in {text,off}, scan still completes."""
    project_id = _seeded_project
    _stub_client(monkeypatch, topics=_STRONG_TOPICS, stars=_STRONG_STARS)

    result = DiscoveryService.scan_project(project_id)
    assert result["readme_mode"] in {"text", "off"}
    assert result["suggestions"] >= 1

    # Explicit off also completes and reports 'off'.
    off_result = DiscoveryService.scan_project(project_id, readme_mode="off")
    assert off_result["readme_mode"] == "off"
    assert off_result["suggestions"] >= 1


def test_scan_caps_seeds_and_reports_truncation(isolated_db, _no_embeddings, monkeypatch):
    """Fix 3: scan fans out AT MOST max_seeds seeds and reports the truncation.

    A project with more github_repo seeds than ``max_seeds`` only scans the cap,
    and the result carries seeds_total > seeds_scanned with truncated=True."""
    project_id = create_project(name="many-seeds")
    for i in range(5):
        CompetitorSourceService.add_source(project_id, f"https://github.com/org{i}/repo{i}")

    scanned_seeds: list = []

    def _topics(cls, owner, repo, **kwargs):
        scanned_seeds.append((owner, repo))
        return []

    monkeypatch.setattr(GitHubSimilarityClient, "find_by_shared_topics", classmethod(_topics))
    monkeypatch.setattr(
        GitHubSimilarityClient, "find_by_stargazer_overlap", classmethod(lambda cls, o, r, **k: [])
    )
    monkeypatch.setattr(
        GitHubSimilarityClient, "repo_metadata", classmethod(lambda cls, o, r: None)
    )

    result = DiscoveryService.scan_project(project_id, max_seeds=2)
    assert result["seeds_total"] == 5
    assert result["seeds_scanned"] == 2
    assert result["scanned"] == 2
    assert result["truncated"] is True
    # The client was only invoked for the 2 capped seeds.
    assert len(scanned_seeds) == 2


def test_scan_request_budget_circuit_breaker(isolated_db, _no_embeddings, monkeypatch):
    """Fix 3: the scan-wide request budget stops launching seed fan-outs early.

    A tiny ``max_requests`` budget (below even one seed's estimated cost) trips the
    circuit-breaker before the first fan-out — truncated=True, 0 seeds scanned."""
    project_id = create_project(name="budget-breaker")
    for i in range(3):
        CompetitorSourceService.add_source(project_id, f"https://github.com/org{i}/repo{i}")

    called: list = []
    monkeypatch.setattr(
        GitHubSimilarityClient,
        "find_by_shared_topics",
        classmethod(lambda cls, o, r, **k: called.append((o, r)) or []),
    )
    monkeypatch.setattr(
        GitHubSimilarityClient, "find_by_stargazer_overlap", classmethod(lambda cls, o, r, **k: [])
    )
    monkeypatch.setattr(
        GitHubSimilarityClient, "repo_metadata", classmethod(lambda cls, o, r: None)
    )

    result = DiscoveryService.scan_project(project_id, max_requests=1)
    assert result["truncated"] is True
    assert result["seeds_scanned"] == 0
    assert called == []  # breaker tripped before any fan-out


def test_scan_no_truncation_when_under_caps(_seeded_project, _no_embeddings, monkeypatch):
    """Under both caps, truncated=False and seeds_scanned == seeds_total."""
    project_id = _seeded_project
    _stub_client(monkeypatch, topics=_STRONG_TOPICS, stars=_STRONG_STARS)

    result = DiscoveryService.scan_project(project_id)
    assert result["truncated"] is False
    assert result["seeds_scanned"] == result["seeds_total"] == 2


def test_readme_lens_aborts_on_throttle(_seeded_project, monkeypatch):
    """Fix 4: a 403/429 README fetch aborts the README lens for the rest of the
    scan instead of burning a GET per candidate. ``_fetch_readme`` returns the
    throttle sentinel and only ONE README fetch happens (the seed's)."""
    project_id = _seeded_project
    # Force the text README path (no embeddings) but DO exercise _fetch_readme.
    monkeypatch.setattr(embedding_service, "is_available", lambda: False)

    # Many candidates so we can prove the lens stops after the throttle.
    topics = [
        {
            "owner": f"cand{i}",
            "repo": f"r{i}",
            "url": f"https://github.com/cand{i}/r{i}",
            "stargazers_count": 100,
            "topics": ["agents", "llm", "orchestration"],
            "shared_topics": ["agents", "llm", "orchestration"],
            "archived": False,
            "fork": False,
        }
        for i in range(5)
    ]
    # repo_metadata must return a dict so the README lens has a seed to fetch
    # (seed_meta_by_key is populated only from non-None metadata).
    seed_meta = {
        "owner": "me",
        "repo": "seed",
        "url": "https://github.com/me/seed",
        "topics": ["agents"],
        "language": "Python",
        "stargazers_count": 10,
        "archived": False,
        "fork": False,
    }
    _stub_client(monkeypatch, topics=topics, stars=[], metadata=seed_meta)

    fetch_calls: list = []

    def _throttled_fetch(owner, repo):
        fetch_calls.append((owner, repo))
        # First call is the seed README (returns text); the very first CANDIDATE
        # fetch throttles → lens must abort, no further candidate fetches.
        if len(fetch_calls) == 1:
            return "seed readme text about agents and orchestration"
        return ds_module._README_THROTTLED

    monkeypatch.setattr(DiscoveryService, "_fetch_readme", staticmethod(_throttled_fetch))

    result = DiscoveryService.scan_project(project_id)
    # Seed README (1) + exactly ONE candidate fetch (the throttling one) = 2 total.
    assert len(fetch_calls) == 2, f"README lens did not abort on throttle: {fetch_calls}"
    # Scan still completed and wrote rows (README throttle never blocks the scan).
    assert result["suggestions"] >= 1
    # No candidate carries a readme_similarity (the lens aborted before any fired).
    rows = discovery_suggestions.list_suggestions(project_id)
    assert all(
        not (isinstance(r["evidence"], dict) and "readme_similarity" in r["evidence"]) for r in rows
    )


# --------------------------------------------------------------------------- #
# list / promote / dismiss
# --------------------------------------------------------------------------- #


def test_list_suggestions_delegates_with_status_filter(
    _seeded_project, _no_embeddings, monkeypatch
):
    project_id = _seeded_project
    _stub_client(monkeypatch, topics=_STRONG_TOPICS, stars=_STRONG_STARS)
    DiscoveryService.scan_project(project_id)

    suggested = DiscoveryService.list_suggestions(project_id, statuses=["suggested"])
    assert suggested
    assert all(r["status"] == "suggested" for r in suggested)
    assert DiscoveryService.list_suggestions(project_id, statuses=["added"]) == []


def test_promote_calls_add_source_with_discovery_origin(
    _seeded_project, _no_embeddings, monkeypatch
):
    """promote_suggestion routes through add_source(origin='discovery') and stamps
    the new source_id onto the suggestion (status -> 'added')."""
    project_id = _seeded_project
    _stub_client(monkeypatch, topics=_STRONG_TOPICS, stars=_STRONG_STARS)
    DiscoveryService.scan_project(project_id)
    rival = next(
        r
        for r in discovery_suggestions.list_suggestions(project_id)
        if r["candidate_repo"] == "rival"
    )

    # Spy on add_source to assert origin='discovery' is passed.
    calls: list[dict] = []
    real_add = CompetitorSourceService.add_source

    def _spy_add_source(project_id_arg, url, label=None, origin="manual"):
        calls.append({"project_id": project_id_arg, "url": url, "origin": origin})
        return real_add(project_id_arg, url, label=label, origin=origin)

    monkeypatch.setattr(CompetitorSourceService, "add_source", staticmethod(_spy_add_source))

    out = DiscoveryService.promote_suggestion(project_id, rival["id"])

    assert len(calls) == 1
    assert calls[0]["origin"] == "discovery"
    assert calls[0]["url"] == "https://github.com/acme/rival"
    assert calls[0]["project_id"] == project_id

    # New source row returned + suggestion flipped to 'added' with stamped source_id.
    assert out["source"]["origin"] == "discovery"
    assert out["source"]["id"].startswith("cmps-")
    assert out["suggestion"]["status"] == "added"
    assert out["suggestion"]["source_id"] == out["source"]["id"]

    # And it persisted.
    reloaded = discovery_suggestions.get_suggestion(rival["id"])
    assert reloaded["status"] == "added"
    assert reloaded["source_id"] == out["source"]["id"]


def test_promote_unknown_suggestion_raises(isolated_db, _no_embeddings):
    project_id = create_project(name="promote-unknown")
    with pytest.raises(ValueError):
        DiscoveryService.promote_suggestion(project_id, "dsug-nope0000")


def test_promote_foreign_project_suggestion_raises(_seeded_project, _no_embeddings, monkeypatch):
    """IDOR: promoting via the WRONG project id raises ValueError (route → 404),
    and does NOT add a source — even though the suggestion id is real."""
    project_id = _seeded_project
    _stub_client(monkeypatch, topics=_STRONG_TOPICS, stars=_STRONG_STARS)
    DiscoveryService.scan_project(project_id)
    rival = next(
        r
        for r in discovery_suggestions.list_suggestions(project_id)
        if r["candidate_repo"] == "rival"
    )

    other_project = create_project(name="attacker-project")
    with pytest.raises(ValueError):
        DiscoveryService.promote_suggestion(other_project, rival["id"])

    # The suggestion is untouched (still 'suggested') and no source was created.
    assert discovery_suggestions.get_suggestion(rival["id"])["status"] == "suggested"
    assert CompetitorSourceService.list_sources(other_project) == []


def test_promote_is_idempotent_single_source_on_double_accept(
    _seeded_project, _no_embeddings, monkeypatch
):
    """Fix 5: a SECOND accept of an already-'added' suggestion returns the EXISTING
    source and does NOT call add_source again — exactly ONE competitor_source row."""
    project_id = _seeded_project
    _stub_client(monkeypatch, topics=_STRONG_TOPICS, stars=_STRONG_STARS)
    DiscoveryService.scan_project(project_id)
    rival = next(
        r
        for r in discovery_suggestions.list_suggestions(project_id)
        if r["candidate_repo"] == "rival"
    )

    add_calls: list = []
    real_add = CompetitorSourceService.add_source

    def _spy_add(pid, url, label=None, origin="manual"):
        add_calls.append(url)
        return real_add(pid, url, label=label, origin=origin)

    monkeypatch.setattr(CompetitorSourceService, "add_source", staticmethod(_spy_add))

    first = DiscoveryService.promote_suggestion(project_id, rival["id"])
    second = DiscoveryService.promote_suggestion(project_id, rival["id"])

    # add_source called exactly ONCE despite two accepts.
    assert len(add_calls) == 1
    # Both calls return the SAME source id.
    assert first["source"]["id"] == second["source"]["id"]

    # Exactly one competitor_source row for that candidate url.
    sources = [
        s
        for s in CompetitorSourceService.list_sources(project_id)
        if s["url"] == "https://github.com/acme/rival"
    ]
    assert len(sources) == 1


def test_promote_concurrent_loser_returns_existing_source_no_second_row(
    _seeded_project, _no_embeddings, monkeypatch
):
    """Round-2 fix (concurrent-accept race): the caller that LOSES the atomic claim
    (``claim_for_promotion`` → False, the row already 'added' by the winner) returns
    the EXISTING source and adds NO second competitor_source row.

    The race is collapsed deterministically: the winner promotes first (creating the
    one source), then ``claim_for_promotion`` is patched to always return False so the
    second promote takes the loser branch — which must NOT call add_source again."""
    project_id = _seeded_project
    _stub_client(monkeypatch, topics=_STRONG_TOPICS, stars=_STRONG_STARS)
    DiscoveryService.scan_project(project_id)
    rival = next(
        r
        for r in discovery_suggestions.list_suggestions(project_id)
        if r["candidate_repo"] == "rival"
    )

    # Winner promotes for real → exactly one source exists and the row is 'added'.
    winner = DiscoveryService.promote_suggestion(project_id, rival["id"])
    assert winner["suggestion"]["status"] == "added"

    # Now force the loser branch: the claim never wins, and add_source must NOT run.
    monkeypatch.setattr(discovery_suggestions, "claim_for_promotion", lambda sid, pid: False)
    add_calls: list = []
    real_add = CompetitorSourceService.add_source

    def _spy_add(pid, url, label=None, origin="manual"):
        add_calls.append(url)
        return real_add(pid, url, label=label, origin=origin)

    monkeypatch.setattr(CompetitorSourceService, "add_source", staticmethod(_spy_add))

    loser = DiscoveryService.promote_suggestion(project_id, rival["id"])

    # The loser added nothing and returned the winner's source.
    assert add_calls == []
    assert loser["source"]["id"] == winner["source"]["id"]

    # Still exactly ONE competitor_source row for that candidate url.
    sources = [
        s
        for s in CompetitorSourceService.list_sources(project_id)
        if s["url"] == "https://github.com/acme/rival"
    ]
    assert len(sources) == 1


def test_promote_reverts_claim_when_add_source_fails(_seeded_project, _no_embeddings, monkeypatch):
    """Round-2 fix: if add_source raises AFTER the claim won, the claim is REVERTED
    (status back to 'suggested', source_id cleared) and the error re-raised — never
    a phantom 'added' row with no backing competitor_source."""
    project_id = _seeded_project
    _stub_client(monkeypatch, topics=_STRONG_TOPICS, stars=_STRONG_STARS)
    DiscoveryService.scan_project(project_id)
    rival = next(
        r
        for r in discovery_suggestions.list_suggestions(project_id)
        if r["candidate_repo"] == "rival"
    )

    def _boom(pid, url, label=None, origin="manual"):
        raise RuntimeError("add_source blew up after the claim")

    monkeypatch.setattr(CompetitorSourceService, "add_source", staticmethod(_boom))

    with pytest.raises(RuntimeError):
        DiscoveryService.promote_suggestion(project_id, rival["id"])

    # Reverted: the row is claimable again (not stuck 'added'), source_id cleared.
    reloaded = discovery_suggestions.get_suggestion(rival["id"])
    assert reloaded["status"] == "suggested"
    assert reloaded["source_id"] is None
    # No discovery source landed for the candidate.
    assert not any(
        s["url"] == "https://github.com/acme/rival"
        for s in CompetitorSourceService.list_sources(project_id)
    )


def test_promote_dismissed_raises_promotion_conflict(_seeded_project, _no_embeddings, monkeypatch):
    """Fix 5: accepting a DISMISSED suggestion raises PromotionConflict (route → 409)
    rather than resurrecting it; no source is added."""
    project_id = _seeded_project
    _stub_client(monkeypatch, topics=_STRONG_TOPICS, stars=_STRONG_STARS)
    DiscoveryService.scan_project(project_id)
    rival = next(
        r
        for r in discovery_suggestions.list_suggestions(project_id)
        if r["candidate_repo"] == "rival"
    )
    DiscoveryService.dismiss_suggestion(project_id, rival["id"])

    # The _seeded_project fixture already watches two seed sources; record the
    # baseline so we can assert NO new (discovery) source was added.
    sources_before = len(CompetitorSourceService.list_sources(project_id))

    with pytest.raises(ds_module.PromotionConflict):
        DiscoveryService.promote_suggestion(project_id, rival["id"])

    # Still dismissed; no NEW source created (the rival candidate was not promoted).
    assert discovery_suggestions.get_suggestion(rival["id"])["status"] == "dismissed"
    assert len(CompetitorSourceService.list_sources(project_id)) == sources_before
    assert not any(
        s["url"] == "https://github.com/acme/rival"
        for s in CompetitorSourceService.list_sources(project_id)
    )


def test_dismiss_flips_status_and_returns_row(_seeded_project, _no_embeddings, monkeypatch):
    project_id = _seeded_project
    _stub_client(monkeypatch, topics=_STRONG_TOPICS, stars=_STRONG_STARS)
    DiscoveryService.scan_project(project_id)
    rival = next(
        r
        for r in discovery_suggestions.list_suggestions(project_id)
        if r["candidate_repo"] == "rival"
    )

    out = DiscoveryService.dismiss_suggestion(project_id, rival["id"])
    assert out["suggestion"]["status"] == "dismissed"
    assert discovery_suggestions.get_suggestion(rival["id"])["status"] == "dismissed"


def test_dismiss_unknown_suggestion_raises(isolated_db, _no_embeddings):
    project_id = create_project(name="dismiss-unknown")
    with pytest.raises(ValueError):
        DiscoveryService.dismiss_suggestion(project_id, "dsug-nope0000")


# --------------------------------------------------------------------------- #
# README similarity helpers (deterministic, no network)
# --------------------------------------------------------------------------- #


def test_text_similarity_bounds():
    assert DiscoveryService._text_similarity("", "anything") == 0.0
    assert DiscoveryService._text_similarity("same text", "same text") == pytest.approx(1.0)
    mixed = DiscoveryService._text_similarity("agent orchestration framework", "agent framework")
    assert 0.0 < mixed < 1.0


def test_readme_similarity_off_or_missing_is_none():
    assert DiscoveryService._readme_similarity("seed", "cand", "off") is None
    assert DiscoveryService._readme_similarity(None, "cand", "text") is None
    assert DiscoveryService._readme_similarity("seed", None, "text") is None


def test_readme_similarity_embedding_degrades_to_text_when_lib_absent(monkeypatch):
    """embed_texts -> [] (lib absent) must fall back to the text ratio, not crash."""
    monkeypatch.setattr(ds_module.embedding_service, "embed_texts", lambda texts: [])
    score = DiscoveryService._readme_similarity("same readme", "same readme", "embedding")
    assert score == pytest.approx(1.0)  # text ratio of identical strings
