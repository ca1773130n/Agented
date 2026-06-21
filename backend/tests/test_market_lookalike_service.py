"""MarketLookalikeService tests (phase 27-03) — provider-resolve + P2-DAO reuse.

The orchestration layer is deterministic and owns NO persistence: a FAKE configured
provider is registered into the 27-01 registry (no Apistemic key, no network) and
the assertions prove the service funnels its ``Candidate``s into the EXISTING P2
``discovery_suggestion`` surface (``kind="company"``) and delegates promote/dismiss
straight through to ``DiscoveryService``. Covers:

  * no provider configured → ``not_configured`` short-circuit, NO rows written;
  * configured fake provider → 2 candidates upserted (kind="company",
    owner=provider, repo=normalized domain, evidence round-trips), outcome "ok";
  * re-scan idempotency (UPSERT, no duplicate rows, score refreshed) — inherited
    from the P2 DAO;
  * sticky verdict — a dismissed row stays ``dismissed`` across a re-scan;
  * NULL score still upserts (never-block-on-optional);
  * non-ok provider outcome (not_configured / throttled / error) passed straight up;
  * promote → ``competitor_source(kind=product_url)`` + status flips to ``added``;
  * dismiss → status ``dismissed``;
  * ``list_suggestions`` returns ONLY market kinds (a github_repo discovery row is
    excluded from the market queue).
"""

from __future__ import annotations

import pytest

from app.db import discovery_suggestions
from app.db.projects import create_project
from app.services import market_lookalike_service as mls_module
from app.services.competitor_source_service import KIND_PRODUCT_URL
from app.services.lookalike_providers import registry
from app.services.lookalike_providers.base import Candidate, LookalikeResult
from app.services.market_lookalike_service import MarketLookalikeService


class _FakeProvider:
    """A configured fake provider returning a canned ``LookalikeResult``.

    Satisfies the ``LookalikeProvider`` Protocol structurally. ``is_configured``
    is forced True so ``active_provider()`` resolves to it (no Apistemic key
    needed — no network is ever touched).
    """

    name = "fake"

    def __init__(self, result: LookalikeResult):
        self._result = result

    def is_configured(self) -> bool:
        return True

    def find_lookalikes(self, seed: str, *, limit: int = 20) -> LookalikeResult:
        return self._result


@pytest.fixture
def _clean_registry(monkeypatch):
    """Empty the registry so a test starts with NO provider (the BUY-gate)."""
    monkeypatch.setattr(registry, "_PROVIDERS", {})
    # Pin nothing so the env explicit-pick path is inert.
    monkeypatch.delenv("MARKET_LOOKALIKE_PROVIDER", raising=False)
    monkeypatch.delenv("APISTEMIC_API_KEY", raising=False)
    return registry


@pytest.fixture
def _project(isolated_db):
    """A project row for the suggestion FK."""
    return create_project(name="Market CI")


def _register(monkeypatch, result: LookalikeResult) -> _FakeProvider:
    """Register a fake configured provider returning ``result``."""
    provider = _FakeProvider(result)
    monkeypatch.setattr(registry, "_PROVIDERS", {provider.name: provider})
    return provider


# --------------------------------------------------------------------------- #
# not_configured short-circuit (BUY gate)
# --------------------------------------------------------------------------- #


def test_scan_no_provider_returns_not_configured_and_writes_no_rows(_clean_registry, _project):
    project_id = _project
    result = MarketLookalikeService.scan_project(project_id, seed="acme.com")
    assert result == {
        "provider": None,
        "outcome": "not_configured",
        "scanned": 0,
        "suggestions": [],
    }
    # No discovery_suggestion rows written.
    assert discovery_suggestions.list_suggestions(project_id) == []


# --------------------------------------------------------------------------- #
# configured provider → upsert via the P2 DAO (kind="company")
# --------------------------------------------------------------------------- #


def _two_candidate_result() -> LookalikeResult:
    return LookalikeResult(
        outcome="ok",
        candidates=[
            Candidate(
                url="https://www.rival-one.com/product",
                name="Rival One",
                score=0.9,
                evidence={"provider": "fake", "reason": "same market", "domain": "rival-one.com"},
            ),
            Candidate(
                url="https://rival-two.io",
                name="Rival Two",
                score=0.4,
                evidence={"provider": "fake", "reason": "adjacent", "domain": "rival-two.io"},
            ),
        ],
    )


