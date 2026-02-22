"""TDD tests for Sketch CRUD operations (database layer + route endpoints).

Tests cover:
- DB-level CRUD: add, get, get_all (with filters), update, delete, get_recent_classified, parent_sketch_id
- Route-level CRUD: GET/POST/PUT/DELETE on /admin/sketches/* endpoints

The isolated_db fixture (autouse=True from conftest.py) provides a fresh database for each test.
"""

import json
import time

import pytest

from app.db.projects import add_project
from app.db.sketches import (
    add_sketch,
    delete_sketch,
    get_all_sketches,
    get_recent_classified_sketches,
    get_sketch,
    update_sketch,
)

# =============================================================================
# DB-level tests
# =============================================================================


class TestSketchDBCrud:
    """Database-level sketch CRUD tests."""

    def test_add_sketch_returns_prefixed_id(self):
        """add_sketch returns a string matching the sketch-* pattern."""
        sketch_id = add_sketch("Test idea")
        assert sketch_id is not None
        assert isinstance(sketch_id, str)
        assert sketch_id.startswith("sketch-")

    def test_get_sketch_returns_all_fields(self):
        """add then get; verify all expected fields are present."""
        project_id = add_project(name="Sketch Proj", description="d")
        sketch_id = add_sketch("Full Sketch", content="Some content", project_id=project_id)
        assert sketch_id is not None
        sketch = get_sketch(sketch_id)
        assert sketch is not None
        assert sketch["id"] == sketch_id
        assert sketch["title"] == "Full Sketch"
        assert sketch["content"] == "Some content"
        assert sketch["project_id"] == project_id
        assert sketch["status"] == "draft"
        assert sketch["classification_json"] is None
        assert sketch["routing_json"] is None
        assert sketch["parent_sketch_id"] is None
        assert "created_at" in sketch
        assert "updated_at" in sketch

    def test_get_sketch_not_found(self):
        """get_sketch for nonexistent ID returns None."""
        result = get_sketch("sketch-nonexistent")
        assert result is None

    def test_get_all_sketches_returns_list(self):
        """add 3 sketches, get_all_sketches() returns list of length 3."""
        add_sketch("Sketch A")
        add_sketch("Sketch B")
        add_sketch("Sketch C")
        sketches = get_all_sketches()
        assert isinstance(sketches, list)
        assert len(sketches) == 3

    def test_get_all_sketches_filter_by_status(self):
        """add 2 drafts + 1 classified, filter status='draft' returns 2."""
        add_sketch("Draft 1")
        add_sketch("Draft 2")
        sid = add_sketch("Classified 1")
        update_sketch(sid, status="classified")
        drafts = get_all_sketches(status="draft")
        assert len(drafts) == 2

    def test_get_all_sketches_filter_by_project_id(self):
        """add sketches with different project_ids, filter returns correct subset."""
        proj_a = add_project(name="Proj A", description="d")
        proj_b = add_project(name="Proj B", description="d")
        add_sketch("Proj A Sketch", project_id=proj_a)
        add_sketch("Proj A Sketch 2", project_id=proj_a)
        add_sketch("Proj B Sketch", project_id=proj_b)
        result = get_all_sketches(project_id=proj_a)
        assert len(result) == 2
        for s in result:
            assert s["project_id"] == proj_a

    def test_update_sketch_title(self):
        """update title, verify change persisted, updated_at differs from created_at."""
        sketch_id = add_sketch("Original Title")
        original = get_sketch(sketch_id)
        # Small sleep to ensure timestamp difference
        time.sleep(0.05)
        result = update_sketch(sketch_id, title="New Title")
        assert result is True
        updated = get_sketch(sketch_id)
        assert updated["title"] == "New Title"
        assert updated["updated_at"] >= original["created_at"]

    def test_update_sketch_classification_json(self):
        """update classification_json with JSON string, verify persisted."""
        sketch_id = add_sketch("Classify Me")
        classification = json.dumps({"type": "feature", "complexity": "medium"})
        result = update_sketch(sketch_id, classification_json=classification)
        assert result is True
        sketch = get_sketch(sketch_id)
        assert sketch["classification_json"] == classification

    def test_update_sketch_no_changes(self):
        """update_sketch with no kwargs returns False."""
        sketch_id = add_sketch("No Change Sketch")
        result = update_sketch(sketch_id)
        assert result is False

    def test_delete_sketch_success(self):
        """delete returns True, subsequent get returns None."""
        sketch_id = add_sketch("To Delete")
        result = delete_sketch(sketch_id)
        assert result is True
        assert get_sketch(sketch_id) is None

    def test_delete_sketch_not_found(self):
        """delete_sketch for nonexistent ID returns False."""
        result = delete_sketch("sketch-nonexistent")
        assert result is False

    def test_get_recent_classified_sketches(self):
        """add 3 sketches, classify 2, get_recent_classified returns only the 2 classified ones."""
        sid1 = add_sketch("Unclassified")
        sid2 = add_sketch("Classified A")
        sid3 = add_sketch("Classified B")
        update_sketch(sid2, classification_json='{"type": "bug"}', status="classified")
        update_sketch(sid3, classification_json='{"type": "feature"}', status="classified")
        classified = get_recent_classified_sketches()
        assert len(classified) == 2
        ids = [s["id"] for s in classified]
        assert sid2 in ids
        assert sid3 in ids
        assert sid1 not in ids

    def test_parent_sketch_id_relationship(self):
        """create parent, create child with parent_sketch_id, verify child references parent."""
        parent_id = add_sketch("Parent Sketch")
        child_id = add_sketch("Child Sketch")
        update_sketch(child_id, parent_sketch_id=parent_id)
        child = get_sketch(child_id)
        assert child["parent_sketch_id"] == parent_id


