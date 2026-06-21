"""Lookalike-provider layer (phase 27): pluggable market-lookalike providers.

Importing this package is the single trigger that registers every provider:
each provider module calls ``registry.register(...)`` at import time, so the
side-effect imports below make ``registry.active_provider()`` complete after one
``import app.services.lookalike_providers``. The surface
(``MarketLookalikeService`` in 27-03) imports the package for exactly this
reason — it never has to know the concrete provider modules.

Public contract lives in ``base`` (``LookalikeProvider`` / ``Candidate`` /
``LookalikeResult`` / ``LookalikeOutcome``) and ``registry`` (``register`` /
``get_provider`` / ``provider_names`` / ``active_provider``); both are safe to
import without the providers (no cycle).

NOTE: ``apistemic`` (27-02) self-registers via the side-effect import below, but
it is key-gated on ``APISTEMIC_API_KEY``: with the key UNSET its ``is_configured()``
is ``False``, so ``active_provider()`` resolves past it to ``None`` — the graceful
BUY-gate state (no crash, no fake data, no paid call) on every default/CI install.
"""

from __future__ import annotations

# Side-effect imports: importing each provider module runs its bottom-line
# ``register(...)`` so the name is live. ``apistemic`` registers ``apistemic`` —
# but it is key-gated (APISTEMIC_API_KEY), so with no key ``active_provider()``
# still resolves to ``None`` (the not_configured BUY-gate). Add future provider
# modules here as they land.
from app.services.lookalike_providers import (  # noqa: F401  (register-on-import)
    apistemic,
    base,
    registry,
)

__all__ = ["apistemic", "base", "registry"]
