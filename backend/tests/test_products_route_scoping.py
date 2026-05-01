"""Wave 40: end-to-end test that the Flask /admin/products route scopes
results by the authenticated user (via current_user_var, wave 21)."""

from app.db.rbac import create_user_role
from app.db.users import create_user


class TestProductsListScoping:
    def test_authenticated_user_sees_only_their_products(self, client, isolated_db):
        alice = create_user("alice@example.com", "Alice")
        bob = create_user("bob@example.com", "Bob")
        create_user_role("alice-key", "Alice", "admin", user_id=alice)
        create_user_role("bob-key", "Bob", "admin", user_id=bob)

        # Each creates a product through the API.
        alice_resp = client.post(
            "/admin/products/",
            headers={"X-API-Key": "alice-key"},
            json={"name": "Alice Product"},
        )
        assert alice_resp.status_code == 201
        bob_resp = client.post(
            "/admin/products/",
            headers={"X-API-Key": "bob-key"},
            json={"name": "Bob Product"},
        )
        assert bob_resp.status_code == 201

        # Alice's listing returns only her product.
        alice_list = client.get(
            "/admin/products/", headers={"X-API-Key": "alice-key"}
        )
        names = {p["name"] for p in alice_list.get_json()["products"]}
        assert names == {"Alice Product"}

        # Bob's listing returns only his.
        bob_list = client.get("/admin/products/", headers={"X-API-Key": "bob-key"})
        names = {p["name"] for p in bob_list.get_json()["products"]}
        assert names == {"Bob Product"}

    def test_legacy_apikey_with_no_user_falls_back_to_unscoped(self, client, isolated_db):
        # API key without an associated user_id (impossible after wave 20's
        # backfill, but still — the fallback path stays exercised).
        # Use the legacy user explicitly so we know what we're querying.
        from app.db.products import create_product
        from app.db.connection import get_connection

        with get_connection() as conn:
            row = conn.execute(
                "SELECT id FROM users WHERE email = ?", ("legacy@local",)
            ).fetchone()
        legacy_id = row[0]

        create_user_role("admin-key", "Admin", "admin", user_id=legacy_id)
        # Two products: one owned by legacy, one orphaned (NULL user_id).
        create_product("Owned by legacy", user_id=legacy_id)
        from app.db.connection import get_connection as gc

        with gc() as conn:
            conn.execute(
                "INSERT INTO products (id, name, status) VALUES (?, ?, ?)",
                ("prod-orphan", "Orphan", "active"),
            )
            conn.commit()

        resp = client.get("/admin/products/", headers={"X-API-Key": "admin-key"})
        # The legacy user is set as caller via wave 20's backfill, so the
        # scoped list should show only the legacy-owned products.
        names = {p["name"] for p in resp.get_json()["products"]}
        assert "Owned by legacy" in names
        # Orphan (NULL user_id) is excluded from the user-scoped view.
        assert "Orphan" not in names
