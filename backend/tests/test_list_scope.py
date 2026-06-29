"""Unit tests for the shared admin-aware list scoping helper."""

from app.logging_config import current_user_var
from app_litestar.auth import Caller
from app_litestar.list_scope import admin_or_scoped


def _caller(role, user_id):
    return Caller(api_key="k", role=role, user_id=user_id)


def test_admin_sees_all_regardless_of_user_id():
    out = admin_or_scoped(
        _caller("admin", "nobody-owns-these"),
        "rules",
        "rules",
        all_=lambda: {"rules": ["a", "b"], "total_count": 2},
        scoped=lambda uid: {"rules": ["WRONG"], "total_count": 1},
    )
    assert out == {"rules": ["a", "b"], "total_count": 2}


def test_non_admin_without_user_id_sees_nothing():
    current_user_var.set(None)  # no context-var fallback either
    out = admin_or_scoped(
        _caller("viewer", None),
        "rules",
        "rules",
        all_=lambda: {"rules": ["leaked"], "total_count": 1},
    )
    assert out == {"rules": [], "total_count": 0}


def test_non_admin_uses_scoped_override():
    out = admin_or_scoped(
        _caller("editor", "u1"),
        "rules",
        "rules",
        all_=lambda: {"rules": ["ALL"], "total_count": 99},
        scoped=lambda uid: {"rules": [f"scoped-{uid}"], "total_count": 1},
    )
    assert out == {"rules": ["scoped-u1"], "total_count": 1}
