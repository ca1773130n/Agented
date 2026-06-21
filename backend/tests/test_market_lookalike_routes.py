"""Market-lookalike route shape tests (27-04 — the operator scan→review loop).

Exercises the project-scoped ``/api/projects/{id}/lookalikes/*`` router through a
Litestar TestClient against an ``isolated_db``. NO live provider call ever runs:

  * the BUY-gate path is exercised with the registry EMPTY + ``APISTEMIC_API_KEY``
    unset → ``active_provider()`` is ``None`` → scan returns a NORMAL 200 with
    ``{provider: null, outcome: 'not_configured', scanned: 0, suggestions: []}``
    (the headline graceful-degradation deliverable — a 200, NEVER a 4xx/5xx);
  * the populated path registers a FAKE configured provider (structural
    ``LookalikeProvider``, ``is_configured()`` forced True, canned candidates — no
    Apistemic key, no network) so the scan→upsert (``kind='company'``) → list →
    accept (``product_url``) → dismiss loop is exercised end-to-end against real
    ``discovery_suggestion`` / ``competitor_source`` rows.

Per CLAUDE.md the TestClient logger doesn't propagate to caplog, so the IDOR
guard is asserted by status code (404, not 403 — the P1 lesson), mirroring
``test_discovery_routes`` (monkeypatch ``routes.can_access → False``).

The live Apistemic request/response stays a DEFERRED, configured-when-keyed seam
(no account): the default/CI install resolves to ``None`` and the populated path
uses the FAKE provider, so this suite never depends on a live Apistemic call.
"""

from __future__ import annotations

import pytest
from litestar.testing import create_test_client

from app.database import get_connection
from app.db import discovery_suggestions as dao
from app.db.projects import create_project
from app.services.competitor_source_service import KIND_PRODUCT_URL
from app.services.lookalike_providers import registry
from app.services.lookalike_providers.base import Candidate, LookalikeResult
from app_litestar.auth import provide_caller
from app_litestar.routes.market_lookalike_routes import market_lookalike_router


def _client():
    return create_test_client(
        route_handlers=[market_lookalike_router],
        dependencies={"caller": provide_caller},
    )


class _FakeProvider:
    """A configured fake provider returning a canned ``LookalikeResult``.

    Satisfies the ``LookalikeProvider`` Protocol structurally; ``is_configured``
    is forced True so ``active_provider()`` resolves to it (no Apistemic key, no
    network). Identical to the 27-03 service-test fake.
    """

    name = "fake"

    def __init__(self, result: LookalikeResult):
        self._result = result

    def is_configured(self) -> bool:
        return True

    def find_lookalikes(self, seed: str, *, limit: int = 20) -> LookalikeResult:
        return self._result


@pytest.fixture
def _no_provider(monkeypatch):
    """Empty the registry + unset the key so ``active_provider()`` is ``None``."""
    monkeypatch.setattr(registry, "_PROVIDERS", {})
    monkeypatch.delenv("MARKET_LOOKALIKE_PROVIDER", raising=False)
    monkeypatch.delenv("APISTEMIC_API_KEY", raising=False)
    return registry


@pytest.fixture
def _fake_provider(monkeypatch):
    """Register a configured FAKE provider returning two canned candidates."""
    monkeypatch.setattr(registry, "_PROVIDERS", {})
    monkeypatch.delenv("MARKET_LOOKALIKE_PROVIDER", raising=False)
    monkeypatch.delenv("APISTEMIC_API_KEY", raising=False)
    result = LookalikeResult(
        outcome="ok",
        candidates=[
            Candidate(
                url="https://acme.example.com",
                name="Acme",
                score=0.91,
                evidence={"reason": "same buyer + adjacent category"},
            ),
            Candidate(
                url="https://www.beta.example.org/product",
                name="Beta",
                score=0.42,
                evidence={"reason": "overlapping keywords"},
            ),
        ],
    )
    provider = _FakeProvider(result)
    registry.register(provider)
    return provider


# ---------------------------------------------------------------------------
# POST /lookalikes/scan — BUY-gate: not_configured is a NORMAL 200
# ---------------------------------------------------------------------------


