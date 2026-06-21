"""Tests for GitHubSimilarityClient — read-only similar-repo discovery (Phase 24-02).

Covers the plan's must-have behaviours, ALL with httpx mocked (zero live network):

  * no-token skip — ``_auth_headers`` → None makes both finders return ``[]``
    WITHOUT any ``httpx.get`` call (never the unauthenticated 60/hr path).
  * S1 topic-search happy path — candidates exclude the seed, carry
    ``shared_topics`` + ``stargazers_count``, capped at ``max_results``.
  * S2 stargazer-overlap — only repos with ``shared_stargazers >= min_shared``
    survive; the total request count stays within the hard ``max_requests`` cap.
  * 403 backoff — a 403 mid-fan-out returns the partial tally and does NOT raise.

HTTP is mocked by monkeypatching ``github_similarity_client.httpx.get`` (the
repo's convention, mirroring ``test_github_monitor_service``) with a small
URL-routing fake. ``_auth_headers`` is patched per-test so no real
``GITHUB_TOKEN`` is consulted.
"""

from __future__ import annotations

import json

import pytest

from app.services import github_similarity_client as gsc
from app.services.github_similarity_client import GitHubSimilarityClient


class _FakeResponse:
    """Minimal stand-in for httpx.Response (only what the client reads)."""

    def __init__(self, status_code: int, *, body=None):
        self.status_code = status_code
        self._body = body
        self.content = json.dumps(body).encode() if body is not None else b""
        self.headers = {}

    def json(self):
        if self._body is None:
            raise ValueError("no body")
        return self._body


class _Router:
    """Records every GET and returns a response from a URL→responder map.

    ``routes`` maps a substring → either a single ``_FakeResponse`` or a list of
    them consumed in order (for paginated endpoints). An unmatched URL yields a
    200 with an empty list so pagination terminates cleanly.
    """

    def __init__(self, routes: dict):
        self.routes = routes
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, url, **kwargs):
        self.calls.append((url, dict(kwargs.get("params") or {})))
        for needle, responder in self.routes.items():
            if needle in url:
                if isinstance(responder, list):
                    if responder:
                        return responder.pop(0)
                    return _FakeResponse(200, body=[])
                return responder
        return _FakeResponse(200, body=[])

    @property
    def count(self) -> int:
        return len(self.calls)


_AUTH = {"Authorization": "Bearer ghp_test", "Accept": "application/vnd.github+json"}


def _patch_auth(monkeypatch, headers=_AUTH):
    monkeypatch.setattr(GitHubSimilarityClient, "_headers", staticmethod(lambda: headers))


def _install(monkeypatch, router: _Router):
    monkeypatch.setattr(gsc.httpx, "get", router)


# ---------------------------------------------------------------------------
# parse_seed delegates to parse_repo_url
# ---------------------------------------------------------------------------


def test_parse_seed_delegates_to_parse_repo_url():
    assert GitHubSimilarityClient.parse_seed("https://github.com/acme/widget") == ("acme", "widget")
    assert GitHubSimilarityClient.parse_seed("https://github.com/o/r.git") == ("o", "r")
    with pytest.raises(ValueError):
        GitHubSimilarityClient.parse_seed("not-a-url")


# ---------------------------------------------------------------------------
# No-token skip — both finders return [] with ZERO network calls
# ---------------------------------------------------------------------------


def test_no_token_skips_both_finders_without_network(monkeypatch):
    _patch_auth(monkeypatch, headers=None)

    def _boom(*a, **k):
        raise AssertionError("httpx.get called without a credential — unauth path taken")

    monkeypatch.setattr(gsc.httpx, "get", _boom)

    assert GitHubSimilarityClient.find_by_shared_topics("acme", "widget") == []
    assert GitHubSimilarityClient.find_by_stargazer_overlap("acme", "widget") == []
    assert GitHubSimilarityClient.repo_metadata("acme", "widget") is None


# ---------------------------------------------------------------------------
# repo_metadata
# ---------------------------------------------------------------------------


