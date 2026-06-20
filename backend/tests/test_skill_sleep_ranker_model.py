"""Tests for skill_sleep._resolve_ranker_model — backend-aware cheap-model
resolution. Regression: a single claude default passed a claude id to non-claude
judge_backends, recreating the provider/model mismatch the discovery fix removed."""

from __future__ import annotations

from app.services import skill_sleep_service as sss


def _patch_discovery(monkeypatch, fn):
    monkeypatch.setattr(
        "app.services.model_discovery_service.ModelDiscoveryService.cheap_model_for",
        classmethod(lambda cls, backend: fn(backend)),
    )


def test_override_wins(monkeypatch):
    _patch_discovery(monkeypatch, lambda b: "discovered")
    assert sss._resolve_ranker_model("explicit-model", "codex") == "explicit-model"


def test_discovery_wins_over_fallback(monkeypatch):
    _patch_discovery(monkeypatch, lambda b: "live-cheap")
    assert sss._resolve_ranker_model(None, "codex") == "live-cheap"


def test_fallback_is_backend_aware_when_discovery_none(monkeypatch):
    # Discovery unavailable (proxy down / unknown backend) -> per-backend pin,
    # NOT a claude id for a non-claude backend (the bug).
    _patch_discovery(monkeypatch, lambda b: None)
    assert sss._resolve_ranker_model(None, "claude") == "claude-haiku-4-5-20251001"
    assert sss._resolve_ranker_model(None, "codex") == "gpt-5.4-mini"
    assert sss._resolve_ranker_model(None, "gemini") == "gemini-2.5-flash-lite"
    assert sss._resolve_ranker_model(None, "opencode") == "auto"


def test_unknown_backend_falls_back_to_auto(monkeypatch):
    _patch_discovery(monkeypatch, lambda b: None)
    assert sss._resolve_ranker_model(None, "weird-backend") == "auto"
