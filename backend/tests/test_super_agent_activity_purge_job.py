"""v0.7.7: scheduler purge job hits super_agent_activity_service.purge_older_than."""

from unittest.mock import patch


def test_purge_job_uses_retention_env(monkeypatch):
    monkeypatch.setenv("SUPER_AGENT_ACTIVITY_RETENTION_DAYS", "7")
    from app.services import super_agent_activity_service
    from app_litestar.lifecycle import purge_super_agent_activity_job

    with patch.object(super_agent_activity_service, "purge_older_than") as fake:
        purge_super_agent_activity_job()
    fake.assert_called_once_with(days=7)


def test_purge_job_default_retention(monkeypatch):
    monkeypatch.delenv("SUPER_AGENT_ACTIVITY_RETENTION_DAYS", raising=False)
    from app.services import super_agent_activity_service
    from app_litestar.lifecycle import purge_super_agent_activity_job

    with patch.object(super_agent_activity_service, "purge_older_than") as fake:
        purge_super_agent_activity_job()
    fake.assert_called_once_with(days=30)
