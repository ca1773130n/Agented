"""Competitor-strategy HITL route shape tests (26-03 — the P4 strategy loop).

Exercises the project-scoped ``/api/projects/{id}/strategies/*`` router through a
Litestar TestClient against an ``isolated_db`` (migration 174 applies, so the
``competitor_strategy`` table exists; 171 gives ``competitor_source`` +
``detected_signal`` for the generate seed).

NO live LLM: ``CompetitorStrategyService.propose`` is monkeypatched to canned data
(it persists a real ``competitor_strategy`` via the 26-01 DAO so the queue read +
verdict + legal flips run end-to-end). The other routes drive the REAL DAO.

Per CLAUDE.md the TestClient logger doesn't propagate to caplog, so the IDOR guard
is asserted by status code (404, not 403 — the P1 lesson), mirroring
``test_discovery_routes`` (monkeypatch ``routes.can_access → False``). The §5B
legal gate lives in the DAO; here we assert the route RECORDS items and surfaces
``legal_cleared_at`` at 7/7 — it never bypasses the gate.
"""

import pytest
from litestar.testing import create_test_client

from app.database import get_connection
from app.db import competitor_strategies as dao
from app.db.competitor_strategies import LEGAL_CHECKLIST_ITEMS
from app.db.ids import generate_id
from app.db.projects import create_project
from app.services.competitor_source_service import CompetitorSourceService
from app_litestar.auth import provide_caller
from app_litestar.routes.competitor_strategy_routes import strategy_router


def _client():
    return create_test_client(
        route_handlers=[strategy_router],
        dependencies={"caller": provide_caller},
    )


def _seed_project_with_signals(*, name="ci-strategy-proj"):
    """Create a project + one competitor_source + 2 detected_signal rows under it.

    Returns ``(project_id, source_id, [signal_ids])``.
    """
    project_id = create_project(name=name)
    source = CompetitorSourceService.add_source(project_id, "https://github.com/acme/widget")
    source_id = source["id"]
    signal_ids = []
    with get_connection() as conn:
        for i, summary in enumerate(("ACME shipped X", "ACME shipped Y")):
            sid = generate_id("csig-", 6)
            conn.execute(
                """
                INSERT INTO detected_signal
                    (id, source_id, summary, signal_type, score, created_at)
                VALUES (?, ?, ?, 'release', ?, CURRENT_TIMESTAMP)
                """,
                (sid, source_id, summary, 0.9 - i * 0.1),
            )
            signal_ids.append(sid)
        conn.commit()
    return project_id, source_id, signal_ids


def _affirm_all_legal(client, project_id, sid):
    """Affirm all 7 §5B items via the route; return the last response body."""
    resp = None
    for item in LEGAL_CHECKLIST_ITEMS:
        resp = client.post(
            f"/api/projects/{project_id}/strategies/{sid}/legal",
            json={"item_key": item, "value": True},
        )
    return resp


# ---------------------------------------------------------------------------
# POST /strategies/generate — LLM (mocked), persists a 'proposed' strategy
# ---------------------------------------------------------------------------


def test_generate_returns_proposed_strategy(isolated_db, monkeypatch):
    """POST /generate delegates to propose (mocked) and returns a persisted row."""
    import app_litestar.routes.competitor_strategy_routes as routes

    project_id, _src, signal_ids = _seed_project_with_signals()
    captured = {}

    def fake_propose(pid, sids, *, backend_kind="claude", model_override=None):
        captured["pid"] = pid
        captured["sids"] = sids
        captured["backend_kind"] = backend_kind
        row = dao.create_strategy(
            pid,
            signal_ids=sids,
            title="Our own turbo path",
            body="Build a fast lane in our own words.",
            backend_kind=backend_kind,
            model="m",
        )
        row["degraded"] = False
        return row

    monkeypatch.setattr(routes.CompetitorStrategyService, "propose", staticmethod(fake_propose))

    with _client() as c:
        resp = c.post(
            f"/api/projects/{project_id}/strategies/generate",
            json={"signal_ids": signal_ids},
        )
    assert resp.status_code == 201
    strategy = resp.json()["strategy"]
    assert strategy["status"] == "proposed"
    assert strategy["legal_cleared_at"] is None
    assert captured["pid"] == project_id
    assert captured["sids"] == signal_ids
    # No backend_kind in the request -> the route falls back to the competitor-intel
    # default (gemini, a general model), NOT claude (Claude Code refuses these prompts).
    assert captured["backend_kind"] == "gemini"
    # Persisted: the queue read returns it.
    rows = dao.list_strategies(project_id)
    assert len(rows) == 1
    assert rows[0]["id"] == strategy["id"]


