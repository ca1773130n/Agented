#!/usr/bin/env python3
"""Claude PreToolUse hook → Agented web-panel permission prompt.

When claude is about to use a tool, this script runs (claude piped
the hook input JSON on stdin). The script POSTs the request to the
Agented backend, which:

  1. Pushes a ``permission_request`` SSE event to the web chat panel
  2. Renders an Approve / Deny card to the user
  3. Blocks the POST response until the user clicks
  4. Returns the decision in the HTTP response

The hook then writes claude's expected output shape on stdout::

    {"hookSpecificOutput": {
      "hookEventName": "PreToolUse",
      "permissionDecision": "allow" | "deny" | "ask"
    }}

Environment contract (set by ``ProjectSessionManager`` when spawning
the subprocess; absent for normal claude use):

* ``AGENTED_PERMISSION_HOOK_ACTIVE=1`` — gate flag. If unset, the
  script returns ``{permissionDecision: "ask"}`` so claude falls
  through to its normal permission flow. This lets the hook be
  installed in ``~/.claude/settings.json`` without affecting any
  non-Agented claude usage.
* ``AGENTED_BACKEND_URL`` — base URL of the Agented Litestar
  backend (e.g. ``http://127.0.0.1:20000``).
* ``AGENTED_API_KEY`` — admin API key for ``X-API-Key`` header.
* ``AGENTED_PROJECT_ID``, ``AGENTED_SESSION_ID`` — the parent
  Agented project + session this claude invocation belongs to.

Behavior on any error (backend unreachable, timeout, missing env):
returns ``{permissionDecision: "ask"}`` to fall through. We never
auto-allow on error; we never auto-deny on error.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

_HOOK_INPUT_TIMEOUT_SEC = 5
_BACKEND_LONG_POLL_SEC = 300


def _emit(decision: str = "ask") -> None:
    """Write the hook's response on stdout and exit cleanly."""
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
        }
    }
    sys.stdout.write(json.dumps(payload))
    sys.stdout.flush()
    sys.exit(0)


def _read_hook_input() -> dict | None:
    """Claude pipes the hook input JSON on stdin. Read with a short
    timeout so we don't hang forever if claude's stdin is empty."""
    raw = sys.stdin.read()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None


def main() -> None:
    # Gate: only intercept when explicitly invoked by Agented.
    if os.environ.get("AGENTED_PERMISSION_HOOK_ACTIVE") != "1":
        _emit("ask")

    backend_url = os.environ.get("AGENTED_BACKEND_URL")
    api_key = os.environ.get("AGENTED_API_KEY")
    project_id = os.environ.get("AGENTED_PROJECT_ID")
    session_id = os.environ.get("AGENTED_SESSION_ID")
    if not all([backend_url, api_key, project_id, session_id]):
        _emit("ask")

    hook_input = _read_hook_input()
    if hook_input is None:
        _emit("ask")

    tool_name = hook_input.get("tool_name") or ""
    tool_input = hook_input.get("tool_input") or {}
    cwd = hook_input.get("cwd")

    url = (
        f"{backend_url.rstrip('/')}/api/projects/{project_id}"
        f"/sessions/{session_id}/permission-request"
    )
    body = json.dumps(
        {
            "tool_name": tool_name,
            "tool_input": tool_input,
            "cwd": cwd,
            "claude_session_id": hook_input.get("session_id"),
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": api_key,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=_BACKEND_LONG_POLL_SEC + 5) as r:
            resp_body = r.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        _emit("ask")
    except Exception:
        _emit("ask")

    try:
        resp = json.loads(resp_body)
    except (json.JSONDecodeError, ValueError):
        _emit("ask")

    decision = resp.get("decision")
    if decision not in ("allow", "deny"):
        _emit("ask")

    _emit(decision)


if __name__ == "__main__":
    main()
