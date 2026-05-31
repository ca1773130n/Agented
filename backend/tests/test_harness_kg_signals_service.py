"""Tests for the Phase E2 KG signal gathering service."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services import harness_kg_signals as svc
from app.services.harness_kg_signals import (
    _DISCOVERY_QUESTIONS,
    _TS_FMT,
    W_MAX,
    W_MIN,
    _compute_signal_id,
    _is_already_forged,
    _norm,
    compute_weight,
    gather_kg_signals,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _ts(dt: datetime) -> str:
    return dt.strftime(_TS_FMT)


def _enable_tesserae(monkeypatch, *, root="/tmp/tess") -> None:
    monkeypatch.setattr(svc, "get_tesserae_root", lambda pid: root)


def _set_ask(monkeypatch, fake) -> None:
    monkeypatch.setattr(svc, "ask_tesserae", fake)


# ---------------------------------------------------------------------------
# _norm
# ---------------------------------------------------------------------------


def test_norm_collapses_whitespace_and_lowercases():
    assert _norm("  HeLLo\t\n  World  ") == "hello world"
    assert _norm("A   B") == "a b"


# ---------------------------------------------------------------------------
# compute_weight
# ---------------------------------------------------------------------------


def test_compute_weight_first_equals_now_is_max():
    now = "2026-05-30 12:00:00"
    assert compute_weight(now, now) == W_MAX


def test_compute_weight_30_days_half():
    now = datetime(2026, 5, 30, 12, 0, 0)
    first = now - timedelta(days=30)
    w = compute_weight(_ts(first), _ts(now))
    # half-life 30d => W_MAX/2 == 0.35, still within [0.3, 0.7)
    assert W_MIN <= w < W_MAX
    assert abs(w - 0.35) < 1e-6


def test_compute_weight_60_days_floor():
    now = datetime(2026, 5, 30, 12, 0, 0)
    first = now - timedelta(days=60)
    assert compute_weight(_ts(first), _ts(now)) == W_MIN


def test_compute_weight_unparseable_returns_max():
    assert compute_weight("not-a-timestamp", "2026-05-30 12:00:00") == W_MAX
    assert compute_weight("2026-05-30 12:00:00", "garbage") == W_MAX


def test_compute_weight_future_first_clamped_to_max():
    now = datetime(2026, 5, 30, 12, 0, 0)
    future = now + timedelta(days=5)
    assert compute_weight(_ts(future), _ts(now)) == W_MAX


# ---------------------------------------------------------------------------
# _is_already_forged
# ---------------------------------------------------------------------------


def test_is_already_forged_short_strings_no_false_positive():
    assert _is_already_forged("abc", ["abc"]) is False
    assert _is_already_forged("short text", ["short text", ""]) is False
    assert _is_already_forged("", ["whatever"]) is False
    assert _is_already_forged("anything", None) is False


def test_is_already_forged_long_shared_slice_matches():
    # The matcher checks the *prefix* of the shorter string against the longer,
    # so the shared region must lead. forged (shorter) leads with `shared`;
    # content (longer) contains it after a prefix.
    shared = "always run the full pytest suite before declaring any task complete"
    assert len(shared) >= 60
    forged = [shared]
    content = _norm("intro note: " + shared + " and then some more trailing text here")
    assert _is_already_forged(content, forged) is True


# ---------------------------------------------------------------------------
# gather_kg_signals
# ---------------------------------------------------------------------------


def test_gather_returns_empty_when_tesserae_disabled(monkeypatch):
    monkeypatch.setattr(svc, "get_tesserae_root", lambda pid: None)
    called = {"n": 0}

    def fake_ask(*a, **k):
        called["n"] += 1
        return "x"

    _set_ask(monkeypatch, fake_ask)
    assert gather_kg_signals("proj-1") == []
    assert called["n"] == 0


def test_gather_happy_path_three_items(monkeypatch, isolated_db):
    _enable_tesserae(monkeypatch)
    answers = iter([f"distinct answer number {i}" for i in range(3)])
    _set_ask(monkeypatch, lambda pid, q, *, top_k=5: next(answers))
    now = "2026-05-30 12:00:00"
    items = gather_kg_signals("proj-happy", now=now)
    assert len(items) == 3
    for it in items:
        assert it.weight == W_MAX
        assert it.already_forged is False
        assert it.first_seen_at == now
        assert it.captured_at == now
    assert {it.question for it in items} == set(_DISCOVERY_QUESTIONS)


def test_gather_decay_clamped_to_floor(monkeypatch, isolated_db):
    from app.db.harness_kg_signals import record_signal

    _enable_tesserae(monkeypatch)
    now_dt = datetime(2026, 5, 30, 12, 0, 0, tzinfo=timezone.utc)
    now = now_dt.strftime(_TS_FMT)
    old = (now_dt - timedelta(days=60)).strftime(_TS_FMT)

    q = _DISCOVERY_QUESTIONS[0]
    content = "recurring decay content for the floor test"
    sid = _compute_signal_id("proj-decay", q, content)
    # pre-seed with an OLD first_seen_at
    record_signal(
        signal_id=sid,
        project_id="proj-decay",
        question=q,
        content=content,
        weight=W_MAX,
        already_forged=False,
        now=old,
    )

    def fake_ask(pid, question, *, top_k=5):
        return content if question == q else None

    _set_ask(monkeypatch, fake_ask)
    items = gather_kg_signals("proj-decay", now=now)
    assert len(items) == 1
    it = items[0]
    assert W_MIN <= it.weight < W_MAX
    assert it.weight == W_MIN
    assert it.first_seen_at == old


def test_gather_already_forged_sets_floor(monkeypatch, isolated_db):
    _enable_tesserae(monkeypatch)
    # forged entry (shorter) leads with the shared text; its 60-char prefix
    # appears inside the longer answer => overlap.
    shared = "never pkill vite or node the just kill recipe must stay port scoped"
    assert len(shared) >= 60
    answer = shared + " and additional explanatory trailing context here to lengthen it"

    def fake_ask(pid, question, *, top_k=5):
        return answer if question == _DISCOVERY_QUESTIONS[0] else None

    _set_ask(monkeypatch, fake_ask)
    items = gather_kg_signals("proj-forged", forged_index=[shared], now="2026-05-30 12:00:00")
    assert len(items) == 1
    assert items[0].already_forged is True
    assert items[0].weight == W_MIN


def test_gather_skips_none_answer(monkeypatch, isolated_db):
    _enable_tesserae(monkeypatch)

    def fake_ask(pid, question, *, top_k=5):
        if question == _DISCOVERY_QUESTIONS[1]:
            return None
        return f"answer for {question[:10]}"

    _set_ask(monkeypatch, fake_ask)
    items = gather_kg_signals("proj-skip", now="2026-05-30 12:00:00")
    assert len(items) == 2
    assert _DISCOVERY_QUESTIONS[1] not in {it.question for it in items}


def test_gather_survives_ask_exception(monkeypatch, isolated_db):
    _enable_tesserae(monkeypatch)

    def fake_ask(pid, question, *, top_k=5):
        if question == _DISCOVERY_QUESTIONS[0]:
            raise RuntimeError("boom")
        return f"ok {question[:8]}"

    _set_ask(monkeypatch, fake_ask)
    items = gather_kg_signals("proj-exc", now="2026-05-30 12:00:00")
    assert len(items) == 2
    assert _DISCOVERY_QUESTIONS[0] not in {it.question for it in items}


def test_gather_skips_blank_answer(monkeypatch, isolated_db):
    _enable_tesserae(monkeypatch)

    def fake_ask(pid, question, *, top_k=5):
        if question == _DISCOVERY_QUESTIONS[2]:
            return "   \n\t  "
        return f"content {question[:8]}"

    _set_ask(monkeypatch, fake_ask)
    items = gather_kg_signals("proj-blank", now="2026-05-30 12:00:00")
    assert len(items) == 2
    assert _DISCOVERY_QUESTIONS[2] not in {it.question for it in items}


def test_gather_survives_record_signal_exception_on_one_signal(monkeypatch, isolated_db):
    _enable_tesserae(monkeypatch)
    answers = iter([f"distinct answer number {i}" for i in range(3)])
    _set_ask(monkeypatch, lambda pid, q, *, top_k=5: next(answers))

    calls = {"n": 0}

    def flaky_record(**kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("db write boom")

    monkeypatch.setattr(svc, "record_signal", flaky_record)

    # A failed write on the SECOND question must skip only that signal,
    # not abort the whole round — q1 and q3 still survive.
    items = gather_kg_signals("proj-flaky", now="2026-05-30 12:00:00")
    assert len(items) == 2
    assert calls["n"] == 3


def test_gather_never_raises_on_unexpected_error(monkeypatch):
    def boom(pid):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(svc, "get_tesserae_root", boom)
    assert gather_kg_signals("proj-boom") == []
