"""Tests for GitHubMonitorService — authenticated conditional polling (REQ-28).

Covers the four contract behaviours from 23-02:
  * 304 Not Modified  -> changed=False, ZERO snapshot rows, etag unchanged (free path).
  * 200 OK + fresh ETag -> changed=True, exactly ONE snapshot with a content_hash,
    source row carries the new etag + an updated watermark.
  * Authorization header is ALWAYS present (the 60/hr unauth path is never taken
    when a PAT is configured).
  * If-None-Match echoes the stored etag on the outgoing request.
Plus the no-PAT skip path (spies on module.logger.warning per the CLAUDE.md
caplog caveat).

HTTP is mocked by monkeypatching ``github_monitor_service.httpx.get`` — no
network. ``isolated_db`` (autouse) gives a fresh migrated DB; a real project is
created so the FK on ``competitor_source.project_id`` is satisfied.
"""

from __future__ import annotations

import json

import pytest

from app.database import get_connection
from app.db.projects import create_project
from app.services import github_monitor_service as gms
from app.services.competitor_source_service import CompetitorSourceService
from app.services.github_monitor_service import GITHUB_PAT_ENV, GitHubMonitorService


class _FakeResponse:
    """Minimal stand-in for httpx.Response (only what poll_source reads)."""

    def __init__(self, status_code: int, *, body: dict | None = None, etag: str | None = None):
        self.status_code = status_code
        self._body = body or {}
        self.content = json.dumps(self._body).encode() if body is not None else b""
        self.headers = {}
        if etag is not None:
            self.headers["ETag"] = etag

    def json(self):
        return self._body


def _seed_source(url: str = "https://github.com/acme/widget", etag: str | None = None) -> dict:
    """Create a project + one github_repo competitor_source; return the row dict."""
    project_id = create_project(name="ci-test-project")
    assert project_id is not None
    source = CompetitorSourceService.add_source(project_id, url)
    assert source["kind"] == "github_repo"
    if etag is not None:
        with get_connection() as conn:
            conn.execute("UPDATE competitor_source SET etag = ? WHERE id = ?", (etag, source["id"]))
            conn.commit()
        source = CompetitorSourceService.get_source(source["id"])
    return source


def _snapshot_count(source_id: str) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM competitor_snapshot WHERE source_id = ?",
            (source_id,),
        ).fetchone()
    return int(row["n"])


def _install_capture(monkeypatch, response: _FakeResponse) -> dict:
    """Patch httpx.get on the service module to record the call and return ``response``."""
    captured: dict = {}

    def _fake_get(url, **kwargs):
        captured["url"] = url
        captured["headers"] = dict(kwargs.get("headers") or {})
        captured["kwargs"] = kwargs
        return response

    monkeypatch.setattr(gms.httpx, "get", _fake_get)
    return captured


def _spy_record_signal(monkeypatch) -> list:
    """Patch SignalSummarizerService.record_signal with a no-op spy (no LLM call);
    return the list of source_ids it was invoked with."""
    import app.services.signal_summarizer_service as sss

    calls: list = []
    monkeypatch.setattr(
        sss.SignalSummarizerService,
        "record_signal",
        classmethod(lambda cls, source_id, *a, **k: (calls.append(source_id), {"id": "csig-x"})[1]),
    )
    return calls


# ---------------------------------------------------------------------------
# 304: the free path — no writes, etag preserved.
# ---------------------------------------------------------------------------


def test_poll_source_304_makes_zero_writes(monkeypatch):
    monkeypatch.setenv(GITHUB_PAT_ENV, "ghp_test_token")
    source = _seed_source(etag='W/"abc123"')

    captured = _install_capture(monkeypatch, _FakeResponse(304))
    result = GitHubMonitorService.poll_source(source)

    assert result == {"changed": False}
    # Zero snapshots written on the free path.
    assert _snapshot_count(source["id"]) == 0
    # ETag is unchanged (no row rewrite).
    refreshed = CompetitorSourceService.get_source(source["id"])
    assert refreshed["etag"] == 'W/"abc123"'
    assert refreshed["watermark"] is None
    # The conditional request echoed the stored etag.
    assert captured["headers"].get("If-None-Match") == 'W/"abc123"'


# ---------------------------------------------------------------------------
# 200: a real change — one snapshot, new etag + watermark persisted.
# ---------------------------------------------------------------------------


