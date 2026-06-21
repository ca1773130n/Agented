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

    DiscoveryService.dismiss_suggestion(rival["id"])
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
    assert result == {"scanned": 0, "suggestions": 0, "readme_mode": result["readme_mode"]}
    assert result["scanned"] == 0
    assert result["suggestions"] == 0


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

    out = DiscoveryService.promote_suggestion(rival["id"])

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
    with pytest.raises(ValueError):
        DiscoveryService.promote_suggestion("dsug-nope0000")


def test_dismiss_flips_status_and_returns_row(_seeded_project, _no_embeddings, monkeypatch):
    project_id = _seeded_project
    _stub_client(monkeypatch, topics=_STRONG_TOPICS, stars=_STRONG_STARS)
    DiscoveryService.scan_project(project_id)
    rival = next(
        r
        for r in discovery_suggestions.list_suggestions(project_id)
        if r["candidate_repo"] == "rival"
    )

    out = DiscoveryService.dismiss_suggestion(rival["id"])
    assert out["suggestion"]["status"] == "dismissed"
    assert discovery_suggestions.get_suggestion(rival["id"])["status"] == "dismissed"


def test_dismiss_unknown_suggestion_raises(isolated_db, _no_embeddings):
    with pytest.raises(ValueError):
        DiscoveryService.dismiss_suggestion("dsug-nope0000")


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
