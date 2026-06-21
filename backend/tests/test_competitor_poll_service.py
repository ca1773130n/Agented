"""Tests for CompetitorPollService — the phase-25 kind-dispatching poll loop.

Covers the contract that generalizes P1's ``poll_due_sources``:

* **dispatch** — every ``status='active'`` source is routed to its kind's adapter
  (no ``kind='github_repo'`` filter); an UNKNOWN kind is skipped with one warning
  and never crashes the loop.
* **per-kind (not whole-batch) throttle** — a ``throttled`` outcome on one
  source backs off only the REST of that kind for the tick; other kinds keep
  polling (the key behavior change from P1's whole-batch break).
* **per-source isolation** — an adapter whose ``fetch`` raises logs a warning and
  the loop continues to the next source.
* **changed -> record_signal** — a ``changed`` outcome commits exactly one
  snapshot AND invokes the (unchanged, kind-agnostic) ``record_signal`` for that
  source id.
* **has_credential / poll-floor skips** — a no-credential adapter is never
  called; a source polled within its kind's floor is skipped this tick.
* **github parity** — the real ``github_repo`` adapter still drives the P1 path
  (the existing ``test_github_monitor_service.py`` is run alongside).

``isolated_db`` (autouse) gives a fresh migrated DB; real projects satisfy the
``competitor_source.project_id`` FK. Adapters are registered ad hoc and
``record_signal`` is spied per the CLAUDE.md caplog caveat (spy the symbol, not
caplog). Unknown-kind warnings are asserted by spying ``module.logger.warning``.
"""

from __future__ import annotations

import app.services.competitor_poll_service as cps
from app.database import get_connection
from app.db.projects import create_project
from app.services.competitor_poll_service import CompetitorPollService
from app.services.competitor_source_service import CompetitorSourceService
from app.services.source_adapters import registry
from app.services.source_adapters.base import AdapterBase, FetchResult

# ---------------------------------------------------------------------------
# Fake adapters + seeding helpers.
# ---------------------------------------------------------------------------


class _RecordingAdapter(AdapterBase):
    """A SourceAdapter whose fetch returns a queued/fixed FetchResult and records
    every source id it was asked to fetch (so we can assert dispatch order)."""

    def __init__(
        self,
        kind: str,
        *,
        result: FetchResult | None = None,
        results: list[FetchResult] | None = None,
        raises: bool = False,
        has_cred: bool = True,
        floor_s: int = 0,
    ):
        self.kind = kind
        self.poll_interval_floor_s = floor_s
        self._result = result or FetchResult(outcome="unchanged")
        self._results = list(results) if results else None
        self._raises = raises
        self._has_cred = has_cred
        self.fetched: list[str] = []

    def has_credential(self) -> bool:
        return self._has_cred

    def fetch(self, source: dict) -> FetchResult:
        self.fetched.append(source["id"])
        if self._raises:
            raise RuntimeError("boom")
        if self._results is not None:
            return self._results.pop(0) if self._results else FetchResult(outcome="unchanged")
        return self._result


def _seed(kind: str, *, url: str = "https://example.com/x") -> str:
    """Create a project + one active source, FORCE its ``kind``; return source id.

    ``add_source`` auto-detects kind from the host, so we overwrite ``kind`` to
    the arbitrary test kind directly (kind is free TEXT — no CHECK).
    """
    project_id = create_project(name=f"poll-test-{kind}")
    source = CompetitorSourceService.add_source(project_id, url)
    with get_connection() as conn:
        conn.execute("UPDATE competitor_source SET kind = ? WHERE id = ?", (kind, source["id"]))
        conn.commit()
    return source["id"]


def _spy_record_signal(monkeypatch) -> list:
    """Patch SignalSummarizerService.record_signal with a no-op spy; return the
    list of source_ids it is invoked with (no LLM call)."""
    import app.services.signal_summarizer_service as sss

    calls: list = []
    monkeypatch.setattr(
        sss.SignalSummarizerService,
        "record_signal",
        classmethod(lambda cls, source_id, *a, **k: (calls.append(source_id), {"id": "csig"})[1]),
    )
    return calls