def test_generate_passes_backend_and_model_overrides(isolated_db, monkeypatch):
    """Optional backend_kind / model_override are forwarded (multi-backend)."""
    import app_litestar.routes.competitor_strategy_routes as routes

    project_id, _src, signal_ids = _seed_project_with_signals()
    captured = {}

    def fake_propose(pid, sids, *, backend_kind="claude", model_override=None):
        captured["backend_kind"] = backend_kind
        captured["model_override"] = model_override
        return dao.create_strategy(pid, signal_ids=sids, title="t", body="b")

    monkeypatch.setattr(routes.CompetitorStrategyService, "propose", staticmethod(fake_propose))

    with _client() as c:
        resp = c.post(
            f"/api/projects/{project_id}/strategies/generate",
            json={
                "signal_ids": signal_ids,
                "backend_kind": "codex",
                "model_override": "gpt-5.4-mini",
            },
        )
    assert resp.status_code == 201
    assert captured["backend_kind"] == "codex"
    assert captured["model_override"] == "gpt-5.4-mini"


def test_generate_missing_signal_ids_400(isolated_db):
    project_id = create_project(name="empty-proj")
    with _client() as c:
        resp = c.post(f"/api/projects/{project_id}/strategies/generate", json={})
    assert resp.status_code == 400


def test_generate_value_error_400(isolated_db, monkeypatch):
    """A service ValueError (e.g. foreign signal id) maps to 400, not 500."""
    import app_litestar.routes.competitor_strategy_routes as routes

    project_id, _src, signal_ids = _seed_project_with_signals()

    def boom(*a, **k):
        raise ValueError("foreign signal id")

    monkeypatch.setattr(routes.CompetitorStrategyService, "propose", staticmethod(boom))
    with _client() as c:
        resp = c.post(
            f"/api/projects/{project_id}/strategies/generate",
            json={"signal_ids": signal_ids},
        )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /strategies — project-scoped, newest first
# ---------------------------------------------------------------------------


def test_list_strategies_newest_first_and_scoped(isolated_db):
    project_a = create_project(name="proj-a")
    project_b = create_project(name="proj-b")
    first = dao.create_strategy(project_a, title="first")
    second = dao.create_strategy(project_a, title="second")
    dao.create_strategy(project_b, title="theirs")

    with _client() as c:
        resp = c.get(f"/api/projects/{project_a}/strategies")
    assert resp.status_code == 200
    rows = resp.json()["strategies"]
    assert [r["id"] for r in rows] == [second["id"], first["id"]]
    assert all(r["project_id"] == project_a for r in rows)


# ---------------------------------------------------------------------------
# approve / reject — status flips
# ---------------------------------------------------------------------------


def test_approve_flips_proposed_to_approved(isolated_db):
    project_id = create_project(name="p")
    st = dao.create_strategy(project_id, title="t")
    with _client() as c:
        resp = c.post(f"/api/projects/{project_id}/strategies/{st['id']}/approve")
    assert resp.status_code == 201
    assert resp.json()["strategy"]["status"] == "approved"


def test_reject_flips_to_rejected(isolated_db):
    project_id = create_project(name="p")
    st = dao.create_strategy(project_id, title="t")
    with _client() as c:
        resp = c.post(f"/api/projects/{project_id}/strategies/{st['id']}/reject")
    assert resp.status_code == 201
    assert resp.json()["strategy"]["status"] == "rejected"


