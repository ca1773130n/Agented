"""Tests for HNAdapter — keyless HN-Algolia query polling (phase 25, plan 05).

Covers the 25-05 contract:
  * First poll (watermark NULL) over a 2-hit Algolia payload -> ``changed``,
    watermark == str(max created_at_i), raw_ref names both story TITLES + urls +
    points/author (a human-readable block, NOT a bare created_at_i number).
  * Second poll with the SAME payload but watermark already at that max ->
    ``unchanged`` (no hit's created_at_i exceeds the cursor; no write).
  * A payload adding ONE story with a newer created_at_i -> ``changed``, raw_ref
    mentions ONLY the new story, watermark advances. The request carries a
    server-side ``numericFilters=created_at_i>...`` cursor.
  * ``403`` / ``429`` -> ``throttled``; malformed JSON / transport error /
    unexpected status -> ``error`` (no raise); empty query -> ``skipped``.
  * Per-item isolation: a hit with no objectID / non-int created_at_i is dropped,
    not fatal.
  * ``has_credential()`` is True and NO Authorization / auth header is ever sent
    (keyless read).

HTTP is mocked by monkeypatching ``hn.httpx.get`` — no network. ``isolated_db``
(autouse) gives a fresh migrated DB; a real project is created so the FK on
``competitor_source.project_id`` is satisfied. The query lives in the ``url``
identifier column (the explicit-kind path).
"""

from __future__ import annotations

import json

import pytest

from app.database import get_connection
from app.db.projects import create_project
from app.services import source_adapters  # noqa: F401  (ensure adapters register)
from app.services.competitor_source_service import KIND_HN_QUERY, CompetitorSourceService
from app.services.source_adapters import hn
from app.services.source_adapters.hn import HNAdapter

# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #


class _FakeResponse:
    """Minimal stand-in for httpx.Response (only what fetch reads)."""

    def __init__(self, status_code: int, *, body: object | None = None, raw: str | None = None):
        self.status_code = status_code
        self._body = body
        self._raw = raw

    def json(self):
        if self._raw is not None:
            return json.loads(self._raw)  # raises ValueError on malformed text
        return self._body


def _seed_source(query: str) -> dict:
    """Create a project + one hn_query source (the query in the url column)."""
    project_id = create_project(name="ci-hn-project")
    assert project_id is not None
    source = CompetitorSourceService.add_source(project_id, query, kind=KIND_HN_QUERY)
    assert source["kind"] == KIND_HN_QUERY
    return source


def _set_watermark(source_id: str, watermark: str) -> dict:
    with get_connection() as conn:
        conn.execute(
            "UPDATE competitor_source SET watermark = ? WHERE id = ?",
            (watermark, source_id),
        )
        conn.commit()
    return CompetitorSourceService.get_source(source_id)


def _install_capture(monkeypatch, response: _FakeResponse) -> dict:
    """Patch httpx.get on the adapter module to record the call + return ``response``."""
    captured: dict = {}

    def _fake_get(url, **kwargs):
        captured["url"] = url
        captured["headers"] = dict(kwargs.get("headers") or {})
        captured["kwargs"] = kwargs
        return response

    monkeypatch.setattr(hn.httpx, "get", _fake_get)
    return captured


def _hit(object_id: str, created_at_i: int, title: str, url: str, points: int, author: str) -> dict:
    return {
        "objectID": object_id,
        "created_at_i": created_at_i,
        "title": title,
        "url": url,
        "points": points,
        "author": author,
    }


def _payload(*hits: dict) -> dict:
    return {"hits": list(hits)}


# --------------------------------------------------------------------------- #
# Adapter shape / registration
# --------------------------------------------------------------------------- #


def test_adapter_is_keyless_1h_floor_and_registered():
    adapter = HNAdapter()
    assert adapter.kind == KIND_HN_QUERY
    assert adapter.poll_interval_floor_s == 3600  # 1h — no ETag free path
    assert adapter.has_credential() is True  # keyless read

    from app.services.source_adapters import registry

    assert KIND_HN_QUERY in registry.active_kinds()
    assert registry.get_adapter(KIND_HN_QUERY) is not None


# --------------------------------------------------------------------------- #
# First poll takes all, watermark dedup, watermark advance
# --------------------------------------------------------------------------- #


