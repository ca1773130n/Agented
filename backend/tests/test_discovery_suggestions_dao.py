"""DAO tests for app.db.discovery_suggestions (phase 24, migration 172).

Covers the contracts plans 24-02/03/04 depend on:
- upsert inserts a single dsug- row (status 'suggested', score persisted,
  evidence round-trips through JSON);
- re-upsert on the same (project, owner, repo) refreshes ranking data without
  duplicating;
- the operator verdict is sticky: an already-'dismissed' (or 'added') row stays
  put across a re-upsert, while its score still refreshes;
- list_suggestions is project-scoped, orders by score DESC (NULLS last), and
  filters by status;
- score=None never blocks an insert (NULL-accepting).

All tests seed a real ``projects`` row first because the FK is enforced.
"""

import time

import pytest

from app.db import discovery_suggestions as dao
from app.db.projects import create_project


@pytest.fixture
def project(isolated_db):
    """A real project id (FK target for discovery_suggestion.project_id)."""
    return create_project(name="Discovery DAO test project")


def test_upsert_inserts_single_row(project):
    row = dao.upsert_suggestion(
        project,
        "acme",
        "widget",
        "https://github.com/acme/widget",
        score=0.8,
        reason="shares 12 stargazers",
        evidence={"shared_stargazers": 12, "shared_topics": ["cli", "agents"]},
    )
    assert row["id"].startswith("dsug-")
    assert len(row["id"]) == len("dsug-") + 8
    assert row["status"] == "suggested"
    assert row["score"] == 0.8
    assert row["candidate_owner"] == "acme"
    assert row["candidate_repo"] == "widget"
    # evidence round-trips back into a dict.
    assert row["evidence"] == {"shared_stargazers": 12, "shared_topics": ["cli", "agents"]}

    listed = dao.list_suggestions(project)
    assert len(listed) == 1


def test_upsert_is_idempotent_on_unique_key(project):
    first = dao.upsert_suggestion(
        project, "acme", "widget", "https://github.com/acme/widget", score=0.5
    )
    time.sleep(1.05)  # ensure CURRENT_TIMESTAMP (1s granularity) advances
    second = dao.upsert_suggestion(
        project,
        "acme",
        "widget",
        "https://github.com/acme/widget",
        score=0.95,
        reason="now stronger",
    )
    # Same row (same id), not a duplicate.
    assert second["id"] == first["id"]
    assert len(dao.list_suggestions(project)) == 1
    # Ranking data refreshed.
    assert second["score"] == 0.95
    assert second["reason"] == "now stronger"
    # updated_at moved forward.
    assert second["updated_at"] >= first["updated_at"]
    assert second["updated_at"] != first["updated_at"]


def test_upsert_preserves_dismissed_verdict(project):
    created = dao.upsert_suggestion(
        project, "acme", "widget", "https://github.com/acme/widget", score=0.4
    )
    dismissed = dao.set_status(created["id"], "dismissed")
    assert dismissed["status"] == "dismissed"

    # A re-scan refreshes the score but MUST NOT resurrect the dismissed row.
    rescanned = dao.upsert_suggestion(
        project, "acme", "widget", "https://github.com/acme/widget", score=0.99
    )
    assert rescanned["id"] == created["id"]
    assert rescanned["status"] == "dismissed", "dismissed verdict must be sticky"
    assert rescanned["score"] == 0.99, "score still refreshes on re-scan"


def test_upsert_preserves_added_verdict_and_source_id(project):
    created = dao.upsert_suggestion(
        project, "acme", "gizmo", "https://github.com/acme/gizmo", score=0.6
    )
    added = dao.set_status(created["id"], "added", source_id="cmps-abc123")
    assert added["status"] == "added"
    assert added["source_id"] == "cmps-abc123"

    rescanned = dao.upsert_suggestion(
        project, "acme", "gizmo", "https://github.com/acme/gizmo", score=0.71
    )
    assert rescanned["status"] == "added", "added verdict must be sticky"
    assert rescanned["source_id"] == "cmps-abc123", "source_id stamp must survive re-scan"
    assert rescanned["score"] == 0.71


def test_get_suggestion_round_trip(project):
    created = dao.upsert_suggestion(
        project, "acme", "widget", "https://github.com/acme/widget", score=0.3
    )
    fetched = dao.get_suggestion(created["id"])
    assert fetched is not None
    assert fetched["id"] == created["id"]
    assert dao.get_suggestion("dsug-nonexist") is None


def test_list_is_project_scoped(project, isolated_db):
    other = create_project(name="Other project")
    dao.upsert_suggestion(project, "acme", "widget", "https://github.com/acme/widget")
    dao.upsert_suggestion(other, "globex", "thing", "https://github.com/globex/thing")

    mine = dao.list_suggestions(project)
    assert len(mine) == 1
    assert mine[0]["candidate_owner"] == "acme"


def test_list_orders_by_score_desc_nulls_last(project):
    dao.upsert_suggestion(project, "a", "low", "https://github.com/a/low", score=0.2)
    dao.upsert_suggestion(project, "b", "high", "https://github.com/b/high", score=0.9)
    dao.upsert_suggestion(project, "c", "noscore", "https://github.com/c/noscore", score=None)

    ordered = dao.list_suggestions(project)
    scores = [r["score"] for r in ordered]
    # High score first, NULL score last.
    assert scores[0] == 0.9
    assert scores[1] == 0.2
    assert scores[2] is None


def test_list_filters_by_status(project):
    a = dao.upsert_suggestion(project, "a", "one", "https://github.com/a/one", score=0.5)
    dao.upsert_suggestion(project, "b", "two", "https://github.com/b/two", score=0.6)
    dao.set_status(a["id"], "dismissed")

    only_suggested = dao.list_suggestions(project, statuses=["suggested"])
    assert {r["candidate_repo"] for r in only_suggested} == {"two"}

    only_dismissed = dao.list_suggestions(project, statuses=["dismissed"])
    assert {r["candidate_repo"] for r in only_dismissed} == {"one"}


def test_score_none_does_not_block_insert(project):
    row = dao.upsert_suggestion(project, "acme", "scoreless", "https://github.com/acme/scoreless")
    assert row["score"] is None
    assert row["status"] == "suggested"
    assert row["id"].startswith("dsug-")


def test_set_status_unknown_id_returns_none(project):
    assert dao.set_status("dsug-missing0", "dismissed") is None


def test_evidence_list_round_trips(project):
    row = dao.upsert_suggestion(
        project,
        "acme",
        "listev",
        "https://github.com/acme/listev",
        evidence=["topic:cli", "topic:agents"],
    )
    assert row["evidence"] == ["topic:cli", "topic:agents"]
    assert dao.get_suggestion(row["id"])["evidence"] == ["topic:cli", "topic:agents"]