def test_approve_illegal_transition_400(isolated_db):
    """Approving an already-rejected strategy → 400 (illegal transition)."""
    project_id = create_project(name="p")
    st = dao.create_strategy(project_id, title="t")
    dao.set_status(st["id"], "rejected")
    with _client() as c:
        resp = c.post(f"/api/projects/{project_id}/strategies/{st['id']}/approve")
    assert resp.status_code == 400


def test_approve_unknown_strategy_404(isolated_db):
    project_id = create_project(name="p")
    with _client() as c:
        resp = c.post(f"/api/projects/{project_id}/strategies/cstr-missing/approve")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# edit — updates body AND resets legal clearance
# ---------------------------------------------------------------------------


def test_edit_updates_body_and_resets_clearance(isolated_db):
    """A prior 7/7 clear is wiped by an edit (§5B edit-resets-clearance)."""
    project_id = create_project(name="p")
    st = dao.create_strategy(project_id, title="t", body="old")
    # Clear all 7 items first.
    for item in LEGAL_CHECKLIST_ITEMS:
        dao.record_legal_item(st["id"], item, True)
    assert dao.get_strategy(st["id"])["legal_cleared_at"] is not None

    with _client() as c:
        resp = c.post(
            f"/api/projects/{project_id}/strategies/{st['id']}/edit",
            json={"body": "new body"},
        )
    assert resp.status_code == 201
    updated = resp.json()["strategy"]
    assert updated["body"] == "new body"
    # Edit reset the gate.
    assert updated["legal_cleared_at"] is None
    assert updated["legal_checklist"]["independent_authorship"] is False
    assert updated["legal_checklist"]["no_copied_code"] is False


def test_edit_unknown_strategy_404(isolated_db):
    project_id = create_project(name="p")
    with _client() as c:
        resp = c.post(
            f"/api/projects/{project_id}/strategies/cstr-missing/edit",
            json={"body": "x"},
        )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# legal — records items; clears at 7/7; unknown item → 400
# ---------------------------------------------------------------------------


def test_legal_records_item_and_clears_at_seven(isolated_db):
    project_id = create_project(name="p")
    st = dao.create_strategy(project_id, title="t")

    with _client() as c:
        # One item: recorded but NOT cleared.
        resp = c.post(
            f"/api/projects/{project_id}/strategies/{st['id']}/legal",
            json={"item_key": LEGAL_CHECKLIST_ITEMS[0], "value": True},
        )
        assert resp.status_code == 201
        body = resp.json()["strategy"]
        assert body["legal_checklist"][LEGAL_CHECKLIST_ITEMS[0]] is True
        assert body["legal_cleared_at"] is None

        # Affirm all 7 → cleared.
        final = _affirm_all_legal(c, project_id, st["id"])
    assert final.json()["strategy"]["legal_cleared_at"] is not None


def test_legal_unknown_item_400(isolated_db):
    project_id = create_project(name="p")
    st = dao.create_strategy(project_id, title="t")
    with _client() as c:
        resp = c.post(
            f"/api/projects/{project_id}/strategies/{st['id']}/legal",
            json={"item_key": "not_a_real_item", "value": True},
        )
    assert resp.status_code == 400


def test_legal_missing_item_key_400(isolated_db):
    project_id = create_project(name="p")
    st = dao.create_strategy(project_id, title="t")
    with _client() as c:
        resp = c.post(
            f"/api/projects/{project_id}/strategies/{st['id']}/legal",
            json={"value": True},
        )
    assert resp.status_code == 400


@pytest.mark.parametrize("junk", ["false", "0", "no", "true", 0, 1, "yes", None])
def test_legal_non_boolean_value_400_and_gate_uncleared(isolated_db, junk):
    """§5B gate-bypass guard: a non-boolean ``value`` is rejected (400), so a
    caller cannot 'affirm' all 7 items with truthy junk. The item is never
    recorded and ``legal_cleared_at`` stays NULL."""
    project_id = create_project(name="p")
    st = dao.create_strategy(project_id, title="t")
    with _client() as c:
        resp = c.post(
            f"/api/projects/{project_id}/strategies/{st['id']}/legal",
            json={"item_key": LEGAL_CHECKLIST_ITEMS[0], "value": junk},
        )
        assert resp.status_code == 400
    # nothing was affirmed; the gate is still uncleared
    assert dao.get_strategy(st["id"])["legal_cleared_at"] is None


