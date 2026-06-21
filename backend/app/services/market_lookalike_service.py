"""MarketLookalikeService — provider-aware market-lookalike discovery (phase 27-03).

A THIN orchestrator over two already-shipped layers, owning NO persistence and NO
promote logic of its own:

1. the 27-01 provider registry (``lookalike_providers.registry.active_provider``) —
   resolves the configured market-lookalike provider, or ``None`` (the BUY-gate)
   when none is keyed;
2. the P2 discovery surface (``app.db.discovery_suggestions`` +
   ``DiscoveryService.promote_suggestion`` / ``.dismiss_suggestion``) — the existing
   idempotent upsert + sticky-verdict + concurrency-safe promote/dismiss machinery.

``scan_project`` resolves ``active_provider()``; with no provider it short-circuits
to ``{"provider": None, "outcome": "not_configured", ...}`` — NO scan, NO error, NO
paid call (the operator-visible "configure a provider" CTA). With a configured
provider it calls ``provider.find_lookalikes(seed)`` and, on ``outcome == "ok"``,
upserts each ``Candidate`` into the EXISTING ``discovery_suggestion`` table with
``kind="company"``, ``owner=provider.name``, ``repo=<normalized domain>`` —
repurposing the shipped ``UNIQUE(project_id, candidate_owner, candidate_repo)`` as
"one suggestion per (project, provider, domain)". This inherits the P2 idempotency
+ sticky-verdict (a re-scan UPSERTs and never resurrects a ``dismissed`` / ``added``
row) for free, with ZERO migrations (``kind`` is free TEXT).

``promote_suggestion`` / ``dismiss_suggestion`` delegate STRAIGHT THROUGH to
``DiscoveryService`` (already project-scoped, idempotent, concurrency-safe,
404/409-correct). A promoted lookalike lands as a ``competitor_source`` on the
``product_url`` lane via ``add_source``'s ``detect_kind`` fallback.

NO DB code, NO LLM, deterministic. Ruff line-length=100 / py310.
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse

from app.db import discovery_suggestions
from app.services.discovery_service import DiscoveryService

# The suggestion kinds this service surfaces in the market-lookalike queue. A scan
# writes ``"company"``; ``"product"`` is reserved for the same lane (both excluded
# github_repo discovery rows from the market queue).
_MARKET_KINDS = ("company", "product")


def _domain_of(url: str) -> Optional[str]:
    """Return the normalized host of ``url`` (lowercased, ``www.``-stripped), or None.

    Pure / deterministic. A url with no resolvable host (empty, scheme-less junk)
    yields ``None`` so the caller can skip a candidate that carries no domain — the
    domain is the per-(project, provider) dedupe key.
    """
    if not url:
        return None
    parsed = urlparse(url if "://" in url else f"//{url}")
    host = (parsed.netloc or "").strip().lower()
    if host.startswith("www."):
        host = host[4:]
    # Drop any userinfo / port that slipped into netloc.
    host = host.split("@")[-1].split(":")[0]
    return host or None


class MarketLookalikeService:
    """Provider-aware market-lookalike discovery over the P2 discovery surface.

    Stateless: every method is a ``@staticmethod`` keying off ``project_id``. NO
    DB code (delegates to the ``discovery_suggestions`` DAO), NO LLM — deterministic.
    """

    @staticmethod
    def scan_project(project_id: str, seed: Optional[str] = None) -> dict:
        """Resolve the provider, scan, and upsert lookalikes into the P2 surface.

        Returns a dict shaped ``{"provider", "outcome", "scanned", "suggestions"}``
        (plus ``"detail"`` on a non-ok outcome). The outcomes:

          * no provider configured → ``{"provider": None, "outcome":
            "not_configured", "scanned": 0, "suggestions": []}`` — the BUY-gate
            short-circuit: NO scan, NO error, NO paid call (the surface renders the
            "configure a provider" CTA).
          * no ``seed`` → ``outcome="error"``, ``detail="no seed"`` (MVP: the route
            passes the operator's seed; auto-deriving a seed from the project's own
            product domain / watched ``product_url`` source is a later refinement).
          * provider returns a non-ok outcome (``not_configured`` / ``throttled`` /
            ``error``) → that tagged outcome is passed straight up with
            ``suggestions: []`` and NO rows written (no fake data).
          * ``outcome="ok"`` → each ``Candidate`` is upserted via the EXISTING
            ``discovery_suggestions.upsert_suggestion`` (``kind="company"``,
            ``owner=provider.name``, ``repo=<normalized domain>``), and the
            ``suggested`` market queue is returned.
        """
        # Import the subpackage first so every provider module self-registers
        # before resolution (the CompetitorPollService-imports-source_adapters
        # discipline) — otherwise ``apistemic`` would not be in the registry.
        import app.services.lookalike_providers as _lp  # noqa: F401 (register-on-import)
        from app.services.lookalike_providers import registry

        provider = registry.active_provider()
        if provider is None:
            # BUY-gate: no provider keyed. No scan, no error, no paid call.
            return {
                "provider": None,
                "outcome": "not_configured",
                "scanned": 0,
                "suggestions": [],
            }

        if not seed:
            # MVP: the route supplies the operator's seed; we never invent one.
            return {
                "provider": provider.name,
                "outcome": "error",
                "detail": "no seed",
                "scanned": 0,
                "suggestions": [],
            }

        result = provider.find_lookalikes(seed)
        if result.outcome != "ok":
            # Pass the tagged outcome straight up — not_configured / throttled /
            # error all render gracefully; write NO rows, return NO fake data.
            return {
                "provider": provider.name,
                "outcome": result.outcome,
                "detail": result.detail,
                "scanned": 0,
                "suggestions": [],
            }

        for cand in result.candidates:
            domain = _domain_of(cand.url)
            if not domain:
                # No dedupe key — skip a candidate that carries no domain.
                continue
            evidence = cand.evidence or {}
            # The EXISTING P2 DAO — kind="company", owner=provider, repo=domain.
            # Repurposes UNIQUE(project_id, candidate_owner, candidate_repo) as
            # "one per (project, provider, domain)": zero migration, inherits the
            # idempotency + sticky verdict for free. ``score`` is NULL-accepting.
            discovery_suggestions.upsert_suggestion(
                project_id,
                owner=provider.name,
                repo=domain,
                url=cand.url,
                kind="company",
                score=cand.score,
                reason=evidence.get("reason"),
                evidence=cand.evidence,
            )

        return {
            "provider": provider.name,
            "outcome": "ok",
            "scanned": len(result.candidates),
            "suggestions": MarketLookalikeService.list_suggestions(project_id),
        }

    @staticmethod
    def list_suggestions(project_id: str) -> list[dict]:
        """Return the project's market-lookalike queue (``suggested`` only).

        Delegates to ``DiscoveryService.list_suggestions`` and filters to the
        market kinds (``company`` / ``product``) so github_repo discovery rows do
        NOT bleed into the market-lookalike queue.
        """
        rows = DiscoveryService.list_suggestions(project_id, statuses=["suggested"])
        return [r for r in rows if r.get("kind") in _MARKET_KINDS]

    @staticmethod
    def promote_suggestion(project_id: str, suggestion_id: str) -> dict:
        """Promote a market lookalike into a watched ``competitor_source``.

        STRAIGHT THROUGH to ``DiscoveryService.promote_suggestion`` (already
        claim → ``add_source(origin="discovery")`` → complete, concurrency-safe,
        404/409-correct). ``add_source`` lands the source as ``product_url`` via
        ``detect_kind``'s fallback. Returns ``{"source", "suggestion"}``.
        """
        return DiscoveryService.promote_suggestion(project_id, suggestion_id)

    @staticmethod
    def dismiss_suggestion(project_id: str, suggestion_id: str) -> dict:
        """Dismiss a market lookalike — STRAIGHT THROUGH to ``DiscoveryService``.

        ``DiscoveryService.dismiss_suggestion`` is project-scoped, sticky on
        re-scan, and claim-safe (409 if mid-promotion). Returns ``{"suggestion"}``.
        """
        return DiscoveryService.dismiss_suggestion(project_id, suggestion_id)