def test_first_poll_takes_all_stories_and_renders_titles(monkeypatch):
    source = _seed_source("Acme Corp")
    assert source["watermark"] is None  # first poll: NULL cursor

    payload = _payload(
        _hit("h1", 1717200000, "Acme launches widget", "https://ex.com/a", 42, "alice"),
        _hit("h2", 1717300000, "Show HN: Acme API", "https://ex.com/b", 99, "bob"),
    )
    captured = _install_capture(monkeypatch, _FakeResponse(200, body=payload))

    result = HNAdapter().fetch(source)

    assert result.outcome == "changed"
    # Watermark == str(max created_at_i) across ALL returned hits.
    assert result.watermark == "1717300000"
    assert result.etag is None  # HN has no conditional-GET cursor
    # raw_ref is the human-readable block: titles + urls + points/author present,
    # NOT a bare created_at_i number.
    assert "Acme launches widget" in result.raw_ref
    assert "Show HN: Acme API" in result.raw_ref
    assert "https://ex.com/a" in result.raw_ref
    assert "42 pts" in result.raw_ref
    assert "by alice" in result.raw_ref
    assert "1717300000" not in result.raw_ref  # cursor is NOT the content
    # First poll has NO numericFilter (no cursor yet); query is in the URL.
    assert "search_by_date" in captured["url"]
    assert "tags=story" in captured["url"]
    assert "numericFilters" not in captured["url"]
    assert "query=Acme" in captured["url"]


def test_second_poll_same_payload_is_unchanged(monkeypatch):
    source = _seed_source("Acme Corp")
    payload = _payload(
        _hit("h1", 1717200000, "Acme launches widget", "https://ex.com/a", 42, "alice"),
        _hit("h2", 1717300000, "Show HN: Acme API", "https://ex.com/b", 99, "bob"),
    )
    # Cursor already at the max created_at_i -> nothing exceeds it.
    source = _set_watermark(source["id"], "1717300000")
    _install_capture(monkeypatch, _FakeResponse(200, body=payload))

    result = HNAdapter().fetch(source)

    assert result.outcome == "unchanged"
    assert result.raw_ref is None
    assert result.watermark is None  # nothing to persist on an unchanged poll


def test_new_story_advances_watermark_and_names_only_new_story(monkeypatch):
    source = _seed_source("Acme Corp")
    source = _set_watermark(source["id"], "1717300000")
    payload = _payload(
        _hit("h1", 1717200000, "Acme launches widget", "https://ex.com/a", 42, "alice"),
        _hit("h2", 1717300000, "Show HN: Acme API", "https://ex.com/b", 99, "bob"),
        _hit("h3", 1717900000, "Acme raises Series B", "https://ex.com/c", 250, "carol"),
    )
    captured = _install_capture(monkeypatch, _FakeResponse(200, body=payload))

    result = HNAdapter().fetch(source)

    assert result.outcome == "changed"
    assert result.watermark == "1717900000"  # advanced to the new max
    # Only the NEW story appears in the diff set.
    assert "Acme raises Series B" in result.raw_ref
    assert "by carol" in result.raw_ref
    assert "Acme launches widget" not in result.raw_ref
    assert "Show HN: Acme API" not in result.raw_ref
    # With a cursor, the request carries the server-side incremental filter.
    assert "numericFilters=created_at_i%3E1717300000" in captured["url"]


# --------------------------------------------------------------------------- #
# Keyless: no auth header is ever sent
# --------------------------------------------------------------------------- #


def test_fetch_sends_no_auth_header(monkeypatch):
    source = _seed_source("Acme Corp")
    payload = _payload(_hit("h1", 1717200000, "Acme", "https://ex.com/a", 1, "alice"))
    captured = _install_capture(monkeypatch, _FakeResponse(200, body=payload))

    HNAdapter().fetch(source)

    header_keys = {k.lower() for k in captured["headers"]}
    assert "authorization" not in header_keys
    assert not any("auth" in k or "token" in k for k in header_keys)


# --------------------------------------------------------------------------- #
# Per-item isolation: a malformed hit is dropped, not fatal
# --------------------------------------------------------------------------- #


def test_malformed_hit_is_dropped_not_fatal(monkeypatch):
    source = _seed_source("Acme Corp")
    payload = {
        "hits": [
            {"title": "no objectID", "created_at_i": 1717200000},  # dropped (no id)
            {"objectID": "h2", "created_at_i": "not-int", "title": "bad ts"},  # dropped
            _hit("h3", 1717300000, "Real story", "https://ex.com/c", 5, "carol"),
        ]
    }
    _install_capture(monkeypatch, _FakeResponse(200, body=payload))

    result = HNAdapter().fetch(source)

    assert result.outcome == "changed"
    assert result.watermark == "1717300000"  # only the one valid hit counts
    assert "Real story" in result.raw_ref
    assert "no objectID" not in result.raw_ref


