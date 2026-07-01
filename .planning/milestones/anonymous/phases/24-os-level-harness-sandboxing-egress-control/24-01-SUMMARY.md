# 24-01 SUMMARY — sandbox_wrap.py

**Status:** DONE. `backend/app/services/sandbox_wrap.py` + `tests/test_sandbox_wrap.py` (9 tests, green).

- `build_sandbox_prefix(cmd, workspace, *, net=False, proxy_url=None) -> (argv, sandboxed)`:
  bwrap argv on Linux (`_build_bwrap_prefix`), `sandbox-exec -p <SBPL>` on macOS
  (`_build_sbpl_profile`); prepend like `stdbuf`, no second launcher.
- `sandbox_available()` = `which(tool)` AND a cached runtime probe (per-OS: bwrap / sandbox-exec).
- Degrade in place to `(cmd, False)` + one warning; never raises. Reuses `sandbox_eval._ENV_ALLOWLIST`.
- Added `sandbox_enabled()` (AGENTED_SANDBOX flag) + `wrap_harness_command()` for the Plan-03 sweep.
- ponytail: env+proxy best-effort ceiling documented; netns+nftables named as the airtight upgrade.

**Platform:** macOS seatbelt path exercised locally; bwrap-argv composition asserted via monkeypatched
platform (no real bwrap on macOS). SBPL network branch corrected in 24-05 after empirical verification.
