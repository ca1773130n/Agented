# Frontend Production-Hardening Audit — Agented (Vue 3 + TS)

Scope: `frontend/src/` API client layer, App/main/env/i18n, router guards,
all `v-html`/`innerHTML` sinks, auth/session/token composables, and
SSE/streaming handling. Findings verified by reading source + tracing data
provenance into the backend where relevant.

## Severity summary

| Severity | Count |
|---|---|
| CRITICAL | 2 |
| HIGH | 3 |
| MEDIUM | 4 |
| LOW | 3 |

The API client (`services/api/client.ts`) and the canonical markdown
pipeline (`composables/useMarkdown.ts`, DOMPurify) are well-built: per-request
timeout via `AbortController`, exponential backoff + jitter, retry only on
transient statuses, Litestar error-shape unwrapping, rotated-token consumption,
and a backpressure-managed SSE queue with bounded reconnect. The hardening gaps
are concentrated in a handful of **`v-html` sinks that bypass DOMPurify** and
in **token storage in localStorage**.

---

## CRITICAL

### C1. Stored XSS via execution-log search snippets rendered with raw `v-html`
- **Files:** `views/ExecutionSearchPage.vue:143,147`; backend
  `app/services/execution_search_service.py:50-51`
- **Problem:** `result.stdout_match` / `result.stderr_match` are bound with
  `v-html` and contain **no client-side sanitization**. They originate from
  SQLite FTS5 `snippet(execution_logs_fts, 0, '<mark>', '</mark>', '...', 32)`.
  `snippet()` wraps matched terms in `<mark>` but does **not** HTML-escape the
  surrounding log text — the raw stdout/stderr of executed CLI harnesses
  (agent/tool-controlled, attacker-influenceable content) flows verbatim into
  the DOM. A log line containing `<img src=x onerror=...>` executes when an
  operator searches logs. This is stored XSS in the operator console.
- **Fix:** Server-side, HTML-escape the column text *before* calling
  `snippet()` (or escape the snippet output and re-introduce only the `<mark>`
  delimiters). Client-side defense-in-depth: run the snippet through
  `DOMPurify.sanitize(value, { ALLOWED_TAGS: ['mark'] })` in a computed before
  binding to `v-html`.

### C2. XSS via unsanitized agent/session markdown in `MarkdownContent.vue`
- **File:** `components/base/MarkdownContent.vue:33-43` (`marked.parse()` with
  **no DOMPurify**), consumed by `components/super-agents/MessageThread.vue:85`,
  `components/monitoring/HistoricalSessionViewer.vue:92`,
  `components/triggers/BranchNavigator.vue:176`
- **Problem:** The component's own doc comment admits the trust model — "Caller
  must ensure content originates from a source we already trust ... not for
  arbitrary user-uploaded markdown without a sanitizer." But it is fed
  `msg.content` from `AgentMessage` inbox/outbox (`MessageThread`) and from
  session history (`HistoricalSessionViewer`) — content produced by autonomous
  agents and remote triggers, i.e. **not** trusted. `marked` with default
  options passes through raw inline HTML, so an agent message containing
  `<img src=x onerror=fetch('/admin/...')>` runs in the operator's session
  (which holds the admin API key in localStorage — see H1).
- **Fix:** Route `MarkdownContent.vue` through the existing
  `renderMarkdown()` in `composables/useMarkdown.ts` (already DOMPurify-backed),
  or `DOMPurify.sanitize()` the `marked.parse()` output. Remove the
  "trusted-only" escape hatch since real callers pass untrusted data.

---

## HIGH

### H1. Session token + admin API key stored in localStorage (XSS-exfiltratable)
- **File:** `services/api/client.ts:16,22,32,54,64`
  (`agented-api-key`, `agented-session-token`); read back into `Authorization:
  Bearer` and `X-API-Key` on every request (lines 136-140).
- **Problem:** Both the bearer session token and the API key live in
  `localStorage`, which is readable by any executing script. Combined with the
  XSS sinks above (C1/C2), an injected script can read
  `localStorage['agented-session-token']` / `agented-api-key` and exfiltrate
  full operator credentials. localStorage tokens are the canonical XSS
  blast-radius amplifier.