def test_poll_source_200_writes_one_snapshot_and_persists_cursor(monkeypatch):
    monkeypatch.setenv(GITHUB_PAT_ENV, "ghp_test_token")
    source = _seed_source(etag='W/"old"')

    response = _FakeResponse(
        200,
        body={"tag_name": "v2.0.0", "published_at": "2026-06-20T00:00:00Z"},
        etag='W/"new-etag"',
    )
    _install_capture(monkeypatch, response)
    result = GitHubMonitorService.poll_source(source)

    assert result["changed"] is True
    assert "snapshot_id" in result
    assert result["content_hash"]  # non-empty sha256 hex
    assert len(result["content_hash"]) == 64

    # Exactly ONE snapshot row, carrying the content_hash.
    assert _snapshot_count(source["id"]) == 1
    with get_connection() as conn:
        snap = conn.execute(
            "SELECT id, content_hash, fetched_at FROM competitor_snapshot WHERE source_id = ?",
            (source["id"],),
        ).fetchone()
    assert snap["id"] == result["snapshot_id"]
    assert snap["content_hash"] == result["content_hash"]
    assert snap["fetched_at"] is not None

    # Source row advanced: new etag + a watermark derived from the body.
    refreshed = CompetitorSourceService.get_source(source["id"])
    assert refreshed["etag"] == 'W/"new-etag"'
    assert refreshed["watermark"] == "2026-06-20T00:00:00Z"


def test_poll_source_200_watermark_falls_back_to_tag_name(monkeypatch):
    monkeypatch.setenv(GITHUB_PAT_ENV, "ghp_test_token")
    source = _seed_source()
    response = _FakeResponse(200, body={"tag_name": "v3.1.0"}, etag='W/"e"')
    _install_capture(monkeypatch, response)

    GitHubMonitorService.poll_source(source)

    refreshed = CompetitorSourceService.get_source(source["id"])
    assert refreshed["watermark"] == "v3.1.0"


def test_poll_source_200_snapshot_stores_release_notes_not_watermark(monkeypatch):
    """Regression (live dogfood): snapshot.raw_ref must hold the release CONTENT
    the summarizer reads — the notes — NOT the published_at watermark. The bug
    stored the timestamp, so summaries were of a bare date."""
    monkeypatch.setenv(GITHUB_PAT_ENV, "ghp_test_token")
    source = _seed_source()
    response = _FakeResponse(
        200,
        body={
            "name": "v2.0.0",
            "tag_name": "v2.0.0",
            "published_at": "2026-06-20T00:00:00Z",
            "body": "## Highlights\n- TURBO mode ships\n- 2x faster cold start",
        },
        etag='W/"e"',
    )
    _install_capture(monkeypatch, response)
    GitHubMonitorService.poll_source(source)

    with get_connection() as conn:
        snap = conn.execute(
            "SELECT raw_ref FROM competitor_snapshot WHERE source_id = ?",
            (source["id"],),
        ).fetchone()
    raw_ref = snap["raw_ref"]
    # The notes (what the summarizer will summarize) are present …
    assert "TURBO mode ships" in raw_ref
    assert "v2.0.0" in raw_ref
    # … and raw_ref is NOT the bare published_at timestamp (the old bug).
    assert raw_ref != "2026-06-20T00:00:00Z"
    # The watermark cursor still tracks published_at on the SOURCE row.
    assert CompetitorSourceService.get_source(source["id"])["watermark"] == "2026-06-20T00:00:00Z"


# ---------------------------------------------------------------------------
# Always authenticated.
# ---------------------------------------------------------------------------


def test_poll_source_is_always_authenticated(monkeypatch):
    monkeypatch.setenv(GITHUB_PAT_ENV, "ghp_secret_value")
    source = _seed_source()
    captured = _install_capture(monkeypatch, _FakeResponse(304))

    GitHubMonitorService.poll_source(source)

    auth = captured["headers"].get("Authorization")
    assert auth is not None, "the unauthenticated 60/hr path must never be taken"
    assert auth == "Bearer ghp_secret_value"


def test_poll_source_no_inm_header_when_no_etag(monkeypatch):
    monkeypatch.setenv(GITHUB_PAT_ENV, "ghp_test_token")
    source = _seed_source()  # etag is NULL
    captured = _install_capture(monkeypatch, _FakeResponse(304))

    GitHubMonitorService.poll_source(source)

    assert "If-None-Match" not in captured["headers"]


# ---------------------------------------------------------------------------
# No PAT -> skip, never unauth. Spy on module.logger.warning.
# ---------------------------------------------------------------------------


def test_poll_source_skips_and_warns_without_pat(monkeypatch):
    monkeypatch.delenv(GITHUB_PAT_ENV, raising=False)
    source = _seed_source()

    warnings: list = []
    monkeypatch.setattr(gms.logger, "warning", lambda *a, **k: warnings.append((a, k)))

    # httpx.get must NOT be called when there's no credential.
    def _boom(*a, **k):  # pragma: no cover - asserts the path isn't taken
        raise AssertionError("httpx.get called without a PAT — unauth path taken")

    monkeypatch.setattr(gms.httpx, "get", _boom)

    result = GitHubMonitorService.poll_source(source)

    assert result == {"changed": False, "skipped": True}
    assert _snapshot_count(source["id"]) == 0
    assert warnings, "a warning should be logged when no PAT is configured"


