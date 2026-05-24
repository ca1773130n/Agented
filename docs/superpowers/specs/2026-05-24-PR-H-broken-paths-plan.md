# PR-H — Fix 4 broken frontend ↔ backend API paths

**Driver:** Joint wiring review (`.planning/wiring-review/codex-findings.md` F5 + Q2). Frontend currently calls 4 backend endpoints that either don't exist or have drifted paths. Each click 404s today.

## In scope (exactly 4 paths)

| # | Frontend caller (file:line) | Backend reality | Fix |
|---|---|---|---|
| 1 | `frontend/src/services/api/conversation-branches.ts:27` → `GET /admin/conversations/{id}/branch-tree` | Backend route is `/conversations/{id}/branches/tree` at `leaf_crud_f.py:509` | **Frontend rename** (cheap path fix) |
| 2 | `frontend/src/services/api/collaborative.ts:59` → `DELETE /admin/execution-comments/{id}` | Backend route is `/comments/{comment_id}` at `leaf_crud_d.py:234` | **Frontend rename** (cheap path fix) |
| 3 | `frontend/src/services/api/mcp-servers.ts:83` → `POST /admin/mcp-servers/{id}/test` | **Backend handler missing** | **Implement backend** |
| 4 | `frontend/src/services/api/super-agents.ts:188` → `DELETE /admin/super-agents/{id}/messages/{messageId}` | **Backend handler missing** | **Implement backend** (+ DB helper) |

## Per-fix detail

### Fix 1 — `branch-tree` → `branches/tree`

Pure string change in `frontend/src/services/api/conversation-branches.ts:25-28`:
```ts
getBranchTree: (conversationId: string) =>
  apiFetch<BranchTree>(`/admin/conversations/${conversationId}/branches/tree`),
```

Confirmed call sites that benefit: `frontend/src/composables/useConversationBranch.ts:27` (treats 404 as `null`), `frontend/src/components/triggers/BranchNavigator.vue` (renders the tree). Backend method `ConversationBranchService.get_branch_tree` exists at line 240.

### Fix 2 — `execution-comments/{id}` → `comments/{id}`

Pure string change in `frontend/src/services/api/collaborative.ts:57-60`:
```ts
deleteComment: (commentId: string) =>
  apiFetch<null>(`/admin/comments/${commentId}`, { method: 'DELETE' }),
```

Backend `delete_inline_comment` at `leaf_crud_d.py:234` already wired and registered. The list/post endpoints at `/admin/executions/{id}/comments` stay as-is — only the delete needs the rename.

### Fix 3 — Implement `POST /admin/mcp-servers/{id}/test`

The MCP server detail page exposes a "Test Connection" button that today gracefully degrades to "Test endpoint not available" on 404. We'll implement a minimal but useful connection probe.

**New handler** in `backend/app_litestar/routes/mcp_servers.py` (insert after the existing `delete_mcp_server` handler at line ~170):

```python
@post("/{server_id:str}/test", sync_to_thread=False)
def test_mcp_server(server_id: str, caller: Caller) -> dict[str, Any]:
    """Probe an MCP server's reachability without launching it.

    HTTP servers: HEAD/GET request with a short timeout.
    stdio servers: shutil.which() to confirm the command is on PATH.
    Other types: returns {success: False, message: "..."} explaining why.
    """
    del caller
    server = get_mcp_server(server_id)
    if not server:
        raise NotFoundException(detail="MCP server not found")
    return McpSyncService.test_connection(server)
```

Register it in the router (line ~205-215 of `mcp_servers.py`).

**New helper** on `McpSyncService` in `backend/app/services/mcp_sync_service.py`:

```python
@staticmethod
def test_connection(server: dict) -> dict[str, Any]:
    """Probe reachability for an MCP server config row."""
    server_type = (server.get("server_type") or "").lower()
    if server_type == "http":
        url = server.get("url")
        if not url:
            return {"success": False, "message": "HTTP server has no URL configured."}
        try:
            import urllib.request
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                return {"success": True, "message": f"Reachable (HTTP {resp.status})."}
        except Exception as e:
            return {"success": False, "message": f"Unreachable: {e}"}
    if server_type == "stdio":
        command = server.get("command")
        if not command:
            return {"success": False, "message": "stdio server has no command configured."}
        import shutil
        if shutil.which(command):
            return {"success": True, "message": f"Command '{command}' is on PATH."}
        return {"success": False, "message": f"Command '{command}' not found on PATH."}
    return {"success": False, "message": f"Connection test not supported for server type '{server_type}'."}
```