def test_scan_not_configured_is_200_not_error(isolated_db, _no_provider):
    """The headline assertion: NO provider keyed → 200 with provider:null /
    outcome:'not_configured' / scanned:0 / suggestions:[] — NEVER a 4xx/5xx."""
    project_id = create_project(name="la-proj")
    with _client() as c:
        resp = c.post(f"/api/projects/{project_id}/lookalikes/scan", json={"seed": "anything"})
    assert resp.status_code == 200  # scan is not a create
    body = resp.json()
    assert body == {
        "provider": None,
        "outcome": "not_configured",
        "scanned": 0,
        "suggestions": [],
    }
    # The BUY-gate wrote NO rows.
    assert dao.list_suggestions(project_id, statuses=["suggested"]) == []


def test_scan_configured_provider_writes_company_rows(isolated_db, _fake_provider):
    """A configured provider → outcome 'ok' and market discovery_suggestion rows
    (kind='company', owner=provider name, repo=normalized domain)."""
    project_id = create_project(name="la-proj")
    with _client() as c:
        resp = c.post(f"/api/projects/{project_id}/lookalikes/scan", json={"seed": "my product"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "fake"
    assert body["outcome"] == "ok"
    assert body["scanned"] == 2

    rows = dao.list_suggestions(project_id, statuses=["suggested"])
    assert len(rows) == 2
    assert {r["kind"] for r in rows} == {"company"}
    # Owner is namespaced (``lookalike:<provider>``) so it never collides with a
    # P2 github_repo suggestion in the shared discovery_suggestion unique key.
    assert {r["candidate_owner"] for r in rows} == {"lookalike:fake"}
    # www.-stripped, lowercased domain is the dedupe key.
    assert {r["candidate_repo"] for r in rows} == {"acme.example.com", "beta.example.org"}


# ---------------------------------------------------------------------------
# GET /lookalikes/suggestions — {provider, suggestions}; market-kind only
# ---------------------------------------------------------------------------


def test_list_reports_provider_name_and_market_kind_only(isolated_db, _fake_provider):
    """GET returns {provider: '<name>', suggestions: [...]} and EXCLUDES a
    github_repo discovery row (only company/product kinds are the market queue)."""
    project_id = create_project(name="la-proj")
    # A market (company) lookalike.
    dao.upsert_suggestion(
        project_id,
        owner="fake",
        repo="acme.example.com",
        url="https://acme.example.com",
        kind="company",
        score=0.9,
        reason="market why",
    )
    # A github_repo discovery row — must NOT bleed into the market queue.
    dao.upsert_suggestion(
        project_id,
        owner="octocat",
        repo="hello-world",
        url="https://github.com/octocat/hello-world",
        kind="github_repo",
        score=0.5,
    )

    with _client() as c:
        resp = c.get(f"/api/projects/{project_id}/lookalikes/suggestions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "fake"
    rows = body["suggestions"]
    assert len(rows) == 1
    assert rows[0]["kind"] == "company"
    assert rows[0]["candidate_owner"] == "fake"


def test_list_provider_null_when_unconfigured(isolated_db, _no_provider):
    """With no provider keyed, the queue reports provider:null (the CTA signal)."""
    project_id = create_project(name="la-proj")
    with _client() as c:
        resp = c.get(f"/api/projects/{project_id}/lookalikes/suggestions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] is None
    assert body["suggestions"] == []


# ---------------------------------------------------------------------------
# POST /accept — promote → competitor_source(kind=product_url), status 'added'
# ---------------------------------------------------------------------------


def test_accept_promotes_to_product_url_source(isolated_db):
    """Accept promotes a company lookalike into a watched competitor_source on the
    product_url lane and flips the suggestion to 'added'."""
    project_id = create_project(name="la-proj")
    sug = dao.upsert_suggestion(
        project_id,
        owner="fake",
        repo="acme.example.com",
        url="https://acme.example.com",
        kind="company",
        score=0.9,
        reason="strong fit",
    )

    with _client() as c:
        resp = c.post(f"/api/projects/{project_id}/lookalikes/suggestions/{sug['id']}/accept")
    assert resp.status_code == 201
    body = resp.json()
    source = body["source"]
    assert source["project_id"] == project_id
    assert source["kind"] == KIND_PRODUCT_URL

    # A competitor_source row on the product_url lane now exists.
    with get_connection() as conn:
        row = conn.execute(
            "SELECT kind FROM competitor_source WHERE id = ?", (source["id"],)
        ).fetchone()
    assert row is not None
    assert row["kind"] == KIND_PRODUCT_URL

    updated = dao.get_suggestion(sug["id"])
    assert updated["status"] == "added"
    assert updated["source_id"] == source["id"]


def test_accept_unknown_suggestion_404(isolated_db):
    project_id = create_project(name="la-proj")
    with _client() as c:
        resp = c.post(f"/api/projects/{project_id}/lookalikes/suggestions/dsug-missing0/accept")
    assert resp.status_code == 404


def test_accept_dismissed_suggestion_409(isolated_db):
    """Accepting a DISMISSED lookalike → 409 (PromotionConflict)."""
    project_id = create_project(name="la-proj")
    sug = dao.upsert_suggestion(
        project_id,
        owner="fake",
        repo="acme.example.com",
        url="https://acme.example.com",
        kind="company",
        score=0.2,
    )
    dao.set_status(sug["id"], "dismissed")

    with _client() as c:
        resp = c.post(f"/api/projects/{project_id}/lookalikes/suggestions/{sug['id']}/accept")
    assert resp.status_code == 409
    assert dao.get_suggestion(sug["id"])["status"] == "dismissed"
    with get_connection() as conn:
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM competitor_source WHERE project_id = ?", (project_id,)
        ).fetchone()["n"]
    assert n == 0


# ---------------------------------------------------------------------------
# POST /dismiss — flip status to 'dismissed'
# ---------------------------------------------------------------------------


def test_dismiss_flips_status(isolated_db):
    project_id = create_project(name="la-proj")
    sug = dao.upsert_suggestion(
        project_id,
        owner="fake",
        repo="noise.example.com",
        url="https://noise.example.com",
        kind="company",
        score=0.1,
    )

    with _client() as c:
        resp = c.post(f"/api/projects/{project_id}/lookalikes/suggestions/{sug['id']}/dismiss")
    assert resp.status_code == 201
    assert resp.json()["suggestion"]["status"] == "dismissed"
    assert dao.get_suggestion(sug["id"])["status"] == "dismissed"


def test_dismiss_unknown_suggestion_404(isolated_db):
    project_id = create_project(name="la-proj")
    with _client() as c:
        resp = c.post(f"/api/projects/{project_id}/lookalikes/suggestions/dsug-missing0/dismiss")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# IDOR — a caller without project access gets 404 (NOT 403) on EVERY route
# ---------------------------------------------------------------------------


def test_every_route_404s_for_inaccessible_project(isolated_db, monkeypatch):
    """The P1 IDOR lesson: a project the caller can't access → 404 (no existence
    leak) on scan + list + accept + dismiss alike."""
    import app_litestar.routes.market_lookalike_routes as routes

    project_id = create_project(name="owned-by-someone-else")
    sug = dao.upsert_suggestion(
        project_id,
        owner="fake",
        repo="acme.example.com",
        url="https://acme.example.com",
        kind="company",
        score=0.5,
    )
    monkeypatch.setattr(routes, "can_access", lambda *a, **k: False)

    with _client() as c:
        assert (
            c.post(f"/api/projects/{project_id}/lookalikes/scan", json={"seed": "x"}).status_code
            == 404
        )
        assert c.get(f"/api/projects/{project_id}/lookalikes/suggestions").status_code == 404
        assert (
            c.post(
                f"/api/projects/{project_id}/lookalikes/suggestions/{sug['id']}/accept"
            ).status_code
            == 404
        )
        assert (
            c.post(
                f"/api/projects/{project_id}/lookalikes/suggestions/{sug['id']}/dismiss"
            ).status_code
            == 404
        )

    # The guard short-circuited BEFORE any mutation.
    assert dao.get_suggestion(sug["id"])["status"] == "suggested"
    with get_connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM competitor_source WHERE project_id = ?", (project_id,)
        ).fetchone()["n"]
    assert count == 0


def test_unknown_project_404_before_scan(isolated_db, _no_provider):
    """A non-existent project 404s on scan (existence check before resolution)."""
    with _client() as c:
        resp = c.post("/api/projects/missing/lookalikes/scan", json={"seed": "x"})
    assert resp.status_code == 404