# ---------------------------------------------------------------------------
# Throttling (403/429) -> back off, no writes.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", [403, 429])
def test_poll_source_throttled_makes_no_writes(monkeypatch, status):
    monkeypatch.setenv(GITHUB_PAT_ENV, "ghp_test_token")
    source = _seed_source(etag='W/"keep"')
    _install_capture(monkeypatch, _FakeResponse(status))

    result = GitHubMonitorService.poll_source(source)

    assert result == {"changed": False, "throttled": True}
    assert _snapshot_count(source["id"]) == 0
    assert CompetitorSourceService.get_source(source["id"])["etag"] == 'W/"keep"'


# ---------------------------------------------------------------------------
# poll_due_sources — iterates active github_repo sources, counts changes.
# ---------------------------------------------------------------------------


def test_poll_due_sources_counts_changed_active_github_sources(monkeypatch):
    monkeypatch.setenv(GITHUB_PAT_ENV, "ghp_test_token")
    project_id = create_project(name="ci-due-project")

    changed_src = CompetitorSourceService.add_source(project_id, "https://github.com/a/b")
    unchanged_src = CompetitorSourceService.add_source(project_id, "https://github.com/c/d")
    # A non-github source must be ignored by the poller entirely.
    CompetitorSourceService.add_source(project_id, "https://arxiv.org/abs/2401.00001")

    def _fake_get(url, **kwargs):
        # The "changed" repo's URL returns 200; everything else 304.
        if "/a/b/" in url:
            return _FakeResponse(200, body={"tag_name": "v1"}, etag='W/"x"')
        return _FakeResponse(304)

    monkeypatch.setattr(gms.httpx, "get", _fake_get)
    record_calls = _spy_record_signal(monkeypatch)

    changed = GitHubMonitorService.poll_due_sources()

    assert changed == 1
    assert _snapshot_count(changed_src["id"]) == 1
    assert _snapshot_count(unchanged_src["id"]) == 0
    # Pipeline wired end-to-end: a changed poll summarizes into a signal —
    # record_signal called once, for the changed source only.
    assert record_calls == [changed_src["id"]]


def test_poll_due_sources_skips_paused_sources(monkeypatch):
    monkeypatch.setenv(GITHUB_PAT_ENV, "ghp_test_token")
    project_id = create_project(name="ci-paused-project")
    src = CompetitorSourceService.add_source(project_id, "https://github.com/a/b")
    with get_connection() as conn:
        conn.execute("UPDATE competitor_source SET status = 'paused' WHERE id = ?", (src["id"],))
        conn.commit()

    def _boom(*a, **k):  # pragma: no cover - paused source must not be polled
        raise AssertionError("paused source was polled")

    monkeypatch.setattr(gms.httpx, "get", _boom)

    assert GitHubMonitorService.poll_due_sources() == 0


def test_poll_due_sources_stops_on_throttle(monkeypatch):
    """A 403/429 stops the batch so the token isn't hammered on remaining repos."""
    monkeypatch.setenv(GITHUB_PAT_ENV, "ghp_test_token")
    project_id = create_project(name="ci-throttle")
    CompetitorSourceService.add_source(project_id, "https://github.com/a/b")
    CompetitorSourceService.add_source(project_id, "https://github.com/c/d")
    _spy_record_signal(monkeypatch)

    polled: list = []

    def _fake_get(url, **kwargs):
        polled.append(url)
        return _FakeResponse(429)

    monkeypatch.setattr(gms.httpx, "get", _fake_get)
    GitHubMonitorService.poll_due_sources()
    assert len(polled) == 1  # broke after the first throttled poll, didn't hammer


def test_poll_source_200_without_etag_preserves_stored_etag(monkeypatch):
    """A 200 lacking an ETag header must NOT clear the stored etag (which would
    permanently disable conditional GETs for the source)."""
    monkeypatch.setenv(GITHUB_PAT_ENV, "ghp_test_token")
    source = _seed_source(etag='W/"keep-me"')
    _install_capture(monkeypatch, _FakeResponse(200, body={"tag_name": "v9", "body": "x"}))

    GitHubMonitorService.poll_source(source)

    assert CompetitorSourceService.get_source(source["id"])["etag"] == 'W/"keep-me"'


# ---------------------------------------------------------------------------
# Config helper.
# ---------------------------------------------------------------------------


def test_get_competitor_intel_config_default_disabled():
    cfg = gms.get_competitor_intel_config()
    assert cfg["enabled"] is False
    assert cfg["polling_minutes"] == 15


def test_get_competitor_intel_config_reads_settings_row():
    from app.db.settings import set_setting

    set_setting(
        gms.COMPETITOR_INTEL_CONFIG_KEY,
        json.dumps({"enabled": True, "polling_minutes": 30}),
    )
    cfg = gms.get_competitor_intel_config()
    assert cfg["enabled"] is True
    assert cfg["polling_minutes"] == 30