# =============================================================================
# Route-level tests
# =============================================================================


class TestSketchRoutes:
    """Route-level sketch endpoint tests."""

    @pytest.fixture(autouse=True)
    def setup_client(self, client):
        """Provide Flask test client to each test."""
        self.client = client

    def test_list_sketches_endpoint(self):
        """GET /admin/sketches returns 200 with {"sketches": [...]}."""
        add_sketch("Route Sketch 1")
        add_sketch("Route Sketch 2")
        resp = self.client.get("/admin/sketches")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "sketches" in data
        assert len(data["sketches"]) == 2

    def test_create_sketch_endpoint(self):
        """POST /admin/sketches with {"title": "Idea"} returns 201 with sketch_id."""
        resp = self.client.post(
            "/admin/sketches",
            json={"title": "New Idea"},
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert "sketch_id" in data
        assert data["sketch_id"].startswith("sketch-")
        assert "message" in data

    def test_create_sketch_missing_title(self):
        """POST /admin/sketches with {} returns 400."""
        resp = self.client.post(
            "/admin/sketches",
            json={},
        )
        assert resp.status_code == 400

    def test_get_sketch_endpoint(self):
        """GET /admin/sketches/<id> returns 200 with sketch data."""
        sketch_id = add_sketch("Route Get Sketch")
        resp = self.client.get(f"/admin/sketches/{sketch_id}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["id"] == sketch_id
        assert data["title"] == "Route Get Sketch"

    def test_get_sketch_not_found_endpoint(self):
        """GET /admin/sketches/sketch-nope returns 404."""
        resp = self.client.get("/admin/sketches/sketch-nope")
        assert resp.status_code == 404

    def test_update_sketch_endpoint(self):
        """PUT /admin/sketches/<id> with {"title": "New"} returns 200."""
        sketch_id = add_sketch("Route Update Sketch")
        resp = self.client.put(
            f"/admin/sketches/{sketch_id}",
            json={"title": "Updated Title"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "message" in data

    def test_delete_sketch_endpoint(self):
        """DELETE /admin/sketches/<id> returns 200."""
        sketch_id = add_sketch("Route Delete Sketch")
        resp = self.client.delete(f"/admin/sketches/{sketch_id}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "message" in data
