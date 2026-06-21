"""Name -> provider registry (phase 27 — market-lookalike discovery).

A flat module-level map from a provider ``name`` to the ``LookalikeProvider``
that serves it. Providers self-register at import time
(``registry.register(ApistemicProvider())`` at the bottom of ``apistemic``),
and the surface (``MarketLookalikeService`` in 27-03) imports the
``lookalike_providers`` subpackage so every provider module runs and registers
before the first lookup.

Registration is lazy by design — the registry module must NOT import the
provider modules itself (a provider imports ``base``, which would create a cycle
if the registry pulled the providers back in). This mirrors the phase-25
``source_adapters.registry`` discipline: the importer (the package
``__init__``) is what triggers registration, not the registry.

``active_provider()`` returns ``None`` — the ``provider_not_configured`` signal —
when no provider is registered OR none ``is_configured()``. ``None`` is the
graceful BUY-gate state the whole phase degrades to: NO crash, NO fake data,
NO paid call. Resolution order: env ``MARKET_LOOKALIKE_PROVIDER`` (explicit pick,
honored only if registered AND configured) -> else the first registered provider
whose ``is_configured()`` is True -> else ``None``.
"""

from __future__ import annotations

import logging
import os

from app.services.lookalike_providers.base import LookalikeProvider

logger = logging.getLogger(__name__)

# name -> provider. Populated at import time by each provider module's
# bottom-line ``register(...)`` call (e.g. ``apistemic`` registers ``apistemic``).
_PROVIDERS: dict[str, LookalikeProvider] = {}

# Env var an operator sets to pin a specific provider (explicit pick). Honored by
# ``active_provider()`` ONLY when the named provider is registered AND configured.
_PROVIDER_ENV = "MARKET_LOOKALIKE_PROVIDER"


def register(provider: LookalikeProvider) -> None:
    """Register ``provider`` under its ``name`` (last registration wins).

    Called once per provider module at import time. Idempotent for re-imports —
    re-registering the same name simply replaces the entry.
    """
    _PROVIDERS[provider.name] = provider


def get_provider(name: str) -> LookalikeProvider | None:
    """Return the provider registered under ``name``, or ``None`` if unknown."""
    return _PROVIDERS.get(name)


def provider_names() -> list[str]:
    """Return the sorted list of registered provider names."""
    return sorted(_PROVIDERS)


def _is_configured(provider: LookalikeProvider) -> bool:
    """``provider.is_configured()`` guarded so a misbehaving provider can't crash
    resolution. ``is_configured`` is contractually never-raise; this is the
    backstop that keeps the BUY-gate (``None``) intact regardless.
    """
    try:
        return bool(provider.is_configured())
    except Exception:
        # ``is_configured`` is contractually never-raise; if a provider violates that
        # we must NOT silently swallow it — log (with the provider name + traceback)
        # so the misbehaving provider is diagnosable, then keep the BUY-gate intact.
        logger.warning(
            "lookalike provider %r raised in is_configured() — treating as unconfigured",
            getattr(provider, "name", provider),
            exc_info=True,
        )
        return False


def active_provider() -> LookalikeProvider | None:
    """Resolve the provider the surface should use, or ``None`` if none is ready.

    Resolution order:

    1. env ``MARKET_LOOKALIKE_PROVIDER`` (explicit pick) — returned ONLY if that
       name is registered AND ``is_configured()``; otherwise fall through (an
       unregistered/unconfigured explicit pick yields ``None``, never a different
       provider).
    2. else the first registered provider (by registration map order) whose
       ``is_configured()`` is True.
    3. else ``None`` — the ``provider_not_configured`` BUY-gate signal: NO crash,
       NO fake data, NO paid call.
    """
    pinned = os.environ.get(_PROVIDER_ENV)
    if pinned:
        provider = _PROVIDERS.get(pinned)
        if provider is not None and _is_configured(provider):
            return provider
        return None

    for provider in _PROVIDERS.values():
        if _is_configured(provider):
            return provider
    return None
