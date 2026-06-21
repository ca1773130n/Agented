"""Tests for ``ApistemicProvider`` (phase 27, plan 02) — ZERO live network.

Every case mocks ``apistemic.httpx.get`` (the ``job_board`` provider-test
discipline) so no paid call is ever made. The headline invariant: with
``APISTEMIC_API_KEY`` unset ``find_lookalikes`` returns ``not_configured`` and
makes NO httpx call (the BUY gate). With the key set, every HTTP/transport/parse
path collapses to a tagged outcome and ``find_lookalikes`` NEVER raises; the
defensive ``_normalize`` yields ``[]`` (never a 500) on a junk payload.
"""

from __future__ import annotations

import httpx
import pytest

from app.services.lookalike_providers import apistemic, registry
from app.services.lookalike_providers.apistemic import (
    APISTEMIC_API_KEY_ENV,
    ApistemicProvider,
    _extract_domain,
    _normalize,
)


class _FakeResponse:
    """Minimal stand-in for an ``httpx.Response`` — status + a ``json()`` hook."""

    def __init__(self, status_code: int, json_data=None, json_raises=False):
        self.status_code = status_code
        self._json_data = json_data
        self._json_raises = json_raises

    def json(self):
        if self._json_raises:
            raise ValueError("not JSON")
        return self._json_data


@pytest.fixture
def provider() -> ApistemicProvider:
    return ApistemicProvider()


# --- registration --------------------------------------------------------------


def test_apistemic_self_registers():
    """Importing the package makes 'apistemic' a live registry name."""
    assert "apistemic" in registry.provider_names()
    assert isinstance(registry.get_provider("apistemic"), ApistemicProvider)


# --- the BUY gate: key unset -> not_configured, ZERO httpx calls ----------------


def test_unset_key_is_not_configured(provider, monkeypatch):
    monkeypatch.delenv(APISTEMIC_API_KEY_ENV, raising=False)
    assert provider.is_configured() is False


def test_unset_key_returns_not_configured_with_no_call(provider, monkeypatch):
    monkeypatch.delenv(APISTEMIC_API_KEY_ENV, raising=False)
    called = {"n": 0}

    def _boom(*args, **kwargs):
        called["n"] += 1
        raise AssertionError("httpx.get must NOT be called when key is unset")

    monkeypatch.setattr(apistemic.httpx, "get", _boom)

    result = provider.find_lookalikes("https://acme.com/x")
    assert result.outcome == "not_configured"
    assert result.candidates == []
    assert called["n"] == 0  # the BUY gate — no unauth paid call.


def test_blank_key_is_not_configured(provider, monkeypatch):
    monkeypatch.setenv(APISTEMIC_API_KEY_ENV, "   ")
    assert provider.is_configured() is False


# --- key set: outcome mapping (all mocked, never live) -------------------------


def test_set_key_is_configured(provider, monkeypatch):
    monkeypatch.setenv(APISTEMIC_API_KEY_ENV, "sekret")
    assert provider.is_configured() is True


def test_ok_maps_candidates(provider, monkeypatch):
    monkeypatch.setenv(APISTEMIC_API_KEY_ENV, "sekret")
    payload = [
        {"website": "https://beta.io", "name": "Beta", "score": 0.8},
        {"domain": "gamma.dev", "name": "Gamma"},
    ]
    monkeypatch.setattr(apistemic.httpx, "get", lambda *a, **k: _FakeResponse(200, payload))

    result = provider.find_lookalikes("https://acme.com")
    assert result.outcome == "ok"
    assert len(result.candidates) == 2

    beta = result.candidates[0]
    assert beta.url == "https://beta.io"
    assert beta.name == "Beta"
    assert beta.score == 0.8
    assert beta.evidence["provider"] == "apistemic"
    assert beta.evidence["domain"] == "beta.io"

    gamma = result.candidates[1]
    # bare domain promoted to an absolute https url; missing score -> None.
    assert gamma.url == "https://gamma.dev"
    assert gamma.name == "Gamma"
    assert gamma.score is None


def test_ok_excludes_seed_domain(provider, monkeypatch):
    monkeypatch.setenv(APISTEMIC_API_KEY_ENV, "sekret")
    payload = [
        {"website": "https://acme.com", "name": "Acme"},  # the seed itself
        {"domain": "delta.io", "name": "Delta"},
    ]
    monkeypatch.setattr(apistemic.httpx, "get", lambda *a, **k: _FakeResponse(200, payload))

    result = provider.find_lookalikes("https://www.acme.com/pricing")
    assert result.outcome == "ok"
    assert [c.evidence["domain"] for c in result.candidates] == ["delta.io"]


