"""Agent-assisted discovery route shape tests (24-04 — discover→review→verdict loop).

Exercises the project-scoped ``/api/projects/{id}/discovery/*`` router through a
Litestar TestClient against an ``isolated_db`` (migration 172 applies, so the
``discovery_suggestion`` table exists; 171 gives ``competitor_source`` for the
accept promotion). NO live GitHub: the heavy ``scan`` is monkeypatched to canned
counts; the queue / accept / dismiss tests seed ``discovery_suggestion`` rows
directly through the 24-01 DAO and run the REAL ``DiscoveryService`` promote /
dismiss against real ``competitor_source`` rows so the ``origin='discovery'``
promotion + the sticky status flip are exercised end-to-end.

Per CLAUDE.md the TestClient logger doesn't propagate to caplog, so the IDOR
guard is asserted by status code (404, not 403 — the P1 lesson), mirroring
``test_competitor_intel_routes`` (monkeypatch ``routes.can_access → False``).
"""

from litestar.testing import create_test_client

from app.database import get_connection
from app.db import discovery_suggestions as dao
from app.db.projects import create_project
from app_litestar.auth import provide_caller
from app_litestar.routes.discovery_routes import discovery_router


def _client():
    return create_test_client(
        route_handlers=[discovery_router],
        dependencies={"caller": provide_caller},
    )


def _seed_suggestion(project_id, owner, repo, *, score=None, reason=None):
    """Insert one discovery_suggestion via the 24-01 DAO (status 'suggested')."""
    return dao.upsert_suggestion(
        project_id,
        owner,
        repo,
        f"https://github.com/{owner}/{repo}",
        score=score,
        reason=reason,
    )


# ---------------------------------------------------------------------------
# POST /discovery/scan — heavy fan-out (mocked), returns the scan summary
# ---------------------------------------------------------------------------


def test_scan_returns_summary_and_writes_rows(isolated_db, monkeypatch):
    """POST /scan returns {scanned, suggestions, readme_mode}; the route delegates
    to DiscoveryService.scan_project (mocked here so no live GitHub fan-out)."""
    import app_litestar.routes.discovery_routes as routes

    project_id = create_project(name="disc-proj")

    captured = {}

    def fake_scan(pid):
        captured["pid"] = pid
        # The mocked scan also writes a row so the queue read below is non-empty.
        dao.upsert_suggestion(
            pid, "acme", "widget", "https://github.com/acme/widget", score=0.8, reason="why"
        )
        return {"scanned": 2, "suggestions": 1, "readme_mode": "text"}

    monkeypatch.setattr(routes.DiscoveryService, "scan_project", staticmethod(fake_scan))

    with _client() as c:
        resp = c.post(f"/api/projects/{project_id}/discovery/scan")
    assert resp.status_code == 201
    body = resp.json()
    assert body == {"scanned": 2, "suggestions": 1, "readme_mode": "text"}
    assert captured["pid"] == project_id
    # The mocked scan persisted a suggestion row.
    rows = dao.list_suggestions(project_id, statuses=["suggested"])
    assert len(rows) == 1
    assert rows[0]["candidate_owner"] == "acme"


# ---------------------------------------------------------------------------
# GET /discovery/suggestions — ranked active queue (score desc, NULLs last)
# ---------------------------------------------------------------------------


def test_list_suggestions_ranked_by_score_desc(isolated_db):
    project_id = create_project(name="disc-proj")
    _seed_suggestion(project_id, "lo", "one", score=0.30, reason="low")
    _seed_suggestion(project_id, "hi", "two", score=0.95, reason="high")

    with _client() as c:
        resp = c.get(f"/api/projects/{project_id}/discovery/suggestions")
    assert resp.status_code == 200
    rows = resp.json()["suggestions"]
    assert len(rows) == 2
    # Ranked: highest score first.
    assert rows[0]["candidate_repo"] == "two"
    assert rows[0]["score"] == 0.95
    assert rows[0]["reason"] == "high"
    assert rows[1]["score"] == 0.30
    # Every queued row is 'suggested'.
    assert all(r["status"] == "suggested" for r in rows)


def test_list_suggestions_excludes_non_suggested(isolated_db):
    """The active queue only returns status='suggested' (accepted/dismissed drop)."""
    project_id = create_project(name="disc-proj")
    kept = _seed_suggestion(project_id, "keep", "me", score=0.5)
    gone = _seed_suggestion(project_id, "drop", "me", score=0.6)
    dao.set_status(gone["id"], "dismissed")

    with _client() as c:
        resp = c.get(f"/api/projects/{project_id}/discovery/suggestions")
    assert resp.status_code == 200
    rows = resp.json()["suggestions"]
    assert [r["id"] for r in rows] == [kept["id"]]