def test_scan_configured_upserts_company_suggestions(_clean_registry, _project, monkeypatch):
    project_id = _project
    _register(monkeypatch, _two_candidate_result())

    result = MarketLookalikeService.scan_project(project_id, seed="acme.com")
    assert result["provider"] == "fake"
    assert result["outcome"] == "ok"
    assert result["scanned"] == 2

    rows = discovery_suggestions.list_suggestions(project_id)
    assert len(rows) == 2
    by_repo = {r["candidate_repo"]: r for r in rows}
    # Normalized domain (www stripped, lowercased) is the repo key.
    assert set(by_repo) == {"rival-one.com", "rival-two.io"}
    top = by_repo["rival-one.com"]
    assert top["kind"] == "company"
    # Owner is NAMESPACED so it can never collide with a P2 github_repo row.
    assert top["candidate_owner"] == "lookalike:fake"
    assert top["candidate_url"] == "https://www.rival-one.com/product"
    assert top["status"] == "suggested"
    # evidence round-trips as a parsed dict; reason mirrors evidence.reason.
    assert top["evidence"]["reason"] == "same market"
    assert top["reason"] == "same market"


def test_scan_skips_candidate_with_no_domain(_clean_registry, _project, monkeypatch):
    project_id = _project
    _register(
        monkeypatch,
        LookalikeResult(
            outcome="ok",
            candidates=[
                Candidate(url="", name="No URL", score=0.5),
                Candidate(url="https://good.com", name="Good", score=0.5),
            ],
        ),
    )
    result = MarketLookalikeService.scan_project(project_id, seed="acme.com")
    # scanned counts the raw candidates; only the domain-bearing one is upserted.
    assert result["scanned"] == 2
    rows = discovery_suggestions.list_suggestions(project_id)
    assert [r["candidate_repo"] for r in rows] == ["good.com"]


# --------------------------------------------------------------------------- #
# idempotency + sticky verdict (inherited from the P2 DAO — verify, not reimplement)
# --------------------------------------------------------------------------- #


def test_rescan_is_idempotent_and_refreshes_score(_clean_registry, _project, monkeypatch):
    project_id = _project
    _register(monkeypatch, _two_candidate_result())
    MarketLookalikeService.scan_project(project_id, seed="acme.com")

    # Re-register with a refreshed score for rival-one; re-scan.
    _register(
        monkeypatch,
        LookalikeResult(
            outcome="ok",
            candidates=[
                Candidate(
                    url="https://www.rival-one.com/product",
                    name="Rival One",
                    score=0.99,
                    evidence={"provider": "fake", "reason": "still same market"},
                ),
                Candidate(
                    url="https://rival-two.io",
                    name="Rival Two",
                    score=0.4,
                    evidence={"provider": "fake", "reason": "adjacent"},
                ),
            ],
        ),
    )
    MarketLookalikeService.scan_project(project_id, seed="acme.com")

    rows = discovery_suggestions.list_suggestions(project_id)
    assert len(rows) == 2  # UPSERT — no duplicate row.
    by_repo = {r["candidate_repo"]: r for r in rows}
    assert by_repo["rival-one.com"]["score"] == 0.99  # refreshed
    assert by_repo["rival-one.com"]["reason"] == "still same market"


def test_dismissed_row_stays_dismissed_across_rescan(_clean_registry, _project, monkeypatch):
    project_id = _project
    _register(monkeypatch, _two_candidate_result())
    MarketLookalikeService.scan_project(project_id, seed="acme.com")

    rows = discovery_suggestions.list_suggestions(project_id)
    target = next(r for r in rows if r["candidate_repo"] == "rival-two.io")
    MarketLookalikeService.dismiss_suggestion(project_id, target["id"])

    # Re-scan: the dismissed row must NOT resurrect to 'suggested'.
    MarketLookalikeService.scan_project(project_id, seed="acme.com")
    refreshed = discovery_suggestions.get_suggestion(target["id"], project_id=project_id)
    assert refreshed["status"] == "dismissed"
    # And it is excluded from the suggested market queue.
    queue_repos = {r["candidate_repo"] for r in MarketLookalikeService.list_suggestions(project_id)}
    assert "rival-two.io" not in queue_repos