def test_ok_results_under_dict_key(provider, monkeypatch):
    monkeypatch.setenv(APISTEMIC_API_KEY_ENV, "sekret")
    payload = {"competitors": [{"domain": "epsilon.io", "title": "Epsilon"}]}
    monkeypatch.setattr(apistemic.httpx, "get", lambda *a, **k: _FakeResponse(200, payload))

    result = provider.find_lookalikes("acme.com")
    assert result.outcome == "ok"
    assert result.candidates[0].name == "Epsilon"


def test_limit_is_capped(provider, monkeypatch):
    monkeypatch.setenv(APISTEMIC_API_KEY_ENV, "sekret")
    payload = [{"domain": f"co{i}.com", "name": f"Co{i}"} for i in range(10)]
    monkeypatch.setattr(apistemic.httpx, "get", lambda *a, **k: _FakeResponse(200, payload))

    result = provider.find_lookalikes("acme.com", limit=3)
    assert result.outcome == "ok"
    assert len(result.candidates) == 3


def test_401_is_not_configured(provider, monkeypatch):
    monkeypatch.setenv(APISTEMIC_API_KEY_ENV, "badkey")
    monkeypatch.setattr(apistemic.httpx, "get", lambda *a, **k: _FakeResponse(401))
    result = provider.find_lookalikes("acme.com")
    assert result.outcome == "not_configured"


def test_403_is_not_configured(provider, monkeypatch):
    monkeypatch.setenv(APISTEMIC_API_KEY_ENV, "badkey")
    monkeypatch.setattr(apistemic.httpx, "get", lambda *a, **k: _FakeResponse(403))
    result = provider.find_lookalikes("acme.com")
    assert result.outcome == "not_configured"


def test_429_is_throttled(provider, monkeypatch):
    monkeypatch.setenv(APISTEMIC_API_KEY_ENV, "sekret")
    monkeypatch.setattr(apistemic.httpx, "get", lambda *a, **k: _FakeResponse(429))
    result = provider.find_lookalikes("acme.com")
    assert result.outcome == "throttled"


def test_500_is_error(provider, monkeypatch):
    monkeypatch.setenv(APISTEMIC_API_KEY_ENV, "sekret")
    monkeypatch.setattr(apistemic.httpx, "get", lambda *a, **k: _FakeResponse(500))
    result = provider.find_lookalikes("acme.com")
    assert result.outcome == "error"


def test_transport_error_is_error(provider, monkeypatch):
    monkeypatch.setenv(APISTEMIC_API_KEY_ENV, "sekret")

    def _raise(*a, **k):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(apistemic.httpx, "get", _raise)
    result = provider.find_lookalikes("acme.com")
    assert result.outcome == "error"  # never propagates


def test_malformed_json_is_error(provider, monkeypatch):
    monkeypatch.setenv(APISTEMIC_API_KEY_ENV, "sekret")
    monkeypatch.setattr(
        apistemic.httpx, "get", lambda *a, **k: _FakeResponse(200, json_raises=True)
    )
    result = provider.find_lookalikes("acme.com")
    assert result.outcome == "error"


def test_seed_without_domain_is_error(provider, monkeypatch):
    monkeypatch.setenv(APISTEMIC_API_KEY_ENV, "sekret")
    called = {"n": 0}

    def _boom(*a, **k):
        called["n"] += 1
        raise AssertionError("no call for an unresolvable seed")

    monkeypatch.setattr(apistemic.httpx, "get", _boom)
    result = provider.find_lookalikes("   ")
    assert result.outcome == "error"
    assert called["n"] == 0


# --- defensive _normalize: junk -> [] (never a 500) ----------------------------


@pytest.mark.parametrize("junk", [{}, {"weird": 1}, [], "nope", 42, None])
def test_normalize_on_junk_returns_empty(junk):
    assert _normalize(junk, "acme.com", limit=20) == []


def test_normalize_drops_item_without_usable_url():
    payload = [{"name": "NoUrl"}, {"domain": "good.io", "name": "Good"}]
    out = _normalize(payload, "acme.com", limit=20)
    assert [c.evidence["domain"] for c in out] == ["good.io"]


def test_normalize_falls_back_name_to_host():
    out = _normalize([{"domain": "noname.io"}], "acme.com", limit=20)
    assert out[0].name == "noname.io"
    assert out[0].evidence["reason"] == "Apistemic lookalike"


# --- _extract_domain ----------------------------------------------------------


def test_extract_domain_from_url():
    assert _extract_domain("https://www.acme.com/path") == "acme.com"


def test_extract_domain_from_bare_host():
    assert _extract_domain("acme.com") == "acme.com"


def test_extract_domain_empty():
    assert _extract_domain("   ") == ""
