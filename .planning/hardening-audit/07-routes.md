# Hardening Audit — HTTP Route Layer (07-routes)

Scope: `backend/app_litestar/routes/` — leaf_crud_a..i, projects, teams, executions,
agents_and_tracing, scheduler, misc, utility, payload_transformers, and the secrets
vault routes (which live in `admin_tooling.py`, not a separate file).

## Auth model (context for every finding)

Authorization is enforced in two layers (`app_litestar/middleware.py` →
`app_litestar/auth_guards.py`):

1. **Global API-key/bearer gate** (`ApiKeyMiddleware`) — every `/admin/*` and
   `/api/*` request must carry a valid key/session.
2. **Coarse method+prefix RBAC** (`required_role`): `GET → viewer`, `POST/PUT/PATCH
   → editor`, `DELETE → admin`, for both `/api/` and `/admin/`. Individual handlers
   may tighten this with a `requires_role(...)` Litestar guard or a
   `require_role(...)` dependency.

The gold-standard handlers are `teams.py` and `payload_transformers.py`: per-route
`require_role` dependencies + length caps. Most other route modules rely solely on
the coarse default, which produces the gaps below.

There is **no per-object ownership (IDOR) enforcement** in most modules even though
the LIST endpoints deliberately scope by `caller.user_id`. There is **no global
request-body size limit** anywhere in the app or `gunicorn.conf.py`.

---

## CRITICAL

### C1. Hardcoded Google OAuth client_secret in source
**`leaf_crud_h.py:483`** (and duplicated at `app/services/provider_usage_client.py:29`)
```python
client_secret = "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"
```
A real OAuth client secret is committed to the repo. Even though this is the
Gemini-CLI "installed-app" desktop client (where Google treats the secret as
non-confidential), shipping it inline is a hardening defect: it cannot be rotated
without a code change, it is indexed by every clone/mirror, and it couples the
backend to one Google project. **Fix:** move to env/secret store
(`os.environ["GEMINI_CLI_CLIENT_SECRET"]`), fail closed if unset, and rotate the
exposed value. Collapse the two copies into one config source.

### C2. Plaintext secret reveal gated only at `editor`
**`admin_tooling.py:320-329` `reveal_secret`** — `POST /admin/secrets/{id}/reveal`
returns the decrypted secret value. Because it is a `POST /admin/*`, the coarse
RBAC default requires only **editor**, so any editor can exfiltrate every stored
credential. The audit accessor is also a static `"api"` string (line 323), so the
access log cannot attribute who revealed a secret. **Fix:** add
`guards=[requires_role("admin")]` to the handler, and pass the authenticated
principal (`Caller`) as `accessor` instead of the literal `"api"`. Consider rate-
limiting reveals.

---

## HIGH

### H1. IDOR — projects operate on any object regardless of owner
**`projects.py`** — `list_projects` (`:70`) scopes results to `caller.user_id` via
`get_for_user(...)`, establishing an ownership model. But every other handler does
`del caller` and acts on the raw `project_id` with no ownership/role check:
`get_project_detail_endpoint:159`, `update_project_endpoint:170`,
`delete_project_endpoint:196`, `run_team_in_project:?`, `deploy_teams`, `sync_project_repo`,
`get_or_create_manager`, etc. An `editor` who owns zero projects can read, mutate,
deploy, and delete another user's project by guessing/enumerating the `proj-XXXXXX`
id. **Fix:** resolve ownership in a shared dependency (mirror `get_for_user` →
`assert_owner_or_admin(project_id, caller)`) and apply it to all single-object
project routes; or accept the "shared workspace" model explicitly and remove the
owner-scoping from the list endpoint so behavior is consistent.

### H2. IDOR — agents operate on any object regardless of owner
**`agents_and_tracing.py:55-95`** — same pattern as H1. `list_agents:46` scopes by
`caller.user_id`, but `get_agent_detail:62`, `update_agent:70`, `delete_agent:79`,
`run_agent:86`, `export_agent:93` all `del caller` and act on any `agent_id`.
`run_agent` is especially sensitive — it launches a CLI execution. **Fix:** same
ownership dependency as H1.

### H3. Mass-assignment of arbitrary fields on create/update
Multiple handlers forward the raw request `dict` straight into a service/DB writer
with no field allow-list:
- `agents_and_tracing.py:58 create_agent` / `:73 update_agent` —
  `AgentService.create_agent({k:v for k,v in data ...})`.
- `leaf_crud_c.py:208 create_finding(data)` / `:222 update_finding(finding_id, data)`.
- `leaf_crud_b.py:415 create_pr_review(data)` / `:425 update_review(review_id, data)`.
- `leaf_crud_b.py:332 add_audit(data)`.
- `admin_tooling.py:376 create_repo` — only filters falsy values.

