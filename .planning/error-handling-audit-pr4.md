# Error Handling Audit: PR #4 feat/agent-memory-tracing

## CRITICAL Issues

### 1. `backend/app/db/agent_memory.py:_row_with_json_metadata` (lines ~305-312) -- JSON parse failure silently returns raw string as metadata

```python
except (json.JSONDecodeError, TypeError):
    pass
```

**Severity:** CRITICAL

**Issue:** When `metadata` contains malformed JSON (e.g., truncated by a DB migration bug, manual edit, or encoding issue), the except block does nothing -- `d["metadata"]` remains the raw unparsed string. Every consumer of this dict now receives a `str` where they expect a `dict | None`. This will cause `TypeError` or `AttributeError` downstream when code tries to call `.get()` or iterate on the metadata, and the stack trace will point to the consumer, not to the real cause (corrupt data).

**Hidden Errors:** Database corruption, encoding issues, migration bugs that truncate JSON. All silently masked.

**User Impact:** API returns metadata as a raw JSON string instead of an object. Frontend JS code calling `metadata.key` silently gets `undefined` on a string. No log, no indication the data is corrupt.

**Recommendation:** Log a warning with the entity ID and the raw value, then set metadata to `None` so consumers have a clean contract:
```python
except (json.JSONDecodeError, TypeError):
    logger.warning("Corrupt JSON in metadata for row id=%s: %r", d.get("id"), d.get("metadata"))
    d["metadata"] = None
```

### 2. `backend/app/db/tracing.py:_parse_json_field` (lines ~320-326) -- JSON parse failure silently returns the raw string

```python
except (json.JSONDecodeError, TypeError):
    return value
```

**Severity:** CRITICAL

**Issue:** This is the same pattern as #1, but worse because it explicitly returns the unparsed string as if it were a valid parsed value. Both `_trace_row_to_dict` and `_span_row_to_dict` call this for `input`, `output`, `attributes`, and `metadata` fields. Any corrupt JSON silently becomes a string in the API response, violating the API contract (these fields should be `dict | null`).

**Hidden Errors:** All JSON corruption in 4 different fields across 2 tables. The function is called ~8 times per trace+spans response.

**User Impact:** The frontend receives `"{"truncated..."` as a string instead of an object for trace input/output. TypeScript code accessing `.key` on what it expects is an object will fail silently or throw.

**Recommendation:** Log and return `None`:
```python
except (json.JSONDecodeError, TypeError):
    logger.warning("Corrupt JSON field value: %r", value[:200] if isinstance(value, str) else value)
    return None
```

### 3. `backend/app/db/tracing.py:end_span` (lines ~205-212) -- JSON parse failure in attributes merge silently drops existing attributes

```python
try:
    existing = json.loads(row["attributes"])
except (json.JSONDecodeError, TypeError):
    pass
```

**Severity:** CRITICAL

**Issue:** If the existing span attributes contain corrupt JSON, the except block silently leaves `existing = {}`, then `existing.update(attributes)` overwrites all previous attributes with only the new ones. This is data loss without any logging.

**Hidden Errors:** Corrupt attributes from a previous `update_span` call, encoding issues, concurrent write corruption.

**User Impact:** Span attributes silently disappear during an `end_span` call. Debugging observability data that itself has data loss is deeply ironic and hard to diagnose.

**Recommendation:** Log the corruption and preserve the raw value in a `_corrupt_attributes` field, or at minimum warn:
```python
except (json.JSONDecodeError, TypeError):
    logger.warning("Corrupt attributes JSON for span %s, overwriting: %r", span_id, row["attributes"])
```

### 4. `backend/app/db/tracing.py:update_span` (lines ~240-245) -- Identical silent attribute corruption as #3

```python
try:
    existing = json.loads(row["attributes"])
except (json.JSONDecodeError, TypeError):
    pass
```

**Severity:** CRITICAL

Same pattern, same data-loss consequence. Corrupt existing attributes are silently replaced.

---

## HIGH Issues

### 5. `backend/app/db/agent_memory.py:recall_messages` -- FTS5 query errors completely unhandled

**Severity:** HIGH

**Issue:** The `recall_messages` function builds an FTS5 query from user input (`query.split()`) with basic escaping, but FTS5 has a complex query syntax. Characters like `*`, `-`, `(`, `)`, `AND`, `OR`, `NOT`, `NEAR` have special meaning. A user searching for `"C++ memory-leak (segfault)"` could cause an `sqlite3.OperationalError` that propagates as an unhandled 500 to the API.

**Hidden Errors:** `sqlite3.OperationalError` from malformed FTS5 queries will become raw 500 errors.

**User Impact:** Users searching for technical terms containing FTS5 syntax characters get unexplained 500 errors instead of a helpful "invalid search query" message.

**Recommendation:** Wrap the FTS5 query execution in a try/except for `sqlite3.OperationalError` and return an empty result list with a warning log, or sanitize FTS5 special characters more thoroughly.

### 6. `backend/app/routes/agent_memory.py:get_memory_config` (lines ~213-217) -- JSON parse failure silently returns default config

```python
try:
    config = json.loads(agent["memory_config"])
except (json.JSONDecodeError, TypeError):
    pass
```

**Severity:** HIGH