def _spy_warnings(monkeypatch) -> list:
    """Spy ``competitor_poll_service.logger.warning`` (caplog caveat)."""
    msgs: list = []
    orig = cps.logger.warning
    monkeypatch.setattr(
        cps.logger, "warning", lambda msg, *a, **k: (msgs.append(msg), orig(msg, *a, **k))[0]
    )
    return msgs


def _snapshot_count(source_id: str) -> int:
    with get_connection() as conn:
        return int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM competitor_snapshot WHERE source_id = ?", (source_id,)
            ).fetchone()["n"]
        )


# ---------------------------------------------------------------------------
# Dispatch + unknown-kind skip.
# ---------------------------------------------------------------------------


def test_dispatches_known_kinds_and_skips_unknown(monkeypatch):
    _spy_record_signal(monkeypatch)
    warnings = _spy_warnings(monkeypatch)
    a1 = _RecordingAdapter("k1")
    a2 = _RecordingAdapter("k2")
    registry.register(a1)
    registry.register(a2)

    s1 = _seed("k1")
    s2 = _seed("k2")
    _seed("totally-unknown-kind")

    changed = CompetitorPollService.poll_due_sources()

    # Both known kinds were fetched; the unknown kind was skipped (not crashed).
    assert s1 in a1.fetched
    assert s2 in a2.fetched
    assert changed == 0  # both returned 'unchanged'
    assert any("no adapter registered for kind" in m for m in warnings)


def test_unknown_kind_logged_once(monkeypatch):
    _spy_record_signal(monkeypatch)
    warnings = _spy_warnings(monkeypatch)
    # Two sources of the SAME unknown kind -> exactly one skip warning for it.
    _seed("mystery", url="https://a.example.com")
    _seed("mystery", url="https://b.example.com")

    CompetitorPollService.poll_due_sources()

    unknown_warns = [m for m in warnings if "no adapter registered for kind" in m]
    assert len(unknown_warns) == 1


# ---------------------------------------------------------------------------
# Per-kind (NOT whole-batch) throttle.
# ---------------------------------------------------------------------------


def test_throttle_is_per_kind_not_whole_batch(monkeypatch):
    _spy_record_signal(monkeypatch)
    _spy_warnings(monkeypatch)
    # k1's FIRST source throttles; k1 has TWO sources; k2 has one.
    k1 = _RecordingAdapter("k1", result=FetchResult(outcome="throttled"))
    k2 = _RecordingAdapter("k2", result=FetchResult(outcome="unchanged"))
    registry.register(k1)
    registry.register(k2)

    k1_a = _seed("k1", url="https://k1a.example.com")
    k1_b = _seed("k1", url="https://k1b.example.com")
    k2_a = _seed("k2", url="https://k2a.example.com")

    CompetitorPollService.poll_due_sources()

    # Exactly ONE k1 fetch (the throttling one); the SECOND k1 source is skipped.
    assert len(k1.fetched) == 1
    assert k1_b not in k1.fetched
    # k2 still polled despite k1 being throttled (independent buckets).
    assert k2_a in k2.fetched
    # Sanity: the first k1 source is the one that fetched.
    assert k1.fetched == [k1_a]


# ---------------------------------------------------------------------------
# Per-source isolation.
# ---------------------------------------------------------------------------


def test_one_raising_source_does_not_stop_the_loop(monkeypatch):
    _spy_record_signal(monkeypatch)
    warnings = _spy_warnings(monkeypatch)
    boom = _RecordingAdapter("kboom", raises=True)
    ok = _RecordingAdapter("kok", result=FetchResult(outcome="unchanged"))
    registry.register(boom)
    registry.register(ok)

    _seed("kboom", url="https://boom.example.com")
    s_ok = _seed("kok", url="https://ok.example.com")

    # Should not raise.
    CompetitorPollService.poll_due_sources()

    assert s_ok in ok.fetched
    assert any("competitor poll raised for source" in m for m in warnings)


# ---------------------------------------------------------------------------
# changed -> commit + record_signal.
# ---------------------------------------------------------------------------


