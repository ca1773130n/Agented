# v0.7.13 State

Status: COMPLETE — shipped 2026-05-10.

## Shipped

Adds detect_version, _version_lt, upgrade, _brew_upgrade,
_linux_upgrade_release_binary, and ensure_min_version classmethods to
CLIProxyManager. macOS uses `brew upgrade cliproxyapi`; Linux pulls
the latest release binary from GitHub and installs to /usr/local/bin
(falls back to ~/.local/bin). MIN_CLIPROXY_VERSION constant set to
7.0.0. ensure_min_version is safe to call on every startup —
no-op when already current, attempts upgrade when behind, returns
(success, message) without raising. Shipped as 4 sequential commits implementing the full slice.

## Key files touched

- `backend/app/services/autofix_service.py`
- `backend/app/services/cliproxy_manager.py`
- `backend/tests/test_cliproxy_upgrade.py`
- `backend/app_litestar/main.py`
- `backend/app_litestar/routes/cliproxy_lifecycle.py`
- `backend/app_litestar/lifecycle.py`

## Reference

- Commit: `0aed98cc`
- Commits in slice: 4
