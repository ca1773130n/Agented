"""Tests for ArxivAdapter — keyless export-API Atom polling (phase 25, plan 03).

Covers the 25-03 contract:
  * First poll (watermark NULL) over a 2-entry Atom feed -> ``changed``,
    watermark == max(entry.published), raw_ref contains BOTH titles +
    abstracts + authors (the new-papers text block the summarizer reads).
  * Second poll with the SAME feed but watermark already at that max ->
    ``unchanged`` (no entry's published exceeds the cursor; no write).
  * A feed adding ONE newer entry -> ``changed``, raw_ref mentions ONLY the
    new paper, watermark advances to the new max.
  * An arXiv ERROR document (an Atom feed whose ``<entry>`` id is an
    ``arxiv.org/api/errors#...`` URL) -> ``error`` (NO raise).
  * Malformed / non-Atom XML -> ``error`` (NO raise).
  * ``429`` / ``503`` -> ``throttled``.
  * The ``>= 3s`` aggregate serialization gate: with a FAKE monotonic clock +
    a recording ``sleep`` (NO real sleeping), two back-to-back fetches force a
    ``>= 3s`` spacing — the second fetch sleeps the remaining delta.
  * ``has_credential()`` is True and NO Authorization / auth header is ever
    sent — the export API is a keyless public read.
  * ``detect_kind`` for ``arxiv.org`` == ``KIND_ARXIV`` (pre-existing; this plan
    only adds the adapter, no detect_kind/constant change).
  * commit integration: a changed fetch writes exactly one snapshot + advances
    the cursor (the EXISTING ``AdapterBase.commit``, unchanged).

HTTP is mocked by monkeypatching ``arxiv.httpx.get`` — no network. The module
global ``arxiv._last_request_monotonic`` is reset before every test (autouse
fixture) so the process-wide rate gate does not leak state across tests.
``isolated_db`` (autouse) gives a fresh migrated DB; a real project is created so
the FK on ``competitor_source.project_id`` is satisfied. Where a warning is
expected we spy ``arxiv.logger.warning`` (the caplog caveat from CLAUDE.md).
"""

from __future__ import annotations

import pytest

from app.database import get_connection
from app.db.projects import create_project
from app.services import source_adapters  # noqa: F401  (ensure adapters register)
from app.services.competitor_source_service import KIND_ARXIV, CompetitorSourceService
from app.services.source_adapters import arxiv as ax
from app.services.source_adapters.arxiv import ArxivAdapter

# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _reset_rate_gate():
    """Reset the process-global rate-gate clock between tests.

    ``arxiv._last_request_monotonic`` is a MODULE GLOBAL (intentionally — the
    aggregate 1-req/3s limit is process-wide). Without resetting it, the first
    fetch in a later test would "see" a previous test's timestamp and sleep.
    """
    ax._last_request_monotonic = None
    yield
    ax._last_request_monotonic = None


class _FakeResponse:
    """Minimal stand-in for httpx.Response (only what fetch reads: status + text)."""

    def __init__(self, status_code: int, *, text: str = ""):
        self.status_code = status_code
        # arXiv returns Atom XML in the body — fetch reads ``.text`` (never .json()).
        self.text = text


def _seed_source(url: str) -> dict:
    """Create a project + one arxiv competitor_source; return the row dict."""
    project_id = create_project(name="ci-arxiv-project")
    assert project_id is not None
    source = CompetitorSourceService.add_source(project_id, url)
    # detect_kind already routes arxiv.org -> KIND_ARXIV (pre-existing).
    assert source["kind"] == KIND_ARXIV
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
    """Patch httpx.get on the adapter module to record the call and return ``response``."""
    captured: dict = {}

    def _fake_get(url, **kwargs):
        captured["url"] = url
        captured["headers"] = dict(kwargs.get("headers") or {})
        captured["kwargs"] = kwargs
        return response

    monkeypatch.setattr(ax.httpx, "get", _fake_get)
    return captured


