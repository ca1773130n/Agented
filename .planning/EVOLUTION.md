# Evolution Notes

## Iteration 1
_2026-02-24T15:19:14.147Z_

### Items Attempted

- **Running executions cannot be cancelled** — unknown
- **Rate limit detection fails execution with no recovery** — unknown
- **No structured audit log for execution events** — unknown
- **Execution log retrieval likely lacks pagination** — unknown
- **Monitoring service polling has no adaptive backoff** — unknown
- **Workflow timeout is hardcoded and cannot be overridden per-run** — unknown
- **Silent exception in skills_sh_service** — unknown
- **Silent exception in monitoring_service** — unknown
- **Silent exception in session_collection_service** — unknown
- **No timeout on subprocess stream reader threads** — unknown
- **Potential race condition in workflow execution state** — unknown
- **Uncaught exceptions in background thread** — unknown
- **Trigger event save failures are swallowed** — unknown

### Decisions Made

None

### Patterns Discovered

None

### Takeaways

None

---
## Iteration 2
_2026-02-24T15:50:52.881Z_

### Items Attempted

- **Replace Optional[str] with explicit result type in orchestration** — unknown
- **Budget enforcement errors need actionable messages** — unknown
- **Document which data structures each lock protects** — unknown
- **Stale conversation/execution thresholds are hardcoded** — unknown
- **Some git operations lack timeouts** — unknown
- **Silent exception swallowing in session collection** — unknown
- **Silent exception in process cleanup** — unknown
- **Monitoring failures silently continue** — unknown
- **App can start in partially broken state** — unknown
- **Subprocess execution has no timeout** — unknown
- **Cloned git directories can leak on exceptions** — unknown
- **In-memory rate-limit retries lost on restart** — unknown
- **Race condition in ProcessManager.register()** — unknown
- **Prompt template substitution passes unsanitized input to subprocess** — unknown
- **Invalid trigger config silently falls back to defaults** — unknown

### Decisions Made

None

### Patterns Discovered

None

### Takeaways

None

---
## Iteration 3
_2026-02-24T16:11:28.003Z_

### Items Attempted

- **Rate limit monitoring iterates snapshots redundantly** — unknown
- **Show user feedback when sidebar data fails to load** — unknown
- **Frontend SSE streams lack reconnection logic** — unknown
- **Silent exception handlers swallow errors** — unknown
- **Workflow execution state lost on server restart** — unknown
- **Sidebar data load failures silently ignored** — unknown
- **Inconsistent API error response shapes** — unknown
- **User input passed directly to child process stdin** — unknown

### Decisions Made

None

### Patterns Discovered

None

### Takeaways

None

---
## Iteration 4
_2026-02-24T16:54:11.804Z_

### Items Attempted

- **Execution timeout is not per-trigger configurable** — unknown
- **Execution cancellation sends SIGKILL without warning process** — unknown
- **Auto-resolve PR flow has no rollback on partial failure** — unknown
- **Webhook triggers lack HMAC signature validation** — unknown
- **SSE execution log stream has no backpressure mechanism** — unknown
- **No dry-run/preview for bot prompt templates** — unknown
- **Auto-resolve subprocess failures silently swallowed** — unknown
- **Prompt template placeholder substitution has no validation** — unknown
- **GitHub clone cleanup silently fails and leaks disk space** — unknown
- **Pending rate-limit retries are lost on server restart** — unknown
- **Process force-kill errors fully suppressed** — unknown
- **Trigger log directory write access never validated** — unknown
- **Execution states are bare string literals, not an enum** — unknown
- **Monitoring silently disables when scheduler unavailable** — unknown
- **SSE EventSource reconnects without exponential backoff** — unknown

### Decisions Made

None

### Patterns Discovered

None

### Takeaways

None

---
## Iteration 5
_2026-02-24T17:27:46.364Z_

### Items Attempted

- **List endpoints return all records without pagination** — unknown
- **Team and agent creation lacks input length/uniqueness validation** — unknown
- **Skills API semaphore limits total concurrency but not per-user** — unknown
- **GitHub webhook endpoint has no rate limiting** — unknown
- **Workflow execution route blocks until DAG completes** — unknown
- **Account rotations happen silently with no user-visible audit entry** — unknown
- **CLIProxy startup failure is silently swallowed** — unknown
- **Bare except with no logging in super_agents route** — unknown
- **stdout/stderr reader threads may outlive process, causing data loss** — unknown
- **Budget exhaustion silently aborts execution with no user notification** — unknown
- **Frontend catch blocks don't guard against non-Error thrown values** — unknown
- **Team generation blocks request thread for up to 120 seconds** — unknown
- **JSON parse failure in conversation log falls back silently** — unknown

