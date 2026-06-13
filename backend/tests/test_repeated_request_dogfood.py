"""Live-dogfood replay harness for the repeated-request auto-skill pipeline
(Phase 22, EVAL D1/D2; REQ-22 success criterion 6).

This is the END-TO-END integration test the per-plan unit suites (P1-P4) cannot
be: it drives ≥3 transcripts through the *assembled* loop

    detect_for_session  ->  upsert_signal (signal store)
                        ->  evaluate_signal / convert_signal (gate, AUTO path)
                        ->  scan_skill_content + forge_origin provenance

with the REAL embedding backend (sentence-transformers MiniLM, cosine path —
NOT the hand-crafted fixture-only path), proving the cosine coalescing and the
skill-create dispatch are wired correctly on real text.

Transcript provenance (D1, disclosed in 22-DOGFOOD.md): at execution time the
live ``agented.db`` carried zero session rows (fresh schema), so qualifying
*live* session_ids were not available. Per 22-06-PLAN.md's stated substitution,
this harness replays ≥3 **recorded-real** operator-request transcripts (genuine
wording drawn from this very milestone's GRD execution requests, not synthetic
template strings) captured as module constants. The replay path is identical to
the live path — only the source of the payload text differs. Rerun against a
live DB with the command recorded in 22-DOGFOOD.md once ≥3 real sessions exist.

The evolver skill-create dispatch is mocked so the test is hermetic (no real
plugin file is materialized to disk), exactly as the proven gate suite
(test_repeated_request_gate.py) does; everything else — embedding, cosine
match, UPSERT accumulation, gate routing, scan, origin recording — runs for
real against the isolated DB.
"""

from __future__ import annotations

import json

import pytest

from app.db import repeated_request_signals as rrs
from app.db.connection import get_connection
from app.services import repeated_request_detector as detector
from app.services import repeated_request_gate as gate
from app.services.embedding_service import embed_text
from app.services.harness_failure_annotator import SessionPayload
from app.services.skill_safety_scanner import scan_skill_content

# --- recorded-real transcripts -----------------------------------------------
# Four differently-worded sightings of ONE genuinely recurring operator request
# ("run codex review on the PR until it is clean, then merge") — a real recurring
# ask in this project (see MEMORY: "Always codex-review every PR until green,
# then merge"). Real phrasing variation, not synthetic templating; measured
# pairwise MiniLM cosine 0.92-0.98 (all above the 0.83 Phase-22 threshold), so a
# correct cosine detector coalesces all four into ONE signal. (A looser real
# phrasing — "do a codex review, fix everything it flags until green, then
# merge" — lands at 0.60-0.65 and would intentionally stay a separate signal;
# excluded here so the recurring group is unambiguous.)
RECURRING_REQUESTS: list[str] = [
    "run a codex review on this PR and keep fixing findings until clean, then merge",
    "run codex review on this PR and keep fixing findings until it is clean, then merge it",
    "do a codex review on this PR, keep fixing findings until it is clean, then merge it",
    "review this PR with codex, resolve all the findings until it passes, and then merge",
]

# Two unrelated real requests that must stay as their own signals.
UNRELATED_REQUESTS: list[str] = [
    "write a Korean .ko.md sibling for every prose doc we add",
    "make sure any new LLM feature accepts a backend_kind and model override",
]

_SESSION_KIND = "project_session"
_PROJECT_ID = "proj-dogfood"


def _payload(text: str) -> SessionPayload:
    """Wrap a user-request string in the claude-jsonl shape the live fetchers
    emit, so the replay path is byte-identical to a real session payload."""
    line = json.dumps({"type": "user", "message": {"content": [{"type": "text", "text": text}]}})
    return SessionPayload(
        text=line, backend_type="claude", project_id=_PROJECT_ID, outcome="success"
    )


def _replay(monkeypatch, requests: list[str], *, start: int = 0) -> None:
    """Replay each request through the FULL detector by monkeypatching the
    project_session fetcher to return the recorded payload, exactly as a live
    replay over real session_ids would behave."""
    for i, text in enumerate(requests):
        sid = f"sess-{start + i}"
        monkeypatch.setitem(detector._FETCHERS, _SESSION_KIND, lambda _sid, _t=text: _payload(_t))
        detector.detect_for_session(_SESSION_KIND, sid, _PROJECT_ID)


def _embedding_available() -> bool:
    return embed_text("warm up the embedding backend") is not None


# --- D1: real-cosine end-to-end ----------------------------------------------


def test_recurring_requests_coalesce_to_one_signal_via_cosine(monkeypatch):
    """≥3 recorded-real paraphrases drive ONE signal to occurrence_count ≥ 3 via
    the real MiniLM cosine path; the two unrelated requests stay separate."""
    if not _embedding_available():
        pytest.skip("embedding backend unavailable; covered by A1 fallback test")

    _replay(monkeypatch, RECURRING_REQUESTS, start=0)
    _replay(monkeypatch, UNRELATED_REQUESTS, start=10)

    signals = rrs.list_signals(project_id=_PROJECT_ID)
    # One coalesced recurring signal + two distinct unrelated signals.
    assert len(signals) == 3, [s.occurrence_count for s in signals]
    top = signals[0]  # list_signals orders by occurrence_count DESC
    assert top.occurrence_count >= 3
    assert len(rrs.list_signals(project_id=_PROJECT_ID)) - 1 == 2  # the 2 unrelated