def _bypass_rate_gate(monkeypatch) -> None:
    """Neutralize the 3s gate for tests not asserting on it (no real sleep).

    Replaces ``_arxiv_rate_gate`` with a no-op so the bulk of the behavior tests
    never sleep. The gate itself has its own dedicated test below.
    """
    monkeypatch.setattr(ax, "_arxiv_rate_gate", lambda: None)


# --- Atom feed builders ---------------------------------------------------- #


def _atom_entry(arxiv_id: str, published: str, title: str, summary: str, authors: list[str]) -> str:
    author_xml = "".join(f"<author><name>{name}</name></author>" for name in authors)
    return (
        "<entry>"
        f"<id>http://arxiv.org/abs/{arxiv_id}</id>"
        f"<published>{published}</published>"
        f"<title>{title}</title>"
        f"<summary>{summary}</summary>"
        f"{author_xml}"
        "</entry>"
    )


def _atom_feed(*entries: str) -> str:
    inner = "".join(entries)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<feed xmlns="http://www.w3.org/2005/Atom">'
        "<title>ArXiv Query</title>"
        f"{inner}"
        "</feed>"
    )


def _atom_error_feed() -> str:
    """arXiv's error response: a feed whose single entry id is an errors# URL."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<feed xmlns="http://www.w3.org/2005/Atom">'
        "<entry>"
        "<id>http://arxiv.org/api/errors#incorrect_id_format_for_abc</id>"
        "<title>Error</title>"
        "<summary>incorrect id format</summary>"
        "</entry>"
        "</feed>"
    )


# Two papers, ISO-8601 published (lexically sortable, newest first in the feed).
_P_OLDER = _atom_entry(
    "2406.00001",
    "2026-06-01T00:00:00Z",
    "Sparse Mixtures for Long Context",
    "We introduce a sparse mixture-of-experts approach to long-context modeling.",
    ["Ada Lovelace", "Alan Turing"],
)
_P_NEWER = _atom_entry(
    "2406.00002",
    "2026-06-02T00:00:00Z",
    "Retrieval-Augmented Planning Agents",
    "A retrieval-augmented planner improves multi-step agent reasoning.",
    ["Grace Hopper"],
)
_P_NEWEST = _atom_entry(
    "2406.00003",
    "2026-06-05T00:00:00Z",
    "Diffusion Policies for Robotics",
    "Diffusion-based policies for robotic manipulation under uncertainty.",
    ["Katherine Johnson"],
)


# --------------------------------------------------------------------------- #
# Adapter shape / registration
# --------------------------------------------------------------------------- #


def test_adapter_is_keyless_daily_floor_and_registered():
    adapter = ArxivAdapter()
    assert adapter.kind == KIND_ARXIV
    assert adapter.poll_interval_floor_s == 86400  # daily — no ETag free path
    assert adapter.has_credential() is True  # keyless export API

    from app.services.source_adapters import registry

    assert KIND_ARXIV in registry.active_kinds()
    assert registry.get_adapter(KIND_ARXIV) is not None


# --------------------------------------------------------------------------- #
# detect_kind routing (pre-existing; this plan does not change it)
# --------------------------------------------------------------------------- #


def test_detect_kind_routes_arxiv_host_to_arxiv():
    assert CompetitorSourceService.detect_kind("https://arxiv.org/abs/2406.00001") == KIND_ARXIV
    assert CompetitorSourceService.detect_kind("https://arxiv.org/list/cs.LG/recent") == KIND_ARXIV
    assert CompetitorSourceService.detect_kind("https://www.arxiv.org/a/lecun_y_1") == KIND_ARXIV


# --------------------------------------------------------------------------- #
# First poll takes the window; watermark dedup; watermark advance
# --------------------------------------------------------------------------- #


def test_first_poll_takes_window_and_sets_published_watermark(monkeypatch):
    _bypass_rate_gate(monkeypatch)
    source = _seed_source("https://arxiv.org/list/cs.LG/recent")
    assert source["watermark"] is None  # first poll: NULL cursor

    feed = _atom_feed(_P_NEWER, _P_OLDER)  # newest-first
    captured = _install_capture(monkeypatch, _FakeResponse(200, text=feed))

    result = ArxivAdapter().fetch(source)

    assert result.outcome == "changed"
    # watermark == max(published) across the returned entries.
    assert result.watermark == "2026-06-02T00:00:00Z"
    assert result.etag is None  # arXiv has no conditional-GET cursor
    # raw_ref is the new-papers text block: BOTH titles + abstracts + authors.
    assert "Sparse Mixtures for Long Context" in result.raw_ref
    assert "sparse mixture-of-experts" in result.raw_ref
    assert "Ada Lovelace" in result.raw_ref
    assert "Retrieval-Augmented Planning Agents" in result.raw_ref
    assert "Grace Hopper" in result.raw_ref
    # The query is derived from the category path and the feed is newest-first.
    assert captured["url"].startswith("https://export.arxiv.org/api/query?")
    assert "search_query=cat%3Acs.LG" in captured["url"]
    assert "sortBy=submittedDate" in captured["url"]
    assert "sortOrder=descending" in captured["url"]


def test_second_poll_same_feed_is_unchanged(monkeypatch):
    _bypass_rate_gate(monkeypatch)
    source = _seed_source("https://arxiv.org/list/cs.LG/recent")
    feed = _atom_feed(_P_NEWER, _P_OLDER)
    # Cursor already at the max published -> nothing exceeds it.
    source = _set_watermark(source["id"], "2026-06-02T00:00:00Z")
    _install_capture(monkeypatch, _FakeResponse(200, text=feed))

    result = ArxivAdapter().fetch(source)

    assert result.outcome == "unchanged"
    assert result.raw_ref is None
    assert result.watermark is None  # nothing to persist on an unchanged poll


def test_new_paper_advances_watermark_and_names_only_new_paper(monkeypatch):
    _bypass_rate_gate(monkeypatch)
    source = _seed_source("https://arxiv.org/list/cs.LG/recent")
    source = _set_watermark(source["id"], "2026-06-02T00:00:00Z")
    feed = _atom_feed(_P_NEWEST, _P_NEWER, _P_OLDER)  # one newer than the cursor
    _install_capture(monkeypatch, _FakeResponse(200, text=feed))

    result = ArxivAdapter().fetch(source)

    assert result.outcome == "changed"
    assert result.watermark == "2026-06-05T00:00:00Z"  # advanced to the new max
    # ONLY the new paper appears in the diff set.
    assert "Diffusion Policies for Robotics" in result.raw_ref
    assert "Katherine Johnson" in result.raw_ref
    assert "Sparse Mixtures for Long Context" not in result.raw_ref
    assert "Retrieval-Augmented Planning Agents" not in result.raw_ref


def test_abs_url_derives_id_query(monkeypatch):
    _bypass_rate_gate(monkeypatch)
    source = _seed_source("https://arxiv.org/abs/2406.00002")
    feed = _atom_feed(_P_NEWER)
    captured = _install_capture(monkeypatch, _FakeResponse(200, text=feed))

    result = ArxivAdapter().fetch(source)

    assert result.outcome == "changed"
    # An /abs/<id> URL watches that specific paper id.
    assert "search_query=id%3A2406.00002" in captured["url"]


# --------------------------------------------------------------------------- #
# Error / throttled paths — never raise
# --------------------------------------------------------------------------- #


def test_arxiv_error_feed_is_error_no_raise(monkeypatch):
    _bypass_rate_gate(monkeypatch)
    source = _seed_source("https://arxiv.org/abs/bad-id")
    warnings: list = []
    monkeypatch.setattr(ax.logger, "warning", lambda *a, **k: warnings.append((a, k)))
    _install_capture(monkeypatch, _FakeResponse(200, text=_atom_error_feed()))

    result = ArxivAdapter().fetch(source)  # must not raise

    # An arXiv error feed is XML, parses fine, but is NOT a real result feed.
    assert result.outcome == "error"
    assert result.raw_ref is None
    assert warnings


def test_malformed_xml_is_error_no_raise(monkeypatch):
    _bypass_rate_gate(monkeypatch)
    source = _seed_source("https://arxiv.org/list/cs.LG/recent")
    warnings: list = []
    monkeypatch.setattr(ax.logger, "warning", lambda *a, **k: warnings.append((a, k)))
    _install_capture(monkeypatch, _FakeResponse(200, text="<feed><entry>unclosed"))

    result = ArxivAdapter().fetch(source)  # must not raise

    assert result.outcome == "error"
    assert warnings


def test_non_feed_xml_is_error(monkeypatch):
    _bypass_rate_gate(monkeypatch)
    source = _seed_source("https://arxiv.org/list/cs.LG/recent")
    monkeypatch.setattr(ax.logger, "warning", lambda *a, **k: None)
    # Well-formed XML that is not an Atom <feed> at all.
    _install_capture(monkeypatch, _FakeResponse(200, text="<html><body>down</body></html>"))

    result = ArxivAdapter().fetch(source)
    assert result.outcome == "error"


@pytest.mark.parametrize("status", [429, 503])
def test_throttled_on_429_503(monkeypatch, status):
    _bypass_rate_gate(monkeypatch)
    source = _seed_source("https://arxiv.org/list/cs.LG/recent")
    warnings: list = []
    monkeypatch.setattr(ax.logger, "warning", lambda *a, **k: warnings.append((a, k)))
    _install_capture(monkeypatch, _FakeResponse(status))

    result = ArxivAdapter().fetch(source)

    assert result.outcome == "throttled"
    assert result.raw_ref is None
    assert warnings  # a throttle warning was logged


def test_transport_error_is_error_no_raise(monkeypatch):
    _bypass_rate_gate(monkeypatch)
    source = _seed_source("https://arxiv.org/list/cs.LG/recent")

    def _boom(url, **kwargs):
        raise ax.httpx.ConnectError("dns failure")

    monkeypatch.setattr(ax.httpx, "get", _boom)
    monkeypatch.setattr(ax.logger, "warning", lambda *a, **k: None)

    result = ArxivAdapter().fetch(source)  # must not raise
    assert result.outcome == "error"


def test_unexpected_status_is_error(monkeypatch):
    _bypass_rate_gate(monkeypatch)
    source = _seed_source("https://arxiv.org/list/cs.LG/recent")
    monkeypatch.setattr(ax.logger, "warning", lambda *a, **k: None)
    _install_capture(monkeypatch, _FakeResponse(500))

    result = ArxivAdapter().fetch(source)
    assert result.outcome == "error"


def test_non_arxiv_url_is_skipped(monkeypatch):
    # A source stored under arxiv but with an un-derivable URL is not pollable ->
    # skipped, no HTTP call, no raise.
    _bypass_rate_gate(monkeypatch)
    source = _seed_source("https://arxiv.org/list/cs.LG/recent")
    with get_connection() as conn:
        conn.execute(
            "UPDATE competitor_source SET url = ? WHERE id = ?",
            ("https://example.com/not-arxiv", source["id"]),
        )
        conn.commit()
    source = CompetitorSourceService.get_source(source["id"])

    def _boom(url, **kwargs):
        raise AssertionError("httpx.get called for a non-arXiv URL")

    monkeypatch.setattr(ax.httpx, "get", _boom)
    monkeypatch.setattr(ax.logger, "warning", lambda *a, **k: None)

    result = ArxivAdapter().fetch(source)
    assert result.outcome == "skipped"


def test_empty_result_feed_is_unchanged(monkeypatch):
    # A feed with zero <entry> (a query that matched nothing) -> unchanged.
    _bypass_rate_gate(monkeypatch)
    source = _seed_source("https://arxiv.org/list/cs.LG/recent")
    _install_capture(monkeypatch, _FakeResponse(200, text=_atom_feed()))

    result = ArxivAdapter().fetch(source)
    assert result.outcome == "unchanged"


# --------------------------------------------------------------------------- #
# Keyless: no auth header is ever sent
# --------------------------------------------------------------------------- #


def test_fetch_sends_no_auth_header(monkeypatch):
    _bypass_rate_gate(monkeypatch)
    source = _seed_source("https://arxiv.org/list/cs.LG/recent")
    captured = _install_capture(monkeypatch, _FakeResponse(200, text=_atom_feed(_P_NEWER)))

    ArxivAdapter().fetch(source)

    # No Authorization (or any auth/token) header — the export API is keyless.
    header_keys = {k.lower() for k in captured["headers"]}
    assert "authorization" not in header_keys
    assert not any("auth" in k or "token" in k for k in header_keys)


# --------------------------------------------------------------------------- #
# The >= 3s aggregate serialization gate (fake clock + recording sleep)
# --------------------------------------------------------------------------- #


def test_rate_gate_enforces_3s_between_back_to_back_fetches(monkeypatch):
    """Two back-to-back fetches are forced >= 3s apart by the module gate.

    A FAKE monotonic clock advances ONLY when the recording ``sleep`` is called
    (and a tiny epsilon per ``monotonic()`` read so order is well-defined). The
    first fetch passes the gate immediately (no prior request); the second fetch,
    happening with ~0 real elapsed time, must sleep ~3s to honor the aggregate
    1-req/3s limit. NO real sleeping occurs.
    """
    source = _seed_source("https://arxiv.org/list/cs.LG/recent")
    _install_capture(monkeypatch, _FakeResponse(200, text=_atom_feed(_P_NEWER)))

    fake_now = {"t": 1000.0}
    slept: list[float] = []

    def _fake_monotonic():
        return fake_now["t"]

    def _fake_sleep(seconds):
        # Record the requested sleep and advance the fake clock by it — but never
        # actually block. This is how the gate's delta is asserted without a
        # 3-second test.
        slept.append(seconds)
        fake_now["t"] += seconds

    monkeypatch.setattr(ax.time, "monotonic", _fake_monotonic)
    monkeypatch.setattr(ax.time, "sleep", _fake_sleep)

    adapter = ArxivAdapter()

    # First fetch: no prior request -> the gate must NOT sleep.
    adapter.fetch(source)
    assert slept == []

    # Second fetch: ~0 elapsed since the first -> the gate sleeps the full ~3s.
    adapter.fetch(source)
    assert len(slept) == 1
    assert slept[0] == pytest.approx(3.0, abs=1e-6)


def test_rate_gate_does_not_sleep_when_interval_already_elapsed(monkeypatch):
    """If >= 3s already elapsed between requests, the gate does not sleep."""
    source = _seed_source("https://arxiv.org/list/cs.LG/recent")
    _install_capture(monkeypatch, _FakeResponse(200, text=_atom_feed(_P_NEWER)))

    fake_now = {"t": 500.0}
    slept: list[float] = []

    monkeypatch.setattr(ax.time, "monotonic", lambda: fake_now["t"])
    monkeypatch.setattr(ax.time, "sleep", lambda s: slept.append(s))

    adapter = ArxivAdapter()
    adapter.fetch(source)  # stamps last-request at t=500
    fake_now["t"] = 510.0  # 10s later — comfortably past the 3s floor
    adapter.fetch(source)

    assert slept == []  # no sleep needed; the interval already elapsed


# --------------------------------------------------------------------------- #
# commit integration: a changed fetch writes one snapshot + advances the cursor
# --------------------------------------------------------------------------- #


def test_changed_fetch_then_commit_writes_one_snapshot_and_persists_watermark(monkeypatch):
    _bypass_rate_gate(monkeypatch)
    source = _seed_source("https://arxiv.org/list/cs.LG/recent")
    feed = _atom_feed(_P_NEWER, _P_OLDER)
    _install_capture(monkeypatch, _FakeResponse(200, text=feed))

    adapter = ArxivAdapter()
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
    # The snapshot stores the CONTENT (paper text), distinct from the cursor.
    assert "Sparse Mixtures for Long Context" in snap["raw_ref"]

    # The source row carries the advanced watermark + a NULL etag (no cond-GET).
    persisted = CompetitorSourceService.get_source(source["id"])
    assert persisted["watermark"] == "2026-06-02T00:00:00Z"
    assert persisted["etag"] is None
