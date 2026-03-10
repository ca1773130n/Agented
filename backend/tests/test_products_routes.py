"""Tests for /admin/products API routes."""


def _create_product(client, **overrides):
    """Helper to create a product via API."""
    data = {"name": "Test Product", "description": "A test product", **overrides}
    return client.post("/admin/products/", json=data)


class TestListProducts:
    def test_list_products_empty(self, client):
        """GET /admin/products/ returns empty list when none exist."""
        resp = client.get("/admin/products/")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["products"] == []
        assert body["total_count"] == 0

    def test_list_products_populated(self, client):
        """GET /admin/products/ returns created products."""
        _create_product(client, name="Product A")
        _create_product(client, name="Product B")
        resp = client.get("/admin/products/")
        assert resp.status_code == 200
        body = resp.get_json()
        assert len(body["products"]) == 2
        assert body["total_count"] == 2


class TestCreateProduct:
    def test_create_product(self, client):
        """POST /admin/products/ creates a product and returns 201."""
        resp = _create_product(client, name="My Product")
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["message"] == "Product created"
        assert body["product"]["name"] == "My Product"
        assert body["product"]["id"].startswith("prod-")

    def test_create_product_missing_name(self, client):
        """POST /admin/products/ without name returns 422."""
        resp = client.post("/admin/products/", json={"description": "no name"})
        assert resp.status_code == 422


class TestGetProduct:
    def test_get_product(self, client):
        """GET /admin/products/:id returns product details."""
        create_resp = _create_product(client)
        product_id = create_resp.get_json()["product"]["id"]

        resp = client.get(f"/admin/products/{product_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["id"] == product_id
        assert body["name"] == "Test Product"

    def test_get_product_not_found(self, client):
        """GET /admin/products/:id returns 404 for nonexistent product."""
        resp = client.get("/admin/products/prod-nonexistent")
        assert resp.status_code == 404


class TestUpdateProduct:
    def test_update_product(self, client):
        """PUT /admin/products/:id updates the product."""
        create_resp = _create_product(client)
        product_id = create_resp.get_json()["product"]["id"]

        resp = client.put(f"/admin/products/{product_id}", json={"name": "Updated Product"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["name"] == "Updated Product"

    def test_update_product_not_found(self, client):
        """PUT /admin/products/:id returns 404 for nonexistent product."""
        resp = client.put("/admin/products/prod-nonexistent", json={"name": "X"})
        assert resp.status_code == 404


class TestDeleteProduct:
    def test_delete_product(self, client):
        """DELETE /admin/products/:id deletes the product."""
        create_resp = _create_product(client)
        product_id = create_resp.get_json()["product"]["id"]

        resp = client.delete(f"/admin/products/{product_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["message"] == "Product deleted"

        # Verify it's gone
        resp = client.get(f"/admin/products/{product_id}")
        assert resp.status_code == 404

    def test_delete_product_not_found(self, client):
        """DELETE /admin/products/:id returns 404 for nonexistent product."""
        resp = client.delete("/admin/products/prod-nonexistent")
        assert resp.status_code == 404
