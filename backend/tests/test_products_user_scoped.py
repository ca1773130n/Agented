"""Tests for the per-user product scoping introduced in wave 39."""

from app.db.connection import get_connection
from app.db.products import (
    create_product,
    get_all_products,
    get_products_for_user,
)
from app.db.users import create_user


def _legacy_user_id() -> str:
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM users WHERE email = ?", ("legacy@local",)).fetchone()
    assert row is not None
    return row[0]


class TestUserIdAttribution:
    def test_create_without_user_id_falls_back_to_legacy(self, isolated_db):
        product_id = create_product("Default Product")
        assert product_id is not None
        with get_connection() as conn:
            row = conn.execute(
                "SELECT user_id FROM products WHERE id = ?", (product_id,)
            ).fetchone()
        assert row[0] == _legacy_user_id()

    def test_create_with_explicit_user_id(self, isolated_db):
        uid = create_user("alice@example.com", "Alice")
        product_id = create_product("Owned", user_id=uid)
        with get_connection() as conn:
            row = conn.execute(
                "SELECT user_id FROM products WHERE id = ?", (product_id,)
            ).fetchone()
        assert row[0] == uid


class TestGetProductsForUser:
    def test_returns_only_users_products(self, isolated_db):
        alice = create_user("alice@example.com", "Alice")
        bob = create_user("bob@example.com", "Bob")
        a_id = create_product("Alice Product 1", user_id=alice)
        create_product("Bob Product", user_id=bob)
        b_id = create_product("Alice Product 2", user_id=alice)

        rows = get_products_for_user(alice)
        ids = {r["id"] for r in rows}
        assert ids == {a_id, b_id}

    def test_returns_empty_when_user_has_none(self, isolated_db):
        ghost = create_user("ghost@example.com", "Ghost")
        # Other users have products; the queried user does not.
        create_product("Someone Else's", user_id=create_user("x@y.com"))
        assert get_products_for_user(ghost) == []

    def test_legacy_user_sees_pre_existing_backfilled_products(self, isolated_db):
        # No explicit user_id — falls back to legacy.
        legacy_pid = create_product("Legacy Product")
        rows = get_products_for_user(_legacy_user_id())
        ids = {r["id"] for r in rows}
        assert legacy_pid in ids

    def test_pagination_works(self, isolated_db):
        uid = create_user("page@example.com", "Pager")
        for i in range(5):
            create_product(f"Product {i:02d}", user_id=uid)
        page1 = get_products_for_user(uid, limit=2, offset=0)
        page2 = get_products_for_user(uid, limit=2, offset=2)
        assert len(page1) == 2
        assert len(page2) == 2
        assert {r["id"] for r in page1} & {r["id"] for r in page2} == set()


class TestUnscopedAdminView:
    def test_get_all_products_still_returns_everything(self, isolated_db):
        alice = create_user("alice@example.com", "Alice")
        bob = create_user("bob@example.com", "Bob")
        ids = {
            create_product("A", user_id=alice),
            create_product("B", user_id=bob),
            create_product("C"),  # legacy
        }
        all_ids = {r["id"] for r in get_all_products()}
        assert ids <= all_ids