### Decisions Made

None

### Patterns Discovered

None

### Takeaways

None

---
## Iteration 6
_2026-02-24T17:57:10.017Z_

### Items Attempted

- **Execution cancel error message doesn't explain what to do** — unknown
- **Hard budget limit error gives no spend context** — unknown
- **Silent fallback when all backends unavailable in 'all' mode** — unknown
- **No backend detail in orchestration unavailability error** — unknown
- **Timeout and exit-code messages go to stdout, not execution logs** — unknown
- **Symlink creation doesn't verify target is readable** — unknown
- **Webhook handler swallows all error context** — unknown
- **Silent failures in scheduler state updates can cause hangs** — unknown
- **Token usage error loses stack trace** — unknown
- **SSE streaming errors not propagated to client** — unknown
- **Processing flag not reset when exception occurs before finally block** — unknown
- **Queue removal failure silently ignored in execution log service** — unknown
- **GitHub service subprocess failures not propagated to callers** — unknown
- **Corrupt conversation_log silently returns empty chat history** — unknown

### Decisions Made

None

### Patterns Discovered

None

### Takeaways

None

---
## Iteration 7
_2026-02-24T18:29:32.591Z_

### Items Attempted

- **Allowed tools list is hardcoded per execution** — unknown
- **No history when trigger prompt templates change** — unknown
- **Execution timeout uses threading.Timer instead of process-level kill** — unknown
- **30+ print() statements instead of structured logging** — unknown
- **Silent fallback to empty dict on JSON parse errors** — unknown
- **Stream read errors lose error details** — unknown
- **Temp directory cleanup not guaranteed on process cancellation** — unknown
- **EventSource registeredListeners Map grows unbounded** — unknown
- **Rate-limit retry scheduling has no max attempts or backoff** — unknown
- **Workflow graph not validated before execution** — unknown
- **Inconsistent null checking on execution dict keys** — unknown
- **Skill install success but silent registration failure** — unknown
- **SSE reconnection timer not cancelled in all teardown paths** — unknown

### Decisions Made

None

### Patterns Discovered

None

### Takeaways

None

---
## Iteration 8
_2026-02-24T19:11:28.592Z_

### Items Attempted

- **Budget limits not enforced during execution** — unknown
- **File watcher debounce interval is hardcoded** — unknown
- **No audit log for sensitive operations** — unknown
- **SSE stream has no backpressure handling** — unknown
- **Retry max attempt enforcement not visible in scheduler** — unknown
- **CLIProxy availability not reflected in health endpoint** — unknown
- **Rate-limit lock not in try/finally** — unknown
- **Orphaned subprocess on exception before finally** — unknown
- **Broad except clauses swallow context in monitoring_service** — unknown
- **Async handler exceptions swallowed in workflow execution** — unknown
- **Duplicate EventSource listeners on reconnect** — unknown
- **Subprocess stderr silently discarded on git calls** — unknown
- **subprocess command hardcodes stdbuf (Unix-only)** — unknown
- **Team topology generation lacks input size validation** — unknown

### Decisions Made

None

### Patterns Discovered

None

### Takeaways

None

---
## Iteration 9
_2026-02-24T19:45:24.461Z_

### Items Attempted

- **Rate limit retry uses linear delay instead of exponential backoff** — unknown
- **Team detail fetching has N+1 query pattern** — unknown
- **Event payload endpoints accept unvalidated dicts** — unknown
- **Monitoring silently degrades when scheduler is unavailable** — unknown
- **Webhook triggers lack debounce/deduplication** — unknown
- **Broad exception catching masks specific failures** — unknown
- **Silent exception suppression with empty pass blocks** — unknown
- **Exception handlers log without stack traces** — unknown
- **SSE queue overflow silently drops events** — unknown
- **Shared in-memory execution state has thread safety risks** — unknown
- **Database migrations have no rollback mechanism** — unknown

### Decisions Made

None

### Patterns Discovered

None

### Takeaways

None

---
## Iteration 10
_2026-02-24T20:04:18.668Z_

### Items Attempted

