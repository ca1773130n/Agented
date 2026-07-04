"""Source-adapter contract: ``SourceAdapter`` Protocol + ``FetchResult`` +
``AdapterBase.commit`` (phase 25 — generalize the phase-23 github monitor).

Phase 23's ``GitHubMonitorService`` baked the *fetch* (conditional GET) and the
*persist* (one snapshot + cursor advance) into one service hard-filtered to
``kind='github_repo'``. Phase 25 lifts that implicit seam into an explicit
per-kind adapter layer so an operator's arXiv / job-board source is polled by
its own fetcher behind a single dispatcher (``CompetitorPollService``):

* ``FetchResult`` — the value an adapter's ``fetch`` returns: a tagged outcome
  plus the bytes-to-persist. ``raw_ref`` is the human-readable content the
  EXISTING ``SignalSummarizerService`` reads (and taint-wraps — every adapter's
  fetched competitor content is prompt-injection-tainted, OWASP LLM01, and MUST
  flow through that one summarizer, never a new LLM path); ``watermark`` is the
  monotonic dedup cursor; ``etag`` is github's conditional-GET cursor.
  ``raw_ref`` and ``watermark`` are kept DISTINCT — P1's ``_extract_content``
  docstring lesson: summarizing a bare ``published_at`` date is wrong.
* ``SourceAdapter`` — a ``typing.Protocol`` (structural, not nominal): any class
  with ``kind`` / ``poll_interval_floor_s`` attrs and ``has_credential`` /
  ``fetch`` methods satisfies it. ``fetch`` consults ONLY ``source['url']`` /
  ``['etag']`` / ``['watermark']`` — read-only, one cheap fetch, no persistence.
* ``AdapterBase`` — the shared base whose ``commit`` is the phase-23
  ``GitHubMonitorService._persist_snapshot_and_cursor`` (:142-174) lifted
  VERBATIM: every adapter writes a snapshot + advances the cursor identically,
  with the same defense-in-depth dedup. Adapters subclass it for ``commit``;
  ``fetch`` is each adapter's own.

Persistence is raw SQLite via ``app.database.get_connection`` (repo convention,
no ORM); ids are prefixed-random via ``app.db.ids.generate_id``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal, Optional, Protocol, runtime_checkable

from app.database import get_connection
from app.db.connection import insertion_tiebreak_col
from app.db.ids import generate_id

# Outcome tags an adapter's ``fetch`` returns. ``changed`` is the only one that
# persists (via ``commit``); ``unchanged`` is the free path (e.g. github 304);
# ``throttled`` (403/429) backs off THIS kind for the tick; ``skipped`` /
# ``error`` are no-op per-source conditions the dispatcher logs and moves past.
FetchOutcome = Literal["changed", "unchanged", "throttled", "skipped", "error"]


@dataclass(frozen=True)
class FetchResult:
    """One adapter ``fetch`` result — a tagged outcome plus what to persist.

    ``raw_ref`` is the human-readable content the summarizer reads (and
    taint-wraps); ``watermark`` is the dedup cursor to persist; ``etag`` is the
    github conditional-GET cursor; ``content_hash`` lets an adapter supply its
    own hash (else ``commit`` derives ``sha256(raw_ref)``). ``raw_ref`` and
    ``watermark`` are DISTINCT — content vs. cursor.
    """

    outcome: FetchOutcome
    raw_ref: Optional[str] = None
    watermark: Optional[str] = None
    etag: Optional[str] = None
    content_hash: Optional[str] = None


@runtime_checkable
class SourceAdapter(Protocol):
    """Structural contract every per-kind fetcher satisfies.

    ``kind`` is the ``competitor_source.kind`` value this adapter handles (the
    registry key). ``poll_interval_floor_s`` is the minimum seconds between two
    fetches of one source (the per-kind poll floor — github is 0 because its
    ETag/304 path is already free); the dispatcher enforces it against
    ``last_polled_at``. ``has_credential`` gates whether the dispatcher may call
    ``fetch`` at all (no credential -> skip, never an unauth call). ``fetch``
    consults ONLY ``source['url']`` / ``['etag']`` / ``['watermark']`` and does
    exactly one cheap read — persistence belongs to ``AdapterBase.commit``.
    """

    kind: str
    poll_interval_floor_s: int

    def has_credential(self) -> bool:
        """True when this adapter has the credential it needs to fetch."""
        ...

    def fetch(self, source: dict) -> FetchResult:
        """One read-only fetch of ``source``; never persists."""
        ...


class AdapterBase:
    """Shared base providing the single snapshot+cursor write for every adapter.

    ``commit`` is ``GitHubMonitorService._persist_snapshot_and_cursor``
    (:142-174) lifted verbatim and generalized to any kind: it owns ALL
    persistence so an adapter's ``fetch`` stays a pure read. Concrete adapters
    subclass this and add their own ``fetch`` (+ ``has_credential`` /
    ``kind`` / ``poll_interval_floor_s``).
    """

    def commit(self, source_id: str, result: FetchResult) -> Optional[str]:
        """Write ONE snapshot + advance the source cursor; return the snapshot id.

        Lifted from ``_persist_snapshot_and_cursor`` (every adapter writes
        identically):

        1. ``content_hash = result.content_hash or sha256(raw_ref)`` — adapters
           may supply a hash; otherwise hash the human-readable ``raw_ref``.
        2. Defense-in-depth dedup: read the source's LATEST
           ``competitor_snapshot.content_hash`` (newest first); if it equals the
           new hash, return ``None`` and write nothing (a re-fetch of identical
           content is not a change).
        3. In ONE ``get_connection()`` transaction (single commit, matching P1's
           ``_persist_snapshot_and_cursor``): the dedup read, the conditional
           snapshot INSERT, and the cursor UPDATE all share one connection so a
           re-fetch can't race between the read and the write. INSERT one
           ``competitor_snapshot`` (``raw_ref`` = the content the summarizer
           reads) then UPDATE the parent ``competitor_source`` SET
           ``etag``/``watermark``/``last_polled_at``. ``raw_ref`` (content) and
           ``watermark`` (cursor) stay DISTINCT.

        ``last_polled_at`` is ALSO stamped by the dispatcher for every fetched
        source regardless of outcome; re-stamping it here on the ``changed`` path
        is idempotent (the poll-floor clock only moves forward).

        Returns the new ``cmsn-`` snapshot id, or ``None`` when deduped.
        """
        raw_ref = result.raw_ref
        content_hash = result.content_hash or hashlib.sha256((raw_ref or "").encode()).hexdigest()

        snapshot_id = generate_id("cmsn-", 6)
        # ONE transaction for the dedup read + INSERT + cursor UPDATE (P1's
        # _persist_snapshot_and_cursor lift): reading the latest hash on the SAME
        # connection that writes closes the dedup->insert race a two-block version
        # left open.
        with get_connection() as conn:
            # Defense-in-depth dedup: don't write a second snapshot for content the
            # source already holds (the adapter's own change check is the first
            # line; this is the backstop, mirroring P1's content-hash equality
            # guard).
            prev = conn.execute(
                "SELECT content_hash FROM competitor_snapshot WHERE source_id = ? "
                # rowid on SQLite / id on Postgres — deterministic insertion-order
                # tiebreaker after fetched_at (see insertion_tiebreak_col).
                f"ORDER BY fetched_at DESC, {insertion_tiebreak_col()} DESC LIMIT 1",  # noqa: S608
                (source_id,),
            ).fetchone()
            if prev is not None and prev["content_hash"] == content_hash:
                return None

            conn.execute(
                """
                INSERT INTO competitor_snapshot
                    (id, source_id, fetched_at, content_hash, raw_ref)
                VALUES (?, ?, CURRENT_TIMESTAMP, ?, ?)
                """,
                (snapshot_id, source_id, content_hash, raw_ref),
            )
            conn.execute(
                "UPDATE competitor_source "
                "SET etag = ?, watermark = ?, last_polled_at = CURRENT_TIMESTAMP "
                "WHERE id = ?",
                (result.etag, result.watermark, source_id),
            )
            conn.commit()
        return snapshot_id