def test_empty_hits_is_unchanged(monkeypatch):
    source = _seed_source("Acme Corp")
    _install_capture(monkeypatch, _FakeResponse(200, body={"hits": []}))

    result = HNAdapter().fetch(source)
    assert result.outcome == "unchanged"


# --------------------------------------------------------------------------- #
# Failure paths: throttled / error / skipped — never raise
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("status", [403, 429])
def test_throttled_on_403_429(monkeypatch, status):
    source = _seed_source("Acme Corp")
    warnings: list = []
    monkeypatch.setattr(hn.logger, "warning", lambda *a, **k: warnings.append((a, k)))
    _install_capture(monkeypatch, _FakeResponse(status))

    result = HNAdapter().fetch(source)

    assert result.outcome == "throttled"
    assert result.raw_ref is None
    assert warnings  # a throttle warning was logged


def test_malformed_json_is_error_no_raise(monkeypatch):
    source = _seed_source("Acme Corp")
    monkeypatch.setattr(hn.logger, "warning", lambda *a, **k: None)
    _install_capture(monkeypatch, _FakeResponse(200, raw="{not valid json"))

    result = HNAdapter().fetch(source)  # must not raise
    assert result.outcome == "error"


def test_transport_error_is_error_no_raise(monkeypatch):
    source = _seed_source("Acme Corp")

    def _boom(url, **kwargs):
        raise hn.httpx.ConnectError("dns failure")

    monkeypatch.setattr(hn.httpx, "get", _boom)
    monkeypatch.setattr(hn.logger, "warning", lambda *a, **k: None)

    result = HNAdapter().fetch(source)  # must not raise
    assert result.outcome == "error"


def test_unexpected_status_is_error(monkeypatch):
    source = _seed_source("Acme Corp")
    monkeypatch.setattr(hn.logger, "warning", lambda *a, **k: None)
    _install_capture(monkeypatch, _FakeResponse(500))

    result = HNAdapter().fetch(source)
    assert result.outcome == "error"


def test_blank_query_is_skipped_no_fetch(monkeypatch):
    source = _seed_source("Acme Corp")
    # Overwrite the identifier with a whitespace-only query.
    with get_connection() as conn:
        conn.execute(
            "UPDATE competitor_source SET url = ? WHERE id = ?",
            ("   ", source["id"]),
        )
        conn.commit()
    source = CompetitorSourceService.get_source(source["id"])

    def _boom(url, **kwargs):
        raise AssertionError("httpx.get called for a blank HN query")

    monkeypatch.setattr(hn.httpx, "get", _boom)
    monkeypatch.setattr(hn.logger, "warning", lambda *a, **k: None)

    result = HNAdapter().fetch(source)
    assert result.outcome == "skipped"


# --------------------------------------------------------------------------- #
# commit integration: a changed fetch writes exactly one snapshot + advances cursor
# --------------------------------------------------------------------------- #


def test_changed_fetch_then_commit_writes_one_snapshot_and_persists_watermark(monkeypatch):
    source = _seed_source("Acme Corp")
    payload = _payload(
        _hit("h1", 1717200000, "Acme launches widget", "https://ex.com/a", 42, "alice"),
        _hit("h2", 1717300000, "Show HN: Acme API", "https://ex.com/b", 99, "bob"),
    )
    _install_capture(monkeypatch, _FakeResponse(200, body=payload))

    adapter = HNAdapter()
    result = adapter.fetch(source)
    assert result.outcome == "changed"

    snapshot_id = adapter.commit(source["id"], result)
    assert snapshot_id is not None and snapshot_id.startswith("cmsn-")

    with get_connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM competitor_snapshot WHERE source_id = ?",
            (source["id"],),
        ).fetchone()["n"]
        snap = conn.execute(
            "SELECT raw_ref FROM competitor_snapshot WHERE id = ?", (snapshot_id,)
        ).fetchone()
    assert int(count) == 1
    # The snapshot stores the CONTENT (story titles), distinct from the cursor.
    assert "Acme launches widget" in snap["raw_ref"]

    persisted = CompetitorSourceService.get_source(source["id"])
    assert persisted["watermark"] == "1717300000"
    assert persisted["etag"] is None