**Issue:** If an agent's `memory_config` is corrupt, the user silently gets the default config back. They may have spent time customizing settings that are now invisible to them. No log is emitted.

**User Impact:** Agent configuration silently resets to defaults. User sees default values instead of their customization, with no indication that their saved config is corrupt.

**Recommendation:** Log a warning and include an `_config_error` flag in the response so the frontend can surface it.

### 7. `backend/app/routes/agent_memory.py:update_memory_config` (lines ~232-236) -- Same silent JSON failure as #6

```python
try:
    existing = json.loads(agent["memory_config"])
except (json.JSONDecodeError, TypeError):
    pass
```

**Severity:** HIGH

**Issue:** When updating config, corrupt existing config is silently replaced with `{}` before the merge. The user's non-updated fields are silently lost.

**User Impact:** User updates one config field, all other previously saved fields silently disappear.

### 8. `backend/app/db/agent_memory.py:get_working_memory` (lines ~260-264) -- JSON parse failure sets content_parsed to None without logging

```python
try:
    d["content_parsed"] = json.loads(d["content"])
except (json.JSONDecodeError, TypeError):
    d["content_parsed"] = None
```

**Severity:** HIGH

**Issue:** While setting `content_parsed = None` is a reasonable fallback (content may legitimately be plain text, not JSON), there is no way to distinguish "content is plain text" from "content was supposed to be JSON but is corrupt." No log is emitted.

**User Impact:** If working memory content was intended to be structured JSON and gets corrupted, nobody knows.

**Recommendation:** This is borderline acceptable since content may be plain text by design, but a DEBUG-level log would help:
```python
except (json.JSONDecodeError, TypeError):
    d["content_parsed"] = None
    logger.debug("Working memory content for %s is not valid JSON (expected for plain text)", entity_id)
```

---

## MEDIUM Issues

### 9. `backend/app/db/tracing.py:end_trace` (lines ~123-128) -- No handling for missing/corrupt `started_at`

**Severity:** MEDIUM

**Issue:** `datetime.fromisoformat(row["started_at"])` will raise `ValueError` if `started_at` is corrupt or in an unexpected format. This would crash the entire `end_trace` call even though the duration calculation is non-essential.

**User Impact:** A trace with a corrupt `started_at` cannot be ended -- every attempt returns a 500.

**Recommendation:** Wrap the duration calculation in a try/except, log the issue, and proceed with `duration_ms = None`.

### 10. `backend/app/db/tracing.py:end_span` (lines ~192-196) -- Same datetime parsing risk as #9

**Severity:** MEDIUM

Same `datetime.fromisoformat()` without error handling for the span's `started_at`.

### 11. `backend/app/routes/agent_memory.py` -- No try/except around any DB operations in routes

**Severity:** MEDIUM

**Issue:** None of the route handlers wrap DB calls in try/except. A `sqlite3.IntegrityError` (e.g., duplicate key race condition on thread creation) or `sqlite3.OperationalError` (e.g., disk full, locked database) will propagate as raw 500 errors with SQLite error messages exposed to the user.

**Recommendation:** Add a route-level error handler or middleware that catches `sqlite3.Error` and returns a proper error response with logging.

### 12. `backend/app/routes/tracing.py` -- Same missing DB error handling as #11

**Severity:** MEDIUM

Same issue for all tracing route handlers.

### 13. `backend/app/db/agent_memory.py:save_messages` -- No validation that thread exists before inserting messages

**Severity:** MEDIUM

**Issue:** If `thread_id` does not exist (or was deleted between the route's check and the insert), the messages are inserted as orphans. The subsequent `UPDATE memory_threads SET updated_at` silently affects 0 rows with no error.

**User Impact:** Messages saved to a deleted thread are invisible -- they exist in the DB but no thread references them.

### 14. `backend/app/db/agent_memory.py:recall_messages` -- Empty query silently returns empty list

**Severity:** MEDIUM

**Issue:** `if not words: return []` silently returns empty results for whitespace-only queries. While this is a reasonable guard, the route layer (`recall_agent_memory`) does not distinguish "no results found" from "query was empty/invalid."

**User Impact:** Minor -- user just sees 0 results. But the API response gives no indication the query was effectively empty.

---

## Summary

| Severity | Count | Description |
|----------|-------|-------------|
| CRITICAL | 4     | Silent JSON corruption handling, data loss in attribute merges |
| HIGH     | 4     | Silent config resets, unhandled FTS5 errors, missing corruption logging |
| MEDIUM   | 6     | Unhandled datetime parsing, missing DB error handlers in routes, orphan records |

## Most Dangerous Patterns

1. **The `_parse_json_field` returning raw strings** (#2) -- This corrupts the API contract for every JSON field in every trace and span response. When data corruption occurs, the frontend receives strings where it expects objects, causing cascading silent failures in the UI.

2. **Silent attribute data loss during span updates** (#3, #4) -- The tracing system, designed for observability and debugging, silently destroys its own data when JSON corruption occurs. This is particularly dangerous because the tool meant to help debug problems has an undetectable data loss bug.

3. **Unhandled FTS5 query syntax** (#5) -- User-provided search queries can crash the recall endpoint with 500 errors when they contain characters that are valid in natural language but special in FTS5 syntax.
