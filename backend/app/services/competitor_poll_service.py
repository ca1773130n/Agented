"""CompetitorPollService — the kind-dispatching competitor poll loop (phase 25).

The NEW scheduler entrypoint (``lifecycle._setup_scheduler`` repoints the
``competitor_intel_poll`` job here). It GENERALIZES phase-23's
``GitHubMonitorService.poll_due_sources`` (``github_monitor_service.py:303-347``):
P1 hard-filtered ``WHERE kind='github_repo'`` and broke the WHOLE batch on a
github throttle; this selects EVERY ``status='active'`` source and routes each
through ``registry.get_adapter(kind)`` — so an operator's arXiv / job-board
source is polled by its own adapter behind one loop, with byte-for-byte
identical ``github_repo`` behavior.

The two-phase isolation P1 established is preserved EXACTLY:

* **Phase 1 — fetch every due source** (fast, rate-limit-sensitive). Per row:
  unknown ``kind`` -> skip + log once; no credential -> skip (never an unauth
  call); polled too recently for its kind's floor -> skip; ``fetch`` wrapped in
  try/except so one bad source can't stall the rest; a ``throttled`` outcome
  backs off only THAT kind for the tick (different APIs = independent buckets —
  NOT P1's whole-batch break); a ``changed`` outcome commits one snapshot.
* **Phase 2 — summarize changed sources AFTER polling** (UNCHANGED from P1
  :340-346): the SAME kind-agnostic ``SignalSummarizerService.record_signal``
  per changed id, each in its own try/except. The summarizer (and its OWASP
  taint-wrap of the fetched competitor content) is reused verbatim — no new LLM
  path.

Persistence is raw SQLite via ``app.database.get_connection`` (repo convention).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from app.database import get_connection

logger = logging.getLogger(__name__)

# Columns the dispatcher selects per active source. ``last_polled_at`` (migration
# 173) is the per-kind poll-floor clock; ``etag``/``watermark`` are the fetch
# cursors an adapter consults read-only.
_POLL_COLUMNS = "id, url, etag, kind, watermark, last_polled_at"

# Accepted timestamp formats for last_polled_at (SQLite CURRENT_TIMESTAMP writes
# the first; the second tolerates a fractional-seconds variant defensively).
_TS_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f")


def _parse_ts(value: str | None) -> float | None:
    """Parse a SQLite UTC timestamp into an epoch float, or ``None`` if unparseable."""
    if not value:
        return None
    for fmt in _TS_FORMATS:
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc).timestamp()
        except (ValueError, TypeError):
            continue
    return None


class CompetitorPollService:
    """Kind-dispatching poll loop over ALL active competitor sources."""

    @staticmethod
    def _stamp_polled(source_id: str) -> None:
        """Advance ``last_polled_at`` to now for a source that was actually fetched.

        The per-kind poll floor (``_polled_too_recently``) reads ``last_polled_at``;
        ``AdapterBase.commit`` only stamps it on a ``changed`` outcome, so an
        ``unchanged``/``throttled``/``error`` fetch would never move the clock and
        the source would be re-fetched EVERY tick, hammering the API past its
        floor. The dispatcher therefore stamps the clock for ANY source it
        fetched, regardless of outcome — a small scoped UPDATE right after
        ``fetch`` returns. (Re-stamping in ``commit`` for ``changed`` is
        idempotent.) Only the PRE-fetch skips (unknown kind / no credential /
        polled-too-recently) must NOT stamp — they never hit the network.
        """
        with get_connection() as conn:
            conn.execute(
                "UPDATE competitor_source SET last_polled_at = CURRENT_TIMESTAMP WHERE id = ?",
                (source_id,),
            )
            conn.commit()

    @staticmethod
    def _polled_too_recently(row: dict, floor_s: int) -> bool:
        """True when ``row`` was polled less than ``floor_s`` seconds ago.

        The per-kind poll floor: ``now - last_polled_at < floor_s``. A floor of 0
        (e.g. ``github_repo``, whose 304s are already free) ALWAYS returns False
        — no throttling. A never-polled source (NULL / unparseable
        ``last_polled_at``) also returns False so it polls immediately.
        """
        if floor_s <= 0:
            return False
        last = _parse_ts(row.get("last_polled_at"))
        if last is None:
            return False
        return (time.time() - last) < floor_s

    @staticmethod
    def poll_due_sources(project_id: str | None = None, force: bool = False) -> int:
        """Poll every active source via its kind's adapter; return the count changed.

        Generalizes ``github_monitor_service.py:303-347`` — selects ALL
        ``status='active'`` rows (no ``kind`` filter) and dispatches per-kind.
        Returns the number of sources that produced a snapshot this tick.

        ``project_id`` (optional) scopes the source SELECT to ONE project
        (``status='active' AND project_id=?``) so an operator can poll their own
        project on demand without touching everyone else's sources. ``force=True``
        SKIPS the ``_polled_too_recently`` per-kind floor — an operator-triggered
        "check now" bypasses the interval throttle (``last_polled_at`` is still
        stamped after each fetch, so the floor governs the NEXT scheduled tick).

        A no-arg call ``poll_due_sources()`` is byte-for-byte the scheduled job
        (every active source, floor enforced) — the scheduler relies on that.
        """
        # Import the adapter subpackage so every adapter module runs its
        # bottom-line register(...) — mirrors P1's in-function import at
        # github_monitor_service.py:319 (lazy, avoids import cycles at module load).
        from app.services.signal_summarizer_service import SignalSummarizerService
        from app.services.source_adapters import registry

        with get_connection() as conn:
            if project_id is not None:
                rows = conn.execute(
                    f"SELECT {_POLL_COLUMNS} FROM competitor_source "
                    "WHERE status = 'active' AND project_id = ?",
                    (project_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"SELECT {_POLL_COLUMNS} FROM competitor_source WHERE status = 'active'",
                ).fetchall()
        sources = [dict(r) for r in rows]

        # Per-tick state. ``throttled_kinds`` backs off a kind after a 403/429 on
        # ONE of its sources — independent per kind (different APIs / buckets), NOT
        # P1's whole-batch break. ``unknown_logged`` keeps the skip log to once per
        # unknown kind so a misconfigured row can't spam the log every tick.
        changed_ids: list[str] = []
        throttled_kinds: set[str] = set()
        unknown_logged: set[str] = set()

        # Phase 1 — fetch every due source FIRST (fast, rate-limit-sensitive).
        for src in sources:
            kind = src.get("kind")
            if kind in throttled_kinds:
                # An earlier source of this kind hit 403/429 this tick — skip the
                # rest of THIS kind only; other kinds keep polling.
                continue

            adapter = registry.get_adapter(kind)
            if adapter is None:
                if kind not in unknown_logged:
                    unknown_logged.add(kind)
                    logger.warning(
                        "competitor poll: no adapter registered for kind %r — skipping its sources",
                        kind,
                    )
                continue

            if not adapter.has_credential():
                # Never issue an unauthenticated call — skip silently (the adapter
                # logs its own credential gap when relevant).
                continue

            if not force and CompetitorPollService._polled_too_recently(
                src, adapter.poll_interval_floor_s
            ):
                continue

            # Per-source isolation spans the WHOLE network-touching body — fetch,
            # the poll-floor stamp, AND commit/outcome handling — so a raise in
            # commit (not just fetch) logs a warning and the loop moves to the
            # next source instead of aborting the batch.
            try:
                result = adapter.fetch(src)

                # Stamp the poll-floor clock for EVERY fetched source regardless of
                # outcome (changed/unchanged/throttled/error). Without this an
                # 'unchanged' source never advances last_polled_at and is re-fetched
                # every tick, ignoring the per-kind floor. Only the pre-fetch skips
                # above (which never reach the network) are exempt.
                CompetitorPollService._stamp_polled(src["id"])

                if result.outcome == "throttled":
                    logger.warning(
                        "competitor poll: kind %r throttled — backing off its remaining sources",
                        kind,
                    )
                    throttled_kinds.add(kind)
                    continue

                if result.outcome == "changed" and adapter.commit(src["id"], result):
                    changed_ids.append(src["id"])
            except Exception:  # noqa: BLE001 — isolate one bad source (fetch or commit)
                logger.warning("competitor poll raised for source %s", src.get("id"), exc_info=True)
                continue

        # Phase 2 — summarize changed sources AFTER polling, so a slow LLM call
        # never stalls the poll loop. UNCHANGED from P1 (:340-346): the same
        # kind-agnostic summarizer, each call isolated.
        for source_id in changed_ids:
            try:
                SignalSummarizerService.record_signal(source_id)
            except Exception:  # noqa: BLE001 — a summarize failure can't stall the rest
                logger.warning(
                    "competitor signal summarize failed for source %s", source_id, exc_info=True
                )
        return len(changed_ids)
