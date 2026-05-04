"""v0.5.13: production healthcheck CLI.

Probes backend liveness/readiness + sidecar health. Used by:
- Operators: `just healthcheck`
- launchd / systemd: KeepAlive / Restart trigger
- Docker compose: HEALTHCHECK directive

Exit codes:
  0 — all green
  1 — at least one red; structured JSON on stderr names the failures.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Optional


_DEFAULT_BACKEND = "http://127.0.0.1:20000"
_DEFAULT_SIDECAR = "http://127.0.0.1:20001"


def _probe(url: str, *, timeout: float = 5.0) -> tuple[bool, str]:
    """Returns (ok, detail). ok=True when status==200."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            if resp.status == 200:
                return True, "200"
            return False, f"status {resp.status}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except urllib.error.URLError as exc:
        return False, f"unreachable: {exc.reason}"
    except (TimeoutError, ConnectionError) as exc:
        return False, f"connection error: {exc}"


def run(
    *,
    backend_base: Optional[str] = None,
    sidecar_base: Optional[str] = None,
) -> tuple[int, dict]:
    """Returns (exit_code, structured_result)."""
    backend_base = backend_base or os.environ.get("AGENTED_BACKEND_URL", _DEFAULT_BACKEND)
    sidecar_base = sidecar_base or os.environ.get("AGENTED_SIDECAR_URL", _DEFAULT_SIDECAR)

    probes = [
        ("backend.liveness", f"{backend_base}/health/liveness"),
        ("backend.readiness", f"{backend_base}/health/readiness"),
        ("sidecar.health", f"{sidecar_base}/health"),
    ]

    results = {}
    any_red = False
    for name, url in probes:
        ok, detail = _probe(url)
        results[name] = {"ok": ok, "detail": detail, "url": url}
        if not ok:
            any_red = True

    return (1 if any_red else 0, results)


def main(argv: Optional[list[str]] = None) -> int:
    rc, results = run()
    if rc != 0:
        print(json.dumps({"status": "red", "probes": results}, indent=2), file=sys.stderr)
    else:
        print(json.dumps({"status": "green", "probes": results}, indent=2))
    return rc


if __name__ == "__main__":
    sys.exit(main())