def test_repo_metadata_trims_repo_object(monkeypatch):
    _patch_auth(monkeypatch)
    router = _Router(
        {
            "/repos/acme/widget": _FakeResponse(
                200,
                body={
                    "html_url": "https://github.com/acme/widget",
                    "topics": ["agents", "llm"],
                    "language": "Python",
                    "stargazers_count": 1820,
                    "archived": False,
                    "fork": False,
                },
            )
        }
    )
    _install(monkeypatch, router)

    meta = GitHubSimilarityClient.repo_metadata("acme", "widget")
    assert meta["owner"] == "acme" and meta["repo"] == "widget"
    assert meta["topics"] == ["agents", "llm"]
    assert meta["language"] == "Python"
    assert meta["stargazers_count"] == 1820


def test_repo_metadata_non_200_returns_none(monkeypatch):
    _patch_auth(monkeypatch)
    _install(monkeypatch, _Router({"/repos/acme/widget": _FakeResponse(404)}))
    assert GitHubSimilarityClient.repo_metadata("acme", "widget") is None


# ---------------------------------------------------------------------------
# S1 — shared-topic search
# ---------------------------------------------------------------------------


def _seed_repo_response():
    return _FakeResponse(
        200,
        body={
            "html_url": "https://github.com/acme/widget",
            "topics": ["agents", "llm"],
            "language": "Python",
            "stargazers_count": 1820,
        },
    )


def _search_item(owner, name, *, stars, topics):
    return {
        "full_name": f"{owner}/{name}",
        "owner": {"login": owner},
        "name": name,
        "html_url": f"https://github.com/{owner}/{name}",
        "stargazers_count": stars,
        "topics": topics,
    }


def test_find_by_shared_topics_excludes_seed_and_carries_signals(monkeypatch):
    _patch_auth(monkeypatch)
    search_body = {
        "items": [
            # the seed itself — must be excluded
            _search_item("acme", "widget", stars=1820, topics=["agents", "llm"]),
            _search_item("rival", "agentkit", stars=900, topics=["agents", "rust"]),
            _search_item("other", "llmbox", stars=400, topics=["llm", "python"]),
        ]
    }
    router = _Router(
        {
            "/repos/acme/widget": _seed_repo_response(),
            "/search/repositories": _FakeResponse(200, body=search_body),
        }
    )
    _install(monkeypatch, router)

    out = GitHubSimilarityClient.find_by_shared_topics("acme", "widget")
    keys = {(c["owner"], c["repo"]) for c in out}
    assert ("acme", "widget") not in keys  # seed excluded
    assert ("rival", "agentkit") in keys and ("other", "llmbox") in keys

    rival = next(c for c in out if c["repo"] == "agentkit")
    assert rival["shared_topics"] == ["agents"]  # case-insensitive intersection
    assert rival["stargazers_count"] == 900


def test_find_by_shared_topics_caps_at_max_results(monkeypatch):
    _patch_auth(monkeypatch)
    items = [_search_item(f"o{i}", f"r{i}", stars=i, topics=["agents"]) for i in range(50)]
    router = _Router(
        {
            "/repos/acme/widget": _seed_repo_response(),
            "/search/repositories": _FakeResponse(200, body={"items": items}),
        }
    )
    _install(monkeypatch, router)

    out = GitHubSimilarityClient.find_by_shared_topics("acme", "widget", max_results=5)
    assert len(out) == 5


def test_find_by_shared_topics_no_topics_returns_empty(monkeypatch):
    _patch_auth(monkeypatch)
    router = _Router(
        {"/repos/acme/widget": _FakeResponse(200, body={"topics": [], "stargazers_count": 1})}
    )
    _install(monkeypatch, router)
    assert GitHubSimilarityClient.find_by_shared_topics("acme", "widget") == []


def test_find_by_shared_topics_search_403_returns_empty_no_raise(monkeypatch):
    _patch_auth(monkeypatch)
    router = _Router(
        {
            "/repos/acme/widget": _seed_repo_response(),
            "/search/repositories": _FakeResponse(403),
        }
    )
    _install(monkeypatch, router)
    # 403 on the first topic search → back off the rest, return [], never raise.
    assert GitHubSimilarityClient.find_by_shared_topics("acme", "widget") == []


