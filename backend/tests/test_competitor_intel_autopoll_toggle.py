"""Tests for the runtime competitor-source SCHEDULED-poll toggle (autopoll).

Mirrors the MonitoringService reconfigure/register/remove contract for the
GLOBAL competitor-intel poll job:

* ``reconfigure({enabled:True, polling_minutes:15})`` saves config AND registers
  the interval job (id ``competitor_intel_poll``) on the scheduler.
* ``reconfigure({enabled:False, ...})`` saves config AND removes the job.
* ``save_competitor_intel_config`` round-trips through
  ``get_competitor_intel_config`` (settings-table upsert, isolated_db).
* the GLOBAL ``/api/competitor-intel/config`` POST route rejects an invalid
  ``polling_minutes``.

The scheduler is monkeypatched to a Mock so NO real scheduled job ever runs —
we assert the add_job/remove_job CALLS, not any execution.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from litestar.testing import create_test_client

import app.services.competitor_poll_service as cps
from app.services.competitor_poll_service import CompetitorPollService
from app.services.github_monitor_service import (
    get_competitor_intel_config,
    save_competitor_intel_config,
)
from app_litestar.auth import provide_caller
from app_litestar.routes.competitor_intel_routes import competitor_intel_config_router


def _patch_scheduler(monkeypatch) -> MagicMock:
    """Install a Mock scheduler so register/remove are observable, nothing runs."""
    scheduler = MagicMock()
    monkeypatch.setattr(cps.CompetitorPollService, "_JOB_ID", "competitor_intel_poll")

    # SchedulerService is imported lazily inside the methods; patch the class attr.
    from app.services import scheduler_service

    monkeypatch.setattr(scheduler_service.SchedulerService, "_scheduler", scheduler)
    return scheduler


# ---------------------------------------------------------------------------
# DB round-trip
# ---------------------------------------------------------------------------


def test_save_config_round_trips(isolated_db):
    """save_competitor_intel_config persists and get_competitor_intel_config reads back."""
    # Default before any save is DISABLED.
    assert get_competitor_intel_config()["enabled"] is False

    save_competitor_intel_config({"enabled": True, "polling_minutes": 30})
    cfg = get_competitor_intel_config()
    assert cfg["enabled"] is True
    assert cfg["polling_minutes"] == 30

    save_competitor_intel_config({"enabled": False, "polling_minutes": 5})
    cfg = get_competitor_intel_config()
    assert cfg["enabled"] is False
    assert cfg["polling_minutes"] == 5


# ---------------------------------------------------------------------------
# reconfigure register / remove
# ---------------------------------------------------------------------------


def test_reconfigure_enabled_registers_job(isolated_db, monkeypatch):
    scheduler = _patch_scheduler(monkeypatch)

    CompetitorPollService.reconfigure({"enabled": True, "polling_minutes": 15})

    # Config persisted.
    assert get_competitor_intel_config()["enabled"] is True
    # Interval job registered with the canonical id.
    assert scheduler.add_job.called
    _, kwargs = scheduler.add_job.call_args
    assert kwargs["id"] == "competitor_intel_poll"
    assert kwargs["trigger"] == "interval"
    assert kwargs["minutes"] == 15
    assert kwargs["func"] is CompetitorPollService.poll_due_sources


def test_reconfigure_disabled_removes_job(isolated_db, monkeypatch):
    scheduler = _patch_scheduler(monkeypatch)
    # Pretend a job already exists so _remove_job calls remove_job.
    scheduler.get_job.return_value = object()

    CompetitorPollService.reconfigure({"enabled": False, "polling_minutes": 15})

    assert get_competitor_intel_config()["enabled"] is False
    scheduler.remove_job.assert_called_once_with("competitor_intel_poll")
    assert not scheduler.add_job.called


def test_register_job_noop_without_scheduler(isolated_db, monkeypatch):
    """No scheduler → _register_job logs + returns, never raises."""
    from app.services import scheduler_service

    monkeypatch.setattr(scheduler_service.SchedulerService, "_scheduler", None)
    # Should not raise even though there is no scheduler.
    CompetitorPollService.reconfigure({"enabled": True, "polling_minutes": 15})
    # Config still saved despite no scheduler.
    assert get_competitor_intel_config()["enabled"] is True


def test_apply_stored_config_registers_when_enabled(isolated_db, monkeypatch):
    """Startup path: read stored config, register when enabled (NO save)."""
    scheduler = _patch_scheduler(monkeypatch)
    save_competitor_intel_config({"enabled": True, "polling_minutes": 60})

    CompetitorPollService.apply_stored_config()

    assert scheduler.add_job.called
    _, kwargs = scheduler.add_job.call_args
    assert kwargs["id"] == "competitor_intel_poll"
    assert kwargs["minutes"] == 60


# ---------------------------------------------------------------------------
# GLOBAL config route
# ---------------------------------------------------------------------------


def _client():
    return create_test_client(
        route_handlers=[competitor_intel_config_router],
        dependencies={"caller": provide_caller},
    )


def test_get_config_route_returns_default(isolated_db):
    with _client() as c:
        resp = c.get("/api/competitor-intel/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is False
    assert "polling_minutes" in body


def test_post_config_route_rejects_invalid_interval(isolated_db, monkeypatch):
    _patch_scheduler(monkeypatch)
    with _client() as c:
        resp = c.post(
            "/api/competitor-intel/config",
            json={"enabled": True, "polling_minutes": 7},
        )
    assert resp.status_code == 400


def test_post_config_route_enables(isolated_db, monkeypatch):
    scheduler = _patch_scheduler(monkeypatch)
    with _client() as c:
        resp = c.post(
            "/api/competitor-intel/config",
            json={"enabled": True, "polling_minutes": 30},
        )
    assert resp.status_code == 201 or resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is True
    assert body["polling_minutes"] == 30
    assert scheduler.add_job.called
    assert get_competitor_intel_config()["enabled"] is True


def test_post_config_route_forbids_non_admin(isolated_db, monkeypatch):
    # The guard must ENFORCE, not just admit admins: a non-admin POST -> 403, and
    # the scheduler is NEVER touched.
    from litestar.di import Provide

    from app_litestar.auth import Caller

    scheduler = _patch_scheduler(monkeypatch)

    def _viewer():
        return Caller(api_key="k", role="viewer", user_id="u1", auth_method="api_key")

    client = create_test_client(
        route_handlers=[competitor_intel_config_router],
        dependencies={"caller": Provide(_viewer, sync_to_thread=False)},
    )
    with client as c:
        resp = c.post(
            "/api/competitor-intel/config",
            json={"enabled": True, "polling_minutes": 15},
        )
    assert resp.status_code == 403
    assert not scheduler.add_job.called


def test_default_llm_backend_is_general_not_claude(isolated_db):
    # Signal summaries + strategy gen default to a GENERAL chat model (gemini),
    # NOT claude — Claude Code refuses these non-coding prompts and degrades.
    from app.services.github_monitor_service import (
        competitor_intel_llm_backend,
        get_competitor_intel_config,
    )

    assert competitor_intel_llm_backend() == "gemini"
    assert get_competitor_intel_config()["llm_backend"] == "gemini"


def test_llm_backend_config_override(isolated_db):
    from app.services.github_monitor_service import (
        competitor_intel_llm_backend,
        save_competitor_intel_config,
    )

    save_competitor_intel_config({"enabled": False, "polling_minutes": 15, "llm_backend": "codex"})
    assert competitor_intel_llm_backend() == "codex"
