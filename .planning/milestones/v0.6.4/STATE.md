# v0.6.4 State

Status: COMPLETE — pending merge.

## Shipped

### Plugin filesystem discovery

- `app/services/plugin_discovery_service.py` — walks the configured
  plugin directories, surfaces installed plugins (directory-with-
  manifest OR single-file `*.plugin.py`).
- Search precedence:
  1. `AGENTED_PLUGIN_PATHS` env var (colon-separated)
  2. `~/.claude/plugins/`
  3. `~/.config/superpowers/plugins/`
- Stable sort by (name, path) so output is deterministic.
- Best-effort: corrupt manifests are skipped, missing dirs ignored.

### `GET /admin/plugins/discover`

- Admin-only endpoint exposing the discovery results.
- Returns `{plugins: [{name, version, description, type, path,
  source}], count: N}`.
- Complements the DB-backed plugin CRUD: shows operator what's
  actually installed regardless of registration state.

### Env var + check_env

- `AGENTED_PLUGIN_PATHS` — optional, colon-separated. Documented
  in `scripts/check_env.py:OPTIONAL_VARS`.

### Tests

- `test_plugin_discovery.py` — 7 tests (empty, directory plugin,
  single-file plugin, dotfile/unmarked-dir skip, stable sort,
  corrupt manifest, AGENTED_PLUGIN_PATHS colon-separated).

## Verification

- Backend touched-area: 16/16.
- `just build` — not run; pure backend addition.

## Out of scope (deferred)

- Plugin import-from-URL / git-clone flow.
- Plugin marketplace mechanics (sharing, rating).
- Frontend plugin catalog page (operator can already query
  `GET /admin/plugins/discover` directly; UI deferred).

## Autopilot run complete

v0.6.1 → v0.6.4 shipped:
- v0.6.1 — tech debt sweep (utcnow shim + expire_sessions soft-delete + rotated_from_token unique)
- v0.6.2 — observability (Prometheus metrics + slow-request log)
- v0.6.3 — UX (session-events viewer page)
- v0.6.4 — plugin filesystem discovery
