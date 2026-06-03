"""Wave 77 — webhook + OAuth callback proxy endpoints (3 routes).

- /api/webhooks/github (POST) — GitHub PR + issue_comment receiver.
- /api/oauth-callback/{rest:path} (GET) — OAuth provider redirect proxy.
- / (POST) — generic JSON webhook receiver.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from http import HTTPStatus
from typing import Any

import httpx
from litestar import Request, Response, Router, get, post
from litestar.exceptions import (
    ClientException,
    HTTPException,
    NotFoundException,
)

from app.database import add_pr_review
from app.services.backend_cli_service import BackendCLIService
from app.services.execution_service import ExecutionService
from app.services.webhook_validation_service import WebhookValidationService

logger = logging.getLogger(__name__)


MAX_GITHUB_WEBHOOK_PAYLOAD_BYTES = 10 * 1024 * 1024
MAX_WEBHOOK_PAYLOAD_BYTES = 10 * 1024 * 1024
GITHUB_WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")

_repo_rate_limit_lock = threading.Lock()
_repo_last_event: dict[str, float] = {}
_REPO_RATE_LIMIT_SECONDS = 60

# Seen GitHub delivery / comment-dedup keys, bounded + insertion-ordered so we
# can evict the oldest. Blocks replay of a captured signed webhook (02 H2) and
# duplicate issue_comment dispatch (05 H2).
from collections import OrderedDict  # noqa: E402

_seen_delivery_keys: "OrderedDict[str, float]" = OrderedDict()
_SEEN_DELIVERY_MAX = 5000

_SLASH_COMMAND_PATTERN = re.compile(r"^/([a-z][a-z0-9_-]*)(?:\s|$)", re.IGNORECASE | re.MULTILINE)


def _is_duplicate_key(key: str) -> bool:
    """Record `key`; return True if it was already seen (replay/dup). Bounded."""
    if not key:
        return False
    with _repo_rate_limit_lock:
        if key in _seen_delivery_keys:
            return True
        _seen_delivery_keys[key] = time.time()
        while len(_seen_delivery_keys) > _SEEN_DELIVERY_MAX:
            _seen_delivery_keys.popitem(last=False)
    return False


def _repo_rate_limited(repo_full_name: str) -> bool:
    """Per-repo fixed-window rate limit; evicts stale entries so the dict can't
    grow without bound on attacker-influenced repo names (05 H2 / 05 L4)."""
    if not repo_full_name:
        return False
    now = time.time()
    with _repo_rate_limit_lock:
        for k in [k for k, t in _repo_last_event.items() if now - t > _REPO_RATE_LIMIT_SECONDS]:
            del _repo_last_event[k]
        last = _repo_last_event.get(repo_full_name, 0)
        if now - last < _REPO_RATE_LIMIT_SECONDS:
            return True
        _repo_last_event[repo_full_name] = now
        return False


# ===========================================================================
# /api/webhooks/github (POST)
# ===========================================================================


def _handle_issue_comment(data: Any) -> dict[str, Any]:
    if not data or not isinstance(data, dict):
        raise ClientException(detail="Content-Type must be application/json")

    issue = data.get("issue", {})
    if not issue.get("pull_request"):
        return {"message": "issue_comment on issue (not PR) ignored"}

    action = data.get("action", "")
    if action not in ("created", "edited"):
        return {"message": f"issue_comment action '{action}' ignored"}

    comment = data.get("comment", {})
    comment_body = comment.get("body", "") or ""
    commenter = comment.get("user", {}).get("login", "")
    repo = data.get("repository", {})
    repo_full_name = repo.get("full_name", "")
    repo_url = repo.get("html_url", "")

    matches = _SLASH_COMMAND_PATTERN.findall(comment_body)
    if not matches:
        return {"message": "issue_comment: no slash command"}

    # Parity with the PR path: per-repo rate limit + dedup so a comment can't
    # trigger unbounded fan-out or duplicate executions (05 H2).
    if _repo_rate_limited(repo_full_name):
        return {"message": "issue_comment: rate limited"}
    comment_id = comment.get("id")
    if comment_id is not None and _is_duplicate_key(
        f"comment:{repo_full_name}:{comment_id}:{action}"
    ):
        return {"message": "issue_comment: duplicate ignored"}

    commands = [f"/{m.lower()}" for m in matches]
    pr_url = issue.get("pull_request", {}).get("html_url", issue.get("html_url", ""))
    pr_number = issue.get("number")
    pr_title = issue.get("title", "")

    try:
        triggered = ExecutionService.dispatch_pr_comment_commands(
            repo_url=repo_url,
            commands=commands,
            pr_data={
                "pr_number": pr_number,
                "pr_title": pr_title,
                "pr_url": pr_url,
                "pr_author": issue.get("user", {}).get("login", ""),
                "repo_full_name": repo_full_name,
                "repo_url": repo_url,
                "commenter": commenter,
                "comment_body": comment_body,
                "commands": commands,
            },
        )
    except Exception:
        logger.exception("Error dispatching PR comment commands")
        raise HTTPException(status_code=500, detail="Internal server error") from None

    return {"message": "PR comment processed", "commands": commands, "triggered": triggered}


@post("/")
async def github_webhook(request: Request) -> Any:
    payload = await request.body()
    if len(payload) > MAX_GITHUB_WEBHOOK_PAYLOAD_BYTES:
        raise HTTPException(
            status_code=HTTPStatus.REQUEST_ENTITY_TOO_LARGE, detail="Payload too large"
        )

    # `WebhookValidationService.validate_github` expects a Flask request; call
    # the underlying signature check directly with the body + header we already
    # have. Mirrors the same secret-required + sha256 contract.
    if not GITHUB_WEBHOOK_SECRET:
        logger.warning("GitHub webhook signature verification failed: secret not configured")
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="GitHub webhook secret not configured",
        )
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not WebhookValidationService.validate_signature(
        payload, signature, GITHUB_WEBHOOK_SECRET, "sha256"
    ):
        logger.warning("GitHub webhook signature verification failed: invalid signature")
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN, detail="Invalid GitHub webhook signature"
        )

    # Replay protection: GitHub doesn't send a timestamp, but every delivery has
    # a unique X-GitHub-Delivery id — reject one we've already processed (02 H2).
    delivery_id = request.headers.get("X-GitHub-Delivery", "")
    if delivery_id and _is_duplicate_key(f"delivery:{delivery_id}"):
        logger.info("Ignoring duplicate GitHub delivery %s", delivery_id)
        return {"message": "duplicate delivery ignored"}

    event_type = request.headers.get("X-GitHub-Event", "")
    if event_type == "ping":
        return {"message": "pong"}

    try:
        data: Any = (await request.json()) if payload else None
    except Exception:
        data = None

    if event_type == "issue_comment":
        return _handle_issue_comment(data)

    if event_type != "pull_request":
        return {"message": f"Event type '{event_type}' ignored"}

    if data is None or not isinstance(data, dict):
        raise ClientException(detail="Content-Type must be application/json")

    action = data.get("action", "")
    if action not in ("opened", "synchronize", "reopened"):
        return {"message": f"PR action '{action}' ignored"}

    pr = data.get("pull_request", {})
    repo = data.get("repository", {})
    pr_number = pr.get("number")
    pr_title = pr.get("title", "")
    pr_url = pr.get("html_url", "")
    pr_author = pr.get("user", {}).get("login", "")
    repo_full_name = repo.get("full_name", "")
    repo_url = repo.get("html_url", "")

    if not all([pr_number, pr_url, repo_full_name]):
        raise ClientException(detail="Missing required PR data")

    now = time.time()
    with _repo_rate_limit_lock:
        last_event = _repo_last_event.get(repo_full_name, 0)
        if now - last_event < _REPO_RATE_LIMIT_SECONDS:
            retry_after = int(_REPO_RATE_LIMIT_SECONDS - (now - last_event)) + 1
            raise HTTPException(
                status_code=HTTPStatus.TOO_MANY_REQUESTS,
                detail={"message": "Rate limit: event ignored", "retry_after": retry_after},
            )
        _repo_last_event[repo_full_name] = now

    try:
        review_id = add_pr_review(
            project_name=repo_full_name,
            pr_number=pr_number,
            pr_url=pr_url,
            pr_title=pr_title,
            github_repo_url=repo_url,
            pr_author=pr_author,
        )
        triggered = ExecutionService.dispatch_github_event(
            repo_url,
            {
                "pr_number": pr_number,
                "pr_title": pr_title,
                "pr_url": pr_url,
                "pr_author": pr_author,
                "repo_full_name": repo_full_name,
                "repo_url": repo_url,
                "action": action,
            },
        )
        return {"message": "PR event processed", "review_id": review_id, "triggered": triggered}
    except Exception:
        logger.exception("GitHub webhook error")
        raise HTTPException(status_code=500, detail="Internal server error") from None


github_webhook_router = Router(
    path="/api/webhooks/github",
    route_handlers=[github_webhook],
)


# ===========================================================================
# /api/oauth-callback/{rest:path} (GET)
# ===========================================================================


@get("/{rest:path}", sync_to_thread=False)
def oauth_callback_proxy(rest: str, request: Request) -> Response:
    port = BackendCLIService.get_callback_port()
    query_string = request.url.query or ""
    target_url = f"http://127.0.0.1:{port}/{rest.lstrip('/')}"
    if query_string:
        target_url += f"?{query_string}"

    logger.info("OAuth callback proxy: forwarding to %s", target_url)
    try:
        # Don't follow redirects (05 M4): the loopback CLI server is the only
        # intended hop — following a 3xx would let it bounce httpx to an
        # arbitrary URL whose body we'd reflect to the unauthenticated caller.
        resp = httpx.get(target_url, timeout=15, follow_redirects=False)
        excluded_headers = {"transfer-encoding", "content-encoding", "connection"}
        headers = {k: v for k, v in resp.headers.items() if k.lower() not in excluded_headers}
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers=headers,
            media_type=resp.headers.get("content-type", "text/html"),
        )
    except httpx.ConnectError:
        logger.warning("OAuth callback proxy: CLI callback server not reachable on port %d", port)
        return Response(
            content=(
                "<html><body><h2>OAuth callback failed</h2>"
                "<p>The CLI login server is not running on this host. "
                "The login session may have expired or already completed.</p>"
                "</body></html>"
            ),
            status_code=502,
            media_type="text/html",
        )
    except Exception as exc:
        logger.error("OAuth callback proxy error: %s", exc, exc_info=True)
        return Response(
            content=(
                "<html><body><h2>OAuth callback error</h2>"
                "<p>An internal error occurred. Please try again.</p></body></html>"
            ),
            status_code=502,
            media_type="text/html",
        )


oauth_callback_router = Router(
    path="/api/oauth-callback",
    route_handlers=[oauth_callback_proxy],
)


# ===========================================================================
# / generic webhook (POST) — supports url_verification challenge
# ===========================================================================


@post("/")
async def generic_webhook(request: Request) -> Any:
    raw_payload = await request.body()
    if len(raw_payload) > MAX_WEBHOOK_PAYLOAD_BYTES:
        raise HTTPException(
            status_code=HTTPStatus.REQUEST_ENTITY_TOO_LARGE, detail="Payload too large"
        )

    signature_header = request.headers.get("X-Webhook-Signature-256", "")
    try:
        payload = await request.json() if raw_payload else None
    except Exception:
        raise ClientException(detail="Content-Type must be application/json") from None

    if not isinstance(payload, dict):
        raise ClientException(detail="Invalid JSON body: expected object")

    if payload.get("type") == "url_verification":
        challenge = payload.get("challenge")
        if challenge:
            return {"challenge": challenge}

    try:
        ExecutionService.dispatch_webhook_event(
            payload, raw_payload=raw_payload, signature_header=signature_header
        )
    except Exception:
        logger.exception("Webhook processing error")
        raise HTTPException(status_code=500, detail="Internal server error") from None

    return Response(content="", status_code=200, media_type="text/plain")


webhook_router = Router(
    path="/",
    route_handlers=[generic_webhook],
)