A caller can set columns the API never intended to expose (e.g. internal status,
owner ids, timestamps). **Fix:** define msgspec `Struct`/Pydantic request models
with an explicit field set (as `teams.py`/`payload_transformers.py` already do) and
reject unknown keys.

### H4. Settings store — arbitrary key read/write, sensitive values exposed
**`admin_tooling.py:85-95`** — `GET /api/settings/{key}` (viewer) returns any
setting value, and `PUT /api/settings/{key}` (editor) writes any key with any
value. `GET /api/settings/` (`:56`) dumps **all** settings. Settings are used
elsewhere to hold tokens/feature flags (e.g. `pr_assignment_*`, harness plugin
ids), so a viewer can read whatever credential-like value an operator stored, and
an editor can flip any behavioral flag. **Fix:** maintain an allow-list of
readable/writable setting keys; redact/deny keys matching `*token*`, `*secret*`,
`*key*`; require admin for writes to security-relevant keys.

### H5. SSRF / localhost port-probe via OAuth callback forwarder
**`leaf_crud_h.py` `proxy_callback_forward`** — accepts a user-supplied
`callback_url`, extracts its `port` and `path`, then issues `httpx.get` to
`http://{host}:{port}{path}` for hosts `[::1]/127.0.0.1/localhost`. The host set is
fixed (good), but the **port and path are attacker-controlled**, turning this into
a localhost port-scanner / request-forger against any loopback service (the sidecar
on :20001, metadata-style local daemons, etc.). **Fix:** pin the port to the value
captured during `start_proxy_login` (`BackendCLIService` callback port) rather than
trusting the URL, and constrain the path to the known OAuth callback path.

---

## MEDIUM

### M1. Spoofable viewer identity in collaborative endpoints
**`leaf_crud_d.py:185-249`** — `viewer_join`, `viewer_leave`, `viewer_heartbeat`,
`post_inline_comment` all trust client-supplied `viewer_id` / `viewer_name` from
the body. Any caller can impersonate another viewer, post comments under someone
else's name, or evict another viewer. **Fix:** derive viewer identity from the
authenticated `Caller` (`caller.user_id`) instead of the request body.

### M2. List endpoints with no upper bound on `limit` (unbounded query → DoS)
Several list handlers accept a `limit` that is passed straight to the DB with **no
`min()` cap** (contrast `executions.py` which caps at 500, and `leaf_crud_b.py`
audit which caps at 500/1000):
- `agents_and_tracing.py:122 list_all_traces` (`limit:int=100`, uncapped).
- `leaf_crud_d.py:? list_tagged_executions` (`limit:int=50`, uncapped),
  `list_recent_assignments` (`limit:int=20`, uncapped).
- `leaf_crud_e.py list_health_alerts` (`limit:int=50`, uncapped),
  `monitoring_history` (uncapped).
- `admin_tooling.py:124 list_errors`, `:434 get_sync_logs`, version-pins, plus
  every `get_all_*` list with no `limit` parameter at all
  (`list_marketplaces`, `list_integrations`, `list_snippets`, `list_filters`,
  `list_all_campaigns`, `list_execution_tags`, `list_findings_route`,
  `list_bot_pipes`, `list_repos`, `list_version_pins`, ...).
A client passing `limit=10000000` (or a table that has grown unbounded) can force a
huge result set into memory and over the wire. **Fix:** apply a shared
`cap = min(max(limit,1), 500)` helper to every list handler; add real
pagination (LIMIT/OFFSET) to the `get_all_*` listers that have none.

### M3. No request-size / item-count limits on bulk + message-append endpoints
- **`leaf_crud_f.py` `_bulk` (`bulk_agents/triggers/plugins/hooks`)** — validates
  that `items` is a list but never caps its length; a single request can submit an
  arbitrarily large batch.
- **`leaf_crud_f.py add_thread_messages`** and **`add_branch_message`** — accept an
  unbounded `messages` array / `content` string with no length cap.
