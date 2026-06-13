"""Tests for the repeated-request detector (Phase 22, REQ-23 / EVAL P1, A1, P4).

- cosine (P1): three paraphrases -> ONE signal occ=3; two unrelated -> 2 more.
- embed_disabled (A1): embed_text -> None falls back to exact-hash; paraphrases
  stay separate, verbatim repeats coalesce. No crash.
- non_blocking (P4, re-scoped to the bus): a detector that raises does NOT make
  emit_session_complete raise, and a sentinel handler still runs.

``isolated_db`` (autouse, conftest) gives each test a fresh migrated DB.
"""

from __future__ import annotations

import pytest

from app.db.repeated_request_signals import list_signals
from app.services import repeated_request_detector as detector
from app.services.embedding_service import embed_text
from app.services.execution_events import (
    clear_session_handlers,
    emit_session_complete,
    register_session_handler,
)
from app.services.harness_failure_annotator import SessionPayload
from tests.fixtures.repeated_request_transcripts import (
    PARAPHRASES,
    UNRELATED,
    VERBATIM,
    build_payload_text,
)

_EMBED_AVAILABLE = embed_text("smoke test for sentence-transformers") is not None


def _make_fetcher(text_by_id: dict[str, str]):
    def _fetch(session_id: str):
        request = text_by_id.get(session_id)
        if request is None:
            return None
        return SessionPayload(
            text=build_payload_text(request),
            backend_type="claude",
            project_id="proj-test",
            outcome="success",
        )

    return _fetch


def _drive(monkeypatch, requests: list[str], *, kind: str = "project_session"):
    """Run detect_for_session once per request via a monkeypatched fetcher."""
    text_by_id = {f"sess-{i}": r for i, r in enumerate(requests)}
    monkeypatch.setitem(detector._FETCHERS, kind, _make_fetcher(text_by_id))
    for sid in text_by_id:
        detector.detect_for_session(kind, sid, "proj-test")


@pytest.mark.skipif(
    not _EMBED_AVAILABLE,
    reason="sentence-transformers unavailable; cosine path covered only when embedder present",
)
def test_cosine_groups_paraphrases_and_splits_unrelated(monkeypatch):
    # Three paraphrases of one intent.
    _drive(monkeypatch, PARAPHRASES)
    signals = list_signals(project_id="proj-test")
    assert len(signals) == 1, [s.representative_text for s in signals]
    assert signals[0].occurrence_count == 3

    # Two clearly unrelated requests -> two more distinct signals.
    _drive(monkeypatch, UNRELATED)
    signals = list_signals(project_id="proj-test")
    assert len(signals) == 3, [s.representative_text for s in signals]
    # The paraphrase signal stays at 3; each unrelated is its own occ=1.
    counts = sorted(s.occurrence_count for s in signals)
    assert counts == [1, 1, 3]


def test_embed_disabled_falls_back_to_exact_hash(monkeypatch):
    monkeypatch.setattr(detector, "embed_text", lambda _text: None)

    # Two differently-worded requests: no cosine -> two separate signals.
    _drive(monkeypatch, [UNRELATED[0], UNRELATED[1]])
    signals = list_signals(project_id="proj-test")
    assert len(signals) == 2
    assert all(s.embedding is None for s in signals)

    # Two verbatim copies of a fresh request: coalesce onto one signal at occ=2.
    _drive(monkeypatch, [VERBATIM, VERBATIM])
    verbatim_signals = [
        s for s in list_signals(project_id="proj-test") if s.representative_text == VERBATIM
    ]
    assert len(verbatim_signals) == 1
    assert verbatim_signals[0].occurrence_count == 2


def test_detector_exception_does_not_escape_bus(monkeypatch):
    clear_session_handlers()
    try:
        ran: list[str] = []

        def _boom(session_kind, session_id, project_id, status, output):
            raise RuntimeError("detector blew up")

        def _sentinel(session_kind, session_id, project_id, status, output):
            ran.append(session_id)

        register_session_handler(_boom)
        register_session_handler(_sentinel)

        # Must NOT raise despite _boom raising, and the sentinel still runs.
        emit_session_complete("project_session", "sess-x", "proj-test", "success", None)

        assert ran == ["sess-x"]
    finally:
        clear_session_handlers()
