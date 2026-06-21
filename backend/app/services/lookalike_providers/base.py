"""Lookalike-provider contract: ``LookalikeProvider`` Protocol + ``Candidate`` +
``LookalikeResult`` (phase 27 — market-lookalike discovery).

This is the structural twin of ``source_adapters.base.SourceAdapter`` (phase 25):
a ``typing.Protocol`` (structural, not nominal) — any object with a ``name`` attr
and ``is_configured`` / ``find_lookalikes`` methods satisfies it. Where the
source adapter's ``has_credential`` gates whether the poller may fetch at all,
``LookalikeProvider.is_configured`` gates whether the surface may call the
provider's (possibly paid) lookalike endpoint: no key -> the surface
short-circuits to ``outcome='not_configured'`` and NEVER makes the http call.

* ``LookalikeOutcome`` — the tagged outcome a ``find_lookalikes`` carries.
  ``not_configured`` is the BUY-gate state (no API key): the operator-visible
  "configure a provider" path, NOT an error. ``throttled`` / ``error`` are
  transient per-call conditions.
* ``Candidate`` — one lookalike company: ``url`` / ``name`` plus a NULL-accepting
  ``score`` (a missing score NEVER blocks a candidate — the P2 ranker NULL-safe
  contract) and an ``evidence`` "why" blob the review queue renders as a chip.
* ``LookalikeResult`` — a tagged outcome plus the candidates; only ``ok`` carries
  candidates. ``detail`` is a human note (for not_configured/error) and MUST hold
  NO secrets.
* ``LookalikeProvider`` — the structural contract every concrete provider (the
  Apistemic adapter in 27-02) satisfies. ``find_lookalikes`` is one read-only
  lookup that NEVER raises (the ``job_board.fetch`` discipline — transport/parse
  failures come back as ``outcome='error'``).

No DB, no http here: this is the pure interface seam. Ruff line-length=100 / py310.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional, Protocol, runtime_checkable

# Outcome tags a provider's ``find_lookalikes`` returns. ``ok`` is the only one
# that carries candidates. ``not_configured`` is the BUY-gate state (no API key)
# — the operator-visible "configure a provider" path, NOT an error.
# ``throttled`` (rate-limit/429) and ``error`` (transport/parse) are transient
# per-call conditions the surface logs and degrades past — never a crash.
LookalikeOutcome = Literal["ok", "not_configured", "throttled", "error"]


@dataclass(frozen=True)
class Candidate:
    """One lookalike company a provider returns.

    ``url`` / ``name`` identify the company. ``score`` is NULL-accepting — a
    missing score NEVER blocks a candidate (the P2 ranker NULL-safe contract;
    the never-block-on-optional-field rule). ``evidence`` is the provider's
    "why" blob (``{provider, reason, domain, ...}``) rendered as the
    review-queue chip.
    """

    url: str
    name: str
    score: Optional[float] = None
    evidence: dict = field(default_factory=dict)


@dataclass(frozen=True)
class LookalikeResult:
    """One ``find_lookalikes`` result — a tagged outcome plus its candidates.

    Only ``outcome='ok'`` carries candidates; every other outcome leaves
    ``candidates`` empty. ``detail`` is a human note for not_configured/error
    surfaces and MUST contain NO secrets. ``not_configured`` is the BUY-gate
    state, NOT an error.
    """

    outcome: LookalikeOutcome
    candidates: list[Candidate] = field(default_factory=list)
    detail: Optional[str] = None


@runtime_checkable
class LookalikeProvider(Protocol):
    """Structural contract every market-lookalike provider satisfies.

    ``name`` is the registry key (the explicit-pick value of
    ``MARKET_LOOKALIKE_PROVIDER``). ``is_configured`` is the has-credential gate
    (the twin of ``SourceAdapter.has_credential``): True ONLY when the provider
    holds its key/credential; no key -> the surface short-circuits to
    ``not_configured`` and NEVER calls the paid endpoint. ``is_configured`` must
    itself never raise. ``find_lookalikes`` does exactly one read-only lookup of
    a domain/product-URL ``seed`` and returns a tagged ``LookalikeResult``;
    returns ``outcome='not_configured'`` when ``is_configured()`` is False and
    NEVER raises — transport/parse failures come back as ``outcome='error'``.
    """

    name: str

    def is_configured(self) -> bool:
        """True only when the provider holds the credential it needs to call."""
        ...

    def find_lookalikes(self, seed: str, *, limit: int = 20) -> LookalikeResult:
        """One read-only lookup of ``seed``; tagged result; never raises."""
        ...
