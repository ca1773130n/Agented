# 24-02 SUMMARY — egress_proxy.py

**Status:** DONE. `backend/app/services/egress_proxy.py` + `tests/test_egress_proxy.py` (5 tests, green).

- `EgressProxy` / `start_egress_proxy(allowlist, *, session_id)`: deny-by-default asyncio forward proxy
  on an ephemeral loopback port. Allowlisted CONNECT/HTTP host → 200 + bidirectional pump; miss → 403 +
  structured deny log `{session_id, host, port, action:deny}`. Empty allowlist blocks everything.
- `proxy_env(handle)` → HTTPS_PROXY/HTTP_PROXY = url + non-bypassing NO_PROXY (127.0.0.1,localhost).
- `ThreadedEgressProxy`: sync facade (own loop in a daemon thread) for the blocking Popen launch sites.
- ponytail: homegrown CONNECT proxy over mitmproxy (no MITM/cert/dep); env-only best-effort noted.

**Test tier:** L2 — local echo server + raw client, no real network; async bodies via `asyncio.run`.
