"""UPSERT-invariant suite for the repeated_request_signals store (Phase 22, S4).

Verifies the core promise of the self-improvement substrate: salience
*accumulates* with repetition rather than decaying.

- first_seen_at is preserved across UPSERTs (set once on the original insert).
- occurrence_count grows monotonically (+1 per upsert), last_seen_at advances.
- example_session_ids is FIFO-capped at 5 (oldest distinct id dropped).
- embedding round-trips through serialize/deserialize.
- skill_created and verified_success_count are mutable via repo helpers.

Uses the autouse ``isolated_db`` fixture (conftest.py) → init_db() builds a
fresh schema in a temp DB.
"""

from __future__ import annotations

from app.db import repeated_request_signals as repo


def _upsert(session_id: str, *, embedding=None, now=None, text="deploy the app"):
    repo.upsert_signal(
        request_hash=repo.normalize_request_hash(text),
        project_id="proj-abc123",
        session_kind="trigger_execution",
        representative_text=text,
        embedding=embedding,
        session_id=session_id,
        now=now,
    )


def test_normalize_request_hash_is_stable_and_collapses_whitespace():
    a = repo.normalize_request_hash("  Deploy   the\tApp  ")
    b = repo.normalize_request_hash("deploy the app")
    assert a == b
    assert len(a) == 64  # sha256 hexdigest
    assert a != repo.normalize_request_hash("deploy the other app")


def test_first_upsert_sets_count_one_and_first_seen():
    _upsert("sess-1", now="2026-01-01T00:00:00Z")
    sig = repo.get_signal(repo.normalize_request_hash("deploy the app"))
    assert sig is not None
    assert sig.occurrence_count == 1
    assert sig.first_seen_at == "2026-01-01T00:00:00Z"
    assert sig.last_seen_at == "2026-01-01T00:00:00Z"
    assert sig.example_session_ids == ["sess-1"]


def test_repeated_upserts_accumulate_and_preserve_first_seen():
    _upsert("sess-1", now="2026-01-01T00:00:00Z")
    _upsert("sess-2", now="2026-01-02T00:00:00Z")
    _upsert("sess-3", now="2026-01-03T00:00:00Z")

    sig = repo.get_signal(repo.normalize_request_hash("deploy the app"))
    assert sig.occurrence_count == 3
    # first_seen_at NEVER overwritten by the ON CONFLICT branch
    assert sig.first_seen_at == "2026-01-01T00:00:00Z"
    # last_seen_at advances every upsert
    assert sig.last_seen_at == "2026-01-03T00:00:00Z"


def test_example_session_ids_fifo_capped_at_five():
    for i in range(1, 7):  # 6 distinct ids
        _upsert(f"sess-{i}", now=f"2026-01-0{i}T00:00:00Z")
    sig = repo.get_signal(repo.normalize_request_hash("deploy the app"))
    # exactly the 5 most-recent; oldest (sess-1) dropped
    assert sig.example_session_ids == ["sess-2", "sess-3", "sess-4", "sess-5", "sess-6"]
    assert sig.occurrence_count == 6


def test_duplicate_session_id_not_appended_twice():
    _upsert("sess-1", now="2026-01-01T00:00:00Z")
    _upsert("sess-1", now="2026-01-02T00:00:00Z")
    sig = repo.get_signal(repo.normalize_request_hash("deploy the app"))
    assert sig.example_session_ids == ["sess-1"]
    assert sig.occurrence_count == 2


def test_embedding_round_trips():
    emb = [float(i) / 384.0 for i in range(384)]
    _upsert("sess-1", embedding=emb, now="2026-01-01T00:00:00Z")
    sig = repo.get_signal(repo.normalize_request_hash("deploy the app"))
    assert sig.embedding is not None
    assert len(sig.embedding) == 384
    for got, want in zip(sig.embedding, emb):
        assert abs(got - want) < 1e-6


def test_embedding_none_stays_none():
    _upsert("sess-1", embedding=None, now="2026-01-01T00:00:00Z")
    sig = repo.get_signal(repo.normalize_request_hash("deploy the app"))
    assert sig.embedding is None


def test_mark_skill_created_flips_flag():
    h = repo.normalize_request_hash("deploy the app")
    _upsert("sess-1", now="2026-01-01T00:00:00Z")
    assert repo.get_signal(h).skill_created is False
    repo.mark_skill_created(h)
    assert repo.get_signal(h).skill_created is True


def test_increment_verified_success_count():
    h = repo.normalize_request_hash("deploy the app")
    _upsert("sess-1", now="2026-01-01T00:00:00Z")
    assert repo.get_signal(h).verified_success_count == 0
    repo.increment_verified_success(h)
    repo.increment_verified_success(h, by=2)
    assert repo.get_signal(h).verified_success_count == 3


def test_get_signal_missing_returns_none():
    assert repo.get_signal("nonexistent-hash") is None


def test_list_signals_filters_by_project_and_kind():
    repo.upsert_signal(
        request_hash=repo.normalize_request_hash("a"),
        project_id="proj-1",
        session_kind="trigger_execution",
        representative_text="a",
        embedding=None,
        session_id="s1",
        now="2026-01-01T00:00:00Z",
    )
    repo.upsert_signal(
        request_hash=repo.normalize_request_hash("b"),
        project_id="proj-2",
        session_kind="team_session",
        representative_text="b",
        embedding=None,
        session_id="s2",
        now="2026-01-01T00:00:00Z",
    )
    assert len(repo.list_signals()) == 2
    assert {s.representative_text for s in repo.list_signals(project_id="proj-1")} == {"a"}
    assert {s.representative_text for s in repo.list_signals(session_kind="team_session")} == {"b"}