def test_find_by_shared_topics_ors_topics_with_per_topic_search(monkeypatch):
    """The OR fix: the seed's topics are searched ONE PER topic (not a single AND
    query), so a repo sharing only ONE of the seed's topics still surfaces.

    Each search responder returns ONLY repos carrying that one topic; a single
    AND'd ``topic:agents topic:llm`` query would have surfaced neither (they
    don't share BOTH). The union must include both."""
    _patch_auth(monkeypatch)

    # The router routes by substring; the client sends q=topic:<t> as a param, so
    # we key the two searches by inspecting the recorded params instead.
    agents_only = _search_item("a", "agentsrepo", stars=500, topics=["agents"])
    llm_only = _search_item("b", "llmrepo", stars=400, topics=["llm"])

    def _get(url, **kwargs):
        params = kwargs.get("params") or {}
        if "/repos/acme/widget" in url:
            return _seed_repo_response()
        if "/search/repositories" in url:
            q = params.get("q", "")
            if "topic:agents" in q:
                return _FakeResponse(200, body={"items": [agents_only]})
            if "topic:llm" in q:
                return _FakeResponse(200, body={"items": [llm_only]})
            return _FakeResponse(200, body={"items": []})
        return _FakeResponse(200, body=[])

    monkeypatch.setattr(gsc.httpx, "get", _get)

    out = GitHubSimilarityClient.find_by_shared_topics("acme", "widget")
    keys = {(c["owner"], c["repo"]) for c in out}
    # Both single-topic repos surface — the OR semantics the AND query lacked.
    assert ("a", "agentsrepo") in keys
    assert ("b", "llmrepo") in keys


def test_find_by_shared_topics_caps_total_searches(monkeypatch):
    """The topic fan-out is bounded by ``topic_search_cap`` — a seed with many
    topics never issues one search per topic unbounded."""
    _patch_auth(monkeypatch)
    many_topics = [f"t{i}" for i in range(20)]
    router = _Router(
        {
            "/repos/acme/widget": _FakeResponse(
                200, body={"topics": many_topics, "stargazers_count": 1, "language": "Python"}
            ),
            "/search/repositories": _FakeResponse(200, body={"items": []}),
        }
    )
    _install(monkeypatch, router)

    GitHubSimilarityClient.find_by_shared_topics("acme", "widget", topic_search_cap=3)
    search_calls = [u for u, _ in router.calls if "/search/repositories" in u]
    assert len(search_calls) == 3  # capped, not 20


def test_find_by_shared_topics_carries_language(monkeypatch):
    """The language fix: a search candidate carries ``language`` so the ranker's
    same-language prior can fire (it was dead at 0.0 before)."""
    _patch_auth(monkeypatch)
    item = {
        "full_name": "rival/agentkit",
        "owner": {"login": "rival"},
        "name": "agentkit",
        "html_url": "https://github.com/rival/agentkit",
        "stargazers_count": 900,
        "language": "Python",
        "topics": ["agents"],
    }
    router = _Router(
        {
            "/repos/acme/widget": _seed_repo_response(),
            "/search/repositories": _FakeResponse(200, body={"items": [item]}),
        }
    )
    _install(monkeypatch, router)

    out = GitHubSimilarityClient.find_by_shared_topics("acme", "widget")
    rival = next(c for c in out if c["repo"] == "agentkit")
    assert rival["language"] == "Python"


# ---------------------------------------------------------------------------
# S2 — stargazer overlap
# ---------------------------------------------------------------------------


def _stargazers_page(logins):
    return _FakeResponse(200, body=[{"login": x} for x in logins])


def _starred_page(repos):
    # repos: list of (owner, name)
    return _FakeResponse(
        200,
        body=[
            {
                "full_name": f"{o}/{n}",
                "owner": {"login": o},
                "name": n,
                "html_url": f"https://github.com/{o}/{n}",
            }
            for (o, n) in repos
        ],
    )


