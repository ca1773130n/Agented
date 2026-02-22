"""Tests for PR review CRUD API endpoints."""

SAMPLE_PR = {
    "project_name": "my-project",
    "github_repo_url": "https://github.com/owner/my-project",
    "pr_number": 42,
    "pr_url": "https://github.com/owner/my-project/pull/42",
    "pr_title": "Fix critical bug",
    "pr_author": "developer1",
}


def _create_pr(client, **overrides):
    """Helper to create a PR review entry."""
    data = {**SAMPLE_PR, **overrides}
    return client.post("/api/pr-reviews/", json=data)


class TestCreatePrReview:
    def test_create_returns_201(self, client):
        resp = _create_pr(client)
        assert resp.status_code == 201
        body = resp.get_json()
        assert "id" in body
        assert body["message"] == "PR review created"

    def test_create_missing_required_field(self, client):
        resp = client.post("/api/pr-reviews/", json={"project_name": "x"})
        assert resp.status_code == 400

    def test_create_duplicate_pr_number_same_project(self, client):
        _create_pr(client)
        resp = _create_pr(client)
        # Second insert with same pr_url should still succeed (not unique-constrained on pr_url alone)
        assert resp.status_code == 201


class TestListPrReviews:
    def test_list_empty(self, client):
        resp = client.get("/api/pr-reviews/")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["reviews"] == []
        assert body["total"] == 0

    def test_list_after_create(self, client):
        _create_pr(client)
        _create_pr(
            client,
            pr_number=43,
            pr_url="https://github.com/owner/my-project/pull/43",
            pr_title="Another PR",
        )
        resp = client.get("/api/pr-reviews/")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["total"] == 2
        assert len(body["reviews"]) == 2

    def test_list_filter_by_pr_status(self, client):
        _create_pr(client)
        resp = client.get("/api/pr-reviews/?pr_status=open")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["total"] == 1

        resp = client.get("/api/pr-reviews/?pr_status=merged")
        body = resp.get_json()
        assert body["total"] == 0


class TestGetPrReview:
    def test_get_existing(self, client):
        create_resp = _create_pr(client)
        review_id = create_resp.get_json()["id"]
        resp = client.get(f"/api/pr-reviews/{review_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["pr_title"] == "Fix critical bug"
        assert body["pr_status"] == "open"
        assert body["review_status"] == "pending"

    def test_get_nonexistent(self, client):
        resp = client.get("/api/pr-reviews/99999")
        assert resp.status_code == 404


class TestUpdatePrReview:
    def test_update_review_status(self, client):
        create_resp = _create_pr(client)
        review_id = create_resp.get_json()["id"]

        resp = client.put(
            f"/api/pr-reviews/{review_id}",
            json={
                "review_status": "approved",
                "review_comment": "LGTM",
            },
        )
        assert resp.status_code == 200

        # Verify the update persisted
        resp = client.get(f"/api/pr-reviews/{review_id}")
        body = resp.get_json()
        assert body["review_status"] == "approved"
        assert body["review_comment"] == "LGTM"

    def test_update_pr_status_to_merged(self, client):
        create_resp = _create_pr(client)
        review_id = create_resp.get_json()["id"]

        resp = client.put(
            f"/api/pr-reviews/{review_id}",
            json={
                "pr_status": "merged",
            },
        )
        assert resp.status_code == 200

        resp = client.get(f"/api/pr-reviews/{review_id}")
        assert resp.get_json()["pr_status"] == "merged"

    def test_update_nonexistent(self, client):
        resp = client.put("/api/pr-reviews/99999", json={"pr_status": "merged"})
        assert resp.status_code == 404


class TestDeletePrReview:
    def test_delete_existing(self, client):
        create_resp = _create_pr(client)
        review_id = create_resp.get_json()["id"]

        resp = client.delete(f"/api/pr-reviews/{review_id}")
        assert resp.status_code == 200

        resp = client.get(f"/api/pr-reviews/{review_id}")
        assert resp.status_code == 404

    def test_delete_nonexistent(self, client):
        resp = client.delete("/api/pr-reviews/99999")
        assert resp.status_code == 404


class TestPrReviewStats:
    def test_stats_empty(self, client):
        resp = client.get("/api/pr-reviews/stats")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["total_prs"] == 0
        assert body["open_prs"] == 0

    def test_stats_after_creates(self, client):
        _create_pr(client)
        _create_pr(
            client, pr_number=43, pr_url="https://github.com/owner/repo/pull/43", pr_title="PR 2"
        )

        resp = client.get("/api/pr-reviews/stats")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["total_prs"] == 2
        assert body["open_prs"] == 2
        assert body["pending_reviews"] == 2

    def test_stats_reflect_status_changes(self, client):
        create_resp = _create_pr(client)
        review_id = create_resp.get_json()["id"]
        client.put(
            f"/api/pr-reviews/{review_id}",
            json={
                "pr_status": "merged",
                "review_status": "approved",
            },
        )

        resp = client.get("/api/pr-reviews/stats")
        body = resp.get_json()
        assert body["total_prs"] == 1
        assert body["open_prs"] == 0
        assert body["merged_prs"] == 1
        assert body["approved_reviews"] == 1
        assert body["pending_reviews"] == 0
