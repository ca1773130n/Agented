# 24-05 SUMMARY — escape proof + docs

**Status:** DONE. `tests/test_sandbox_escape.py` (2, green on macOS seatbelt) + docs (EN + KO 1:1).

- `test_escape_write_outside_workspace_blocked`: real wrapped `sh -c` — write to /etc + / contained,
  write inside workspace succeeds (boundary, not blanket block).
- `test_escape_connect_non_allowlisted_blocked`: real wrapped python client through a real egress proxy
  → 403 + deny log for blocked.invalid. Both `@skipif(not sandbox_available())`.
- Corrected the SBPL net-without-proxy branch: empirically a broad `(allow network*)` after
  `(deny network*)` is deny-wins; the specific `(remote ip "localhost:PORT")` allow IS honored.
- docs/sandboxing.md + docs/sandboxing.ko.md: 1:1 (7 headings each), model / egress / enforce_sandbox /
  cloud runners / best-effort ceiling + upgrade paths / house-gate runbook.

**House gates:** all 6 new suites green (30); touched-service regressions green (179); frontend build run.