- **Trigger timeout_seconds not validated against allowed range** — unknown
- **Schedule trigger config accepts invalid day/time combos** — unknown
- **Duplicate trigger names not prevented** — unknown
- **Workflow versions always publish, no draft mode** — unknown
- **Execution cancellation grace period is hardcoded** — unknown
- **Pending retry queue not visible via API** — unknown
- **Workflow timeout is workflow-level only, not per-node** — unknown
- **Frontend uses any type extensively** — unknown
- **Bare except Exception in webhook handler** — unknown
- **Bare except Exception in GitHub webhook handler** — unknown
- **Debug print() calls left in production code** — unknown
- **Missing None checks before JSON field access** — unknown
- **Initialization errors logged but don't halt startup** — unknown
- **Race condition in ProcessManager registration** — unknown
- **No size limit on webhook payloads** — unknown

### Decisions Made

None

### Patterns Discovered

None

### Takeaways

None

---
## Iteration 11
_2026-02-24T20:43:07.271Z_

### Items Attempted

- **Scheduled trigger config not validated for correctness** — unknown
- **Duplicate trigger names allowed within a project** — unknown
- **Workflows publish immediately with no draft mode** — unknown
- **SIGTERM grace period hardcoded at 10 seconds** — unknown
- **Workflow nodes share a global timeout with no per-node control** — unknown
- **Excessive use of 'any' type in frontend API layer** — unknown
- **Audit log tracks entity lifecycle but not field-level changes** — unknown
- **Bare except Exception swallows all errors in webhook routes** — unknown
- **get_json() result not checked for None before use** — unknown
- **Race condition between process spawn and getpgid()** — unknown
- **Startup cleanup errors logged as warnings and swallowed** — unknown
- **Payload size check can be bypassed with wrong Content-Type** — unknown
- **DB CRUD functions lack connection error handling** — unknown

### Decisions Made

None

### Patterns Discovered

None

### Takeaways

None

---
## Iteration 12
_2026-02-24T21:14:56.721Z_

### Items Attempted

- **API client ignores Retry-After header on 429 responses** — unknown
- **Unsafe as unknown type casts in SSE event handler** — unknown
- **SSE backpressure queue has no metrics or warnings before saturation** — unknown
- **shell=True subprocess in workflow node execution** — unknown
- **35 bare except Exception catches swallow errors** — unknown
- **Race condition in ProcessManager.register()** — unknown
- **Multiple lock/unlock cycles allow race conditions in AgentConversationService** — unknown
- **Cloned directory cleanup silently fails on error** — unknown
- **Temp file cleanup in finally block has no exception guard** — unknown
- **SSE event queue overflow silently drops execution log events** — unknown
- **SSE stops retrying after max attempts with no user notification** — unknown
- **Fallback chain validation doesn't verify account-backend-type match** — unknown
- **Stale conversation cleanup is not scheduled automatically** — unknown
- **Workflow execution TTL cleanup uses daemon timer that dies on restart** — unknown

### Decisions Made

None

### Patterns Discovered

None

### Takeaways

None

---
## Iteration 13
_2026-02-24T21:38:53.973Z_

### Items Attempted

- **Workflow enable/disable toggle is hardcoded to fail** — unknown
- **No tests to verify migration correctness or idempotency** — unknown
- **Silent exception swallowing in provider_usage_client** — unknown
- **Silent OSError suppression in pty_service cleanup** — unknown
- **Silent failures in cliproxy_manager process cleanup** — unknown
- **Race condition in execution retry timer cancellation** — unknown
- **Unguarded numeric type conversions in provider_usage_client** — unknown
- **Unguarded int() cast in json_path array indexing** — unknown
- **SSE JSON parse errors silently swallowed in useProjectSession** — unknown
- **SSE event parse errors silently swallowed in useAiChat** — unknown
- **Missing catch on clipboard.writeText in useMarkdown** — unknown
- **Partial state corruption on edge save failure in useOrgCanvas** — unknown

### Decisions Made

None

### Patterns Discovered

None

### Takeaways

None

---
## Iteration 14
_2026-02-24T22:12:11.331Z_

### Items Attempted

- **Audit log service exists but has no UI** — unknown
- **No retry UI for failed executions or operations** — unknown
- **No proactive warnings when approaching rate limits** — unknown
- **SSE event drops are silent when queue is full** — unknown
- **YAML/JSON configs loaded without schema validation** — unknown
- **Silent failure on repo clone error** — unknown
- **Bare except swallows credential resolution errors** — unknown
- **Generic except swallows subprocess errors in backend detection** — unknown
- **Silent failure drops messages in agent message bus** — unknown
- **In-memory execution state lost on server restart** — unknown
- **No rate limiting on API endpoints** — unknown
- **Blocking git clone on execution thread** — unknown
- **No API versioning strategy** — unknown

### Decisions Made

None

### Patterns Discovered

None

### Takeaways

None

---