def test_full_pipeline_auto_creates_clean_provenanced_skill(monkeypatch):
    """End-to-end AUTO path: recurring signal (occ≥3) + verified + policy-on ->
    convert_signal creates a skill once, the content passes scan_skill_content,
    and origin_hash is recorded in forge_origin. This is the D1 core assertion."""
    if not _embedding_available():
        pytest.skip("embedding backend unavailable; covered by A1 fallback test")

    # Hermetic skill-create dispatch (mirror test_repeated_request_gate.py).
    from app.services import harness_evolver as ev

    create_calls: list[dict] = []

    def fake_create(*, name, payload, project_id):
        create_calls.append({"name": name, "payload": payload, "project_id": project_id})
        return "dogfood-skill-1"

    monkeypatch.setitem(ev._create_dispatch, "skill", fake_create)

    # Enable per-project auto policy.
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO project_autonomy_config (project_id, enabled, policy_json) "
            "VALUES (?, 1, '{}')",
            (_PROJECT_ID,),
        )
        conn.commit()

    # Drive the signal to occ≥3 through the real detector, then mark verified.
    _replay(monkeypatch, RECURRING_REQUESTS, start=0)
    signal = rrs.list_signals(project_id=_PROJECT_ID)[0]
    assert signal.occurrence_count >= 3
    rrs.increment_verified_success(signal.request_hash, by=1)
    signal = rrs.get_signal(signal.request_hash)

    skill_content = (
        "When asked to land a PR: run `codex review` on the pull request, "
        "fix every finding it reports, re-review until the report is clean, "
        "then merge. Do not merge before the review is green."
    )
    # Skill content must be scan-clean BEFORE we let the gate auto-create it.
    assert scan_skill_content(skill_content).safe is True

    result = gate.convert_signal(
        signal,
        skill_name="codex-review-until-clean-then-merge",
        skill_description="Run codex review on a PR until clean, then merge.",
        skill_content=skill_content,
        scan_safe=True,
        dedup_existing=None,
        provenance_ok=True,
    )

    assert result["route"] == "auto"
    assert result["confidence"] == 0.9
    assert len(create_calls) == 1
    assert result["asset_id"] == "dogfood-skill-1"

    # origin_hash recorded in forge_origin (provenance proven).
    from app.db.forge_origin import get_origin

    assert get_origin("dogfood-skill-1", "skill") is not None
    # signal marked skill_created.
    assert rrs.get_signal(signal.request_hash).skill_created is True


def test_emit_session_complete_does_not_raise(monkeypatch):
    """No exception propagates to the bus caller when a real transcript is
    driven through the registered session-completion handler (P4 live-replay)."""
    monkeypatch.setitem(
        detector._FETCHERS,
        _SESSION_KIND,
        lambda _sid: _payload(RECURRING_REQUESTS[0]),
    )
    from app.services.execution_events import emit_session_complete

    # Must return cleanly even if downstream handlers misbehave.
    emit_session_complete(_SESSION_KIND, "sess-bus", _PROJECT_ID, "success", None)


# --- A1: embedding-disabled fallback (deterministic, no backend) -------------


def test_embed_disabled_falls_back_to_exact_hash(monkeypatch):
    """With embed_text patched to None, verbatim repeats still coalesce on the
    normalized hash while differently-worded paraphrases stay separate. This
    keeps the harness green where the embedding backend is absent."""
    monkeypatch.setattr(detector, "embed_text", lambda _t: None)

    # Three VERBATIM repeats of one request -> one signal, occ == 3.
    verbatim = "rotate the API signing keys every 90 days"
    for i in range(3):
        monkeypatch.setitem(
            detector._FETCHERS, _SESSION_KIND, lambda _sid, _t=verbatim: _payload(_t)
        )
        detector.detect_for_session(_SESSION_KIND, f"v-{i}", _PROJECT_ID)

    h = rrs.normalize_request_hash(verbatim)
    sig = rrs.get_signal(h)
    assert sig is not None
    assert sig.occurrence_count == 3
    assert sig.embedding is None  # no embedding stored in fallback

    # A differently-worded paraphrase stays a SEPARATE signal under exact-hash.
    para = "please rotate the api signing keys on a 90 day schedule"
    monkeypatch.setitem(detector._FETCHERS, _SESSION_KIND, lambda _sid: _payload(para))
    detector.detect_for_session(_SESSION_KIND, "v-para", _PROJECT_ID)
    assert rrs.get_signal(rrs.normalize_request_hash(para)) is not None
    assert len(rrs.list_signals(project_id=_PROJECT_ID)) == 2