- **Fix:** Prefer an `HttpOnly; Secure; SameSite` cookie for the session token
  (backend already rotates via `x-new-session-token` header — move that to a
  Set-Cookie). If cookies are infeasible, treat C1/C2 as release-blocking since
  they are the only thing that makes localStorage storage exploitable. At
  minimum, scope/short-TTL the token and never store the long-lived admin
  API key in the browser.

### H2. XSS via ANSI-to-HTML conversion with no escaping (live terminal)
- **File:** `views/LiveExecutionTerminal.vue:52-60,256`
- **Problem:** `ansiToHtml(line.text)` replaces ANSI escape codes with
  `<span style=...>` but **never HTML-escapes `line.text`** first. The result
  is bound with `v-html`. `line.text` is streamed stdout/stderr from the
  running harness. A log line like `</span><img src=x onerror=...>` injects
  arbitrary markup into the live terminal as it streams.
- **Fix:** HTML-escape `text` (`&`,`<`,`>`) **before** applying the ANSI→span
  replacements, exactly as the plaintext fallback in `useMarkdown.ts:83-86`
  already does. Optionally DOMPurify the final string.

### H3. XSS via search-highlight injecting both query and unescaped text
- **File:** `views/ExecutionTaggingPage.vue:223-235,354`
- **Problem:** `highlightMatch(text, query)` slices `text` (the log snippet)
  and the user's `query` into a string with `<mark>...</mark>` and binds it via
  `v-html` — neither `text` nor `query` is escaped. The log snippet is
  agent-controlled output, and the query is operator input; both reach the DOM
  unescaped.
- **Fix:** Escape `text` and the highlighted slice before concatenation; only
  the literal `<mark>` tags should be HTML. Or render with a text-node +
  `<mark>` element approach instead of `v-html`.

---

## MEDIUM

### M1. Self-XSS via hand-rolled markdown link regex in DocumentEditor
- **File:** `components/super-agents/DocumentEditor.vue:106-139,197`
- **Problem:** A bespoke `renderMarkdown` escapes `<>&` up front (good) but
  then re-introduces HTML via regex, including
  `[text](url) -> <a href="$2" target="_blank">`. Because the captured URL is
  not validated/escaped, a payload like `[x](javascript:alert(1))` or a URL
  containing `"` breaks out of the attribute. Content is the editor's own
  `editContent` (operator-typed preview), so impact is self-XSS / lower, but it
  is still an unsanitized `v-html` path that diverges from the DOMPurify
  pipeline.
- **Fix:** Replace with `renderMarkdown()` from `useMarkdown.ts`, or
  `DOMPurify.sanitize()` the output and reject non-`http(s)`/relative hrefs.

### M2. `v-html` of i18n strings with interpolated HTML
- **Files:** `views/WelcomePage.vue:132`,
  `components/tour/TourOverlay.vue:262`, `components/monitoring/RateLimitGauge.vue:105`
- **Problem:** These bind `t(...)` output to `v-html`. Values are currently
  static (locale catalog strings + developer-supplied interpolation, e.g.
  `RateLimitGauge.label` comes from `gaugeLabel()`/`t()` in
  `MonitoringAccountCard.vue`, and `TourOverlay` interpolates `step.title`).
  No untrusted data flows in today, so this is not currently exploitable — but
  `v-html` on translation strings is a fragile pattern: a future catalog entry
  or a dynamic `step.title`/`label` makes it XSS. `TourOverlay` interpolating
  `currentTargetName` into `<strong>${...}</strong>` is the closest to dynamic.
- **Fix:** Prefer slot/`<i18n-t>` component interpolation or split into
  separate `t()` + static markup so no translation value reaches `v-html`.
  If `v-html` must stay, assert the inputs are constant and add a lint guard.

### M3. `v-html` for inline SVG icons (currently static, drift risk)
- **File:** `components/triggers/TriggerList.vue:99` via `getTriggerIcon()`
- **Problem:** `getTriggerIcon(trigger.trigger_source)` returns hardcoded SVG
  strings selected by a `switch` — safe today. The `default` branch returns a
  fixed SVG (not the raw source), so no untrusted value reaches `v-html`. Flagged
  as a maintenance hazard: if the function ever returns interpolated/server
  data it becomes XSS.
- **Fix:** Render the SVGs as static `<template>` components or an icon map
  rather than `v-html` strings.