**Why this is minimal-but-correct:** the test never spawns the stdio command (avoids running arbitrary code) and uses a 2-second timeout for HTTP. The UI already handles a `{success, message}` shape exactly.

### Fix 4 — Implement `DELETE /admin/super-agents/{id}/messages/{message_id}`

**New DB helper** in `backend/app/db/messages.py` (append after `update_message_status` at line ~117):

```python
def delete_message(message_id: str) -> bool:
    """Hard delete an agent message. Returns True if a row was removed."""
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM agent_messages WHERE id = ?", (message_id,))
        conn.commit()
        return cur.rowcount > 0
```

**New handler** in `backend/app_litestar/routes/leaf_crud_i.py` after `mark_message_read` at line ~204:

```python
@delete(
    "/{super_agent_id:str}/messages/{message_id:str}",
    status_code=200,
    sync_to_thread=False,
)
def delete_agent_message(super_agent_id: str, message_id: str) -> dict[str, Any]:
    del super_agent_id
    from app.db.messages import delete_message

    if not delete_message(message_id):
        raise NotFoundException(detail="Message not found")
    return {"message": "Message deleted"}
```

Add `delete_agent_message` to the `super_agent_messages_router` route_handlers tuple.

## Backend tests

For each new handler, add a test:
- `test_litestar_leaf_crud_f.py` — already tests branch endpoints; the existing tests use the *correct* `branches/tree` path. No update needed there. **Frontend fix only for #1.**
- `test_litestar_leaf_crud_d.py` — already tests comment delete via the existing `/comments/{id}` path. **Frontend fix only for #2.**
- `test_litestar_mcp_servers.py` — add `test_mcp_server_test_connection_http_reachable` (mock urlopen success), `_http_unreachable` (urlopen raises), `_stdio_found` (mock which → '/usr/bin/foo'), `_stdio_missing`, `_unknown_type`, `_server_not_found` (404).
- `test_litestar_leaf_crud_i.py` (or existing super-agent messages test file) — add `test_delete_agent_message_success`, `_not_found`.

## Frontend tests

- No new tests required for #1 + #2 (pure string changes; existing tests should still pass if any).
- For #3 — `frontend/src/views/__tests__/McpServerDetailPage.test.ts`: existing graceful-degradation test asserts the "endpoint not available" fallback fires on 404. After this PR, the endpoint exists, so we can leave that test as-is (it'd still pass on a 200 if mocked accordingly) OR add a complementary success-path test. Lean: add one `testConnection success → testResult is set` test.
- For #4 — `frontend/src/components/super-agents/__tests__/MessageInbox.test.ts` (if exists): existing tests for deleteMessage error path should still pass; add a happy-path test if not present.

## Out of scope

- Refactoring the conversation-branches URL surface (e.g., grouping under `/api`).
- Building richer MCP test capability (e.g., actually invoking a tool/listTools).
- Adding undo/restore for super-agent message delete.
- The other 26+ unverified API paths in the audit (those will surface in PR-J triage).

## Verification

- `cd backend && uv run pytest` — full backend.
- `cd frontend && npm run test:run` — full frontend.
- `cd frontend && npx vue-tsc --noEmit` — clean.

## Risks

| Risk | Mitigation |
|------|------------|
| `urllib.request` HEAD against an MCP HTTP server gets rejected — many MCP servers only speak POST | Catch the exception; the "Unreachable" message is informative. Acceptable for a v1 test. |
| Deleting an agent message creates an orphan delivery in some message-bus state | Audit: `app_message_bus_service` reads from the messages table by status; deleting a row just removes it from any future inbox query. No orphan state.
| Existing tests use `/admin/execution-comments/...` literal in fixture data | Grep before impl; should be zero. |
| Frontend `apiFetch` retries 404s | It does not (per `frontend/src/services/api/client.ts`); 404 is final. |

## Commit shape

One commit, one PR. Two frontend string changes + 2 backend handlers + 1 service method + 1 DB helper + backend tests.
