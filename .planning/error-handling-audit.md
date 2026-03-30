# Error Handling Audit: feat/unified-auth-redesign

## CRITICAL Issues

### 1. `__init__.py:476-477` -- Empty catch block in error capture swallows arbitrary exceptions
**Severity:** CRITICAL
```python
except Exception:
    pass  # Never let error capture break error handling
```
**Hidden Errors:** ImportError (missing `error_capture` module), AttributeError, TypeError, database errors inside `capture_error()` itself. If `capture_error` is permanently broken, every 500 error silently loses its capture and nobody knows.
**Recommendation:** Log at DEBUG level: `logging.getLogger(__name__).debug("Error capture failed: %s", exc, exc_info=True)`. Same issue at line 517.

### 2. `__init__.py:55-56` -- Silent OSError on secret key persistence
**Severity:** CRITICAL
```python
except OSError:
    pass  # Fallback: ephemeral key (not ideal but won't crash)
```
**User Impact:** On every restart, Flask gets a new secret key, invalidating all sessions. Users get mysterious auth failures. The comment says "not ideal" -- it is actually a production outage for session-dependent features.
**Recommendation:** Log at WARNING level and add to `_startup_warnings` so it surfaces in `/health/readiness`.

### 3. `oauth_callback.py:67-69` -- Broad `Exception` catch leaks internal error details to browser
**Severity:** CRITICAL
```python
except Exception as exc:
    return (f"<html><body><h2>OAuth callback error</h2><p>{exc}</p></body></html>"), 502
```
**Hidden Errors:** This catches absolutely everything -- including `KeyError`, `AttributeError`, `MemoryError`. The raw `{exc}` is rendered in HTML without escaping, creating an XSS vector and leaking internal state (stack traces, file paths, environment variables).
**Recommendation:** Return a generic error message to the browser; log the full exception server-side.

### 4. `AccountWizard.vue:284-291` -- SSE onerror treats all disconnects as successful completion
**Severity:** CRITICAL
```typescript
loginEventSource.onerror = () => {
  if (loginStatus.value === 'streaming') {
    loginStatus.value = 'completed';
  }
};
```
**User Impact:** If the backend crashes, the network drops, or the server returns a 500, the user sees "Login successful!" when login actually failed. This is the textbook definition of a silent failure masquerading as success.
**Recommendation:** Set status to `'error'` on unexpected SSE close. Use a `complete` event from the server to distinguish normal completion from error disconnection.

---

## HIGH Issues

### 5. `useTourMachine.ts:66-74` -- fetchInstanceId silently returns null on all failures
**Severity:** HIGH
```typescript
async function fetchInstanceId(): Promise<string | null> {
  try { ... }
  catch { return null }
}
```
**Hidden Errors:** Network failures, CORS errors, JSON parse errors, server 500s. If the backend is down, the tour machine silently starts fresh instead of informing the user.
**User Impact:** Tour state is silently discarded on transient network errors. User loses progress without explanation.

### 6. `useTourMachine.ts:77-90` -- fetchWithAuth silently returns null on all failures
**Severity:** HIGH
Same pattern as #5. Guard checks (`runGuardChecks`) rely on this, meaning any API failure causes the tour to believe nothing is configured, potentially re-prompting users to redo steps.

### 7. `useTourMachine.ts:61-63` -- persistSnapshot empty catch block
**Severity:** HIGH
```typescript
catch {
  // localStorage may be full or unavailable -- degrade gracefully
}
```
**User Impact:** If localStorage is full, every tour transition silently fails to persist. The user completes the tour, refreshes, and starts from the beginning with no explanation.
**Recommendation:** At minimum, log to console.warn once.

### 8. `guards.ts:113-119` -- Auth status check swallows all errors, sets authChecked=true
**Severity:** HIGH
```typescript
catch {
  authChecked = true;
}
```
**Hidden Errors:** Network failures, CORS errors, server down. If the backend is unreachable, the app assumes "no setup needed" and skips the welcome page, then every API call fails with no auth context.
**User Impact:** Broken first-run experience when backend is temporarily unavailable.

### 9. `AccountWizard.vue:149-153` -- checkCli catch swallows all errors
**Severity:** HIGH
```typescript
catch {
  // Keep existing state
}
```
**Hidden Errors:** Network errors, 401/403 auth failures, JSON parse errors, timeouts. The user sees stale CLI status with no indication the check failed.

### 10. `AccountWizard.vue:306-308` -- sendResponse catch swallows all errors
**Severity:** HIGH
```typescript
catch {
  // Ignore -- session may have ended
}
```
**User Impact:** If the user's response fails to send for any reason (auth error, network, server error), they see their typed response echoed in the terminal as if it was sent, but the CLI never receives it. The session hangs with no feedback.

### 11. `useTour.ts:143-148` -- loadState returns empty object on parse failure
**Severity:** HIGH
```typescript
catch {
  return {}
}
```
**Hidden Errors:** Corrupted localStorage data, quota errors. Tour state silently resets.

### 12. `oauth_callback.py:72-79` -- _find_callback_port hardcoded fallback to 54545
**Severity:** HIGH
```python
return 54545
```
**User Impact:** If no session has a stored callback_port, the proxy silently tries port 54545. If a different service is on that port, the OAuth callback goes to the wrong place. No logging when the fallback is used.
**Recommendation:** Log a warning when falling back to the default port.

---

## MEDIUM Issues

### 13. `__init__.py:199-200` -- Flask request context failure silently drops host_url
**Severity:** MEDIUM
```python
except RuntimeError:
    pass  # Outside request context -- host_url stays None
```
**Impact:** If host_url is None, OAuth URL rewriting is silently skipped. The user gets an unreachable localhost URL in the browser.

### 14. `WelcomePage.vue:53-59` -- copyKey catch block provides no user feedback
**Severity:** MEDIUM
```typescript
catch {
  // Fallback: select the text
}
```
**User Impact:** The comment says "Fallback: select the text" but the catch body is empty -- it doesn't actually select the text. The copy silently fails and the user believes they copied the key.

### 15. `WelcomePage.vue:45-48` -- generateKey loses error details
**Severity:** MEDIUM
```typescript
catch (err) {
  error.value = t('welcome.generateFailed');
}
```
**Impact:** The actual error reason (403 "Already configured", network failure, etc.) is replaced with a generic i18n string. Users cannot distinguish between different failure modes.

### 16. `useTourMachine.ts:182-184` -- Snapshot restore silently falls back to fresh state
**Severity:** MEDIUM
```typescript
catch {
  sharedActor = createActor(tourMachine)
}
```
**Impact:** If the persisted snapshot is incompatible, the user's tour progress is silently lost with no console warning.

### 17. `backend_cli_service.py:342,346,350` -- Multiple silent `pass` blocks in cleanup
**Severity:** MEDIUM
The `OSError`, `ProcessLookupError`, and `ChildProcessError` catches during cleanup are defensible for resource cleanup, but they should at minimum log at DEBUG level for post-mortem analysis.

### 18. `AccountWizard.vue:324` -- cancelConnect error silently swallowed
**Severity:** MEDIUM
```typescript
backendApi.cancelConnect(props.backendId, loginSessionId.value).catch(() => {});
```
**Impact:** If session cancellation fails (e.g., orphaned process on server), nobody knows. The PTY process may leak.

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 4     |
| HIGH     | 8     |
| MEDIUM   | 6     |

The two most dangerous patterns in this PR are:
1. **SSE onerror treating disconnects as success** (#4) -- users will believe failed OAuth logins succeeded
2. **Broad Exception catch with unsanitized HTML output** (#3) -- XSS risk in OAuth callback