def test_legal_unknown_strategy_404(isolated_db):
    project_id = create_project(name="p")
    with _client() as c:
        resp = c.post(
            f"/api/projects/{project_id}/strategies/cstr-missing/legal",
            json={"item_key": LEGAL_CHECKLIST_ITEMS[0], "value": True},
        )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# SCOPE — a {sid} from project A accessed under project B's path → 404
# ---------------------------------------------------------------------------


def test_cross_project_sid_404(isolated_db):
    """A strategy seeded under A, mutated via B's path → 404 (scope guard)."""
    project_a = create_project(name="proj-a")
    project_b = create_project(name="proj-b")
    st = dao.create_strategy(project_a, title="A's strategy")

    with _client() as c:
        assert c.post(f"/api/projects/{project_b}/strategies/{st['id']}/approve").status_code == 404
        assert c.post(f"/api/projects/{project_b}/strategies/{st['id']}/reject").status_code == 404
        assert (
            c.post(
                f"/api/projects/{project_b}/strategies/{st['id']}/edit",
                json={"body": "x"},
            ).status_code
            == 404
        )
        assert (
            c.post(
                f"/api/projects/{project_b}/strategies/{st['id']}/legal",
                json={"item_key": LEGAL_CHECKLIST_ITEMS[0], "value": True},
            ).status_code
            == 404
        )
    # The strategy under A is untouched.
    assert dao.get_strategy(st["id"])["status"] == "proposed"


# ---------------------------------------------------------------------------
# IDOR — a caller without project access gets 404 (NOT 403) on EVERY route
# ---------------------------------------------------------------------------


def test_every_route_404s_for_inaccessible_project(isolated_db, monkeypatch):
    """The P1 IDOR lesson: a project the caller can't access → 404 on every route."""
    import app_litestar.routes.competitor_strategy_routes as routes

    project_id = create_project(name="owned-by-someone-else")
    st = dao.create_strategy(project_id, title="t")
    monkeypatch.setattr(routes, "can_access", lambda *a, **k: False)

    with _client() as c:
        assert (
            c.post(
                f"/api/projects/{project_id}/strategies/generate",
                json={"signal_ids": ["x"]},
            ).status_code
            == 404
        )
        assert c.get(f"/api/projects/{project_id}/strategies").status_code == 404
        assert (
            c.post(f"/api/projects/{project_id}/strategies/{st['id']}/approve").status_code == 404
        )
        assert c.post(f"/api/projects/{project_id}/strategies/{st['id']}/reject").status_code == 404
        assert (
            c.post(
                f"/api/projects/{project_id}/strategies/{st['id']}/edit",
                json={"body": "x"},
            ).status_code
            == 404
        )
        assert (
            c.post(
                f"/api/projects/{project_id}/strategies/{st['id']}/legal",
                json={"item_key": LEGAL_CHECKLIST_ITEMS[0], "value": True},
            ).status_code
            == 404
        )

    # The guard short-circuited BEFORE any mutation.
    assert dao.get_strategy(st["id"])["status"] == "proposed"
    assert dao.get_strategy(st["id"])["legal_cleared_at"] is None


# ---------------------------------------------------------------------------
# POST /strategies/{sid}/autoimplement — the TRIPLE-GATED auto-code route
# ---------------------------------------------------------------------------


def _seed_cleared_strategy(project_id, *, name_prefix=""):
    """Seed an approved + 7/7 §5B-cleared strategy. Returns sid."""
    st = dao.create_strategy(project_id, title=f"{name_prefix}strategy", body="behavior-only")
    sid = st["id"]
    for item in LEGAL_CHECKLIST_ITEMS:
        dao.record_legal_item(sid, item, True, project_id=project_id)
    dao.set_status(sid, "approved", project_id=project_id)
    return sid