def test_list_suggestions_is_project_scoped(isolated_db):
    project_a = create_project(name="proj-a")
    project_b = create_project(name="proj-b")
    _seed_suggestion(project_a, "a", "mine", score=0.5)
    _seed_suggestion(project_b, "b", "theirs", score=0.5)

    with _client() as c:
        resp = c.get(f"/api/projects/{project_a}/discovery/suggestions")
    assert resp.status_code == 200
    rows = resp.json()["suggestions"]
    assert len(rows) == 1
    assert rows[0]["candidate_owner"] == "a"
    assert all(r["project_id"] == project_a for r in rows)


# ---------------------------------------------------------------------------
# POST /discovery/suggestions/{sid}/accept — promote → competitor_source
# ---------------------------------------------------------------------------


def test_accept_promotes_to_competitor_source_origin_discovery(isolated_db):
    """Accept promotes via add_source(origin='discovery') and flips status='added'.

    Runs the REAL DiscoveryService.promote_suggestion (add_source needs no
    network) so the origin stamp + the source_id back-reference are exercised."""
    project_id = create_project(name="disc-proj")
    sug = _seed_suggestion(project_id, "acme", "widget", score=0.9, reason="strong overlap")

    with _client() as c:
        resp = c.post(f"/api/projects/{project_id}/discovery/suggestions/{sug['id']}/accept")
    assert resp.status_code == 201
    body = resp.json()
    assert "source" in body
    source = body["source"]
    assert source["id"].startswith("cmps-")
    assert source["origin"] == "discovery"
    assert source["project_id"] == project_id

    # A competitor_source row with origin='discovery' now exists.
    with get_connection() as conn:
        row = conn.execute(
            "SELECT origin FROM competitor_source WHERE id = ?", (source["id"],)
        ).fetchone()
    assert row is not None
    assert row["origin"] == "discovery"

    # The suggestion flipped to 'added' and back-references the new source.
    updated = dao.get_suggestion(sug["id"])
    assert updated["status"] == "added"
    assert updated["source_id"] == source["id"]
    # It drops out of the active queue.
    with _client() as c:
        queue = c.get(f"/api/projects/{project_id}/discovery/suggestions").json()["suggestions"]
    assert sug["id"] not in [r["id"] for r in queue]


def test_accept_unknown_suggestion_404(isolated_db):
    """An unknown suggestion id → 404 (ValueError out of the service)."""
    project_id = create_project(name="disc-proj")
    with _client() as c:
        resp = c.post(f"/api/projects/{project_id}/discovery/suggestions/dsug-missing0/accept")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /discovery/suggestions/{sid}/dismiss — flip status='dismissed'
# ---------------------------------------------------------------------------


def test_dismiss_flips_status(isolated_db):
    project_id = create_project(name="disc-proj")
    sug = _seed_suggestion(project_id, "noise", "repo", score=0.2)

    with _client() as c:
        resp = c.post(f"/api/projects/{project_id}/discovery/suggestions/{sug['id']}/dismiss")
    assert resp.status_code == 201
    assert resp.json()["suggestion"]["status"] == "dismissed"
    assert dao.get_suggestion(sug["id"])["status"] == "dismissed"


def test_dismiss_unknown_suggestion_404(isolated_db):
    project_id = create_project(name="disc-proj")
    with _client() as c:
        resp = c.post(f"/api/projects/{project_id}/discovery/suggestions/dsug-missing0/dismiss")
    assert resp.status_code == 404


def test_dismiss_in_flight_claim_409_no_clobber(isolated_db):
    """The MAJOR fix at the route: dismissing a suggestion a promotion has mid-claim
    ('claiming') → 409 (PromotionConflict), and the row stays 'claiming' — the dismiss
    can never clobber the claim and orphan the promoter's just-added source."""
    project_id = create_project(name="disc-proj")
    sug = _seed_suggestion(project_id, "noise", "repo", score=0.2)
    # Simulate a promotion in flight: the row is 'claiming'.
    assert dao.claim_for_promotion(sug["id"], project_id) is True

    with _client() as c:
        resp = c.post(f"/api/projects/{project_id}/discovery/suggestions/{sug['id']}/dismiss")
    assert resp.status_code == 409
    # Untouched — still claimable-by-its-promoter, never flipped to 'dismissed'.
    assert dao.get_suggestion(sug["id"])["status"] == "claiming"


# ---------------------------------------------------------------------------
# IDOR — accept/dismiss must be scoped to the URL's project (Fix 1)
# ---------------------------------------------------------------------------


