---
phase: 24-os-level-harness-sandboxing-egress-control
plan: 01
subsystem: backend/execution-sandboxing
tags: [sandbox, bwrap, sandbox-exec, sbpl, egress, security]
requires: []
provides:
  - "build_sandbox_prefix(cmd, *, workspace, proxy_addr=None) -> (argv, bool)"
  - "sandbox_available() -> bool (probe-backed detection)"
affects:
  - "24-03 (policy enforce_sandbox decides launch-vs-refuse on sandboxed=False)"
  - "execution_service.py Popen chokepoint (prefix prepend, wired later)"
tech-stack:
  added: []  # stdlib only — no new deps (ponytail/lazy bias honored)
  patterns:
    - "Pure argv/profile builders (no I/O) for deterministic CI testing"
    - "Probe-run detection (not just shutil.which) — Pitfall 2 graceful degrade"
    - "Reuse sandbox_eval env-scrub convention (no new allowlist)"
key-files:
  created:
    - backend/app/services/sandbox_wrap.py
    - backend/tests/test_sandbox_wrap.py
  modified: []
decisions:
  - "Argv-PREFIX builder prepended at existing Popen chokepoint, not a new launcher"
  - "Degrade to (cmd, False)+warning when primitive missing/unusable; never raise"
  - "Env-var egress (HTTPS_PROXY) is best-effort; netns+nftables deferred (Pitfall 3)"
metrics:
  duration: ~4m
  tasks: 2
  files: 2
  completed: 2026-06-30
---

# Phase 24 Plan 01: Sandbox-Command-Prefix Builder Summary

One reusable, stdlib-only builder that wraps a harness launch in an OS sandbox
(bwrap on Linux, `sandbox-exec`/SBPL on macOS) by returning an argv PREFIX plus a
`sandboxed: bool` — prepended at the single existing `Popen` chokepoint, with
graceful degradation to `(cmd, False)` when the OS primitive is missing or unusable.

## What Was Built

- `backend/app/services/sandbox_wrap.py`:
  - `_build_bwrap_prefix` — Linux bwrap: rw-bind workspace, ro-bind existing
    system dirs (`/usr /bin /sbin /lib /lib64 /etc/ssl /etc/resolv.conf
    /etc/ca-certificates`), `--proc --dev --tmpfs /tmp`, `--chdir <ws>`,
    `--unshare-all --share-net --die-with-parent`, and `HTTPS_PROXY`/`HTTP_PROXY`
    setenv when a proxy address is given; terminates with `--` then `*cmd`.
  - `_build_sbpl_profile` / `_build_sbpl_prefix` — macOS deny-default seatbelt:
    `(deny default)`, `file-write*` limited to workspace + `(param "TMPDIR")`,
    `(deny network*)` plus a specific `(allow network* (remote ip "<proxy>:*"))`
    carve-out when a proxy is given (deny-wins floor).
  - `sandbox_available()` — `shutil.which` + a cached probe-run of the primitive
    (`bwrap --ro-bind / / true` / `sandbox-exec -p '(version 1)(allow default)'
    true`); any failure → `False` (Pitfall 2: disabled unprivileged userns passes
    `which()` but fails the probe).
  - `build_sandbox_prefix` — picks the platform builder when available; else logs
    a warning naming the missing primitive and returns `(cmd, False)`. Never raises.
- `backend/tests/test_sandbox_wrap.py`: 9 pure/deterministic tests (no real
  sandbox) — bwrap token composition, SBPL profile composition, FS-only (no-proxy)
  mode, command-wrapping, degrade-path warning, platform branch selection, and
  probe-failure degrade.

## Deviations from Plan

The two tasks (builders+composition tests, then public entrypoint+detection) were
co-authored into the same two files in one TDD cycle, so they landed in a single
commit rather than two. RED was verified (ModuleNotFoundError) before GREEN. The
commit message was amended from `test(24-01)` to `feat(24-01)` to accurately
describe the combined module+tests. No behavioral deviations from the plan.

No Rule 1–5 deviations otherwise.

## Verification

- `uv run pytest tests/test_sandbox_wrap.py -v` → 9 passed.
- `uv run ruff check app/services/sandbox_wrap.py` → All checks passed.
- `uv run ruff format --check app/services/sandbox_wrap.py` → already formatted.

## Notes for Downstream Plans

- 24-02 supplies the local proxy; pass its `addr` as `proxy_addr` to force egress.
- 24-03 wires `build_sandbox_prefix` into the `execution_service.py` Popen
  chokepoint and uses `sandboxed=False` as the signal for the Phase-23
  `enforce_sandbox` policy to decide launch-vs-refuse.
- Deferred: env-var egress is best-effort (a process can unset `HTTPS_PROXY`);
  airtight egress via network-namespace + nftables redirect is the planned upgrade
  (RESEARCH Pitfall 3).

## Self-Check: PASSED

- FOUND: backend/app/services/sandbox_wrap.py
- FOUND: backend/tests/test_sandbox_wrap.py
- FOUND commit: 0478a9cd43
