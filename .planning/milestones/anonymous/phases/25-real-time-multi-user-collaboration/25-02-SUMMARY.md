# 25-02 SUMMARY — co-drive: policy-checked teammate message

**Status:** DONE. `app/services/session_sharing_service.py:co_drive` + `app_litestar/routes/session_shares.py:co_drive_send`, `app_litestar/main.py` registration, frontend `SharedSessionView.vue` (co-drive compose) + 4 locales. Tests: `tests/test_co_drive.py` (7, green).

- `co_drive(session_id, token, text, actor_user_id)` routes a chat-scope teammate message through Phase-23 `enforce_action(PolicyContext)` BEFORE `ProjectSessionManager.send_input` — scope = the operator's running session, actor = the teammate's user_id. The operator's own send_input path is unchanged.
- DENY → `PolicyDeniedError` and the message never reaches stdin; ASK blocks until the operator resolves it (`POLICY_ASK_EVENT`); ALLOW proceeds with a single send. A read-scope token is rejected on the write route.
- Frontend adds a co-drive compose affordance to the read-only shared view; co-drive strings key-identical across en/ko/ja/zh.

Security-hardening (Codex): the co-drive SEND route (auth-bypassed, token-in-URL) got CSRF defense — require the token echoed in an `X-Share-Token` header + reject a cross-site `Origin` (localhost/`AGENTED_TRUSTED_ORIGINS` trusted for vite dev); SharedSessionView sends the header (25 #5, shipped in the 25-01 share-token commit). And the gate is fed the session's REAL context — `co_drive` enriches the action ctx with accumulated `total_cost_usd` (via new `get_session_total_cost`), tool_calls, backend, sandboxed — so `cost_budget`/`max_tool_calls_per_session` caps actually trip for a teammate rather than being toothless (25 #4, +55 tests).