def test_accept_cross_project_suggestion_404_and_unchanged(isolated_db):
    """A suggestion seeded under project B, accepted via project A's URL → 404,
    and the suggestion is UNCHANGED + no source promoted under either project.

    The caller has full access to project A (no can_access patch) but pairs A's
    URL with B's suggestion id — the per-row project scoping must 404 it."""
    project_a = create_project(name="proj-a")
    project_b = create_project(name="proj-b")
    sug_b = _seed_suggestion(project_b, "victim", "repo", score=0.9, reason="b's row")

    with _client() as c:
        resp = c.post(f"/api/projects/{project_a}/discovery/suggestions/{sug_b['id']}/accept")
    assert resp.status_code == 404

    # The suggestion under B is untouched (still 'suggested', no source stamp).
    after = dao.get_suggestion(sug_b["id"])
    assert after["status"] == "suggested"
    assert after["source_id"] is None
    # No competitor_source promoted under either project.
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM competitor_source").fetchone()["n"]
    assert total == 0


def test_dismiss_cross_project_suggestion_404_and_unchanged(isolated_db):
    """A suggestion seeded under project B, dismissed via project A's URL → 404,
    and the suggestion stays 'suggested' (the dismiss never landed on B's row)."""
    project_a = create_project(name="proj-a")
    project_b = create_project(name="proj-b")
    sug_b = _seed_suggestion(project_b, "victim", "repo", score=0.5)

    with _client() as c:
        resp = c.post(f"/api/projects/{project_a}/discovery/suggestions/{sug_b['id']}/dismiss")
    assert resp.status_code == 404
    assert dao.get_suggestion(sug_b["id"])["status"] == "suggested"


# ---------------------------------------------------------------------------
# Idempotent promote — re-accept returns one source; dismissed → 409 (Fix 5)
# ---------------------------------------------------------------------------


def test_double_accept_is_idempotent_single_source(isolated_db):
    """Two accept POSTs create exactly ONE competitor_source row; the second
    returns the existing source (status stays 'added')."""
    project_id = create_project(name="disc-proj")
    sug = _seed_suggestion(project_id, "acme", "widget", score=0.9)

    with _client() as c:
        first = c.post(f"/api/projects/{project_id}/discovery/suggestions/{sug['id']}/accept")
        second = c.post(f"/api/projects/{project_id}/discovery/suggestions/{sug['id']}/accept")
    assert first.status_code == 201
    assert second.status_code == 201
    first_source = first.json()["source"]
    second_source = second.json()["source"]
    assert first_source["id"] == second_source["id"]

    # Exactly one competitor_source row for the project.
    with get_connection() as conn:
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM competitor_source WHERE project_id = ?", (project_id,)
        ).fetchone()["n"]
    assert n == 1


def test_accept_dismissed_suggestion_409(isolated_db):
    """Accepting a DISMISSED suggestion → 409 (PromotionConflict), not a 201/404."""
    project_id = create_project(name="disc-proj")
    sug = _seed_suggestion(project_id, "noise", "repo", score=0.2)
    dao.set_status(sug["id"], "dismissed")

    with _client() as c:
        resp = c.post(f"/api/projects/{project_id}/discovery/suggestions/{sug['id']}/accept")
    assert resp.status_code == 409
    # Still dismissed; no source promoted.
    assert dao.get_suggestion(sug["id"])["status"] == "dismissed"
    with get_connection() as conn:
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM competitor_source WHERE project_id = ?", (project_id,)
        ).fetchone()["n"]
    assert n == 0


# ---------------------------------------------------------------------------
# IDOR — a caller without project access gets 404 (NOT 403) on EVERY route
# ---------------------------------------------------------------------------


def test_every_route_404s_for_inaccessible_project(isolated_db, monkeypatch):
    """The P1 IDOR lesson: a project the caller can't access → 404 (no existence
    leak), on scan + list + accept + dismiss alike. Patching can_access→False
    exercises the guard wiring on the real (existing) project + suggestion."""
    import app_litestar.routes.discovery_routes as routes

    project_id = create_project(name="owned-by-someone-else")
    sug = _seed_suggestion(project_id, "acme", "widget", score=0.5)
    monkeypatch.setattr(routes, "can_access", lambda *a, **k: False)

    with _client() as c:
        assert c.post(f"/api/projects/{project_id}/discovery/scan").status_code == 404
        assert c.get(f"/api/projects/{project_id}/discovery/suggestions").status_code == 404
        assert (
            c.post(
                f"/api/projects/{project_id}/discovery/suggestions/{sug['id']}/accept"
            ).status_code
            == 404
        )
        assert (
            c.post(
                f"/api/projects/{project_id}/discovery/suggestions/{sug['id']}/dismiss"
            ).status_code
            == 404
        )

    # The guard short-circuited BEFORE any mutation: the suggestion is untouched
    # and no source was promoted.
    assert dao.get_suggestion(sug["id"])["status"] == "suggested"
    with get_connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM competitor_source WHERE project_id = ?", (project_id,)
        ).fetchone()["n"]
    assert count == 0


def test_unknown_project_404_before_scan(isolated_db):
    """A non-existent project 404s on scan (existence check before the fan-out)."""
    with _client() as c:
        resp = c.post("/api/projects/missing/discovery/scan")
    assert resp.status_code == 404
