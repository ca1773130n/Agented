"""v0.5.14: rate_limit_guard tests."""

import pytest


@pytest.fixture(autouse=True)
def _clean_registry():
    from app_litestar.rate_limit_guard import clear_overrides

    clear_overrides()
    yield
    clear_overrides()


class TestRequiresRateLimit:
    def test_factory_rejects_non_positive_limit(self):
        from app_litestar.rate_limit_guard import requires_rate_limit

        with pytest.raises(ValueError, match="positive"):
            requires_rate_limit(0, 60)
        with pytest.raises(ValueError, match="positive"):
            requires_rate_limit(5, 0)
        with pytest.raises(ValueError, match="positive"):
            requires_rate_limit(-1, 60)

    def test_register_and_lookup(self):
        from app_litestar.rate_limit_guard import get_override, register_override

        register_override("POST", "/api/auth/login", 5, 60.0)
        assert get_override("POST", "/api/auth/login") == (5, 60.0)
        assert get_override("GET", "/api/auth/login") is None
        assert get_override("POST", "/api/other") is None

    def test_clear_overrides(self):
        from app_litestar.rate_limit_guard import (
            clear_overrides,
            get_override,
            register_override,
        )

        register_override("POST", "/x", 1, 1.0)
        clear_overrides()
        assert get_override("POST", "/x") is None
