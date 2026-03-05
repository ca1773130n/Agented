"""Tests for multi-repo campaign orchestration."""

import time
from unittest.mock import MagicMock, patch

from app.db.campaigns import (
    add_campaign_execution,
    create_campaign,
    delete_campaign,
    get_campaign,
    list_campaign_executions,
    list_campaigns,
    update_campaign_execution,
    update_campaign_status,
)
from app.services.campaign_service import (
    _semaphore,
    get_campaign_results,
    start_campaign,
)

# Predefined trigger IDs seeded by isolated_db fixture
TRIGGER_A = "bot-security"
TRIGGER_B = "bot-pr-review"


# ---- DB CRUD Tests ----


def test_create_campaign(isolated_db):
    """Campaign creation returns a camp- prefixed ID."""
    cid = create_campaign(
        "test-campaign", TRIGGER_A, ["https://github.com/a", "https://github.com/b"]
    )
    assert cid is not None
    assert cid.startswith("camp-")


def test_get_campaign(isolated_db):
    """Retrieved campaign has correct fields and parsed repo_urls."""
    cid = create_campaign("my-campaign", TRIGGER_A, ["https://github.com/repo1"])
    campaign = get_campaign(cid)
    assert campaign is not None
    assert campaign["name"] == "my-campaign"
    assert campaign["trigger_id"] == TRIGGER_A
    assert campaign["status"] == "running"
    assert campaign["repo_urls"] == ["https://github.com/repo1"]
    assert campaign["total_repos"] == 1


def test_get_campaign_not_found(isolated_db):
    """Non-existent campaign returns None."""
    assert get_campaign("camp-nonexistent") is None


def test_list_campaigns(isolated_db):
    """List campaigns returns all campaigns."""
    create_campaign("c1", TRIGGER_A, ["https://github.com/r1"])
    create_campaign("c2", TRIGGER_B, ["https://github.com/r2"])
    campaigns = list_campaigns()
    assert len(campaigns) == 2


def test_list_campaigns_filter_by_trigger(isolated_db):
    """List campaigns filters by trigger_id."""
    create_campaign("c1", TRIGGER_A, ["https://github.com/r1"])
    create_campaign("c2", TRIGGER_B, ["https://github.com/r2"])
    campaigns = list_campaigns(trigger_id=TRIGGER_A)
    assert len(campaigns) == 1
    assert campaigns[0]["trigger_id"] == TRIGGER_A


def test_list_campaigns_filter_by_status(isolated_db):
    """List campaigns filters by status."""
    cid = create_campaign("c1", TRIGGER_A, ["https://github.com/r1"])
    update_campaign_status(cid, "completed", completed=1, failed=0)
    create_campaign("c2", TRIGGER_B, ["https://github.com/r2"])

    completed = list_campaigns(status="completed")
    assert len(completed) == 1
    running = list_campaigns(status="running")
    assert len(running) == 1


def test_update_campaign_status(isolated_db):
    """Update campaign status and counters."""
    cid = create_campaign("c1", TRIGGER_A, ["https://github.com/r1", "https://github.com/r2"])
    updated = update_campaign_status(cid, "completed", completed=2, failed=0)
    assert updated is True
    campaign = get_campaign(cid)
    assert campaign["status"] == "completed"
    assert campaign["completed_repos"] == 2
    assert campaign["finished_at"] is not None


def test_campaign_executions_crud(isolated_db):
    """Campaign execution entries can be created, updated, and listed."""
    cid = create_campaign("c1", TRIGGER_A, ["https://github.com/r1"])
    row_id = add_campaign_execution(cid, "https://github.com/r1")
    assert row_id is not None

    # Update to running
    update_campaign_execution(cid, "https://github.com/r1", status="running")
    execs = list_campaign_executions(cid)
    assert len(execs) == 1
    assert execs[0]["status"] == "running"
    assert execs[0]["started_at"] is not None

    # Update to completed with execution_id
    update_campaign_execution(
        cid,
        "https://github.com/r1",
        execution_id="exec-bot-security-20260101T000000-abcd",
        status="completed",
    )
    execs = list_campaign_executions(cid)
    assert execs[0]["status"] == "completed"
    assert execs[0]["execution_id"] == "exec-bot-security-20260101T000000-abcd"


def test_delete_campaign(isolated_db):
    """Delete removes campaign and cascades to executions."""
    cid = create_campaign("c1", TRIGGER_A, ["https://github.com/r1"])
    add_campaign_execution(cid, "https://github.com/r1")
    assert delete_campaign(cid) is True
    assert get_campaign(cid) is None
    assert list_campaign_executions(cid) == []


# ---- Service Tests ----


@patch("app.services.orchestration_service.OrchestrationService", autospec=False)
@patch("app.db.triggers.get_trigger")
def test_start_campaign_three_repos(mock_get_trigger, mock_orch, isolated_db):
    """Campaign dispatches to 3 repos and collects results."""
    mock_get_trigger.return_value = {
        "id": TRIGGER_A,
        "name": "Test",
        "trigger_source": "webhook",
    }

    mock_result = MagicMock()
    mock_result.execution_id = "exec-123"
    mock_result.status = MagicMock(value="dispatched")
    mock_result.detail = None
    mock_orch.execute_with_fallback.return_value = mock_result

    repo_urls = [
        "https://github.com/org/repo1",
        "https://github.com/org/repo2",
        "https://github.com/org/repo3",
    ]

    cid = start_campaign("test-3-repos", TRIGGER_A, repo_urls)
    assert cid is not None

    # Wait for campaign to complete (threads are daemon)
    for _ in range(50):
        campaign = get_campaign(cid)
        if campaign and campaign["status"] != "running":
            break
        time.sleep(0.1)

    campaign = get_campaign(cid)
    assert campaign["status"] == "completed"
    assert campaign["completed_repos"] == 3
    assert campaign["failed_repos"] == 0


