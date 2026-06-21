"""Tests for JobBoardAdapter — keyless Greenhouse + Lever polling (phase 25, plan 02).

Covers the 25-02 contract:
  * First poll (watermark NULL) over a Greenhouse payload of 2 postings ->
    ``changed``, watermark == str(max updated_at), raw_ref names both
    titles + departments (the diff-set text block the summarizer reads).
  * Second poll with the SAME payload but watermark already at that max ->
    ``unchanged`` (no posting's updated_at exceeds the cursor; no write).
  * A payload adding ONE posting with a newer updated_at -> ``changed``,
    raw_ref mentions ONLY the new role, watermark advances.
  * Lever payload shape (``mode=json`` bare list, ``updatedAt`` epoch-ms,
    ``text`` / ``categories.team`` / ``categories.location``) parsed
    equivalently for a ``jobs.lever.co`` source.
  * ``429`` -> ``throttled``; malformed JSON -> ``error`` (no raise);
    empty / garbage board URL -> ``skipped``.
  * ``has_credential()`` is True and NO Authorization / auth header is ever
    sent — the slug is path-only (keyless read).
  * ``detect_kind`` for greenhouse + lever hosts == ``KIND_JOB_BOARD``.

HTTP is mocked by monkeypatching ``job_board.httpx.get`` — no network.
``isolated_db`` (autouse) gives a fresh migrated DB; a real project is created so
the FK on ``competitor_source.project_id`` is satisfied. Where a warning is
expected we spy ``job_board.logger.warning`` (the TestClient/caplog caveat from
CLAUDE.md does not bite here, but spying keeps it explicit and assertion-friendly).
"""

from __future__ import annotations

import json

import pytest

from app.database import get_connection
from app.db.projects import create_project
from app.services import source_adapters  # noqa: F401  (ensure adapters register)
from app.services.competitor_source_service import KIND_JOB_BOARD, CompetitorSourceService
from app.services.source_adapters import job_board as jb
from app.services.source_adapters.job_board import JobBoardAdapter

# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #


class _FakeResponse:
    """Minimal stand-in for httpx.Response (only what fetch reads)."""

    def __init__(self, status_code: int, *, body: object | None = None, raw: str | None = None):
        self.status_code = status_code
        self._body = body
        # ``raw`` lets a test force a malformed JSON body (json() raises).
        self._raw = raw

    def json(self):
        if self._raw is not None:
            return json.loads(self._raw)  # raises ValueError on malformed text
        return self._body


def _seed_source(url: str) -> dict:
    """Create a project + one job_board competitor_source; return the row dict."""
    project_id = create_project(name="ci-jobboard-project")
    assert project_id is not None
    source = CompetitorSourceService.add_source(project_id, url)
    assert source["kind"] == KIND_JOB_BOARD
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

    monkeypatch.setattr(jb.httpx, "get", _fake_get)
    return captured


# Greenhouse payload: {"jobs": [...]}, ISO-8601 updated_at (lexically sortable).
def _gh_job(jid: int, updated_at: str, title: str, dept: str, location: str) -> dict:
    return {
        "id": jid,
        "updated_at": updated_at,
        "title": title,
        "departments": [{"name": dept}],
        "location": {"name": location},
    }


def _gh_payload(*jobs: dict) -> dict:
    return {"jobs": list(jobs)}


# Lever payload: bare top-level list, updatedAt epoch-ms (13-digit, sortable as str).
def _lever_posting(pid: str, updated_at_ms: int, text: str, team: str, location: str) -> dict:
    return {
        "id": pid,
        "updatedAt": updated_at_ms,
        "text": text,
        "categories": {"team": team, "location": location},
    }


# --------------------------------------------------------------------------- #
# Adapter shape / registration
# --------------------------------------------------------------------------- #


def test_adapter_is_keyless_6h_floor_and_registered():
    adapter = JobBoardAdapter()
    assert adapter.kind == KIND_JOB_BOARD
    assert adapter.poll_interval_floor_s == 21600  # 6h — no ETag free path
    assert adapter.has_credential() is True  # keyless read

    from app.services.source_adapters import registry

    assert KIND_JOB_BOARD in registry.active_kinds()
    assert registry.get_adapter(KIND_JOB_BOARD) is not None


# --------------------------------------------------------------------------- #
# detect_kind routing
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "url",
    [
        "https://boards.greenhouse.io/acme",
        "https://job-boards.greenhouse.io/acme",
        "https://api.greenhouse.io/acme",
        "https://jobs.lever.co/acme",
        "https://api.lever.co/acme",
    ],
)
def test_detect_kind_routes_board_hosts_to_job_board(url):
    assert CompetitorSourceService.detect_kind(url) == KIND_JOB_BOARD


