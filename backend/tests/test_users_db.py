"""Tests for app.db.users — multi-user table CRUD (wave 19)."""

from app.db.users import (
    count_users,
    create_user,
    deactivate_user,
    get_user,
    get_user_by_email,
    list_users,
    update_user,
)


class TestCreateUser:
    def test_create_returns_prefixed_id(self, isolated_db):
        uid = create_user("alice@example.com", "Alice")
        assert uid is not None
        assert uid.startswith("user-")

    def test_create_normalizes_email_case(self, isolated_db):
        uid = create_user("ALICE@example.com", "Alice")
        assert uid is not None
        row = get_user(uid)
        assert row["email"] == "alice@example.com"

    def test_create_rejects_invalid_email(self, isolated_db):
        baseline = count_users()  # includes legacy@local from migration v102
        assert create_user("notanemail", "X") is None
        assert create_user("", "X") is None
        assert count_users() == baseline

    def test_create_unique_email_constraint(self, isolated_db):
        baseline = count_users()
        first = create_user("dup@example.com", "First")
        assert first is not None
        second = create_user("dup@example.com", "Second")
        assert second is None
        assert count_users() == baseline + 1


class TestGetUser:
    def test_get_unknown_returns_none(self, isolated_db):
        assert get_user("user-doesnotexist") is None

    def test_get_by_email_normalizes(self, isolated_db):
        create_user("bob@example.com", "Bob")
        assert get_user_by_email("BOB@EXAMPLE.COM")["display_name"] == "Bob"


class TestListUsers:
    def test_list_returns_all_by_default(self, isolated_db):
        baseline = len(list_users())  # legacy@local
        create_user("a@x.com")
        create_user("b@x.com")
        rows = list_users()
        assert len(rows) == baseline + 2

    def test_list_active_only_filters_deactivated(self, isolated_db):
        active_id = create_user("a@x.com")
        inactive_id = create_user("b@x.com")
        deactivate_user(inactive_id)
        rows = list_users(active_only=True)
        ids = [r["id"] for r in rows]
        assert active_id in ids
        assert inactive_id not in ids


class TestUpdateUser:
    def test_update_display_name(self, isolated_db):
        uid = create_user("c@x.com", "Old")
        assert update_user(uid, display_name="New") is True
        assert get_user(uid)["display_name"] == "New"

    def test_update_unknown_returns_false(self, isolated_db):
        assert update_user("user-nope", display_name="X") is False


class TestDeactivate:
    def test_deactivate_flips_is_active(self, isolated_db):
        uid = create_user("d@x.com")
        assert get_user(uid)["is_active"] == 1
        deactivate_user(uid)
        assert get_user(uid)["is_active"] == 0

    def test_count_active_only(self, isolated_db):
        baseline_total = count_users()
        baseline_active = count_users(active_only=True)
        create_user("e@x.com")
        deact = create_user("f@x.com")
        deactivate_user(deact)
        assert count_users() == baseline_total + 2
        assert count_users(active_only=True) == baseline_active + 1
