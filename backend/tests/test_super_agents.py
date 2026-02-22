"""Tests for SuperAgent and Document CRUD API endpoints."""

SAMPLE_SUPER_AGENT = {
    "name": "DevOps Lead",
    "description": "Handles infrastructure automation",
    "backend_type": "claude",
    "max_concurrent_sessions": 5,
}


def _create_super_agent(client, **overrides):
    """Helper to create a super agent via API."""
    data = {**SAMPLE_SUPER_AGENT, **overrides}
    return client.post("/admin/super-agents/", json=data)


def _create_document(client, super_agent_id, **overrides):
    """Helper to create a document via API."""
    data = {
        "doc_type": "SOUL",
        "title": "Core Identity",
        "content": "You are a DevOps lead.",
        **overrides,
    }
    return client.post(f"/admin/super-agents/{super_agent_id}/documents", json=data)


class TestCreateSuperAgent:
    def test_create_super_agent(self, client):
        """POST creates a super agent and returns 201 with super-* ID."""
        resp = _create_super_agent(client)
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["message"] == "SuperAgent created"
        assert body["super_agent_id"].startswith("super-")


class TestListSuperAgents:
    def test_list_super_agents(self, client):
        """GET / returns all created super agents."""
        _create_super_agent(client, name="Agent A")
        _create_super_agent(client, name="Agent B")
        resp = client.get("/admin/super-agents/")
        assert resp.status_code == 200
        body = resp.get_json()
        assert len(body["super_agents"]) == 2


class TestGetSuperAgent:
    def test_get_super_agent(self, client):
        """GET /:id returns all fields for the super agent."""
        create_resp = _create_super_agent(client)
        sa_id = create_resp.get_json()["super_agent_id"]

        resp = client.get(f"/admin/super-agents/{sa_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["id"] == sa_id
        assert body["name"] == "DevOps Lead"
        assert body["description"] == "Handles infrastructure automation"
        assert body["backend_type"] == "claude"
        assert body["max_concurrent_sessions"] == 5
        assert body["enabled"] == 1
        assert "created_at" in body
        assert "updated_at" in body


class TestUpdateSuperAgent:
    def test_update_super_agent(self, client):
        """PUT /:id updates the super agent name."""
        create_resp = _create_super_agent(client)
        sa_id = create_resp.get_json()["super_agent_id"]

        resp = client.put(f"/admin/super-agents/{sa_id}", json={"name": "Security Lead"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["message"] == "SuperAgent updated"

        # Verify the change
        get_resp = client.get(f"/admin/super-agents/{sa_id}")
        assert get_resp.get_json()["name"] == "Security Lead"


class TestDeleteSuperAgent:
    def test_delete_super_agent(self, client):
        """DELETE /:id removes the super agent and returns 200; subsequent GET returns 404."""
        create_resp = _create_super_agent(client)
        sa_id = create_resp.get_json()["super_agent_id"]

        resp = client.delete(f"/admin/super-agents/{sa_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["message"] == "SuperAgent deleted"

        # Verify it's gone
        get_resp = client.get(f"/admin/super-agents/{sa_id}")
        assert get_resp.status_code == 404


class TestCreateDocument:
    def test_create_document(self, client):
        """POST creates a SOUL document and returns 201 with document_id."""
        create_resp = _create_super_agent(client)
        sa_id = create_resp.get_json()["super_agent_id"]

        resp = _create_document(client, sa_id, doc_type="SOUL")
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["message"] == "Document created"
        assert isinstance(body["document_id"], int)


class TestListDocuments:
    def test_list_documents(self, client):
        """GET /documents returns all documents for a super agent."""
        create_resp = _create_super_agent(client)
        sa_id = create_resp.get_json()["super_agent_id"]

        _create_document(client, sa_id, doc_type="SOUL", title="Soul Doc")
        _create_document(client, sa_id, doc_type="IDENTITY", title="Identity Doc")

        resp = client.get(f"/admin/super-agents/{sa_id}/documents")
        assert resp.status_code == 200
        body = resp.get_json()
        assert len(body["documents"]) == 2


class TestGetDocument:
    def test_get_document(self, client):
        """GET /documents/:doc_id returns document with all fields."""
        create_resp = _create_super_agent(client)
        sa_id = create_resp.get_json()["super_agent_id"]

        doc_resp = _create_document(client, sa_id)
        doc_id = doc_resp.get_json()["document_id"]

        resp = client.get(f"/admin/super-agents/{sa_id}/documents/{doc_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["id"] == doc_id
        assert body["super_agent_id"] == sa_id
        assert body["doc_type"] == "SOUL"
        assert body["title"] == "Core Identity"
        assert body["content"] == "You are a DevOps lead."
        assert body["version"] == 1


class TestUpdateDocument:
    def test_update_document(self, client):
        """PUT /documents/:doc_id updates the title."""
        create_resp = _create_super_agent(client)
        sa_id = create_resp.get_json()["super_agent_id"]

        doc_resp = _create_document(client, sa_id)
        doc_id = doc_resp.get_json()["document_id"]

        resp = client.put(
            f"/admin/super-agents/{sa_id}/documents/{doc_id}",
            json={"title": "Updated Title"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["message"] == "Document updated"

        # Verify change and version increment
        get_resp = client.get(f"/admin/super-agents/{sa_id}/documents/{doc_id}")
        body = get_resp.get_json()
        assert body["title"] == "Updated Title"
        assert body["version"] == 2


class TestDeleteDocument:
    def test_delete_document(self, client):
        """DELETE /documents/:doc_id removes the document."""
        create_resp = _create_super_agent(client)
        sa_id = create_resp.get_json()["super_agent_id"]

        doc_resp = _create_document(client, sa_id)
        doc_id = doc_resp.get_json()["document_id"]

        resp = client.delete(f"/admin/super-agents/{sa_id}/documents/{doc_id}")
        assert resp.status_code == 200
        assert resp.get_json()["message"] == "Document deleted"


class TestCascadeDelete:
    def test_cascade_delete(self, client):
        """Deleting a super agent cascade-deletes its documents."""
        create_resp = _create_super_agent(client)
        sa_id = create_resp.get_json()["super_agent_id"]

        doc_resp = _create_document(client, sa_id)
        doc_id = doc_resp.get_json()["document_id"]

        # Delete the super agent
        client.delete(f"/admin/super-agents/{sa_id}")

        # Document should be gone too
        get_resp = client.get(f"/admin/super-agents/{sa_id}/documents/{doc_id}")
        assert get_resp.status_code == 404


class TestInvalidDocType:
    def test_invalid_doc_type(self, client):
        """POST with invalid doc_type returns 400."""
        create_resp = _create_super_agent(client)
        sa_id = create_resp.get_json()["super_agent_id"]

        resp = _create_document(client, sa_id, doc_type="INVALID")
        assert resp.status_code == 400