def test_stargazer_overlap_keeps_only_above_min_shared(monkeypatch):
    _patch_auth(monkeypatch)
    # 3 stargazers; cobalt/x is co-starred by all 3 (>= min_shared=3),
    # lonely/y by only 1 (dropped). Seed repo is excluded from the tally.
    routes = {
        "/repos/acme/widget/stargazers": [
            _stargazers_page(["u1", "u2", "u3"]),
            _stargazers_page([]),
        ],
        "/users/u1/starred": [
            _starred_page([("cobalt", "x"), ("acme", "widget"), ("lonely", "y")])
        ],
        "/users/u2/starred": [_starred_page([("cobalt", "x")])],
        "/users/u3/starred": [_starred_page([("cobalt", "x")])],
    }
    router = _Router(routes)
    _install(monkeypatch, router)

    out = GitHubSimilarityClient.find_by_stargazer_overlap(
        "acme", "widget", sample_stargazers=10, per_user_repos=10, min_shared=3
    )
    keys = {(c["owner"], c["repo"]) for c in out}
    assert ("cobalt", "x") in keys  # 3 shared >= min_shared
    assert ("lonely", "y") not in keys  # only 1 shared
    assert ("acme", "widget") not in keys  # seed excluded
    cobalt = next(c for c in out if c["repo"] == "x")
    assert cobalt["shared_stargazers"] == 3
    assert set(cobalt["shared_stargazer_logins"]) == {"u1", "u2", "u3"}


def test_stargazer_overlap_respects_request_hard_cap(monkeypatch):
    _patch_auth(monkeypatch)
    # Many stargazers available, but a tiny request budget must bound total GETs.
    routes = {
        "/repos/acme/widget/stargazers": [_stargazers_page([f"u{i}" for i in range(100)])],
    }
    # default starred (empty list) for any /users/*/starred via router fallback.
    router = _Router(routes)
    _install(monkeypatch, router)

    GitHubSimilarityClient.find_by_stargazer_overlap(
        "acme", "widget", sample_stargazers=100, per_user_repos=10, min_shared=1, max_requests=4
    )
    assert router.count <= 4  # hard cap on total requests honored


def test_stargazer_overlap_403_midfanout_returns_partial_no_raise(monkeypatch):
    _patch_auth(monkeypatch)
    # u1 yields a co-star; u2's starred fetch 403s → back off, keep u1's tally.
    routes = {
        "/repos/acme/widget/stargazers": [
            _stargazers_page(["u1", "u2", "u3"]),
            _stargazers_page([]),
        ],
        "/users/u1/starred": [_starred_page([("cobalt", "x")])],
        "/users/u2/starred": [_FakeResponse(403)],
        "/users/u3/starred": [_starred_page([("cobalt", "x")])],
    }
    router = _Router(routes)
    _install(monkeypatch, router)

    out = GitHubSimilarityClient.find_by_stargazer_overlap(
        "acme", "widget", sample_stargazers=10, per_user_repos=10, min_shared=1
    )
    # Did not raise; u3 never fetched (backed off at u2's 403); u1's single
    # co-star survives at min_shared=1.
    assert any(c["repo"] == "x" for c in out)
    assert all("/users/u3/starred" not in url for url, _ in router.calls)


def test_stargazer_overlap_stargazer_page_403_returns_empty(monkeypatch):
    _patch_auth(monkeypatch)
    router = _Router({"/repos/acme/widget/stargazers": [_FakeResponse(403)]})
    _install(monkeypatch, router)
    # 403 on the very first stargazer page → no stargazers gathered → [].
    assert GitHubSimilarityClient.find_by_stargazer_overlap("acme", "widget", min_shared=1) == []


def test_stargazer_overlap_isolates_one_bad_user(monkeypatch):
    _patch_auth(monkeypatch)
    # u2's starred fetch raises a transport error inside _get → returns None →
    # the per-user fetch yields nothing; u1 and u3 still tally. No 403, so the
    # loop continues past u2 (isolation, not back-off).
    routes = {
        "/repos/acme/widget/stargazers": [
            _stargazers_page(["u1", "u2", "u3"]),
            _stargazers_page([]),
        ],
        "/users/u1/starred": [_starred_page([("cobalt", "x")])],
        "/users/u3/starred": [_starred_page([("cobalt", "x")])],
    }
    raising = {"/users/u2/starred"}

    base_router = _Router(routes)

    def _get(url, **kwargs):
        if any(n in url for n in raising):
            raise gsc.httpx.ConnectError("boom")
        return base_router(url, **kwargs)

    monkeypatch.setattr(gsc.httpx, "get", _get)

    out = GitHubSimilarityClient.find_by_stargazer_overlap(
        "acme", "widget", sample_stargazers=10, per_user_repos=10, min_shared=2
    )
    cobalt = next(c for c in out if c["repo"] == "x")
    assert cobalt["shared_stargazers"] == 2  # u1 + u3, u2 isolated