def test_changed_outcome_commits_snapshot_and_records_signal(monkeypatch):
    calls = _spy_record_signal(monkeypatch)
    _spy_warnings(monkeypatch)
    adapter = _RecordingAdapter(
        "kchange",
        result=FetchResult(outcome="changed", raw_ref="new release notes", watermark="w1"),
    )
    registry.register(adapter)
    sid = _seed("kchange", url="https://change.example.com")

    changed = CompetitorPollService.poll_due_sources()

    assert changed == 1
    assert _snapshot_count(sid) == 1
    assert calls == [sid]  # record_signal invoked exactly for the changed source.


def test_changed_but_deduped_does_not_count_or_record(monkeypatch):
    calls = _spy_record_signal(monkeypatch)
    _spy_warnings(monkeypatch)
    sid = _seed("kdedup", url="https://dedup.example.com")
    # Pre-seed an identical-content snapshot so commit dedups.
    AdapterBase().commit(sid, FetchResult(outcome="changed", raw_ref="same", watermark="w0"))

    adapter = _RecordingAdapter(
        "kdedup", result=FetchResult(outcome="changed", raw_ref="same", watermark="w1")
    )
    registry.register(adapter)

    changed = CompetitorPollService.poll_due_sources()

    assert changed == 0  # commit returned None (dedup) -> not counted.
    assert calls == []  # no signal recorded for a non-write.
    assert _snapshot_count(sid) == 1


# ---------------------------------------------------------------------------
# has_credential + poll-floor skips.
# ---------------------------------------------------------------------------


def test_no_credential_adapter_is_never_fetched(monkeypatch):
    _spy_record_signal(monkeypatch)
    _spy_warnings(monkeypatch)
    adapter = _RecordingAdapter("knocred", has_cred=False)
    registry.register(adapter)
    _seed("knocred", url="https://nocred.example.com")

    CompetitorPollService.poll_due_sources()

    assert adapter.fetched == []  # skipped before fetch — never an unauth call.


def test_polled_too_recently_skips_this_tick(monkeypatch):
    _spy_record_signal(monkeypatch)
    _spy_warnings(monkeypatch)
    adapter = _RecordingAdapter("kfloor", floor_s=3600, result=FetchResult(outcome="unchanged"))
    registry.register(adapter)
    sid = _seed("kfloor", url="https://floor.example.com")
    # Stamp last_polled_at to now so it's within the 1h floor.
    with get_connection() as conn:
        conn.execute(
            "UPDATE competitor_source SET last_polled_at = CURRENT_TIMESTAMP WHERE id = ?", (sid,)
        )
        conn.commit()

    CompetitorPollService.poll_due_sources()

    assert adapter.fetched == []  # within floor -> skipped.


def test_floor_zero_always_polls(monkeypatch):
    _spy_record_signal(monkeypatch)
    _spy_warnings(monkeypatch)
    adapter = _RecordingAdapter("kfree", floor_s=0, result=FetchResult(outcome="unchanged"))
    registry.register(adapter)
    sid = _seed("kfree", url="https://free.example.com")
    with get_connection() as conn:
        conn.execute(
            "UPDATE competitor_source SET last_polled_at = CURRENT_TIMESTAMP WHERE id = ?", (sid,)
        )
        conn.commit()

    CompetitorPollService.poll_due_sources()

    assert sid in adapter.fetched  # floor 0 ignores last_polled_at.


def test_polled_too_recently_helper_floor_zero_is_false():
    assert CompetitorPollService._polled_too_recently({"last_polled_at": None}, 0) is False


def test_inactive_sources_are_not_polled(monkeypatch):
    _spy_record_signal(monkeypatch)
    _spy_warnings(monkeypatch)
    adapter = _RecordingAdapter("kinactive", result=FetchResult(outcome="unchanged"))
    registry.register(adapter)
    sid = _seed("kinactive", url="https://inactive.example.com")
    with get_connection() as conn:
        conn.execute("UPDATE competitor_source SET status = 'paused' WHERE id = ?", (sid,))
        conn.commit()

    CompetitorPollService.poll_due_sources()

    assert adapter.fetched == []  # status != 'active' -> excluded by the SELECT.
