"""Scenario tests for utility, setup, specialized bots, backends, chunks, sketches,
plugin exports, and webhook route domains.
"""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_project(client, name="test-project"):
    """Create a project and return its ID."""
    resp = client.post("/admin/projects/", json={"name": name, "description": "Test project"})
    assert resp.status_code == 201
    return resp.get_json()["project"]["id"]


def _create_team(client, name="test-team"):
    """Create a team and return its ID."""
    resp = client.post("/admin/teams/", json={"name": name, "description": "Test team"})
    assert resp.status_code == 201
    return resp.get_json()["team"]["id"]


def _create_trigger(client, name="test-bot", trigger_source="webhook"):
    """Create a trigger/bot and return its ID."""
    resp = client.post(
        "/admin/triggers/",
        json={
            "name": name,
            "trigger_source": trigger_source,
            "prompt_template": "/test {message}",
        },
    )
    assert resp.status_code == 201
    return resp.get_json()["trigger_id"]


# ===========================================================================
# 1. Utility routes (/api/*)
# ===========================================================================


class TestUtilityRoutes:
    """Scenario tests for utility API endpoints."""

    def test_get_version(self, client):
        """GET /api/version returns a version string."""
        resp = client.get("/api/version")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "version" in body
        assert isinstance(body["version"], str)

    def test_get_version_when_git_fails(self, client):
        """GET /api/version returns 'unknown' when git is unavailable."""
        with patch("app.routes.utility.subprocess.run", side_effect=Exception("no git")):
            resp = client.get("/api/version")
            assert resp.status_code == 200
            assert resp.get_json()["version"] == "unknown"

    def test_check_backend_valid_name(self, client):
        """GET /api/check-backend with valid backend name returns status."""
        resp = client.get("/api/check-backend?name=claude")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["backend"] == "claude"
        assert "installed" in body

    def test_check_backend_invalid_name(self, client):
        """GET /api/check-backend rejects unknown backend names."""
        resp = client.get("/api/check-backend?name=foobar")
        assert resp.status_code == 400
        assert "Invalid backend" in resp.get_json()["message"]

    def test_check_backend_missing_name(self, client):
        """GET /api/check-backend with empty name returns 400."""
        resp = client.get("/api/check-backend?name=")
        assert resp.status_code == 400

    def test_validate_path_missing(self, client):
        """GET /api/validate-path without path param returns 400."""
        resp = client.get("/api/validate-path")
        assert resp.status_code == 400
        assert "Path parameter required" in resp.get_json()["message"]

    def test_validate_path_in_home(self, client):
        """GET /api/validate-path accepts paths under home directory."""
        home = str(os.path.expanduser("~"))
        resp = client.get(f"/api/validate-path?path={home}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["exists"] is True
        assert body["is_directory"] is True

    def test_validate_path_nonexistent_under_home(self, client):
        """GET /api/validate-path reports non-existent path under home."""
        home = str(os.path.expanduser("~"))
        path = os.path.join(home, "nonexistent-path-abc123")
        resp = client.get(f"/api/validate-path?path={path}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["exists"] is False
        assert body["is_directory"] is False

    def test_validate_path_outside_allowed(self, client):
        """GET /api/validate-path rejects paths outside home/tmp."""
        resp = client.get("/api/validate-path?path=/etc/passwd")
        assert resp.status_code == 403
        body = resp.get_json()
        assert "error" in body

    def test_validate_github_url_missing(self, client):
        """GET /api/validate-github-url without url returns 400."""
        resp = client.get("/api/validate-github-url")
        assert resp.status_code == 400
        assert "url parameter required" in resp.get_json()["message"]

    def test_validate_github_url_malformed(self, client):
        """GET /api/validate-github-url with bad url returns valid=false."""
        resp = client.get("/api/validate-github-url?url=not-a-url")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["valid"] is False
        assert body["owner"] is None
        assert body["repo"] is None

    def test_validate_github_url_well_formed(self, client):
        """GET /api/validate-github-url parses owner/repo from valid URL."""
        url = "https://github.com/octocat/hello-world"
        with patch("app.routes.utility.GitHubService.validate_repo_url", return_value=True):
            resp = client.get(f"/api/validate-github-url?url={url}")
            assert resp.status_code == 200
            body = resp.get_json()
            assert body["owner"] == "octocat"
            assert body["repo"] == "hello-world"
            assert body["valid"] is True

    def test_resolve_issues_missing_body(self, client):
        """POST /api/resolve-issues without JSON body returns 400."""
        resp = client.post("/api/resolve-issues", content_type="application/json")
        assert resp.status_code == 400

    def test_resolve_issues_missing_fields(self, client):
        """POST /api/resolve-issues without required fields returns 400."""
        resp = client.post("/api/resolve-issues", json={"audit_summary": "test"})
        assert resp.status_code == 400
        assert "project_paths required" in resp.get_json()["message"]

        resp = client.post("/api/resolve-issues", json={"project_paths": ["/tmp/a"]})
        assert resp.status_code == 400
        assert "audit_summary required" in resp.get_json()["message"]

    def test_resolve_issues_success(self, client):
        """POST /api/resolve-issues starts resolution and returns 202."""
        with patch("app.routes.utility.ExecutionService.run_resolve_command"):
            resp = client.post(
                "/api/resolve-issues",
                json={
                    "audit_summary": "Found XSS vulnerabilities",
                    "project_paths": ["/tmp/project"],
                },
            )
            assert resp.status_code == 202
            body = resp.get_json()
            assert body["status"] == "running"
            assert body["project_count"] == 1

    def test_discover_skills_default(self, client):
        """GET /api/discover-skills returns skills list from project root."""
        resp = client.get("/api/discover-skills")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "skills" in body
        assert isinstance(body["skills"], list)

    def test_discover_skills_with_invalid_trigger(self, client):
        """GET /api/discover-skills with bad trigger_id returns 404."""
        resp = client.get("/api/discover-skills?trigger_id=nonexistent")
        assert resp.status_code == 404

    def test_discover_skills_with_paths(self, client):
        """GET /api/discover-skills with paths param scans those dirs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            resp = client.get(f"/api/discover-skills?paths={tmpdir}")
            assert resp.status_code == 200
            assert "skills" in resp.get_json()


# ===========================================================================
# 2. Setup routes (/api/setup/*)
# ===========================================================================


class TestSetupRoutes:
    """Scenario tests for interactive plugin setup endpoints."""

    def test_start_setup_missing_project(self, client):
        """POST /api/setup/start with nonexistent project returns 404."""
        resp = client.post(
            "/api/setup/start",
            json={"project_id": "proj-nonexistent", "command": "npm init"},
        )
        assert resp.status_code == 404

    def test_start_setup_success(self, client):
        """POST /api/setup/start with valid project starts setup."""
        project_id = _create_project(client)
        with patch(
            "app.routes.setup.SetupExecutionService.start_setup",
            return_value="setup-abc12345",
        ):
            resp = client.post(
                "/api/setup/start",
                json={"project_id": project_id, "command": "npm init"},
            )
            assert resp.status_code == 201
            body = resp.get_json()
            assert body["execution_id"] == "setup-abc12345"
            assert body["status"] == "running"

    def test_get_setup_status_not_found(self, client):
        """GET /api/setup/<id>/status returns 404 for unknown execution."""
        resp = client.get("/api/setup/setup-nonexistent/status")
        assert resp.status_code == 404

    def test_get_setup_status_success(self, client):
        """GET /api/setup/<id>/status returns status when execution exists."""
        mock_status = {
            "execution_id": "setup-abc12345",
            "project_id": "proj-test",
            "status": "running",
            "command": "npm init",
        }
        with patch(
            "app.routes.setup.SetupExecutionService.get_status",
            return_value=mock_status,
        ):
            resp = client.get("/api/setup/setup-abc12345/status")
            assert resp.status_code == 200
            assert resp.get_json()["status"] == "running"

    def test_cancel_setup_not_found(self, client):
        """DELETE /api/setup/<id> returns 404 for unknown execution."""
        resp = client.delete("/api/setup/setup-nonexistent")
        assert resp.status_code == 404

    def test_cancel_setup_success(self, client):
        """DELETE /api/setup/<id> cancels a running setup."""
        with patch(
            "app.routes.setup.SetupExecutionService.get_status",
            return_value={"execution_id": "setup-abc", "status": "running"},
        ):
            with patch("app.routes.setup.SetupExecutionService.cancel_setup"):
                resp = client.delete("/api/setup/setup-abc")
                assert resp.status_code == 200
                assert "cancelled" in resp.get_json()["message"].lower()

    def test_respond_setup_not_found(self, client):
        """POST /api/setup/<id>/respond returns 404 for unknown execution."""
        resp = client.post(
            "/api/setup/setup-nonexistent/respond",
            json={"interaction_id": "int-1", "response": {"answer": "yes"}},
        )
        assert resp.status_code == 404

    def test_respond_setup_success(self, client):
        """POST /api/setup/<id>/respond submits a response successfully."""
        with patch(
            "app.routes.setup.SetupExecutionService.get_status",
            return_value={"execution_id": "setup-abc", "status": "running"},
        ):
            with patch(
                "app.routes.setup.SetupExecutionService.submit_response",
                return_value=True,
            ):
                resp = client.post(
                    "/api/setup/setup-abc/respond",
                    json={"interaction_id": "int-1", "response": {"answer": "yes"}},
                )
                assert resp.status_code == 200
                assert resp.get_json()["status"] == "ok"

    def test_respond_setup_no_pending(self, client):
        """POST /api/setup/<id>/respond returns 404 when no pending interaction."""
        with patch(
            "app.routes.setup.SetupExecutionService.get_status",
            return_value={"execution_id": "setup-abc", "status": "running"},
        ):
            with patch(
                "app.routes.setup.SetupExecutionService.submit_response",
                return_value=False,
            ):
                resp = client.post(
                    "/api/setup/setup-abc/respond",
                    json={"interaction_id": "int-1", "response": {"answer": "yes"}},
                )
                assert resp.status_code == 404

    def test_bundle_install(self, client):
        """POST /api/setup/bundle-install triggers bundle install."""
        with patch(
            "app.routes.setup.SetupBundleService.bundle_install",
            return_value=({"status": "already_installed"}, 200),
        ):
            resp = client.post("/api/setup/bundle-install")
            assert resp.status_code == 200


# ===========================================================================
# 3. Specialized bots (/admin/specialized-bots/*)
# ===========================================================================


class TestSpecializedBotRoutes:
    """Scenario tests for specialized bot status and health endpoints."""

    def test_get_specialized_bot_status(self, client):
        """GET /admin/specialized-bots/status returns predefined bot statuses."""
        resp = client.get("/admin/specialized-bots/status")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "bots" in body
        assert isinstance(body["bots"], list)
        assert len(body["bots"]) > 0
        # Each bot should have the expected fields
        for bot in body["bots"]:
            assert "id" in bot
            assert "name" in bot
            assert "trigger_exists" in bot
            assert "skill_file_exists" in bot
            assert "enabled" in bot

    def test_specialized_bot_status_contains_predefined_bots(self, client):
        """Status includes the predefined security and PR review bots."""
        resp = client.get("/admin/specialized-bots/status")
        body = resp.get_json()
        bot_ids = [b["id"] for b in body["bots"]]
        assert "bot-security" in bot_ids
        assert "bot-pr-review" in bot_ids

    def test_specialized_bot_health(self, client):
        """GET /admin/specialized-bots/health returns dependency health."""
        resp = client.get("/admin/specialized-bots/health")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "gh_authenticated" in body
        assert "osv_scanner_available" in body
        assert "search_index_count" in body
        assert isinstance(body["gh_authenticated"], bool)
        assert isinstance(body["osv_scanner_available"], bool)
        assert isinstance(body["search_index_count"], int)


# ===========================================================================
# 4. Backends (/admin/backends/*)
# ===========================================================================


class TestBackendRoutes:
    """Scenario tests for AI backend management endpoints.

    Note: list/get/create/update/delete backend account routes were removed in
    the ai-accounts migration (Task 33). Those are now served by /api/v1/backends.
    """

    def test_check_backend_endpoint(self, client):
        """POST /admin/backends/<id>/check returns capabilities."""
        resp = client.post("/admin/backends/backend-claude/check")
        assert resp.status_code in (200, 404)

    def test_connect_session_not_found(self, client):
        """GET /admin/backends/<id>/connect/<sid>/stream returns 404 for unknown session."""
        resp = client.get("/admin/backends/backend-claude/connect/sess-nonexistent/stream")
        assert resp.status_code == 404

    def test_cancel_connect_not_found(self, client):
        """DELETE /admin/backends/<id>/connect/<sid> returns 404 for unknown session."""
        resp = client.delete("/admin/backends/backend-claude/connect/sess-nonexistent")
        assert resp.status_code == 404

    def test_respond_connect_not_found(self, client):
        """POST /admin/backends/<id>/connect/<sid>/respond returns 404 for unknown session."""
        resp = client.post(
            "/admin/backends/backend-claude/connect/sess-nonexistent/respond",
            json={"interaction_id": "int-1", "response": {"answer": "y"}},
        )
        assert resp.status_code == 404

    def test_discover_models(self, client):
        """POST /admin/backends/<id>/discover-models returns model list."""
        resp = client.post("/admin/backends/backend-claude/discover-models")
        assert resp.status_code in (200, 404)

    def test_auth_status(self, client):
        """GET /admin/backends/<id>/auth-status checks auth for a backend."""
        resp = client.get("/admin/backends/backend-claude/auth-status")
        assert resp.status_code in (200, 404)

    def test_proxy_status(self, client):
        """GET /admin/backends/proxy/status returns proxy availability."""
        resp = client.get("/admin/backends/proxy/status")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "available" in body
        assert "account_count" in body

    def test_proxy_accounts(self, client):
        """GET /admin/backends/proxy/accounts returns account list."""
        resp = client.get("/admin/backends/proxy/accounts")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "accounts" in body
        assert isinstance(body["accounts"], list)


# ===========================================================================
# 5. Chunks (/admin/bots/*/run-chunked, /admin/chunked-executions/*)
# ===========================================================================


class TestChunkRoutes:
    """Scenario tests for chunked bot execution endpoints."""

    def test_run_chunked_bot_not_found(self, client):
        """POST /admin/bots/<id>/run-chunked returns 404 for unknown bot."""
        resp = client.post(
            "/admin/bots/bot-nonexistent/run-chunked",
            json={"content": "test content"},
        )
        assert resp.status_code == 404

    def test_run_chunked_missing_content(self, client):
        """POST /admin/bots/<id>/run-chunked returns 400 without content."""
        trigger_id = _create_trigger(client)
        resp = client.post(f"/admin/bots/{trigger_id}/run-chunked", json={})
        assert resp.status_code == 400
        assert "content" in resp.get_json()["message"].lower()

    def test_run_chunked_success(self, client):
        """POST /admin/bots/<id>/run-chunked creates a chunked execution."""
        trigger_id = _create_trigger(client, name="chunk-test-bot")
        content = "line 1\n" * 100  # some content to chunk
        resp = client.post(
            f"/admin/bots/{trigger_id}/run-chunked",
            json={"content": content},
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert "chunked_execution_id" in body
        assert body["bot_id"] == trigger_id
        assert body["total_chunks"] >= 1
        assert body["status"] == "processing"

    def test_get_chunked_execution_not_found(self, client):
        """GET /admin/chunked-executions/<id> returns 404 for unknown."""
        resp = client.get("/admin/chunked-executions/chk-nonexistent")
        assert resp.status_code == 404

    def test_get_chunked_execution_status(self, client):
        """Create a chunked execution then retrieve its status."""
        trigger_id = _create_trigger(client, name="chunk-status-bot")
        create_resp = client.post(
            f"/admin/bots/{trigger_id}/run-chunked",
            json={"content": "some test content for chunking"},
        )
        assert create_resp.status_code == 201
        exec_id = create_resp.get_json()["chunked_execution_id"]

        status_resp = client.get(f"/admin/chunked-executions/{exec_id}")
        assert status_resp.status_code == 200
        body = status_resp.get_json()
        assert body["bot_id"] == trigger_id
        assert "status" in body

    def test_get_chunked_execution_results_not_found(self, client):
        """GET /admin/chunked-executions/<id>/results returns 404 for unknown."""
        resp = client.get("/admin/chunked-executions/chk-nonexistent/results")
        assert resp.status_code == 404

    def test_get_chunked_execution_results_still_processing(self, client):
        """Results endpoint returns 409 when chunks are still processing."""
        trigger_id = _create_trigger(client, name="chunk-results-bot")
        create_resp = client.post(
            f"/admin/bots/{trigger_id}/run-chunked",
            json={"content": "content to process in chunks"},
        )
        exec_id = create_resp.get_json()["chunked_execution_id"]

        results_resp = client.get(f"/admin/chunked-executions/{exec_id}/results")
        # Should be 409 Conflict since processing hasn't completed
        assert results_resp.status_code == 409
        body = results_resp.get_json()
        assert "still processing" in body.get("error", "").lower()


# ===========================================================================
# 6. Sketches (/admin/sketches/*)
# ===========================================================================


class TestSketchRoutes:
    """Scenario tests for sketch management CRUD."""

    def test_list_sketches_empty(self, client):
        """GET /admin/sketches/ returns empty list initially."""
        resp = client.get("/admin/sketches/")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["sketches"] == []
        assert body["total_count"] == 0

    def test_create_sketch(self, client):
        """POST /admin/sketches/ creates a new sketch."""
        resp = client.post(
            "/admin/sketches/",
            json={"title": "Add user auth", "content": "Implement OAuth2 login flow"},
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["sketch_id"].startswith("sketch-")
        assert body["message"] == "Sketch created"

    def test_create_sketch_missing_title(self, client):
        """POST /admin/sketches/ without title returns 422."""
        resp = client.post("/admin/sketches/", json={"content": "no title"})
        assert resp.status_code == 422

    def test_get_sketch(self, client):
        """GET /admin/sketches/<id> returns sketch details."""
        create_resp = client.post("/admin/sketches/", json={"title": "Test sketch"})
        sketch_id = create_resp.get_json()["sketch_id"]

        resp = client.get(f"/admin/sketches/{sketch_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["title"] == "Test sketch"
        assert body["status"] == "draft"

    def test_get_sketch_not_found(self, client):
        """GET /admin/sketches/<id> returns 404 for unknown sketch."""
        resp = client.get("/admin/sketches/sketch-nonexistent")
        assert resp.status_code == 404

    def test_update_sketch(self, client):
        """PUT /admin/sketches/<id> updates sketch fields."""
        create_resp = client.post("/admin/sketches/", json={"title": "Original title"})
        sketch_id = create_resp.get_json()["sketch_id"]

        resp = client.put(
            f"/admin/sketches/{sketch_id}",
            json={"title": "Updated title", "content": "New content"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["message"] == "Sketch updated"

        # Verify update
        get_resp = client.get(f"/admin/sketches/{sketch_id}")
        assert get_resp.get_json()["title"] == "Updated title"

    def test_update_sketch_not_found(self, client):
        """PUT /admin/sketches/<id> returns 404 for unknown sketch."""
        resp = client.put("/admin/sketches/sketch-nonexistent", json={"title": "whatever"})
        assert resp.status_code == 404

    def test_delete_sketch(self, client):
        """DELETE /admin/sketches/<id> removes a sketch."""
        create_resp = client.post("/admin/sketches/", json={"title": "To be deleted"})
        sketch_id = create_resp.get_json()["sketch_id"]

        resp = client.delete(f"/admin/sketches/{sketch_id}")
        assert resp.status_code == 200
        assert resp.get_json()["message"] == "Sketch deleted"

        # Verify deletion
        get_resp = client.get(f"/admin/sketches/{sketch_id}")
        assert get_resp.status_code == 404

    def test_delete_sketch_not_found(self, client):
        """DELETE /admin/sketches/<id> returns 404 for unknown sketch."""
        resp = client.delete("/admin/sketches/sketch-nonexistent")
        assert resp.status_code == 404

    def test_list_sketches_with_filters(self, client):
        """GET /admin/sketches/ supports status and project_id filters."""
        project_id = _create_project(client, name="sketch-proj")
        client.post(
            "/admin/sketches/",
            json={"title": "Sketch A", "project_id": project_id},
        )
        client.post("/admin/sketches/", json={"title": "Sketch B"})

        # Filter by project_id
        resp = client.get(f"/admin/sketches/?project_id={project_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["total_count"] == 1
        assert body["sketches"][0]["title"] == "Sketch A"

    def test_classify_sketch(self, client):
        """POST /admin/sketches/<id>/classify classifies the sketch."""
        create_resp = client.post(
            "/admin/sketches/",
            json={"title": "Add user authentication", "content": "Implement OAuth2 flow"},
        )
        sketch_id = create_resp.get_json()["sketch_id"]

        resp = client.post(f"/admin/sketches/{sketch_id}/classify")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["message"] == "Sketch classified"
        assert "classification" in body

    def test_classify_sketch_not_found(self, client):
        """POST /admin/sketches/<id>/classify returns 404 for unknown sketch."""
        resp = client.post("/admin/sketches/sketch-nonexistent/classify")
        assert resp.status_code == 404

    def test_route_sketch_requires_classification(self, client):
        """POST /admin/sketches/<id>/route returns 400 if not classified."""
        create_resp = client.post("/admin/sketches/", json={"title": "Unclassified sketch"})
        sketch_id = create_resp.get_json()["sketch_id"]

        resp = client.post(f"/admin/sketches/{sketch_id}/route")
        assert resp.status_code == 400
        assert "classified first" in resp.get_json()["message"].lower()

    def test_route_sketch_after_classification(self, client):
        """POST /admin/sketches/<id>/route works after classification."""
        create_resp = client.post(
            "/admin/sketches/",
            json={"title": "Build REST API", "content": "Create endpoints for users"},
        )
        sketch_id = create_resp.get_json()["sketch_id"]

        # Classify first
        client.post(f"/admin/sketches/{sketch_id}/classify")

        # Now route
        resp = client.post(f"/admin/sketches/{sketch_id}/route")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["message"] == "Sketch routed"
        assert "routing" in body

    def test_full_sketch_lifecycle(self, client):
        """Full lifecycle: create -> classify -> route -> update status -> delete."""
        # Create
        create_resp = client.post(
            "/admin/sketches/",
            json={"title": "Deploy new service", "content": "Deploy microservice to production"},
        )
        assert create_resp.status_code == 201
        sketch_id = create_resp.get_json()["sketch_id"]

        # Classify
        classify_resp = client.post(f"/admin/sketches/{sketch_id}/classify")
        assert classify_resp.status_code == 200

        # Route
        route_resp = client.post(f"/admin/sketches/{sketch_id}/route")
        assert route_resp.status_code == 200

        # Update status to in_progress
        update_resp = client.put(f"/admin/sketches/{sketch_id}", json={"status": "in_progress"})
        assert update_resp.status_code == 200

        # Verify final state
        get_resp = client.get(f"/admin/sketches/{sketch_id}")
        assert get_resp.status_code == 200
        sketch = get_resp.get_json()
        assert sketch["status"] == "in_progress"
        assert sketch["classification_json"] is not None
        assert sketch["routing_json"] is not None

        # Delete
        del_resp = client.delete(f"/admin/sketches/{sketch_id}")
        assert del_resp.status_code == 200


# ===========================================================================
# 7. Plugin exports (/admin/plugin-exports/*)
# ===========================================================================


class TestPluginExportRoutes:
    """Scenario tests for plugin export, import, deploy, and sync endpoints."""

    def test_export_missing_body(self, client):
        """POST /admin/plugin-exports/export without JSON returns 400."""
        resp = client.post("/admin/plugin-exports/export", content_type="application/json")
        assert resp.status_code == 400

    def test_export_missing_team_id(self, client):
        """POST /admin/plugin-exports/export without team_id returns 400."""
        resp = client.post(
            "/admin/plugin-exports/export",
            json={"export_format": "claude"},
        )
        assert resp.status_code == 400
        assert "team_id" in resp.get_json()["message"]

    def test_export_invalid_format(self, client):
        """POST /admin/plugin-exports/export with invalid format returns 400."""
        resp = client.post(
            "/admin/plugin-exports/export",
            json={"team_id": "team-abc", "export_format": "invalid"},
        )
        assert resp.status_code == 400
        assert "export_format" in resp.get_json()["message"]

    def test_export_team_not_found(self, client):
        """POST /admin/plugin-exports/export with non-existent team returns 404."""
        resp = client.post(
            "/admin/plugin-exports/export",
            json={"team_id": "team-nonexistent", "export_format": "claude"},
        )
        assert resp.status_code == 404

    def test_export_claude_format(self, client):
        """POST /admin/plugin-exports/export exports as Claude plugin."""
        team_id = _create_team(client, name="export-team")
        with tempfile.TemporaryDirectory() as tmpdir:
            resp = client.post(
                "/admin/plugin-exports/export",
                json={
                    "team_id": team_id,
                    "export_format": "claude",
                    "output_dir": tmpdir,
                },
            )
            assert resp.status_code == 200
            body = resp.get_json()
            assert body["format"] == "claude"

    def test_export_agented_format(self, client):
        """POST /admin/plugin-exports/export exports as Agented package."""
        team_id = _create_team(client, name="export-team-agented")
        with tempfile.TemporaryDirectory() as tmpdir:
            resp = client.post(
                "/admin/plugin-exports/export",
                json={
                    "team_id": team_id,
                    "export_format": "agented",
                    "output_dir": tmpdir,
                },
            )
            assert resp.status_code == 200
            body = resp.get_json()
            assert body["format"] == "agented"

    def test_import_missing_body(self, client):
        """POST /admin/plugin-exports/import without JSON returns 400."""
        resp = client.post("/admin/plugin-exports/import", content_type="application/json")
        assert resp.status_code == 400

    def test_import_missing_source_path(self, client):
        """POST /admin/plugin-exports/import without source_path returns 400."""
        resp = client.post("/admin/plugin-exports/import", json={"plugin_name": "test"})
        assert resp.status_code == 400
        assert "source_path" in resp.get_json()["message"]

    def test_import_nonexistent_path(self, client):
        """POST /admin/plugin-exports/import with bad path returns 404."""
        resp = client.post(
            "/admin/plugin-exports/import",
            json={"source_path": "/tmp/nonexistent-plugin-path-abc123"},
        )
        assert resp.status_code == 404

    def test_deploy_missing_fields(self, client):
        """POST /admin/plugin-exports/deploy without required fields returns 400."""
        resp = client.post("/admin/plugin-exports/deploy", json={})
        assert resp.status_code == 400

        resp = client.post("/admin/plugin-exports/deploy", json={"plugin_id": "plug-abc"})
        assert resp.status_code == 400
        assert "marketplace_id" in resp.get_json()["message"]

    def test_test_connection_missing_marketplace(self, client):
        """POST /admin/plugin-exports/test-connection without marketplace_id returns 400."""
        resp = client.post("/admin/plugin-exports/test-connection", json={})
        assert resp.status_code == 400

    def test_list_plugin_exports(self, client):
        """GET /admin/plugin-exports/<id>/exports returns export records."""
        resp = client.get("/admin/plugin-exports/plug-abc/exports")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "exports" in body
        assert "total_count" in body

    def test_sync_missing_fields(self, client):
        """POST /admin/plugin-exports/sync without required fields returns 400."""
        resp = client.post("/admin/plugin-exports/sync", json={})
        assert resp.status_code == 400

        resp = client.post("/admin/plugin-exports/sync", json={"plugin_id": "plug-abc"})
        assert resp.status_code == 400

    def test_sync_entity_missing_fields(self, client):
        """POST /admin/plugin-exports/sync/entity without required fields returns 400."""
        resp = client.post("/admin/plugin-exports/sync/entity", json={})
        assert resp.status_code == 400

    def test_watch_missing_plugin_id(self, client):
        """POST /admin/plugin-exports/watch without plugin_id returns 400."""
        resp = client.post("/admin/plugin-exports/watch", json={})
        assert resp.status_code == 400

    def test_watch_enable_missing_plugin_dir(self, client):
        """POST /admin/plugin-exports/watch enable without plugin_dir returns 400."""
        resp = client.post(
            "/admin/plugin-exports/watch",
            json={"plugin_id": "plug-abc", "enabled": True},
        )
        assert resp.status_code == 400
        assert "plugin_dir" in resp.get_json()["message"]

    def test_import_from_marketplace_missing_fields(self, client):
        """POST /admin/plugin-exports/import-from-marketplace without required fields."""
        resp = client.post("/admin/plugin-exports/import-from-marketplace", json={})
        assert resp.status_code == 400

        resp = client.post(
            "/admin/plugin-exports/import-from-marketplace",
            json={"marketplace_id": "mkt-abc"},
        )
        assert resp.status_code == 400
        assert "remote_plugin_name" in resp.get_json()["message"]

    def test_get_plugin_sync_status(self, client):
        """GET /admin/plugin-exports/<id>/sync-status returns sync status."""
        resp = client.get("/admin/plugin-exports/plug-abc/sync-status")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "watching" in body


# ===========================================================================
# 8. Webhook (/ root)
# ===========================================================================


class TestWebhookRoutes:
    """Scenario tests for generic webhook endpoint."""

    def test_webhook_get(self, client):
        """GET / returns 200 (health check pattern)."""
        resp = client.get("/")
        assert resp.status_code == 200

    def test_webhook_post_no_json(self, client):
        """POST / without JSON content type returns 400."""
        resp = client.post("/", data="not json", content_type="text/plain")
        assert resp.status_code == 400
        assert "application/json" in resp.get_json()["message"]

    def test_webhook_post_non_object(self, client):
        """POST / with non-object JSON returns 400."""
        resp = client.post("/", json=[1, 2, 3])
        assert resp.status_code == 400
        assert "expected object" in resp.get_json()["message"]

    def test_webhook_url_verification(self, client):
        """POST / with url_verification challenge returns the challenge."""
        resp = client.post(
            "/",
            json={"type": "url_verification", "challenge": "test-challenge-123"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["challenge"] == "test-challenge-123"

    def test_webhook_dispatch_event(self, client):
        """POST / dispatches a webhook event and returns 200."""
        with patch("app.routes.webhook.ExecutionService.dispatch_webhook_event"):
            resp = client.post(
                "/",
                json={"event": "deploy", "status": "success"},
            )
            assert resp.status_code == 200

    def test_webhook_dispatch_error(self, client):
        """POST / returns 500 when dispatch raises."""
        with patch(
            "app.routes.webhook.ExecutionService.dispatch_webhook_event",
            side_effect=RuntimeError("boom"),
        ):
            resp = client.post("/", json={"event": "deploy"})
            assert resp.status_code == 500

    def test_webhook_unsupported_method(self, client):
        """PUT / returns 501 Not Implemented."""
        resp = client.put("/", json={"data": "test"})
        assert resp.status_code == 501

    def test_webhook_delete_method(self, client):
        """DELETE / returns 501 Not Implemented."""
        resp = client.delete("/", json={"data": "test"})
        assert resp.status_code == 501

    def test_webhook_patch_method(self, client):
        """PATCH / returns 501 Not Implemented."""
        resp = client.patch("/", json={"data": "test"})
        assert resp.status_code == 501