def test_detect_kind_leaves_other_hosts_unchanged():
    assert CompetitorSourceService.detect_kind("https://github.com/o/r") == "github_repo"
    assert CompetitorSourceService.detect_kind("https://arxiv.org/abs/2401.1") == "arxiv"
    assert CompetitorSourceService.detect_kind("https://example.com/x") == "product_url"


# --------------------------------------------------------------------------- #
# Greenhouse: first poll takes all, watermark dedup, watermark advance
# --------------------------------------------------------------------------- #


def test_greenhouse_first_poll_takes_all_postings(monkeypatch):
    source = _seed_source("https://boards.greenhouse.io/acme")
    assert source["watermark"] is None  # first poll: NULL cursor

    payload = _gh_payload(
        _gh_job(1, "2026-06-01T00:00:00Z", "Staff ML Eng", "Research", "Remote"),
        _gh_job(2, "2026-06-02T00:00:00Z", "Product Designer", "Design", "NYC"),
    )
    captured = _install_capture(monkeypatch, _FakeResponse(200, body=payload))

    result = JobBoardAdapter().fetch(source)

    assert result.outcome == "changed"
    # Watermark == str(max updated_at) across ALL returned postings.
    assert result.watermark == "2026-06-02T00:00:00Z"
    assert result.etag is None  # job boards have no conditional-GET cursor
    # raw_ref is the diff-set text block: both titles + departments present.
    assert "Staff ML Eng" in result.raw_ref
    assert "Research" in result.raw_ref
    assert "Product Designer" in result.raw_ref
    assert "Design" in result.raw_ref
    # The public board token is in the PATH, not auth.
    assert captured["url"] == "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true"


def test_greenhouse_second_poll_same_payload_is_unchanged(monkeypatch):
    source = _seed_source("https://boards.greenhouse.io/acme")
    payload = _gh_payload(
        _gh_job(1, "2026-06-01T00:00:00Z", "Staff ML Eng", "Research", "Remote"),
        _gh_job(2, "2026-06-02T00:00:00Z", "Product Designer", "Design", "NYC"),
    )
    # Cursor already at the max updated_at -> nothing exceeds it.
    source = _set_watermark(source["id"], "2026-06-02T00:00:00Z")
    _install_capture(monkeypatch, _FakeResponse(200, body=payload))

    result = JobBoardAdapter().fetch(source)

    assert result.outcome == "unchanged"
    assert result.raw_ref is None
    assert result.watermark is None  # nothing to persist on an unchanged poll


def test_greenhouse_new_posting_advances_watermark_and_names_only_new_role(monkeypatch):
    source = _seed_source("https://boards.greenhouse.io/acme")
    source = _set_watermark(source["id"], "2026-06-02T00:00:00Z")
    payload = _gh_payload(
        _gh_job(1, "2026-06-01T00:00:00Z", "Staff ML Eng", "Research", "Remote"),
        _gh_job(2, "2026-06-02T00:00:00Z", "Product Designer", "Design", "NYC"),
        _gh_job(3, "2026-06-05T00:00:00Z", "GTM Lead", "Marketing", "London"),
    )
    _install_capture(monkeypatch, _FakeResponse(200, body=payload))

    result = JobBoardAdapter().fetch(source)

    assert result.outcome == "changed"
    assert result.watermark == "2026-06-05T00:00:00Z"  # advanced to the new max
    # Only the NEW role appears in the diff set.
    assert "GTM Lead" in result.raw_ref
    assert "Marketing" in result.raw_ref
    assert "Staff ML Eng" not in result.raw_ref
    assert "Product Designer" not in result.raw_ref


# --------------------------------------------------------------------------- #
# Lever: parsed equivalently (mode=json bare list, updatedAt epoch-ms)
# --------------------------------------------------------------------------- #


def test_lever_first_poll_parses_bare_list_shape(monkeypatch):
    source = _seed_source("https://jobs.lever.co/acme")
    assert source["kind"] == KIND_JOB_BOARD
    payload = [
        _lever_posting("p1", 1717200000000, "Backend Engineer", "Platform", "Berlin"),
        _lever_posting("p2", 1717300000000, "Sales Eng", "Sales", "Austin"),
    ]
    captured = _install_capture(monkeypatch, _FakeResponse(200, body=payload))

    result = JobBoardAdapter().fetch(source)

    assert result.outcome == "changed"
    assert result.watermark == "1717300000000"  # max(updatedAt) as str
    assert "Backend Engineer" in result.raw_ref
    assert "Platform" in result.raw_ref
    assert "Sales Eng" in result.raw_ref
    # Company slug is path-only on the Lever endpoint.
    assert captured["url"] == "https://api.lever.co/v0/postings/acme?mode=json"


