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
from app.services.competitor_source_service import KIND_PRODUCT_URL, CompetitorSourceService
from app.services.discovery_service import DiscoveryService

# The suggestion kinds this service surfaces in the market-lookalike queue. A scan
# writes ``"company"``; ``"product"`` is reserved for the same lane (both excluded
# github_repo discovery rows from the market queue).
_MARKET_KINDS = ("company", "product")

# Namespace prefix stamped onto a company suggestion's ``candidate_owner`` so it can
# NEVER collide with a P2 github_repo row in the SHARED ``discovery_suggestion`` table
# (UNIQUE(project_id, candidate_owner, candidate_repo)). A github row keys off the bare
# repo owner (e.g. ``("acme", "widget")``); a company row keys off
# ``("lookalike:<provider>", "<domain>")`` — the two key spaces are disjoint, so a
# github suggestion and a company suggestion that would otherwise share (project, owner,
# repo) now coexist instead of clobbering each other. The promote path keys off
# ``candidate_url`` (unaffected by the owner namespace), and the UI renders the
# company/domain from ``candidate_repo`` / ``candidate_url`` (never the namespaced owner).
_OWNER_NS = "lookalike:"


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
    def _derive_seeds(project_id: str) -> list[str]:
        """Derive lookalike seed domains from the project's watched product sources.

        Mirrors the P2 discovery seed-derivation (``DiscoveryService.scan_project``
        turns ``kind=='github_repo'`` competitor_sources into github seeds): here we
        turn the project's ``kind=='product_url'`` competitor_sources into seed
        DOMAINS via the same URL→host parsing (``_domain_of``). De-duplicated,
        order-preserving. Empty list → the project has nothing to seed from.
        """
        seeds: list[str] = []
        seen: set[str] = set()
        for source in CompetitorSourceService.list_sources(project_id):
            if source.get("kind") != KIND_PRODUCT_URL:
                continue
            domain = _domain_of(source.get("url") or "")
            if domain and domain not in seen:
                seen.add(domain)
                seeds.append(domain)
        return seeds

    @staticmethod
    def scan_project(project_id: str, seed: Optional[str] = None) -> dict:
        """Resolve the provider, scan, and upsert lookalikes into the P2 surface.

        Returns a dict shaped ``{"provider", "outcome", "scanned", "suggestions"}``
        (plus ``"detail"`` on a non-ok outcome). The outcomes:

          * no provider configured → ``{"provider": None, "outcome":
            "not_configured", "scanned": 0, "suggestions": []}`` — the BUY-gate
            short-circuit: NO scan, NO error, NO paid call (the surface renders the
            "configure a provider" CTA).
          * no derivable seed (no ``product_url`` competitor_source to seed from, and
            no explicit ``seed`` passed) → ``{"outcome": "no_seed", "scanned": 0,
            "suggestions": []}`` — a GRACEFUL 200 (NOT an error/500): the surface
            renders the "add a product/company competitor source" hint.
          * provider returns a non-ok outcome (``not_configured`` / ``throttled`` /
            ``error``) → that tagged outcome is passed straight up with
            ``suggestions: []`` and NO rows written (no fake data).
          * ``outcome="ok"`` → each ``Candidate`` (across every derived seed) is
            upserted via the EXISTING ``discovery_suggestions.upsert_suggestion``
            (``kind="company"``, ``owner="lookalike:<provider>"``,
            ``repo=<normalized domain>``), and the ``suggested`` market queue is
            returned.

        ``seed`` (optional) overrides the derivation — when passed, it is used
        verbatim as the single seed; otherwise seeds are derived SERVER-SIDE from the
        project's ``product_url`` competitor_sources (mirroring P2 discovery). This
        lets the seedless UI call (``scan(projectId)``) work end-to-end.
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

        # An explicit seed overrides; otherwise derive seed domain(s) from the
        # project's watched product_url competitor_sources (mirror P2 discovery).
        seeds = [seed] if seed else MarketLookalikeService._derive_seeds(project_id)
        if not seeds:
            # No product_url source to seed from — graceful no-op, NOT an error.
            return {
                "provider": provider.name,
                "outcome": "no_seed",
                "detail": "add a product/company competitor source to seed lookalikes",
                "scanned": 0,
                "suggestions": [],
            }

        scanned = 0
        for one_seed in seeds:
            result = provider.find_lookalikes(one_seed)
            if result.outcome != "ok":
                # Pass the tagged outcome straight up — not_configured / throttled /
                # error all render gracefully; write NO rows, return NO fake data.
                # One bad seed aborts the scan (consistent with the MVP single-seed
                # contract); the operator retries once the provider recovers.
                return {
                    "provider": provider.name,
                    "outcome": result.outcome,
                    "detail": result.detail,
                    "scanned": 0,
                    "suggestions": [],
                }

            scanned += len(result.candidates)
            for cand in result.candidates:
                domain = _domain_of(cand.url)
                if not domain:
                    # No dedupe key — skip a candidate that carries no domain.
                    continue
                evidence = cand.evidence or {}
                # The EXISTING P2 DAO — kind="company", owner="lookalike:<provider>",
                # repo=domain. The NAMESPACED owner keeps the company key space
                # disjoint from P2 github_repo rows in the SHARED unique key
                # UNIQUE(project_id, candidate_owner, candidate_repo): zero migration,
                # inherits the idempotency + sticky verdict for free. ``score`` is
                # NULL-accepting.
                discovery_suggestions.upsert_suggestion(
                    project_id,
                    owner=f"{_OWNER_NS}{provider.name}",
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
            "scanned": scanned,
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
