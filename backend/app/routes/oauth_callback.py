"""OAuth callback proxy route.

Proxies OAuth provider redirects (e.g. from Anthropic Console) to the CLI's
local HTTP callback server running on the Agented host.  This allows remote
users to complete ``claude /login`` and ``gemini auth login`` flows whose
redirect_uri points back to ``localhost`` on the server.

The route lives under ``/api/oauth-callback/`` which is added to the auth
bypass list so that OAuth providers can hit it without an API key.
"""

import logging

import httpx
from flask import Response, request
from flask_openapi3 import APIBlueprint

from ..services.backend_cli_service import BackendCLIService

logger = logging.getLogger(__name__)

oauth_callback_bp = APIBlueprint("oauth_callback", __name__, url_prefix="/api/oauth-callback")


@oauth_callback_bp.get("/<path:rest>")
def oauth_callback_proxy(rest: str):
    """Proxy an OAuth callback to the CLI's local HTTP server.

    The OAuth provider redirects the user's browser to
    ``{agented_host}/api/oauth-callback/callback?code=...&state=...``.
    We forward the full path + query string to
    ``http://127.0.0.1:{port}/{rest}?{query_string}`` on this machine,
    where the CLI is listening for the callback.
    """
    # Determine the port the CLI callback server is listening on.
    # Check active sessions for a stored callback_port; fall back to 54545.
    port = _find_callback_port()

    query_string = request.query_string.decode("utf-8", errors="replace")
    target_url = f"http://127.0.0.1:{port}/{rest}"
    if query_string:
        target_url += f"?{query_string}"

    logger.info("OAuth callback proxy: forwarding to %s", target_url)

    try:
        resp = httpx.get(target_url, timeout=15, follow_redirects=True)

        # Forward the response back to the user's browser
        excluded_headers = {"transfer-encoding", "content-encoding", "connection"}
        headers = {k: v for k, v in resp.headers.items() if k.lower() not in excluded_headers}

        return Response(
            resp.content,
            status=resp.status_code,
            headers=headers,
            content_type=resp.headers.get("content-type", "text/html"),
        )
    except httpx.ConnectError:
        logger.warning("OAuth callback proxy: CLI callback server not reachable on port %d", port)
        return (
            "<html><body><h2>OAuth callback failed</h2>"
            "<p>The CLI login server is not running on this host. "
            "The login session may have expired or already completed.</p>"
            "</body></html>"
        ), 502
    except Exception as exc:
        logger.error("OAuth callback proxy error: %s", exc, exc_info=True)
        return (
            "<html><body><h2>OAuth callback error</h2>"
            "<p>An internal error occurred. Please try again.</p></body></html>"
        ), 502


def _find_callback_port() -> int:
    """Find the callback port from active CLI sessions, or return default."""
    return BackendCLIService.get_callback_port()