def test_lever_watermark_dedup_unchanged(monkeypatch):
    source = _seed_source("https://jobs.lever.co/acme")
    source = _set_watermark(source["id"], "1717300000000")
    payload = [
        _lever_posting("p1", 1717200000000, "Backend Engineer", "Platform", "Berlin"),
        _lever_posting("p2", 1717300000000, "Sales Eng", "Sales", "Austin"),
    ]
    _install_capture(monkeypatch, _FakeResponse(200, body=payload))

    result = JobBoardAdapter().fetch(source)
    assert result.outcome == "unchanged"


# --------------------------------------------------------------------------- #
# Keyless: no auth header is ever sent
# --------------------------------------------------------------------------- #


def test_fetch_sends_no_auth_header(monkeypatch):
    source = _seed_source("https://boards.greenhouse.io/acme")
    payload = _gh_payload(_gh_job(1, "2026-06-01T00:00:00Z", "Eng", "R&D", "Remote"))
    captured = _install_capture(monkeypatch, _FakeResponse(200, body=payload))

    JobBoardAdapter().fetch(source)

    # No Authorization (or any auth) header — the slug is a public path id only.
    header_keys = {k.lower() for k in captured["headers"]}
    assert "authorization" not in header_keys
    assert not any("auth" in k or "token" in k for k in header_keys)


# --------------------------------------------------------------------------- #
# Failure paths: throttled / error / skipped — never raise
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("status", [403, 429])
def test_throttled_on_403_429(monkeypatch, status):
    source = _seed_source("https://boards.greenhouse.io/acme")
    warnings: list = []
    monkeypatch.setattr(jb.logger, "warning", lambda *a, **k: warnings.append((a, k)))
    _install_capture(monkeypatch, _FakeResponse(status))

    result = JobBoardAdapter().fetch(source)

    assert result.outcome == "throttled"
    assert result.raw_ref is None
    assert warnings  # a throttle warning was logged


def test_malformed_json_is_error_no_raise(monkeypatch):
    source = _seed_source("https://boards.greenhouse.io/acme")
    warnings: list = []
    monkeypatch.setattr(jb.logger, "warning", lambda *a, **k: warnings.append((a, k)))
    _install_capture(monkeypatch, _FakeResponse(200, raw="{not valid json"))

    result = JobBoardAdapter().fetch(source)  # must not raise

    assert result.outcome == "error"
    assert warnings


def test_transport_error_is_error_no_raise(monkeypatch):
    source = _seed_source("https://boards.greenhouse.io/acme")

    def _boom(url, **kwargs):
        raise jb.httpx.ConnectError("dns failure")

    monkeypatch.setattr(jb.httpx, "get", _boom)
    monkeypatch.setattr(jb.logger, "warning", lambda *a, **k: None)

    result = JobBoardAdapter().fetch(source)  # must not raise
    assert result.outcome == "error"


def test_unexpected_status_is_error(monkeypatch):
    source = _seed_source("https://boards.greenhouse.io/acme")
    monkeypatch.setattr(jb.logger, "warning", lambda *a, **k: None)
    _install_capture(monkeypatch, _FakeResponse(500))

    result = JobBoardAdapter().fetch(source)
    assert result.outcome == "error"


def test_unparseable_board_url_is_skipped(monkeypatch):
    # A non-greenhouse/lever URL stored under job_board (or a board host with no
    # path segment) is not pollable -> skipped, no HTTP call, no raise.
    source = _seed_source("https://jobs.lever.co/acme")
    # Overwrite the URL to one with no public slug in the path.
    with get_connection() as conn:
        conn.execute(
            "UPDATE competitor_source SET url = ? WHERE id = ?",
            ("https://boards.greenhouse.io/", source["id"]),
        )
        conn.commit()
    source = CompetitorSourceService.get_source(source["id"])

    def _boom(url, **kwargs):
        raise AssertionError("httpx.get called for an unparseable board URL")

    monkeypatch.setattr(jb.httpx, "get", _boom)
    monkeypatch.setattr(jb.logger, "warning", lambda *a, **k: None)

    result = JobBoardAdapter().fetch(source)
    assert result.outcome == "skipped"


def test_empty_board_is_skipped(monkeypatch):
    source = _seed_source("https://boards.greenhouse.io/acme")
    _install_capture(monkeypatch, _FakeResponse(200, body={"jobs": []}))

    result = JobBoardAdapter().fetch(source)
    assert result.outcome == "skipped"


