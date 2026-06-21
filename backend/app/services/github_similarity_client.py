"""GitHubSimilarityClient — read-only similar-repo discovery on the PAT seam (Phase 24).

The discovery brain's *fetch* half. Given a seed ``owner/repo`` it surfaces
candidate similar repos with two research-backed signals
(``discovery-engine-design-phase24.md`` §"Signals ranked by value/cost"):

  * **S1 shared-topic** (REST ``search/repositories?q=topic:T``) — cheap, the MVP
    core. The seed's own topic set drives the query; candidates carry the
    intersection.
  * **S2 stargazer-overlap** (``/repos/{o}/{r}/stargazers`` →
    ``/users/{u}/starred``) — the precision signal. We *sample* the seed's
    stargazers (cap ``K``), fetch each sampled user's starred repos (cap ``M``),
    tally co-starred repos, and keep those above a ``min_shared`` threshold.

Two hard rules inherited from ``GitHubMonitorService`` (REQ-28):

  * **Single credential seam.** Every request reuses
    ``GitHubMonitorService._auth_headers()`` — the ONE place a PAT is turned into
    headers (``Bearer`` + ``Accept`` + ``X-GitHub-Api-Version``). When the token
    is unset it returns ``None`` and *every* public method here returns ``[]``
    immediately. We NEVER fall through to the unauthenticated 60/hr path.
  * **Rate-limit discipline.** A ``403``/``429`` (secondary / abuse limit) makes
    us back off — break the fan-out loop and return what we already have. Each
    per-candidate fetch is wrapped in its own ``try/except`` so one bad item
    never aborts the batch. A hard cap bounds total requests per call. The fan-out
    is sequential (no concurrency) to respect the secondary 100-concurrent limit.

Read-only: this client only ever issues GETs against search / repo / user
resources — it never touches the content-creation bucket. NO persistence here
(that is 24-03's ``DiscoveryService``); NO LLM (the ranker is deterministic).

HTTP uses ``httpx`` (the codebase's standard outbound client) — no new dependency.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.services.github_monitor_service import GitHubMonitorService
from app.services.github_service import GitHubService

logger = logging.getLogger(__name__)

# GitHub REST API root. Same host the rest of the backend already talks to.
_API_ROOT = "https://api.github.com"

# HTTP timeout for a single similarity GET (seconds). Short — every call is a
# cheap read, mirroring github_monitor_service._POLL_TIMEOUT.
_HTTP_TIMEOUT = 15.0

# Throttle status codes (secondary / abuse rate limit). Inherited verbatim from
# GitHubMonitorService.poll_source :239 — back off, return partial, never raise.
_THROTTLE_STATUS = (403, 429)

# --- S2 fan-out blast-radius caps (design §1.2 "purely on cost") -------------
# Sample at most K stargazers of the seed, fetch at most M starred repos for each
# sampled user, and never issue more than _MAX_REQUESTS GETs in a single overlap
# call (the run-level budget). All overridable per call for tests / tuning.
_DEFAULT_SAMPLE_STARGAZERS = 100  # K
_DEFAULT_PER_USER_REPOS = 100  # M
_DEFAULT_MIN_SHARED = 3
_MAX_REQUESTS = 120  # hard cap on total GETs per overlap call

# S1 default candidate cap.
_DEFAULT_MAX_RESULTS = 30

# S1 topic fan-out caps. GitHub's code search treats `topic:a topic:b` as AND
# (a repo must carry EVERY listed topic) — but the intent is "shares >= 1 topic"
# (OR). So we run one search per top-K topic (most-saturating topics first) and
# merge/dedupe candidates, tracking which topics each shares. ``_TOPIC_SEARCH_CAP``
# bounds the number of searches per seed (each is one request against the search
# bucket) regardless of how many topics the seed declares.
_TOPIC_SEARCH_CAP = 5

# GitHub's per-page maximum for paginated list endpoints.
_PER_PAGE = 100


class GitHubSimilarityClient:
    """Read-only similar-repo finder built on the authenticated PAT seam.

    Every public method short-circuits to ``[]`` when no credential is
    configured (``_auth_headers()`` is ``None``) — it NEVER issues an
    unauthenticated request.
    """

    # -- credential seam (reuse, do not reconstruct) ---------------------

    @staticmethod
    def _headers() -> Optional[dict]:
        """The single credential seam — delegates to ``GitHubMonitorService``.

        Returns the authenticated header dict, or ``None`` when ``GITHUB_TOKEN``
        is unset. Public methods treat ``None`` as "skip, return ``[]``".

        A fresh dict per call so a caller may safely add request-scoped headers
        (e.g. a topic preview ``Accept``) without mutating shared state.
        """
        return GitHubMonitorService._auth_headers()

    # -- url derivation --------------------------------------------------

    @staticmethod
    def parse_seed(url: str) -> tuple[str, str]:
        """``(owner, repo)`` from a seed repo URL — the universal extractor.

        Delegates to ``GitHubService.parse_repo_url`` (github_service.py:25) so
        seed URLs (the project's ``kind == 'github_repo'`` competitor_source
        rows) parse identically everywhere. Raises ``ValueError`` on a non
        ``owner/repo`` URL, matching ``parse_repo_url``.
        """
        return GitHubService.parse_repo_url(url)

    # -- internal GET helper (throttle-aware, never raises) --------------

    @staticmethod
    def _get(url: str, headers: dict, *, params: Optional[dict] = None) -> Optional[httpx.Response]:
        """Authenticated GET with poll_source's discipline.

        Returns the ``httpx.Response`` on a normal completion (including non-200,
        which the caller inspects), or ``None`` on a transport error so the
        caller can skip this single item without aborting the batch. A throttle
        (403/429) is returned as a *response* (status preserved) so the caller
        can distinguish "back off the whole loop" from "skip one item".
        """
        try:
            return httpx.get(
                url,
                headers=headers,
                params=params,
                timeout=_HTTP_TIMEOUT,
                follow_redirects=False,
            )
        except httpx.HTTPError:
            # Transport error (DNS / timeout / connection) — a PER-ITEM failure,
            # not a rate limit. Mirror poll_source :225-230: skip, keep going.
            logger.warning("similarity GET transport error for %s", url, exc_info=True)
            return None

    @staticmethod
    def _is_throttled(resp: Optional[httpx.Response]) -> bool:
        """True when a response is a secondary-rate-limit throttle (403/429)."""
        return resp is not None and resp.status_code in _THROTTLE_STATUS

    @staticmethod
    def _json_or_none(resp: httpx.Response):
        """Parse a JSON body, returning ``None`` on a non-JSON / empty body."""
        try:
            return resp.json()
        except (ValueError, TypeError):
            return None

    # -- repo metadata ---------------------------------------------------

    @classmethod
    def repo_metadata(cls, owner: str, repo: str) -> Optional[dict]:
        """``GET repos/{owner}/{repo}`` via the authenticated seam.

        Re-fetches the repo through ``_auth_headers`` (NOT the unauthenticated
        ``github_service.validate_repo_url`` path) so it benefits from the 5,000
        req/hr PAT budget. Returns a trimmed dict
        ``{owner, repo, url, topics, language, stargazers_count, archived,
        fork}`` for the seed, or ``None`` when the token is unset, the request
        errors, or GitHub answers non-200.

        ``topics`` come from the repo object's ``topics`` array, available with
        the standard ``application/vnd.github+json`` accept on a pinned API
        version (no preview header needed).
        """
        headers = cls._headers()
        if headers is None:
            return None

        resp = cls._get(f"{_API_ROOT}/repos/{owner}/{repo}", headers)
        if resp is None or resp.status_code != 200:
            return None
        body = cls._json_or_none(resp)
        if not isinstance(body, dict):
            return None

        return {
            "owner": owner,
            "repo": repo,
            "url": body.get("html_url") or f"https://github.com/{owner}/{repo}",
            "topics": list(body.get("topics") or []),
            "language": body.get("language"),
            "stargazers_count": int(body.get("stargazers_count") or 0),
            "archived": bool(body.get("archived")),
            "fork": bool(body.get("fork")),
        }

    # -- S1: shared-topic search -----------------------------------------

    @classmethod
    def find_by_shared_topics(
        cls,
        owner: str,
        repo: str,
        *,
        max_results: int = _DEFAULT_MAX_RESULTS,
        topic_search_cap: int = _TOPIC_SEARCH_CAP,
    ) -> list[dict]:
        """S1 — candidates that share ≥1 topic with the seed (OR, not AND).

        Reads the seed's topics (via :meth:`repo_metadata`), then runs ONE
        ``GET search/repositories?q=topic:T&sort=stars`` PER topic (top
        ``topic_search_cap`` topics) and merges/dedupes the candidates, EXCLUDING
        the seed itself:

            {owner, repo, url, stargazers_count, language, topics, shared_topics}

        GitHub search ANDs space-joined ``topic:`` qualifiers (a repo must have
        EVERY listed topic), so a single combined query only surfaces repos
        sharing ALL the seed's topics — too strict for "shares ≥1 topic". Running
        a search per topic and unioning the results restores the OR semantics;
        ``shared_topics`` accumulates every seed topic a merged candidate matches.

        Each candidate dict's ``shared_topics`` reflects the full case-insensitive
        intersection with the seed's topics (recomputed on merge), not just the
        topic whose search surfaced it. Returns ``[]`` when the token is unset,
        the seed has no topics, or every search errors / throttles. A throttle on
        any topic search backs off the remaining topic searches (never raises).
        """
        headers = cls._headers()
        if headers is None:
            return []

        seed = cls.repo_metadata(owner, repo)
        if seed is None:
            return []
        seed_topics = [t for t in (seed.get("topics") or []) if t]
        if not seed_topics:
            return []
        seed_topic_set = {t.lower() for t in seed_topics}
        seed_key = (owner.lower(), repo.lower())

        # One search per top-K topic (OR), most-starred first. Dedupe across
        # searches keyed by lowercased owner/repo; recompute shared_topics on
        # merge so a candidate that surfaced via several topic searches reports
        # the full intersection.
        merged: dict[tuple[str, str], dict] = {}
        for topic in seed_topics[: max(1, topic_search_cap)]:
            resp = cls._get(
                f"{_API_ROOT}/search/repositories",
                headers,
                params={
                    "q": f"topic:{topic}",
                    "sort": "stars",
                    "order": "desc",
                    "per_page": _PER_PAGE,
                },
            )
            if resp is None or resp.status_code != 200:
                if cls._is_throttled(resp):
                    logger.warning(
                        "topic search throttled (HTTP %s) for %s/%s — backing off remaining topics",
                        resp.status_code,
                        owner,
                        repo,
                    )
                    break  # back off the rest of the topic fan-out
                continue  # a non-throttle miss on one topic: skip it, try the next
            body = cls._json_or_none(resp)
            items = (body or {}).get("items") if isinstance(body, dict) else None
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                cand = cls._candidate_from_search_item(item, seed_topic_set)
                if cand is None:
                    continue
                key = (cand["owner"].lower(), cand["repo"].lower())
                if key == seed_key:
                    continue  # exclude the seed itself
                if key not in merged:
                    merged[key] = cand

        # Highest-starred first across the merged set, then cap.
        candidates = sorted(
            merged.values(), key=lambda c: c.get("stargazers_count") or 0, reverse=True
        )
        return candidates[:max_results]

    @staticmethod
    def _candidate_from_search_item(item: dict, seed_topic_set: set[str]) -> Optional[dict]:
        """Map one ``search/repositories`` item → a candidate dict, or ``None``.

        Computes ``shared_topics`` (case-insensitive intersection, preserving the
        candidate's own casing) so the ranker / "why" gets readable topic names.
        """
        full_name = item.get("full_name") or ""
        owner_login = (item.get("owner") or {}).get("login")
        name = item.get("name")
        if "/" in full_name:
            o, _, r = full_name.partition("/")
            owner_login = owner_login or o
            name = name or r
        if not owner_login or not name:
            return None

        cand_topics = [t for t in (item.get("topics") or []) if t]
        shared = [t for t in cand_topics if t.lower() in seed_topic_set]
        return {
            "owner": owner_login,
            "repo": name,
            "url": item.get("html_url") or f"https://github.com/{owner_login}/{name}",
            "stargazers_count": int(item.get("stargazers_count") or 0),
            # ``language`` feeds the ranker's same-language prior — omitting it
            # left that prior dead at 0.0 for every search candidate.
            "language": item.get("language"),
            "topics": cand_topics,
            "shared_topics": shared,
            "archived": bool(item.get("archived")),
            "fork": bool(item.get("fork")),
        }

    # -- S2: stargazer overlap -------------------------------------------

    @classmethod
    def find_by_stargazer_overlap(
        cls,
        owner: str,
        repo: str,
        *,
        sample_stargazers: int = _DEFAULT_SAMPLE_STARGAZERS,
        per_user_repos: int = _DEFAULT_PER_USER_REPOS,
        min_shared: int = _DEFAULT_MIN_SHARED,
        max_requests: int = _MAX_REQUESTS,
    ) -> list[dict]:
        """S2 — candidates co-starred by the seed's stargazers (precision signal).

        Pages the seed's stargazers (cap ``sample_stargazers`` = K), then for each
        sampled stargazer fetches their starred repos (cap ``per_user_repos`` = M),
        tallying co-starred repos. Keeps those with ``shared_stargazers >=
        min_shared`` and returns:

            {owner, repo, url, shared_stargazers, shared_stargazer_logins: [...]}

        Discipline: sequential (no concurrency), a hard ``max_requests`` budget on
        total GETs, and a 403/429 anywhere → back off (break the loop) and return
        the partial tally. One bad per-user fetch is skipped, never fatal. Returns
        ``[]`` when the token is unset.
        """
        headers = cls._headers()
        if headers is None:
            return []

        request_budget = max(1, max_requests)
        requests_made = 0

        # --- page the seed's stargazers (cap K) -------------------------
        stargazers: list[str] = []
        page = 1
        while len(stargazers) < sample_stargazers and requests_made < request_budget:
            resp = cls._get(
                f"{_API_ROOT}/repos/{owner}/{repo}/stargazers",
                headers,
                params={"per_page": _PER_PAGE, "page": page},
            )
            requests_made += 1
            if cls._is_throttled(resp):
                logger.warning("stargazer paging throttled for %s/%s — backing off", owner, repo)
                break  # back off; return whatever we gathered so far
            if resp is None or resp.status_code != 200:
                break
            body = cls._json_or_none(resp)
            if not isinstance(body, list) or not body:
                break  # no more pages
            for entry in body:
                login = entry.get("login") if isinstance(entry, dict) else None
                if login:
                    stargazers.append(login)
                if len(stargazers) >= sample_stargazers:
                    break
            if len(body) < _PER_PAGE:
                break  # last page
            page += 1

        if not stargazers:
            return []

        # --- fan out: each sampled stargazer's starred repos (cap M) -----
        # tally[(owner_lc, repo_lc)] -> {"owner", "repo", "url", "count", "logins"}
        tally: dict[tuple[str, str], dict] = {}
        seed_key = (owner.lower(), repo.lower())
        for login in stargazers:
            if requests_made >= request_budget:
                break
            try:
                throttled = cls._tally_user_starred(login, headers, tally, seed_key, per_user_repos)
            except Exception:  # noqa: BLE001 — isolate one bad stargazer
                logger.warning("similarity: starred fetch raised for user %s", login, exc_info=True)
                requests_made += 1
                continue
            requests_made += throttled.get("requests", 1)
            if throttled.get("throttled"):
                logger.warning(
                    "starred fan-out throttled — backing off after %d requests", requests_made
                )
                break  # back off; return the partial tally

        results: list[dict] = []
        for entry in tally.values():
            if entry["count"] >= min_shared:
                results.append(
                    {
                        "owner": entry["owner"],
                        "repo": entry["repo"],
                        "url": entry["url"],
                        "shared_stargazers": entry["count"],
                        "shared_stargazer_logins": entry["logins"][:10],
                    }
                )
        results.sort(key=lambda c: c["shared_stargazers"], reverse=True)
        return results

    @classmethod
    def _tally_user_starred(
        cls,
        login: str,
        headers: dict,
        tally: dict[tuple[str, str], dict],
        seed_key: tuple[str, str],
        per_user_repos: int,
    ) -> dict:
        """Fetch one user's starred repos (cap M) and fold them into ``tally``.

        Returns ``{"requests": int, "throttled": bool}`` so the caller can keep
        the run-level request budget and stop the whole fan-out on a 403/429.
        Excludes the seed repo itself from the tally.
        """
        requests = 0
        collected = 0
        page = 1
        while collected < per_user_repos:
            resp = cls._get(
                f"{_API_ROOT}/users/{login}/starred",
                headers,
                params={"per_page": _PER_PAGE, "page": page},
            )
            requests += 1
            if cls._is_throttled(resp):
                return {"requests": requests, "throttled": True}
            if resp is None or resp.status_code != 200:
                return {"requests": requests, "throttled": False}
            body = cls._json_or_none(resp)
            if not isinstance(body, list) or not body:
                return {"requests": requests, "throttled": False}
            for item in body:
                if not isinstance(item, dict):
                    continue
                key, meta = cls._starred_key(item)
                if key is None or key == seed_key:
                    continue
                bucket = tally.get(key)
                if bucket is None:
                    bucket = {**meta, "count": 0, "logins": []}
                    tally[key] = bucket
                bucket["count"] += 1
                bucket["logins"].append(login)
                collected += 1
                if collected >= per_user_repos:
                    break
            if len(body) < _PER_PAGE:
                return {"requests": requests, "throttled": False}
            page += 1
        return {"requests": requests, "throttled": False}

    @staticmethod
    def _starred_key(item: dict) -> tuple[Optional[tuple[str, str]], dict]:
        """``((owner_lc, repo_lc), meta)`` for a starred-repo item, or ``(None, {})``."""
        full_name = item.get("full_name") or ""
        owner_login = (item.get("owner") or {}).get("login")
        name = item.get("name")
        if "/" in full_name:
            o, _, r = full_name.partition("/")
            owner_login = owner_login or o
            name = name or r
        if not owner_login or not name:
            return None, {}
        meta = {
            "owner": owner_login,
            "repo": name,
            "url": item.get("html_url") or f"https://github.com/{owner_login}/{name}",
        }
        return (owner_login.lower(), name.lower()), meta
