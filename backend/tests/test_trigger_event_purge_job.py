"""v0.7.1: scheduler purge job hits trigger_event_service.purge_older_than."""

from unittest.mock import patch


def test_purge_job_uses_retention_env(monkeypatch):
    monkeypatch.setenv("TRIGGER_EVENT_RETENTION_DAYS", "7")
    from app.services import trigger_event_service
    from app_litestar.lifecycle import purge_trigger_events_job

    with patch.object(trigger_event_service, "purge_older_than") as fake:
        purge_trigger_events_job()
    fake.assert_called_once_with(days=7)


def test_purge_job_default_retention(monkeypatch):
    monkeypatch.delenv("TRIGGER_EVENT_RETENTION_DAYS", raising=False)
    from app.services import trigger_event_service
    from app_litestar.lifecycle import purge_trigger_events_job

    with patch.object(trigger_event_service, "purge_older_than") as fake:
        purge_trigger_events_job()
    fake.assert_called_once_with(days=30)