# --------------------------------------------------------------------------- #
# Slug injection hardening (MAJOR): a bad first path segment can't steer the URL
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "bad_path",
    [
        "..",  # path traversal token
        ".",  # current-dir token
        "a%2Fb",  # pre-encoded slash (urlparse leaves %2F in the segment)
        "a@b",  # userinfo delimiter
        "a:b",  # scheme/port delimiter
    ],
)
def test_injection_slug_in_single_segment_is_skipped_no_fetch(monkeypatch, bad_path):
    """A single path segment that is a traversal token or carries a URL delimiter
    fails the strict slug gate -> skipped, NO httpx call (can't be interpolated)."""
    source = _seed_source("https://boards.greenhouse.io/acme")
    with get_connection() as conn:
        conn.execute(
            "UPDATE competitor_source SET url = ? WHERE id = ?",
            (f"https://boards.greenhouse.io/{bad_path}", source["id"]),
        )
        conn.commit()
    source = CompetitorSourceService.get_source(source["id"])

    def _boom(url, **kwargs):
        raise AssertionError(f"httpx.get called for an injection slug: {url}")

    monkeypatch.setattr(jb.httpx, "get", _boom)
    monkeypatch.setattr(jb.logger, "warning", lambda *a, **k: None)

    result = JobBoardAdapter().fetch(source)
    assert result.outcome == "skipped"


@pytest.mark.parametrize(
    "url,expected_slug",
    [
        # A multi-segment path (e.g. "a/b") takes only the FIRST segment, and that
        # segment must itself be a clean slug — here "a" is fine, "b" is ignored.
        ("https://boards.greenhouse.io/a/b", "a"),
        # A query/fragment never bleeds into the slug: urlparse splits them off, so
        # the first path segment is the clean board id.
        ("https://boards.greenhouse.io/acme?x=1", "acme"),
        ("https://boards.greenhouse.io/acme#frag", "acme"),
    ],
)
def test_provider_and_slug_takes_clean_first_segment(url, expected_slug):
    """Multi-segment / query / fragment URLs resolve to the clean first segment;
    the slug never carries an injection payload."""
    provider, slug = jb._provider_and_slug(url)
    assert provider == jb._PROVIDER_GREENHOUSE
    assert slug == expected_slug


@pytest.mark.parametrize(
    "bad_segment",
    ["..", ".", "a/b", "a?x=1", "a@b", "a#f", "a%2Fb", "a b", "-leading-dash-ok-? no"],
)
def test_provider_and_slug_rejects_injection_payloads(bad_segment):
    """A first path segment that is a traversal token OR contains a delimiter
    yields (None, None) so the adapter skips instead of building a tainted URL."""
    # Build a URL whose first path segment is exactly ``bad_segment`` (quoting it
    # so urlparse keeps it as a single segment where possible).
    from urllib.parse import quote

    url = f"https://boards.greenhouse.io/{quote(bad_segment, safe='')}"
    provider, slug = jb._provider_and_slug(url)
    assert (provider, slug) == (None, None)


def test_endpoint_percent_escapes_slug_defense_in_depth():
    """``_endpoint`` percent-escapes the slug even if an unvalidated one reaches it
    (defense-in-depth) — no raw delimiter survives into the provider URL."""
    gh = jb._endpoint(jb._PROVIDER_GREENHOUSE, "ev/il?x=1")
    lv = jb._endpoint(jb._PROVIDER_LEVER, "ev/il?x=1")
    # The injected '/', '?', '=' are escaped, so the path/query can't be steered.
    assert "ev%2Fil%3Fx%3D1" in gh
    assert "ev%2Fil%3Fx%3D1" in lv
    # A normal slug is unchanged (escape is a no-op for the validated charset).
    assert jb._endpoint(jb._PROVIDER_GREENHOUSE, "acme").endswith("/boards/acme/jobs?content=true")


# --------------------------------------------------------------------------- #
# commit integration: a changed fetch writes exactly one snapshot + advances cursor
# --------------------------------------------------------------------------- #


def test_changed_fetch_then_commit_writes_one_snapshot_and_persists_watermark(monkeypatch):
    source = _seed_source("https://boards.greenhouse.io/acme")
    payload = _gh_payload(
        _gh_job(1, "2026-06-01T00:00:00Z", "Staff ML Eng", "Research", "Remote"),
        _gh_job(2, "2026-06-02T00:00:00Z", "Product Designer", "Design", "NYC"),
    )
    _install_capture(monkeypatch, _FakeResponse(200, body=payload))

    adapter = JobBoardAdapter()
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
    # The snapshot stores the CONTENT (diff text), distinct from the cursor.
    assert "Staff ML Eng" in snap["raw_ref"]

    # The source row carries the advanced watermark + a NULL etag (no cond-GET).
    persisted = CompetitorSourceService.get_source(source["id"])
    assert persisted["watermark"] == "2026-06-02T00:00:00Z"
    assert persisted["etag"] is None
