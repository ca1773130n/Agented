"""CompetitorSourceService tests (REQ-27).

Covers the kind autodetect (github/arxiv/product_url), the label-optional
insert contract (an omitted/blank label must never block add_source), label
persistence, project-scoped listing, and get-by-id round-trip.
"""

import pytest

from app.db.projects import create_project
from app.services.competitor_source_service import CompetitorSourceService as S


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://github.com/o/r", "github_repo"),
        ("https://www.github.com/o/r", "github_repo"),
        ("https://arxiv.org/abs/2401.00001", "arxiv"),
        ("https://www.arxiv.org/abs/2401.00001", "arxiv"),
        # The export API host must also route to arxiv — the ArxivAdapter honors a
        # pasted export-API URL, so an operator-supplied export host must reach the
        # adapter rather than fall through to product_url.
        ("https://export.arxiv.org/api/query?search_query=cat:cs.LG", "arxiv"),
        ("https://www.export.arxiv.org/api/query?search_query=all:agents", "arxiv"),
        ("https://acme.com/product", "product_url"),
        ("https://example.com", "product_url"),
        ("", "product_url"),
        ("not-a-url", "product_url"),
    ],
)
def test_detect_kind(url, expected):
    assert S.detect_kind(url) == expected


def test_add_source_without_label_never_blocks(isolated_db):
    """REQ-27 / wizard-defaults: a missing label must not block the insert."""
    project_id = create_project(name="CI no-label")
    row = S.add_source(project_id, "https://github.com/openai/gpt")
    assert row["id"].startswith("cmps-")
    assert len(row["id"]) == len("cmps-") + 6
    assert row["kind"] == "github_repo"
    assert row["project_id"] == project_id
    assert row["url"] == "https://github.com/openai/gpt"
    assert row["origin"] == "manual"
    assert row["status"] == "active"
    # Optional fields default to NULL; an omitted label stays NULL.
    assert row["label"] is None
    assert row["etag"] is None
    assert row["watermark"] is None


def test_add_source_non_string_label_coerced_to_none(isolated_db):
    """A non-string label (e.g. a malformed JSON object) is coerced to NULL, not
    bound raw to SQLite — an "optional" field must never block the insert."""
    project_id = create_project(name="CI bad-label")
    row = S.add_source(project_id, "https://github.com/o/r", label={"x": 1})
    assert row["label"] is None


def test_add_source_blank_label_normalized_to_null(isolated_db):
    project_id = create_project(name="CI blank-label")
    row = S.add_source(project_id, "https://acme.com", label="   ")
    assert row["kind"] == "product_url"
    assert row["label"] is None


def test_add_source_with_label_persists(isolated_db):
    project_id = create_project(name="CI labelled")
    row = S.add_source(project_id, "https://arxiv.org/abs/1", label="ACME paper")
    assert row["kind"] == "arxiv"
    assert row["label"] == "ACME paper"
    # And it survives a reload via get_source.
    fetched = S.get_source(row["id"])
    assert fetched is not None
    assert fetched["label"] == "ACME paper"


def test_add_source_custom_origin(isolated_db):
    project_id = create_project(name="CI origin")
    row = S.add_source(project_id, "https://example.com", origin="discovery")
    assert row["origin"] == "discovery"


def test_list_sources_filters_by_project(isolated_db):
    project_a = create_project(name="Project A")
    project_b = create_project(name="Project B")
    S.add_source(project_a, "https://github.com/a/1")
    S.add_source(project_a, "https://arxiv.org/abs/2")
    S.add_source(project_b, "https://b.com")

    a_rows = S.list_sources(project_a)
    b_rows = S.list_sources(project_b)
    assert len(a_rows) == 2
    assert len(b_rows) == 1
    assert all(r["project_id"] == project_a for r in a_rows)
    assert b_rows[0]["url"] == "https://b.com"


def test_list_sources_empty_for_unknown_project(isolated_db):
    assert S.list_sources("proj-doesnotexist") == []


def test_get_source_returns_row_then_none(isolated_db):
    project_id = create_project(name="CI get")
    created = S.add_source(project_id, "https://github.com/x/y")
    fetched = S.get_source(created["id"])
    assert fetched is not None
    assert fetched["id"] == created["id"]
    assert fetched["url"] == "https://github.com/x/y"
    # Unknown id -> None.
    assert S.get_source("cmps-nope00") is None