@patch("app.services.orchestration_service.OrchestrationService", autospec=False)
@patch("app.db.triggers.get_trigger")
def test_campaign_partial_failure(mock_get_trigger, mock_orch, isolated_db):
    """Campaign with 1/3 failures results in partial_failure status."""
    mock_get_trigger.return_value = {
        "id": TRIGGER_A,
        "name": "Test",
        "trigger_source": "webhook",
    }

    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 2:
            # Second call fails
            result.execution_id = None
            result.status = MagicMock(value="launch_failed")
            result.detail = "Process crash"
        else:
            result.execution_id = f"exec-{call_count}"
            result.status = MagicMock(value="dispatched")
            result.detail = None
        return result

    mock_orch.execute_with_fallback.side_effect = side_effect

    repo_urls = [
        "https://github.com/org/repo1",
        "https://github.com/org/repo2",
        "https://github.com/org/repo3",
    ]

    cid = start_campaign("partial-fail", TRIGGER_A, repo_urls)

    # Wait for completion
    for _ in range(50):
        campaign = get_campaign(cid)
        if campaign and campaign["status"] != "running":
            break
        time.sleep(0.1)

    campaign = get_campaign(cid)
    assert campaign["status"] == "partial_failure"
    assert campaign["completed_repos"] == 2
    assert campaign["failed_repos"] == 1


def test_semaphore_limits_concurrency(isolated_db):
    """Semaphore limits concurrent repo executions to 5."""
    # The module-level semaphore should have capacity 5
    acquired = []
    for i in range(5):
        assert _semaphore.acquire(blocking=False), f"Should acquire slot {i}"
        acquired.append(True)

    # 6th should fail (non-blocking)
    assert not _semaphore.acquire(blocking=False), "Should not acquire 6th slot"

    # Release all
    for _ in acquired:
        _semaphore.release()


def test_get_campaign_results(isolated_db):
    """Campaign results consolidated by repo."""
    cid = create_campaign("c1", TRIGGER_A, ["https://github.com/r1", "https://github.com/r2"])
    add_campaign_execution(cid, "https://github.com/r1")
    add_campaign_execution(cid, "https://github.com/r2")
    update_campaign_execution(cid, "https://github.com/r1", status="completed", execution_id="e1")
    update_campaign_execution(cid, "https://github.com/r2", status="failed", error="timeout")
    update_campaign_status(cid, "partial_failure", completed=1, failed=1)

    results = get_campaign_results(cid)
    assert results is not None
    assert results["repos"]["https://github.com/r1"]["status"] == "completed"
    assert results["repos"]["https://github.com/r2"]["status"] == "failed"
    assert results["summary"]["total"] == 2


def test_get_campaign_results_not_found(isolated_db):
    """Non-existent campaign returns None from results."""
    assert get_campaign_results("camp-nonexistent") is None


# ---- Route Tests ----


def test_route_create_campaign(client):
    """POST /admin/campaigns creates a campaign."""
    resp = client.post(
        "/admin/campaigns",
        json={
            "name": "route-test",
            "trigger_id": TRIGGER_A,
            "repo_urls": ["https://github.com/org/repo1"],
        },
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert "campaign" in data
    assert data["campaign"]["name"] == "route-test"


def test_route_list_campaigns(client):
    """GET /admin/campaigns lists campaigns."""
    client.post(
        "/admin/campaigns",
        json={
            "name": "list-test",
            "trigger_id": TRIGGER_A,
            "repo_urls": ["https://github.com/org/repo1"],
        },
    )
    resp = client.get("/admin/campaigns")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "campaigns" in data
    assert len(data["campaigns"]) >= 1


def test_route_get_campaign_detail(client):
    """GET /admin/campaigns/<id> returns campaign with executions."""
    resp = client.post(
        "/admin/campaigns",
        json={
            "name": "detail-test",
            "trigger_id": TRIGGER_A,
            "repo_urls": ["https://github.com/org/repo1"],
        },
    )
    cid = resp.get_json()["campaign"]["id"]
    resp = client.get(f"/admin/campaigns/{cid}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["campaign"]["id"] == cid
    assert "executions" in data


def test_route_get_campaign_not_found(client):
    """GET /admin/campaigns/<id> returns 404 for missing campaign."""
    resp = client.get("/admin/campaigns/camp-nonexistent")
    assert resp.status_code == 404


def test_route_delete_campaign(client):
    """DELETE /admin/campaigns/<id> deletes campaign."""
    resp = client.post(
        "/admin/campaigns",
        json={
            "name": "delete-test",
            "trigger_id": TRIGGER_A,
            "repo_urls": ["https://github.com/org/repo1"],
        },
    )
    cid = resp.get_json()["campaign"]["id"]
    resp = client.delete(f"/admin/campaigns/{cid}")
    assert resp.status_code == 200
    assert resp.get_json()["deleted"] is True


def test_route_trigger_campaigns(client):
    """GET /admin/triggers/<id>/campaigns returns trigger-scoped campaigns."""
    client.post(
        "/admin/campaigns",
        json={
            "name": "trigger-test",
            "trigger_id": TRIGGER_A,
            "repo_urls": ["https://github.com/org/repo1"],
        },
    )
    resp = client.get(f"/admin/triggers/{TRIGGER_A}/campaigns")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["campaigns"]) >= 1