def test_null_score_candidate_still_upserts(_clean_registry, _project, monkeypatch):
    project_id = _project
    _register(
        monkeypatch,
        LookalikeResult(
            outcome="ok",
            candidates=[Candidate(url="https://noscore.com", name="No Score", score=None)],
        ),
    )
    result = MarketLookalikeService.scan_project(project_id, seed="acme.com")
    assert result["scanned"] == 1
    rows = discovery_suggestions.list_suggestions(project_id)
    assert len(rows) == 1
    assert rows[0]["candidate_repo"] == "noscore.com"
    assert rows[0]["score"] is None


# --------------------------------------------------------------------------- #
# non-ok outcomes + no-seed pass straight through
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("outcome", ["not_configured", "throttled", "error"])
def test_non_ok_outcome_passes_through_and_writes_no_rows(
    _clean_registry, _project, monkeypatch, outcome
):
    project_id = _project
    _register(monkeypatch, LookalikeResult(outcome=outcome, detail="provider says"))
    result = MarketLookalikeService.scan_project(project_id, seed="acme.com")
    assert result["provider"] == "fake"
    assert result["outcome"] == outcome
    assert result["detail"] == "provider says"
    assert result["scanned"] == 0
    assert result["suggestions"] == []
    assert discovery_suggestions.list_suggestions(project_id) == []


def test_configured_provider_no_derivable_seed_returns_no_seed(
    _clean_registry, _project, monkeypatch
):
    """No explicit seed AND no product_url source → graceful ``no_seed`` (NOT 500)."""

    class _ExplodingProvider(_FakeProvider):
        def find_lookalikes(self, seed: str, *, limit: int = 20):  # pragma: no cover
            raise AssertionError("provider must NOT be called when there is no seed")

    provider = _ExplodingProvider(_two_candidate_result())
    monkeypatch.setattr(registry, "_PROVIDERS", {provider.name: provider})

    project_id = _project
    result = MarketLookalikeService.scan_project(project_id)  # no seed, no product source
    assert result["provider"] == "fake"
    assert result["outcome"] == "no_seed"
    assert "product" in result["detail"]
    assert result["scanned"] == 0
    assert result["suggestions"] == []
    assert discovery_suggestions.list_suggestions(project_id) == []


def test_scan_derives_seeds_from_product_url_sources(_clean_registry, _project, monkeypatch):
    """Seedless scan derives seed domain(s) from the project's product_url sources."""
    from app.services.competitor_source_service import CompetitorSourceService

    project_id = _project
    # A product_url source (derivable seed) + a github_repo source (NOT a seed).
    CompetitorSourceService.add_source(project_id, url="https://www.acme-corp.com/app")
    CompetitorSourceService.add_source(
        project_id, url="https://github.com/acme/widget", kind="github_repo"
    )

    seen_seeds: list[str] = []

    class _RecordingProvider(_FakeProvider):
        def find_lookalikes(self, seed: str, *, limit: int = 20):
            seen_seeds.append(seed)
            return self._result

    provider = _RecordingProvider(_two_candidate_result())
    monkeypatch.setattr(registry, "_PROVIDERS", {provider.name: provider})

    result = MarketLookalikeService.scan_project(project_id)  # seedless UI call
    # The provider was called with the derived domain (host of the product_url),
    # NOT the github_repo source.
    assert seen_seeds == ["acme-corp.com"]
    assert result["outcome"] == "ok"
    assert result["scanned"] == 2
    repos = {r["candidate_repo"] for r in discovery_suggestions.list_suggestions(project_id)}
    assert {"rival-one.com", "rival-two.io"} <= repos


# --------------------------------------------------------------------------- #
# pass-through promote / dismiss to DiscoveryService
# --------------------------------------------------------------------------- #