- **`leaf_crud_a.py upsert_bot_memory`** — writes `data["value"]` with no size check
  (the read side advertises `max_bytes: 65536` but the write path doesn't enforce it).
- **`leaf_crud_i.py run_chunked`** — `content` is unbounded; `ChunkService.chunk_code`
  splits it and the handler spawns **one thread per chunk** (`threading.Thread(...).start()`
  in a loop). A large payload → thread explosion (the `Semaphore(3)` only bounds
  concurrent execution, not thread creation). **Fix:** enforce a global max body size
  (Litestar `request_max_body_size` / reverse-proxy limit), cap bulk `items` (e.g.
  ≤500), cap memory `value` to 64 KiB to match the documented quota, and bound the
  number of chunks per request.

### M4. Unvalidated free-text fields (no length caps) on create/update
Most string creators trim-and-require but set **no maximum length**, unlike
`teams.py` (255-char cap). Examples: `leaf_crud_a.py create_snippet` (name regex but
unbounded `content`), `leaf_crud_c.py create_product` (`name`), `leaf_crud_g.py
create_sketch` (`title`/`content`), `leaf_crud_d.py create_campaign`,
`leaf_crud_e.py create_bot_pipe`, `projects.py create_project`. Combined with M2/M3
this lets oversized rows accumulate. **Fix:** add length caps consistent with the
`teams.py` convention.

### M5. `del caller` discards identity across most `/admin` mutators
Beyond projects (H1) and agents (H2), the pattern `del caller` / `del authorized`
appears throughout (e.g. `projects.py` team-edge, install, deploy handlers). Even
where coarse RBAC is acceptable, the actor identity is dropped before reaching the
service layer, so audit events (where they exist) cannot attribute the change to a
user, and no ownership decision is possible. **Fix:** stop discarding `caller`;
thread it into audit logging and ownership checks.

---

## LOW

### L1. Internal exception text leaked in 500 details
Many handlers do `raise HTTPException(status_code=500, detail=f"... {e}")` /
`detail=str(exc)`, surfacing raw exception strings (paths, SQL fragments, stack
context) to clients: e.g. `leaf_crud_g.py export/import/deploy/sync handlers`,
`leaf_crud_h.py gemini_auth_complete`, `leaf_crud_i.py start_setup`,
`admin_tooling.py create_secret`. **Fix:** log the detail server-side, return a
generic message to the client.

### L2. `browse_directory` / `create_directory` are filesystem primitives over HTTP
**`leaf_crud_h.py`** — these expose directory listing and `mkdir` under
`~`, `/tmp`, `/opt` to any **editor**. The allow-list and symlink checks are decent,
but `create_directory` (write) and `browse_directory` (enumeration of the operator's
home tree) are sensitive enough to warrant `requires_role("admin")` and an audit
entry. **Fix:** tighten role and audit-log these operations.

### L3. `discover_skills` / `import_plugin` / `sync_to_disk` accept arbitrary host paths
**`leaf_crud_h.py discover_skills`** (scans caller-supplied comma-separated `paths`)
and **`leaf_crud_g.py import_plugin`/`sync_to_disk`/`sync_entity`** take raw
`source_path`/`plugin_dir`/`output_dir` filesystem paths with no allow-list. These
let an editor point the scanner/importer at any directory the backend process can
read. Lower severity because they don't write outside the given path, but worth an
allow-list consistent with `_ALLOWED_BASES`. **Fix:** validate these paths through
the same `_is_path_allowed` gate used by `browse_directory`.

### L4. `_get_sigterm_grace` / numeric coercions trust DB/body without range checks
Minor: `executions.py` `float(trigger["sigterm_grace_seconds"])`,
`leaf_crud_d.py create_pr_rule` `int(body.get("priority", 0))`,
`leaf_crud_e.py monitoring_history_batch` `int(...)` — no range/negativity checks.
A negative/huge value could distort behavior. **Fix:** clamp to sane ranges.

---

## Notable things done RIGHT (not findings)

- `teams.py` and `payload_transformers.py`: per-route `require_role` dependencies +
  255-char name caps + structured request bodies — the pattern to replicate.
- `leaf_crud_h.py install_backend_cli`, `leaf_crud_i.py bundle_install`: correctly
  use `guards=[requires_role("admin"), requires_rate_limit(...)]`.
- `db.secrets.list_secrets` is metadata-only and never returns the encrypted value;
  `_secret_metadata` projection is used for create/get/update.
- `leaf_crud_b.py get_slack_status` returns a `connected` bool, never the token.
- `executions.py` and the audit listers cap `limit` at 500/1000 — apply this
  everywhere (M2).
- 501 stubs (anomalies, slack-commands, alert-rules, sandboxes) are honest, not
  silent-success.

## Suggested remediation order

1. C1 (rotate + externalize OAuth secret), C2 (admin-gate `reveal_secret`).
2. H4 (settings allow-list), H1/H2 (ownership dependency), H5 (pin callback port).
3. H3 (request models / field allow-lists), M3 + global body-size limit, M2 (limit caps).
4. M1, M4, M5, then the LOW items.
