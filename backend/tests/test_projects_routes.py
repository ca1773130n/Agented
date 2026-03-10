"""Tests for /admin/projects API routes."""


def _create_project(client, **overrides):
    """Helper to create a project via API (uses raw JSON, no github_repo to avoid validation)."""
    data = {"name": "Test Project", "description": "A test project", **overrides}
    return client.post("/admin/projects/", json=data)


class TestListProjects:
    def test_list_projects_empty(self, client):
        """GET /admin/projects/ returns empty list when none exist."""
        resp = client.get("/admin/projects/")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["projects"] == []
        assert body["total_count"] == 0

    def test_list_projects_populated(self, client):
        """GET /admin/projects/ returns created projects."""
        _create_project(client, name="Project A")
        _create_project(client, name="Project B")
        resp = client.get("/admin/projects/")
        assert resp.status_code == 200
        body = resp.get_json()
        assert len(body["projects"]) == 2
        assert body["total_count"] == 2


class TestCreateProject:
    def test_create_project(self, client):
        """POST /admin/projects/ creates a project and returns 201."""
        resp = _create_project(client, name="My Project")
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["message"] == "Project created"
        assert body["project"]["name"] == "My Project"
        assert body["project"]["id"].startswith("proj-")

    def test_create_project_missing_name(self, client):
        """POST /admin/projects/ without name returns 400."""
        resp = client.post("/admin/projects/", json={"description": "no name"})
        assert resp.status_code == 400

    def test_create_project_no_body(self, client):
        """POST /admin/projects/ without JSON body returns 400."""
        resp = client.post("/admin/projects/", content_type="application/json")
        assert resp.status_code == 400


class TestGetProject:
    def test_get_project(self, client):
        """GET /admin/projects/:id returns project details."""
        create_resp = _create_project(client)
        project_id = create_resp.get_json()["project"]["id"]

        resp = client.get(f"/admin/projects/{project_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["id"] == project_id
        assert body["name"] == "Test Project"

    def test_get_project_not_found(self, client):
        """GET /admin/projects/:id returns 404 for nonexistent project."""
        resp = client.get("/admin/projects/proj-nonexistent")
        assert resp.status_code == 404


class TestUpdateProject:
    def test_update_project(self, client):
        """PUT /admin/projects/:id updates the project."""
        create_resp = _create_project(client)
        project_id = create_resp.get_json()["project"]["id"]

        resp = client.put(f"/admin/projects/{project_id}", json={"name": "Updated Project"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["name"] == "Updated Project"

    def test_update_project_not_found(self, client):
        """PUT /admin/projects/:id returns 404 for nonexistent project."""
        resp = client.put("/admin/projects/proj-nonexistent", json={"name": "X"})
        assert resp.status_code == 404


class TestDeleteProject:
    def test_delete_project(self, client):
        """DELETE /admin/projects/:id deletes the project."""
        create_resp = _create_project(client)
        project_id = create_resp.get_json()["project"]["id"]

        resp = client.delete(f"/admin/projects/{project_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["message"] == "Project deleted"

        # Verify it's gone
        resp = client.get(f"/admin/projects/{project_id}")
        assert resp.status_code == 404

    def test_delete_project_not_found(self, client):
        """DELETE /admin/projects/:id returns 404 for nonexistent project."""
        resp = client.delete("/admin/projects/proj-nonexistent")
        assert resp.status_code == 404