def test_autoimplement_flag_off_403(isolated_db, monkeypatch):
    """Flag off (default) → 403, NO session."""
    monkeypatch.delenv("AGENTED_STRATEGY_AUTOIMPLEMENT", raising=False)
    project_id = create_project(name="ai-route-off")
    sid = _seed_cleared_strategy(project_id)
    with _client() as c:
        resp = c.post(
            f"/api/projects/{project_id}/strategies/{sid}/autoimplement",
            json={"confirm_token": "yes"},
        )
    assert resp.status_code == 403


def test_autoimplement_no_confirm_400(isolated_db, monkeypatch):
    """Flag on + cleared but no confirm_token → 400."""
    monkeypatch.setenv("AGENTED_STRATEGY_AUTOIMPLEMENT", "1")
    project_id = create_project(name="ai-route-noconfirm")
    sid = _seed_cleared_strategy(project_id)
    with _client() as c:
        resp = c.post(
            f"/api/projects/{project_id}/strategies/{sid}/autoimplement",
            json={},
        )
    assert resp.status_code == 400


def test_autoimplement_not_materialized_409(isolated_db, monkeypatch):
    """Flag on + cleared + confirm but no plan_id → 409 not_materialized."""
    monkeypatch.setenv("AGENTED_STRATEGY_AUTOIMPLEMENT", "1")
    project_id = create_project(name="ai-route-unmat")
    sid = _seed_cleared_strategy(project_id)
    with _client() as c:
        resp = c.post(
            f"/api/projects/{project_id}/strategies/{sid}/autoimplement",
            json={"confirm_token": "yes"},
        )
    assert resp.status_code == 409


def test_autoimplement_started_returns_session_id(isolated_db, monkeypatch):
    """All gates pass + materialized → 200 {session_id} from the goal-loop launch."""
    monkeypatch.setenv("AGENTED_STRATEGY_AUTOIMPLEMENT", "1")
    project_id = create_project(name="ai-route-started")
    sid = _seed_cleared_strategy(project_id)
    # Stamp a plan_id so the strategy is materialized.
    with get_connection() as conn:
        conn.execute("UPDATE competitor_strategy SET plan_id = 'plan-fake1' WHERE id = ?", (sid,))
        conn.commit()

    # Stub the service launch to a started result (the wired-path mechanics are
    # covered by the service-level test; here we assert the route maps it to 200).
    from app.services.competitor_strategy_service import CompetitorStrategyService

    monkeypatch.setattr(
        CompetitorStrategyService,
        "start_autoimplement",
        classmethod(
            lambda cls, pid, s, *, confirm_token=None: {
                "status": "started",
                "session_id": "psess-route1",
                "plan_id": "plan-fake1",
                "worktree_path": "/tmp/wt",
            }
        ),
    )
    with _client() as c:
        resp = c.post(
            f"/api/projects/{project_id}/strategies/{sid}/autoimplement",
            json={"confirm_token": "yes"},
        )
    assert resp.status_code in (200, 201)
    assert resp.json()["session_id"] == "psess-route1"


def test_autoimplement_cross_project_sid_404(isolated_db, monkeypatch):
    """A strategy from A reached via B's path → 404 (scope guard)."""
    monkeypatch.setenv("AGENTED_STRATEGY_AUTOIMPLEMENT", "1")
    project_a = create_project(name="ai-route-a")
    project_b = create_project(name="ai-route-b")
    sid = _seed_cleared_strategy(project_a)
    with _client() as c:
        resp = c.post(
            f"/api/projects/{project_b}/strategies/{sid}/autoimplement",
            json={"confirm_token": "yes"},
        )
    assert resp.status_code == 404


def test_autoimplement_idor_404(isolated_db, monkeypatch):
    """Caller without project access → 404 (NOT 403), even with the flag on."""
    monkeypatch.setenv("AGENTED_STRATEGY_AUTOIMPLEMENT", "1")
    import app_litestar.routes.competitor_strategy_routes as routes

    project_id = create_project(name="ai-route-idor")
    sid = _seed_cleared_strategy(project_id)
    monkeypatch.setattr(routes, "can_access", lambda *a, **k: False)
    with _client() as c:
        resp = c.post(
            f"/api/projects/{project_id}/strategies/{sid}/autoimplement",
            json={"confirm_token": "yes"},
        )
    assert resp.status_code == 404