def test_promote_lands_product_url_source_and_flips_added(_clean_registry, _project, monkeypatch):
    project_id = _project
    _register(monkeypatch, _two_candidate_result())
    MarketLookalikeService.scan_project(project_id, seed="acme.com")

    rows = discovery_suggestions.list_suggestions(project_id)
    target = next(r for r in rows if r["candidate_repo"] == "rival-one.com")
    out = MarketLookalikeService.promote_suggestion(project_id, target["id"])

    # The promoted competitor_source is on the product_url lane (detect_kind fallback).
    assert out["source"]["kind"] == KIND_PRODUCT_URL
    assert out["source"]["url"] == "https://www.rival-one.com/product"
    # The suggestion flips to 'added' with a stamped source_id.
    assert out["suggestion"]["status"] == "added"
    assert out["suggestion"]["source_id"] == out["source"]["id"]


def test_dismiss_passes_through(_clean_registry, _project, monkeypatch):
    project_id = _project
    _register(monkeypatch, _two_candidate_result())
    MarketLookalikeService.scan_project(project_id, seed="acme.com")

    rows = discovery_suggestions.list_suggestions(project_id)
    target = rows[0]
    out = MarketLookalikeService.dismiss_suggestion(project_id, target["id"])
    assert out["suggestion"]["status"] == "dismissed"


# --------------------------------------------------------------------------- #
# market-only list filter
# --------------------------------------------------------------------------- #


def test_list_suggestions_excludes_github_repo_rows(_clean_registry, _project, monkeypatch):
    project_id = _project
    _register(monkeypatch, _two_candidate_result())
    MarketLookalikeService.scan_project(project_id, seed="acme.com")

    # Seed a github_repo discovery row directly via the P2 DAO (a non-market kind).
    discovery_suggestions.upsert_suggestion(
        project_id,
        owner="someorg",
        repo="somerepo",
        url="https://github.com/someorg/somerepo",
        kind="github_repo",
        score=0.7,
    )

    queue = MarketLookalikeService.list_suggestions(project_id)
    kinds = {r["kind"] for r in queue}
    assert kinds == {"company"}  # github_repo excluded from the market queue
    repos = {r["candidate_repo"] for r in queue}
    assert "somerepo" not in repos


# --------------------------------------------------------------------------- #
# discovery_suggestion key namespace — github + company rows must COEXIST
# --------------------------------------------------------------------------- #


def test_github_and_company_rows_coexist_no_clobber(_clean_registry, _project, monkeypatch):
    """A github_repo row and a company row at the OLD (project, owner, repo) key
    now coexist — the namespaced company owner prevents the clobber, and promote
    still lands the right product_url competitor_source."""
    from app.services.competitor_source_service import KIND_PRODUCT_URL

    project_id = _project

    # A P2 github_repo suggestion at the key the OLD un-namespaced company code
    # would have used: owner="fake" (the provider name), repo="rival-one.com".
    discovery_suggestions.upsert_suggestion(
        project_id,
        owner="fake",
        repo="rival-one.com",
        url="https://github.com/fake/rival-one.com",
        kind="github_repo",
        score=0.7,
    )

    # Now the company scan writes owner="lookalike:fake", repo="rival-one.com" —
    # a DISJOINT key, so the github row is NOT clobbered.
    _register(monkeypatch, _two_candidate_result())
    MarketLookalikeService.scan_project(project_id, seed="acme.com")

    rows = discovery_suggestions.list_suggestions(project_id)
    by_key = {(r["candidate_owner"], r["candidate_repo"]): r for r in rows}
    # Both rows exist side by side.
    github_row = by_key[("fake", "rival-one.com")]
    company_row = by_key[("lookalike:fake", "rival-one.com")]
    assert github_row["kind"] == "github_repo"
    assert github_row["candidate_url"] == "https://github.com/fake/rival-one.com"
    assert company_row["kind"] == "company"
    assert company_row["candidate_url"] == "https://www.rival-one.com/product"

    # Promote the company row → product_url source keyed off candidate_url
    # (unaffected by the namespaced owner).
    out = MarketLookalikeService.promote_suggestion(project_id, company_row["id"])
    assert out["source"]["kind"] == KIND_PRODUCT_URL
    assert out["source"]["url"] == "https://www.rival-one.com/product"


def test_module_exposes_service(_clean_registry):
    # Sanity: the service is importable off the module (route wiring in 27-04).
    assert mls_module.MarketLookalikeService is MarketLookalikeService
