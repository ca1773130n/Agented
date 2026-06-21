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


def test_get_suggestion_project_scoped_blocks_foreign(project, isolated_db):
    """A project-scoped get returns None for a suggestion owned by ANOTHER project
    (the IDOR guard the accept/dismiss path relies on)."""
    other = create_project(name="Foreign project")
    row = dao.upsert_suggestion(other, "acme", "widget", "https://github.com/acme/widget")
    # Unscoped read still finds it; scoped to the wrong project returns None.
    assert dao.get_suggestion(row["id"]) is not None
    assert dao.get_suggestion(row["id"], project_id=other) is not None
    assert dao.get_suggestion(row["id"], project_id=project) is None


def test_set_status_project_scoped_is_noop_for_foreign(project, isolated_db):
    """``set_status`` scoped to the wrong project does NOT mutate the row and
    returns None — closing the IDOR where project A flips project B's suggestion."""
    other = create_project(name="Foreign project")
    row = dao.upsert_suggestion(
        other, "acme", "widget", "https://github.com/acme/widget", score=0.5
    )

    # Project A (``project``) tries to dismiss project B's (``other``) suggestion.
    result = dao.set_status(row["id"], "dismissed", project_id=project)
    assert result is None  # scoped mutation found no matching row

    # The suggestion is UNCHANGED — still 'suggested' under its real project.
    unchanged = dao.get_suggestion(row["id"])
    assert unchanged["status"] == "suggested"

    # The legitimate owner CAN flip it.
    owned = dao.set_status(row["id"], "dismissed", project_id=other)
    assert owned["status"] == "dismissed"


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


# --------------------------------------------------------------------------- #
# claim_for_promotion — atomic concurrent-accept guard (round-2 fix)
# --------------------------------------------------------------------------- #


def test_claim_for_promotion_wins_once_then_loses(project):
    """The first claim flips 'suggested'→'added' and returns True; a second claim
    of the now-'added' row changes zero rows and returns False — the predicate
    that stops a concurrent double-add."""
    row = dao.upsert_suggestion(project, "acme", "claimone", "https://github.com/acme/claimone")
    assert row["status"] == "suggested"

    assert dao.claim_for_promotion(row["id"], project) is True
    # The row is now 'added' (the atomic flip landed).
    assert dao.get_suggestion(row["id"])["status"] == "added"
    # A second claim cannot re-win — status is no longer 'suggested'.
    assert dao.claim_for_promotion(row["id"], project) is False


def test_claim_for_promotion_foreign_project_returns_false(project, isolated_db):
    """A claim scoped to the WRONG project matches no row (returns False) and does
    NOT mutate the real row — the IDOR guard on the atomic path."""
    other = create_project(name="other-claim-project")
    row = dao.upsert_suggestion(project, "acme", "claimscope", "https://github.com/acme/claimscope")

    assert dao.claim_for_promotion(row["id"], other) is False
    # Untouched: still 'suggested' under its real project.
    assert dao.get_suggestion(row["id"])["status"] == "suggested"


def test_claim_for_promotion_dismissed_row_returns_false(project):
    """A dismissed row is not 'suggested', so the claim cannot win it (False) and
    leaves it dismissed — the route maps that to a 409, never a silent resurrect."""
    row = dao.upsert_suggestion(project, "acme", "claimdis", "https://github.com/acme/claimdis")
    dao.set_status(row["id"], "dismissed", project_id=project)

    assert dao.claim_for_promotion(row["id"], project) is False
    assert dao.get_suggestion(row["id"])["status"] == "dismissed"


def test_revert_promotion_claim_restores_suggested_and_clears_source(project):
    """revert undoes a won claim: 'added'→'suggested' and clears source_id — the
    compensating action when add_source raises after the claim."""
    row = dao.upsert_suggestion(project, "acme", "claimrev", "https://github.com/acme/claimrev")
    assert dao.claim_for_promotion(row["id"], project) is True
    # Simulate a stamped source id (as set_status would after a successful add).
    dao.set_status(row["id"], "added", project_id=project, source_id="cmps-tmp123")
    assert dao.get_suggestion(row["id"])["source_id"] == "cmps-tmp123"

    dao.revert_promotion_claim(row["id"], project)
    reverted = dao.get_suggestion(row["id"])
    assert reverted["status"] == "suggested"
    assert reverted["source_id"] is None
    # And it is claimable again.
    assert dao.claim_for_promotion(row["id"], project) is True
