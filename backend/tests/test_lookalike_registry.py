"""Registry-resolution tests for the phase-27 lookalike-provider seam.

Pure registry — no DB. A tiny in-memory ``FakeProvider`` satisfies the
``LookalikeProvider`` Protocol structurally; each test gets a fresh ``_PROVIDERS``
map (set back to ``{}`` so state never leaks). Covers: empty -> ``None`` (the
BUY-gate signal), configured-resolution, the first-configured rule, the
``MARKET_LOOKALIKE_PROVIDER`` explicit-pick (still configured-gated),
``runtime_checkable`` ``isinstance``, and the NULL-accepting ``Candidate.score``.
"""

from __future__ import annotations

import pytest

from app.services.lookalike_providers import registry
from app.services.lookalike_providers.base import (
    Candidate,
    LookalikeProvider,
    LookalikeResult,
)


class FakeProvider:
    """In-memory provider satisfying the Protocol structurally (no key/http)."""

    def __init__(self, name: str, *, configured: bool) -> None:
        self.name = name
        self._configured = configured

    def is_configured(self) -> bool:
        return self._configured

    def find_lookalikes(self, seed: str, *, limit: int = 20) -> LookalikeResult:
        return LookalikeResult(
            outcome="ok",
            candidates=[Candidate(url="https://acme.com", name="Acme")],
        )


@pytest.fixture(autouse=True)
def _fresh_registry(monkeypatch):
    """Fresh empty ``_PROVIDERS`` per test — no leaked registrations."""
    monkeypatch.setattr(registry, "_PROVIDERS", {})
    # Default: no explicit pick unless a test sets it.
    monkeypatch.delenv("MARKET_LOOKALIKE_PROVIDER", raising=False)


def test_empty_registry_active_provider_is_none():
    assert registry.active_provider() is None
    assert registry.provider_names() == []


def test_register_configured_provider_is_active():
    fake = FakeProvider("fake", configured=True)
    registry.register(fake)

    assert registry.active_provider() is fake
    assert registry.provider_names() == ["fake"]
    assert registry.get_provider("fake") is fake


def test_unconfigured_provider_yields_none():
    registry.register(FakeProvider("fake", configured=False))

    # Registered but not configured -> still the not_configured BUY-gate (None).
    assert registry.active_provider() is None
    assert registry.provider_names() == ["fake"]


def test_first_configured_wins_among_many():
    unconfigured = FakeProvider("a_unconfigured", configured=False)
    configured = FakeProvider("b_configured", configured=True)
    registry.register(unconfigured)
    registry.register(configured)

    # Resolution skips the unconfigured one and returns the first configured.
    assert registry.active_provider() is configured


def test_env_explicit_pick_returns_named_when_configured(monkeypatch):
    other = FakeProvider("other", configured=True)
    fake = FakeProvider("fake", configured=True)
    registry.register(other)
    registry.register(fake)

    monkeypatch.setenv("MARKET_LOOKALIKE_PROVIDER", "fake")
    # Explicit pick overrides first-configured ordering.
    assert registry.active_provider() is fake


def test_env_explicit_pick_unregistered_yields_none(monkeypatch):
    registry.register(FakeProvider("fake", configured=True))

    monkeypatch.setenv("MARKET_LOOKALIKE_PROVIDER", "nope")
    # Explicit pick that isn't registered -> None, never a fallback provider.
    assert registry.active_provider() is None


def test_env_explicit_pick_unconfigured_yields_none(monkeypatch):
    registry.register(FakeProvider("fake", configured=False))

    monkeypatch.setenv("MARKET_LOOKALIKE_PROVIDER", "fake")
    # Explicit pick must STILL be configured — unconfigured -> None.
    assert registry.active_provider() is None


def test_register_is_last_wins_idempotent():
    first = FakeProvider("fake", configured=False)
    second = FakeProvider("fake", configured=True)
    registry.register(first)
    registry.register(second)

    assert registry.get_provider("fake") is second
    assert registry.provider_names() == ["fake"]
    assert registry.active_provider() is second


def test_runtime_checkable_isinstance_holds():
    fake = FakeProvider("fake", configured=True)
    assert isinstance(fake, LookalikeProvider)


def test_candidate_score_is_null_accepting():
    candidate = Candidate(url="https://acme.com", name="Acme")
    assert candidate.score is None
    assert candidate.evidence == {}


def test_not_configured_result_carries_no_candidates():
    result = LookalikeResult(outcome="not_configured")
    assert result.candidates == []
    assert result.detail is None


def test_provider_raising_in_is_configured_logs_and_yields_none(monkeypatch):
    """A provider that violates the never-raise contract for ``is_configured`` is
    treated as unconfigured (BUY-gate stays intact) AND a warning is logged with
    the provider name + traceback (NOT silently swallowed)."""

    class _Exploding:
        name = "boom"

        def is_configured(self) -> bool:
            raise RuntimeError("kaboom")

        def find_lookalikes(self, seed, *, limit=20):  # pragma: no cover
            raise AssertionError("never called")

    registry.register(_Exploding())

    warnings: list = []
    monkeypatch.setattr(registry.logger, "warning", lambda *a, **k: warnings.append((a, k)))

    assert registry.active_provider() is None
    assert len(warnings) == 1
    args, kwargs = warnings[0]
    assert "boom" in args  # provider name passed to the log record
    assert kwargs.get("exc_info") is True
