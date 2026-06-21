"""Tests for the phase-25 source-adapter registry + ``AdapterBase.commit``.

Two contracts:

* **registry** — ``register`` / ``get_adapter`` / ``active_kinds`` round-trip: a
  fake adapter is findable by its kind, shows up in ``active_kinds`` alongside
  the import-registered ``github_repo``, and an unknown kind returns ``None``.
* **AdapterBase.commit** — the lifted ``_persist_snapshot_and_cursor``: a first
  commit writes exactly ONE ``competitor_snapshot`` with the ``sha256(raw_ref)``
  content hash and advances ``etag`` / ``watermark`` / ``last_polled_at``; a
  second commit of IDENTICAL content (same hash) returns ``None`` and writes NO
  second snapshot (defense-in-depth dedup).

``isolated_db`` (autouse) gives a fresh migrated DB; a real project is created so
the FK on ``competitor_source.project_id`` is satisfied.
"""

from __future__ import annotations

import hashlib

from app.database import get_connection
from app.db.projects import create_project
from app.services.competitor_source_service import CompetitorSourceService
from app.services.source_adapters import registry
from app.services.source_adapters.base import AdapterBase, FetchResult, SourceAdapter


class _FakeAdapter(AdapterBase):
    """Minimal SourceAdapter for registry tests — fetch is never called here."""

    kind = "fake"
    poll_interval_floor_s = 0

    def has_credential(self) -> bool:
        return True

    def fetch(self, source: dict) -> FetchResult:
        return FetchResult(outcome="unchanged")


def _seed_source(url: str = "https://example.com/widget") -> dict:
    """Create a project + one competitor_source; return the row dict."""
    project_id = create_project(name="adapter-registry-test")
    assert project_id is not None
    source = CompetitorSourceService.add_source(project_id, url)
    return source


def _snapshot_rows(source_id: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, content_hash, raw_ref FROM competitor_snapshot WHERE source_id = ? "
            "ORDER BY fetched_at DESC, rowid DESC",
            (source_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def _source_row(source_id: str) -> dict:
    return CompetitorSourceService.get_source(source_id)


# ---------------------------------------------------------------------------
# Registry round-trip.
# ---------------------------------------------------------------------------


def test_register_and_get_adapter_round_trip():
    adapter = _FakeAdapter()
    registry.register(adapter)
    assert registry.get_adapter("fake") is adapter


def test_active_kinds_includes_fake_and_github_repo():
    registry.register(_FakeAdapter())
    kinds = registry.active_kinds()
    assert "fake" in kinds
    # github_repo self-registered when the source_adapters package was imported.
    assert "github_repo" in kinds


def test_get_adapter_unknown_returns_none():
    assert registry.get_adapter("nope-not-a-kind") is None


def test_fake_adapter_satisfies_protocol():
    # The Protocol is runtime_checkable — a structural conformance smoke test.
    assert isinstance(_FakeAdapter(), SourceAdapter)


# ---------------------------------------------------------------------------
# AdapterBase.commit — single snapshot + cursor advance + dedup.
# ---------------------------------------------------------------------------


def test_commit_writes_one_snapshot_and_advances_cursor():
    source = _seed_source()
    raw = "Release v1.0\n\nFirst notes."
    result = FetchResult(
        outcome="changed", raw_ref=raw, watermark="2026-06-01T00:00:00Z", etag='W/"a"'
    )

    snapshot_id = AdapterBase().commit(source["id"], result)

    assert snapshot_id is not None
    rows = _snapshot_rows(source["id"])
    assert len(rows) == 1
    assert rows[0]["content_hash"] == hashlib.sha256(raw.encode()).hexdigest()
    assert rows[0]["raw_ref"] == raw

    row = _source_row(source["id"])
    assert row["etag"] == 'W/"a"'
    assert row["watermark"] == "2026-06-01T00:00:00Z"
    # last_polled_at was advanced from its initial NULL.
    with get_connection() as conn:
        lp = conn.execute(
            "SELECT last_polled_at FROM competitor_source WHERE id = ?", (source["id"],)
        ).fetchone()["last_polled_at"]
    assert lp is not None


def test_commit_uses_supplied_content_hash_when_present():
    source = _seed_source()
    result = FetchResult(
        outcome="changed", raw_ref="body-text", content_hash="deadbeef" * 8, watermark="w1"
    )
    AdapterBase().commit(source["id"], result)
    rows = _snapshot_rows(source["id"])
    assert len(rows) == 1
    assert rows[0]["content_hash"] == "deadbeef" * 8


def test_commit_dedups_identical_content():
    source = _seed_source()
    raw = "Identical release body"
    first = FetchResult(outcome="changed", raw_ref=raw, watermark="w1", etag='W/"1"')
    second = FetchResult(outcome="changed", raw_ref=raw, watermark="w2", etag='W/"2"')

    first_id = AdapterBase().commit(source["id"], first)
    second_id = AdapterBase().commit(source["id"], second)

    assert first_id is not None
    # Identical content hash -> no second snapshot, cursor NOT re-advanced.
    assert second_id is None
    assert len(_snapshot_rows(source["id"])) == 1
    row = _source_row(source["id"])
    assert row["etag"] == 'W/"1"'
    assert row["watermark"] == "w1"


def test_commit_writes_second_snapshot_when_content_changes():
    source = _seed_source()
    AdapterBase().commit(source["id"], FetchResult(outcome="changed", raw_ref="v1", watermark="w1"))
    AdapterBase().commit(source["id"], FetchResult(outcome="changed", raw_ref="v2", watermark="w2"))
    assert len(_snapshot_rows(source["id"])) == 2


def test_commit_snapshot_and_cursor_land_atomically():
    """MAJOR: the dedup read + snapshot INSERT + cursor UPDATE are ONE transaction.

    A single commit must leave a consistent pair — exactly one snapshot AND the
    cursor advanced — with no half-written state (the snapshot inserted but the
    cursor not, or vice versa). This is the faithful single-transaction lift of
    P1's ``_persist_snapshot_and_cursor``; the read and the writes share one
    connection so a re-fetch can't slip between the dedup read and the insert."""
    source = _seed_source()
    raw = "Release v2.0\n\nAtomic notes."
    snapshot_id = AdapterBase().commit(
        source["id"],
        FetchResult(outcome="changed", raw_ref=raw, watermark="2026-06-09T00:00:00Z", etag='W/"z"'),
    )

    rows = _snapshot_rows(source["id"])
    row = _source_row(source["id"])
    # Snapshot written AND cursor advanced in the same commit — both, not one.
    assert snapshot_id is not None
    assert len(rows) == 1
    assert rows[0]["content_hash"] == hashlib.sha256(raw.encode()).hexdigest()
    assert row["etag"] == 'W/"z"'
    assert row["watermark"] == "2026-06-09T00:00:00Z"
    with get_connection() as conn:
        lp = conn.execute(
            "SELECT last_polled_at FROM competitor_source WHERE id = ?", (source["id"],)
        ).fetchone()["last_polled_at"]
    assert lp is not None  # cursor + clock advanced alongside the snapshot