### M4. Auth route guard is trivially bypassable (defense-in-depth only)
- **File:** `router/guards.ts:99-172`
- **Problem:** The `beforeEach` guard gates non-public routes on
  `getApiKey()`/`getSessionToken()` presence and a one-time `authStatus()`
  check; entity validation "fails open on network errors." This is purely
  client-side and bypassable by anyone (edit localStorage, skip the SPA). That
  is acceptable **only if** every `/admin/*` and `/api/*` endpoint enforces
  authz server-side. This audit did not verify server-side enforcement —
  flagging as a cross-cutting requirement, not a frontend-fixable bug.
- **Fix:** Confirm backend middleware (`app_litestar/middleware.py` ApiKey /
  bearer gate) rejects unauthenticated/unauthorized calls for all protected
  routes. Treat the guard strictly as UX, never as the security boundary.

---

## LOW

### L1. `console.error`/`console.warn` left in production code
- **Files:** `main.ts:62` (global error handler logs full `err`),
  `composables/useProjectSession.ts` (many `console.warn` with raw `event.data`),
  `services/api/client.ts:286-300` (SSE queue warnings),
  `router/guards.ts:33,170`, `components/.../CredentialStatusBanner.vue:59`, etc.
- **Problem:** None log tokens/passwords/keys directly (verified: the only
  credential-adjacent log is `CredentialStatusBanner` logging an error object,
  not a secret). But raw `event.data` and error objects in
  `useProjectSession.ts` may include backend payloads, and verbose logging aids
  reconnaissance in production.
- **Fix:** Gate diagnostic logs behind `import.meta.env.DEV` (as the
  `warnHandler` in `main.ts:84` already does), or route through a logger that
  strips payloads in prod. Keep the user-facing toast in `main.ts`.

### L2. External font loaded from Google CDN at runtime
- **File:** `App.vue:278` — `@import url('https://fonts.googleapis.com/...')`
- **Problem:** Runtime dependency on a third-party origin (privacy + a
  third-party that could serve CSS). Not a secret leak; the CLAUDE.md states
  Geist is the project font, so this is intentional, but it is the only
  hardcoded external URL in `src/` and bypasses any self-hosting/CSP hardening.
- **Fix:** Self-host the Geist/Geist Mono woff2 files and add the font origin
  to CSP (`SecurityHeaders` middleware) if kept remote.

### L3. SSE `onerror`/`scheduleReconnect` give-up is silent to the user
- **File:** `services/api/client.ts:399-407,472-476`;
  `composables/useEventSource.ts:110`
- **Problem:** After `SSE_MAX_ATTEMPTS` (10) the connection calls optional
  `onGiveUp()` and stops; `useConversation.ts:189-190` comments that native
  reconnect handles drops "no toast needed." If `onGiveUp` is not wired by a
  consumer, a permanently-dead stream looks like a hung-but-fine UI (honesty of
  state). Connections are otherwise correctly closed on unmount
  (`close()` aborts + clears queue/timeout) — no leak found.
- **Fix:** Ensure every SSE consumer wires `onGiveUp`/`onerror` to a visible
  "connection lost — retry" state so a dead stream is never indistinguishable
  from an idle one.

---

## Things checked and found OK (no action)

- `services/api/client.ts`: per-request timeout (`DEFAULT_TIMEOUT_MS` 120s) via
  `AbortController`, external-signal merge, retry on `[429,502,503,504]` + network
  `TypeError` only, jittered backoff, `Retry-After` honored, never retries
  aborts/timeouts. Errors are surfaced as typed `ApiError`, not swallowed.
- Litestar error-shape unwrapping (lines 169-178) avoids `[object Object]` leaks.
- Rotated session token consumed from `x-new-session-token` header (line 155).
- SSE: backpressure queue with bounded size + rAF draining, fatal-401 stops
  reconnect, `close()` fully tears down (abort + timers + listeners + queue).
- `composables/useMarkdown.ts`: `renderMarkdown()` and `highlightCodeBlocks()`
  both DOMPurify-sanitize; `template.innerHTML` at line 147 receives only
  already-sanitized shiki output.
- `useAuth.ts`: clears token on `me()` failure (expired/revoked), best-effort
  logout revoke, no token logging.
- `env.ts`: no secrets; only `VITE_ALLOWED_HOSTS` validated via zod.
- No `eval`, no `dangerouslySetInnerHTML`, no `document.write` in `src/`.
- No hardcoded API keys/secrets/passwords in `src/` (only the Google Fonts URL).
- `API_BASE = ''` (same-origin/proxy) — no hardcoded backend host.
