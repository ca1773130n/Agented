# Flask → Litestar Migration Playbook

**Status:** living document, written during the wave 22–25 foundation. Each
remaining route migration follows this playbook; deviations should be added
back here so the next migrator finds the gotcha already documented.

## Architecture during transition

```
frontend (Vite, :3000)
  /api/v1/*       → ai-accounts sidecar (:20001, Litestar)
  /admin/rbac/*   → Litestar (:20002)         ← migrated
  /admin/*        → Flask (:20000)             ← unmigrated
  /api/*, /health, /docs, /openapi → Flask (:20000)
```

Vite proxy keys are evaluated longest-first, so `/admin/rbac` wins over the
`/admin` catch-all. As more routes migrate, add their prefixes ABOVE
`/admin` in `frontend/vite.config.ts`.

## Per-route migration steps

### 1. Pick the route

Order by safety: read-only first, write-path next, finally anything that
emits SSE / streaming. Never migrate two routes in the same commit.

### 2. Port the handler

Place under `backend/app_litestar/routes/<area>.py`. Use Litestar's
decorators directly; map flask-openapi3 patterns:

| Flask (flask-openapi3) | Litestar |
|---|---|
| `@bp.get("/path")` | `@get("/path", sync_to_thread=False)` |
| `@bp.post("/path")` | `@post("/path", sync_to_thread=False)` |
| `path: PathModel` (Pydantic) | `role_id: str` (path param) |
| `body: BodyModel` (Pydantic) | `data: BodyStruct` (msgspec.Struct) |
| `return value, HTTPStatus.OK` | `return value` (200 default for GET) |
| `return value, HTTPStatus.CREATED` | implicit 201 for POST |
| `return error_response(...)` | raise `NotFoundException` / `ValidationException` |

### 3. Add the auth dependency

Authenticated reads:
```python
@get("/permissions",
     dependencies={"authorized": require_role("viewer", "operator", "editor", "admin")},
     sync_to_thread=False)
def get_permissions(authorized: Caller) -> ...:
    del authorized  # presence enforces; body doesn't need it
```

**Gotcha:** Litestar resolves dep injection by name. Do NOT name the
override `caller` — that recurses against the global `caller` provider
(`provide_caller`). Use `authorized` (or any other name).

### 4. Register on the router

Add the handler to `backend/app_litestar/routes/<area>.py`'s `Router(...)`
and ensure the router is included in `app_litestar/main.py:create_app()`.

### 5. Write parity tests

In `backend/tests/test_litestar_<area>.py`:

```python
def _client(isolated_db):
    return create_test_client(
        route_handlers=[liveness, area_router],
        dependencies={"caller": provide_caller},
    )
```

**Gotcha:** Litestar `Litestar` instances do NOT expose `.route_handlers`.
Pass the handler list directly to `create_test_client`. Same for
`dependencies={"caller": provide_caller}`.

For each route, write:
- happy path with valid key
- 401 for missing key (when roles configured)
- 403 for insufficient role (where applicable)
- 404 / 422 for not-found / validation errors

While both apps still serve the route, also add a **byte-equal parity
test** that hits both ports and asserts identical bodies — this catches
schema drift at migration time, not in production. Once the Flask version
retires (step 7), the parity test is deleted.

### 6. Update the vite proxy

In `frontend/vite.config.ts`, add the new prefix ABOVE `/admin`:

```ts
proxy: {
  '/admin/rbac': { target: 'http://127.0.0.1:20002', changeOrigin: true },
  '/admin/<next>': { target: 'http://127.0.0.1:20002', changeOrigin: true },
  '/admin': { target: 'http://127.0.0.1:20000', changeOrigin: true },
}
```

Mirror the change in the `preview` block.

### 7. Retire the Flask version

Delete the route handler from `backend/app/routes/<area>.py` and any
Flask-only tests that hit it (`TestRotateRoute` in `test_rbac.py` is the
template — three tests that exercised the now-Litestar path). DB-layer
tests stay (they don't depend on which app dispatches).

Delete the parity test from step 5 — the Flask 404 would fail it.

### 8. Verify

```bash
# Backend: Litestar tests + remaining Flask tests both green.
cd backend && uv run pytest tests/test_litestar_<area>.py tests/test_<area>.py

# Frontend: build + the relevant component test.
cd frontend && just build && npm run test:run -- src/views/...
```

## What's done so far

- **Wave 22:** Skeleton + auth dependency. `/health/liveness` smoke route.
- **Wave 23:** `GET /admin/rbac/permissions` ported.
- **Wave 24:** `POST /admin/rbac/roles/{id}/rotate` ported.
- **Wave 25:** Flask versions of the above retired; vite proxy updated.

## What remains

77 routes across `backend/app/routes/`. Suggested batch ordering for
follow-on milestones:

1. **Read-only health/version routes** (~5 routes) — easy, no auth surface.
2. **Read-only catalog routes** (`/admin/agents`, `/admin/teams`,
   `/admin/products`, `/admin/projects`, etc., GET endpoints) — ~15 routes.
3. **Single-entity CRUD** (POST/PUT/DELETE for the same catalogs) — ~30 routes.
4. **Streaming routes** (executions, conversations, SSE) — these need
   Litestar's streaming response patterns; do these last.
5. **Webhook + GitHub event handlers** — auth model differs (HMAC, not
   API key); requires its own brainstorm.

Once all routes are off Flask, `backend/app/__init__.py:create_app` can
drop the flask-openapi3 wiring entirely and the run script collapses
onto a single port (:20000).
