# Phase 16: Frontend Quality & User Experience - Research

**Researched:** 2026-03-04
**Domain:** Vue 3 frontend UX patterns -- error boundaries, loading states, SSE composables, API error handling, environment validation
**Confidence:** HIGH

## Summary

This phase addresses nine UX requirements across five categories: loading/error states (UX-01, UX-05, UX-06, UX-08), error boundaries (UX-02), SSE composable consolidation (UX-03), centralized API error handling (UX-04), OpenAPI documentation (UX-07), and startup environment validation (UX-09). The codebase already has strong foundations -- `LoadingState`, `ErrorState`, and `EmptyState` base components exist; `apiFetch` with retry logic and `createAuthenticatedEventSource` with backoff/backpressure are production-ready; and `useToast` provides typed toast injection. The gaps are: (1) no Vue error boundary component (`onErrorCaptured` is unused anywhere), (2) sidebar fires 7 concurrent fetches with only `console.warn` on failure (no loading indicator, no retry), (3) `useConversation` and `useAiChat` duplicate SSE connection setup patterns, (4) API errors are inconsistently surfaced (mix of `showToast`, `console.warn`, and silent `catch {}`), and (5) OpenAPI endpoint summaries are partial.

**Primary recommendation:** Build all nine features as additive layers on top of existing infrastructure -- wrap `router-view` in a new `ErrorBoundary.vue` using `onErrorCaptured`, extract a `useEventSource` composable from the common SSE patterns, create a centralized `handleApiError` function that maps `ApiError.status` to user-friendly messages with error codes, coordinate sidebar loading with `Promise.allSettled`, and add `@julr/vite-plugin-validate-env` for startup validation.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Vue 3 | ^3.5.24 | UI framework | Already in use; `onErrorCaptured` hook is the standard Vue error boundary mechanism |
| @microsoft/fetch-event-source | ^2.0.1 | Authenticated SSE | Already in use via `createAuthenticatedEventSource`; supports custom headers unlike native `EventSource` |
| vue-router | ^4.6.4 | Routing | Already in use; `router-view` wrapping for error boundaries |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| @julr/vite-plugin-validate-env | latest | Build/dev-time env validation | UX-09: fail-fast on missing `VITE_*` variables |
| zod | (transitive via zod-to-json-schema) | Schema validation | UX-09: already a transitive dep; use for env schema definition |

### Alternatives Considered

| Instead of | Could Use | Tradeoff | Rationale |
|------------|-----------|----------|-----------|
| Hand-rolled ErrorBoundary | vu-error-boundary (npm) | Adds dependency for ~30 lines of code | Hand-roll preferred -- Vue's `onErrorCaptured` is trivial to wrap |
| @julr/vite-plugin-validate-env | Custom env check in main.ts | Plugin validates at build AND dev time; runtime-only misses build CI | Plugin preferred for fail-fast at every stage |
| VueUse useEventSource | Custom useEventSource | VueUse's version doesn't support authenticated headers or backpressure | Custom preferred -- must wrap existing `createAuthenticatedEventSource` |

**Installation:**
```bash
cd frontend && npm install --save-dev @julr/vite-plugin-validate-env
```

No other new dependencies required. All other work uses existing libraries and Vue 3 built-in APIs.

## Architecture Patterns

### Recommended Project Structure

```
frontend/src/
  components/
    base/
      ErrorBoundary.vue      # NEW: Vue error boundary using onErrorCaptured
      LoadingState.vue        # EXISTS: enhance with skeleton variant prop
      ErrorState.vue          # EXISTS: enhance with error code + action props
      EmptyState.vue          # EXISTS: no changes needed
  composables/
    useEventSource.ts         # NEW: shared SSE composable extracted from useConversation/useAiChat
    useConversation.ts        # MODIFY: delegate SSE to useEventSource
    useAiChat.ts              # MODIFY: delegate SSE to useEventSource
    useProjectSession.ts      # MODIFY: delegate SSE to useEventSource
    useToast.ts               # EXISTS: no changes needed
  services/
    api/
      client.ts               # MODIFY: add centralized error handler
      error-handler.ts        # NEW: ApiError -> user-friendly message mapping
  env.ts                      # NEW: environment variable schema + validation
```

### Pattern 1: Vue Error Boundary via `onErrorCaptured`

**What:** A component that catches rendering errors in its subtree and displays a fallback UI with recovery option instead of crashing the entire SPA.

**When to use:** Wrap `<router-view>` in `App.vue` and optionally wrap individual high-risk sections (canvas views, chart components).

**How it works:** Vue's `onErrorCaptured(err, instance, info)` lifecycle hook fires when an error propagates from a descendant component. Returning `false` stops propagation (prevents SPA crash). The component switches to an error state slot showing the error message and a "Recover" button that resets by incrementing a `:key` on the default slot wrapper, forcing Vue to re-create the subtree.

**Example:**
```vue
<script setup lang="ts">
import { ref, onErrorCaptured } from 'vue';

const hasError = ref(false);
const errorMessage = ref('');
const recoveryKey = ref(0);

onErrorCaptured((err: Error) => {
  hasError.value = true;
  errorMessage.value = err.message;
  return false; // Stop propagation -- prevents SPA crash
});

function recover() {
  hasError.value = false;
  errorMessage.value = '';
  recoveryKey.value++; // Force re-creation of child subtree
}
</script>

<template>
  <div v-if="hasError" class="error-boundary-fallback">
    <h2>Something went wrong</h2>
    <p>{{ errorMessage }}</p>
    <button @click="recover">Try Again</button>
  </div>
  <slot v-else :key="recoveryKey" />
</template>
```

**Limitation:** `onErrorCaptured` only catches errors during Vue lifecycle hooks and rendering. Errors in event handlers (`@click`, `@submit`) are NOT caught. Those must be handled via try/catch in the handler itself or via the centralized API error handler.

### Pattern 2: Centralized API Error Handler

**What:** A single function that maps `ApiError` status codes to user-friendly messages with error codes and suggested actions.

**When to use:** In every `catch` block that handles API calls, replacing inconsistent `showToast(e.message, 'error')` patterns.

**Example:**
```typescript
// services/api/error-handler.ts
import type { ShowToastFn } from '../../composables/useToast';

interface ErrorMapping {
  code: string;
  message: string;
  action: string;
}

const STATUS_MAP: Record<number, ErrorMapping> = {
  0:   { code: 'ERR-TIMEOUT', message: 'Request timed out', action: 'Check your connection and try again.' },
  401: { code: 'ERR-401', message: 'Unauthorized', action: 'Check your API key in Settings.' },
  403: { code: 'ERR-403', message: 'Forbidden', action: 'You do not have permission for this action.' },
  404: { code: 'ERR-404', message: 'Not found', action: 'The resource may have been deleted. Return to the list.' },
  409: { code: 'ERR-409', message: 'Conflict', action: 'The resource was modified. Refresh and try again.' },
  422: { code: 'ERR-422', message: 'Validation error', action: 'Check your input and try again.' },
  429: { code: 'ERR-429', message: 'Rate limited', action: 'Wait a moment and try again.' },
  500: { code: 'ERR-500', message: 'Server error', action: 'The server encountered an error. Try again later.' },
  503: { code: 'ERR-503', message: 'Service unavailable', action: 'The service is temporarily down. Try again shortly.' },
};

export function formatApiError(status: number, serverMessage?: string): string {
  const mapping = STATUS_MAP[status];
  if (mapping) {
    const detail = serverMessage && serverMessage !== `HTTP ${status}` ? ` (${serverMessage})` : '';
    return `${mapping.message}${detail} (${mapping.code}). ${mapping.action}`;
  }
  return serverMessage || `Unexpected error (ERR-${status}). Try again or contact support.`;
}

export function handleApiError(error: unknown, showToast: ShowToastFn, fallbackMessage = 'Operation failed'): string {
  if (error instanceof ApiError) {
    const message = formatApiError(error.status, error.message);
    showToast(message, 'error');
    return message;
  }
  const message = error instanceof Error ? error.message : fallbackMessage;
  showToast(`${message} (ERR-UNKNOWN). Try again.`, 'error');
  return message;
}
```

### Pattern 3: Shared useEventSource Composable

**What:** A composable that encapsulates the common SSE connection lifecycle: create connection, register typed event listeners, handle cleanup on unmount.

**When to use:** Replace duplicated SSE setup in `useConversation`, `useAiChat`, and `useProjectSession`.

**Key design decisions:**
- Wraps `createAuthenticatedEventSource` (not native `EventSource`) to preserve authenticated headers and backpressure
- Returns reactive `status` ref (`connecting`, `open`, `error`, `closed`)
- Accepts a typed event map so consumers declare their event handlers declaratively
- Handles `onUnmounted` cleanup automatically
- Does NOT dictate message parsing -- each consumer parses their own event format

**Example:**
```typescript
// composables/useEventSource.ts
import { ref, onUnmounted, type Ref } from 'vue';
import { createAuthenticatedEventSource, type AuthenticatedEventSource } from '../services/api/client';

type SSEStatus = 'idle' | 'connecting' | 'open' | 'error' | 'closed';

interface UseEventSourceOptions {
  url: string | Ref<string>;
  events?: Record<string, (event: MessageEvent) => void>;
  onOpen?: () => void;
  onError?: (event: Event) => void;
  autoConnect?: boolean;
}

export function useEventSource(options: UseEventSourceOptions) {
  const status = ref<SSEStatus>('idle');
  let source: AuthenticatedEventSource | null = null;

  function connect() {
    close();
    status.value = 'connecting';
    const url = typeof options.url === 'string' ? options.url : options.url.value;
    source = createAuthenticatedEventSource(url);

    source.onopen = () => {
      status.value = 'open';
      options.onOpen?.();
    };

    source.onerror = (event) => {
      status.value = 'error';
      options.onError?.(event);
    };

    if (options.events) {
      for (const [eventName, handler] of Object.entries(options.events)) {
        source.addEventListener(eventName, handler);
      }
    }
  }

  function close() {
    if (source) {
      source.close();
      source = null;
    }
    status.value = 'closed';
  }

  if (options.autoConnect !== false) {
    connect();
  }

  onUnmounted(close);

  return { status, connect, close, source: () => source };
}
```

### Pattern 4: Sidebar Loading Coordination via Promise.allSettled

**What:** Wrap all 7 sidebar data fetches in `Promise.allSettled()` to coordinate a unified loading state. Show a skeleton/spinner while any fetch is pending. On individual failures, show the sidebar with degraded sections (error indicator per section) rather than blocking the entire sidebar.

**When to use:** Replace the current 7 independent `loadX()` calls in `App.vue:onMounted`.

**Example:**
```typescript
const sidebarLoading = ref(true);
const sidebarErrors = ref<Record<string, string | null>>({});

async function loadSidebarData() {
  sidebarLoading.value = true;
  const results = await Promise.allSettled([
    loadTriggers(),
    loadProjects(),
    loadProducts(),
    loadTeams(),
    loadPlugins(),
    loadSidebarBackends(),
    loadVersion(),
  ]);

  const keys = ['triggers', 'projects', 'products', 'teams', 'plugins', 'backends', 'version'];
  results.forEach((result, i) => {
    sidebarErrors.value[keys[i]] = result.status === 'rejected' ? result.reason?.message : null;
  });

  sidebarLoading.value = false;
}
```

### Anti-Patterns to Avoid

- **Silent `console.warn` on user-visible errors:** Six sidebar fetch failures in `App.vue` only log to console. Users see stale/empty sidebar sections with no indication of failure. Always surface errors visually.
- **Raw exception text in UI:** `showToast(e.message, 'error')` can expose stack traces or technical messages like `"HTTP 503"`. Always map through the centralized error handler.
- **Duplicated SSE boilerplate:** Three composables (`useConversation`, `useAiChat`, `useProjectSession`) each independently manage SSE lifecycle (connect, event registration, error handling, cleanup). Extract the shared pattern.
- **Global `app.config.errorHandler` without recovery:** Setting a global error handler logs errors but provides no recovery path. An error boundary component with a recovery button is strictly better.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Build-time env validation | Custom Vite plugin | `@julr/vite-plugin-validate-env` | Handles build, dev, and preview modes; integrates with Zod schemas |
| SSE reconnection + backoff | New reconnection logic | `createAuthenticatedEventSource` (existing) | Already handles backoff, backpressure queue, auth header injection, fatal error detection |
| Skeleton loading animations | Custom CSS keyframe skeletons | CSS `background-size` animation on pseudo-element | Skeleton shimmer is a solved CSS pattern -- 10 lines of CSS, no JS |
| Error code catalog | Per-component error strings | Centralized `STATUS_MAP` in `error-handler.ts` | Single source of truth for all error messages; easy to update and localize |

**Key insight:** This phase is about consistency and consolidation, not new capabilities. The individual building blocks (toast system, API client, SSE client, base components) already exist. The work is wiring them together into a cohesive error/loading UX.

## Common Pitfalls

### Pitfall 1: onErrorCaptured Not Catching Event Handler Errors

**What goes wrong:** Developers add `ErrorBoundary` wrapping `<router-view>` and assume all errors are caught. Then a `@click` handler throws and the SPA still shows a blank screen.

**Why it happens:** Vue's `onErrorCaptured` only captures errors during rendering, lifecycle hooks, and watchers. Event handler errors (`@click`, `@submit`, `@input`) propagate to `window.onerror` instead.

**How to avoid:** Keep try/catch in all event handlers that call API methods. The centralized `handleApiError` function reduces boilerplate. For defense-in-depth, also set `app.config.errorHandler` in `main.ts` to log uncaught errors and show a toast.

**Warning signs:** `window.onerror` or `unhandledrejection` events in the console despite having an ErrorBoundary.

### Pitfall 2: Sidebar Loading Blocks Navigation

**What goes wrong:** If sidebar loading uses a full-page spinner, users cannot navigate for 2-3 seconds on slow connections. The sidebar should load progressively, not block.

**Why it happens:** Using a single boolean `isLoading` gates all content rendering, including the router-view.

**How to avoid:** `sidebarLoading` only affects the sidebar component, not the `<router-view>`. The main content area loads independently. Use skeleton placeholders in the sidebar itself.

**Warning signs:** Users on slow connections report being unable to click any link until the page fully loads.

### Pitfall 3: Retry Buttons Re-fetching Everything

**What goes wrong:** A "Retry" button on a failed section triggers a full page reload or re-fetches all data, including sections that loaded successfully.

**Why it happens:** The retry handler calls the page-level `loadAll()` function instead of the section-specific `loadX()` function.

**How to avoid:** Each section with independent data should have its own `isLoading` + `error` + `retry()` triple. The `ErrorState` component already emits a `retry` event -- wire it to the section-specific loader. For the sidebar, each of the 7 fetches should be independently retryable.

**Warning signs:** Clicking "Retry" on a single failed section causes other sections to flash/reload.

### Pitfall 4: SSE Composable Losing Protocol-Specific Logic

**What goes wrong:** Extracting SSE into a shared composable strips away protocol-specific parsing (e.g., `state_delta` seq tracking in `useAiChat`, `response_chunk` streaming markdown in `useConversation`).

**Why it happens:** Over-abstraction -- trying to make the shared composable handle all event types.

**How to avoid:** The shared `useEventSource` composable handles ONLY connection lifecycle (connect, reconnect, cleanup, status tracking). Event-specific parsing stays in each consumer composable. The shared composable accepts an event map of handlers, not event type definitions.

**Warning signs:** The shared composable has protocol-specific imports or type definitions from a single consumer.

### Pitfall 5: Environment Validation Breaking Existing Deployments

**What goes wrong:** Adding strict env validation causes all existing deployments (that never set certain `VITE_*` vars) to fail on next build.

**Why it happens:** Required env vars are enforced without defaults for vars that previously had implicit defaults.

**How to avoid:** Currently the frontend has only one env var (`VITE_ALLOWED_HOSTS`), which is optional. The validation schema should mark it as optional with a default of `''`. Only add required validation for truly critical vars. Use `optional().default()` pattern in the Zod schema.

**Warning signs:** CI builds that previously succeeded start failing with "missing env var" errors.

## Experiment Design

### Recommended Experimental Setup

**Independent variables:** Error boundary placement strategy (router-view only vs. nested per-section), skeleton vs. spinner loading indicators, centralized vs. distributed API error handling.

**Dependent variables:** SPA crash rate (should be zero with error boundary), loading indicator coverage (% of async views with loading states), error message consistency (all errors should include error code + action).

**Controlled variables:** Same backend, same API surface, same browser matrix.

**Baseline comparison:**
- Method: Current state -- no error boundary, inconsistent loading/error states, duplicated SSE code
- Expected performance: Some views show blank content during load, SPA crashes on component render errors, sidebar loads silently fail
- Our target: Zero SPA crashes from component errors, all async views show loading feedback, all API errors show actionable messages

**Ablation plan:**
1. Error boundary only (UX-02) vs. full phase -- tests whether error boundary alone prevents SPA crashes
2. Centralized error handler only (UX-04) vs. full phase -- tests whether error messaging improves without other changes
3. Shared SSE composable only (UX-03) -- tests code reduction without UX changes

**Statistical rigor:**
- Number of runs: Manual smoke testing of all ~60 views for loading/error states
- Error injection: Deliberately throw errors in components to verify boundary catches them
- Network simulation: Slow 3G throttle to verify skeleton/loading states are visible

### Recommended Metrics

| Metric | Why | How to Compute | Baseline |
|--------|-----|----------------|----------|
| SPA crash rate | UX-02 success | Throw error in child of ErrorBoundary; verify recovery UI shows | Currently: crash (blank screen) |
| Loading state coverage | UX-01, UX-08 | Count views with proper loading states / total async views | Estimated 70% coverage currently |
| Error message quality | UX-06 | % of API errors showing error code + action suggestion | Currently ~0% (raw messages) |
| SSE code duplication | UX-03 | Lines of SSE setup code across composables | ~60 lines duplicated across 3 files |
| Silent failure count | UX-04 | `console.warn` calls in catch blocks without UI feedback | Currently 6 in App.vue alone |

## Verification Strategy

### Recommended Verification Tiers for This Phase

| Item | Recommended Tier | Rationale |
|------|-----------------|-----------|
| ErrorBoundary catches rendering errors | Level 1 (Sanity) | Unit test: throw in child, assert fallback renders |
| ErrorBoundary recovery button works | Level 1 (Sanity) | Unit test: click recover, assert child re-renders |
| Loading states exist on all async views | Level 1 (Sanity) | Visual audit of all views (checklist) |
| Sidebar coordinated loading | Level 1 (Sanity) | Unit test: mock slow API, assert skeleton shows |
| useEventSource replaces duplicated code | Level 1 (Sanity) | Verify useConversation/useAiChat use shared composable |
| Centralized error messages include codes | Level 1 (Sanity) | Unit test: formatApiError(404) includes "ERR-404" |
| Per-section retry buttons work | Level 1 (Sanity) | Unit test: ErrorState retry event re-fetches section only |
| OpenAPI summaries on all endpoints | Level 2 (Proxy) | Automated check: parse /openapi/openapi.json, verify all paths have summary |
| Env validation fails fast | Level 1 (Sanity) | Remove required var, verify build fails with clear message |
| No console.warn on user-visible errors | Level 2 (Proxy) | Grep codebase for console.warn in catch blocks |
| Full UX audit across all 60+ views | Level 3 (Deferred) | Manual testing post-implementation |

**Level 1 checks to always include:**
- ErrorBoundary renders fallback on child error
- ErrorBoundary recovery re-creates child subtree (key increment)
- `formatApiError(404)` returns string containing "ERR-404"
- `formatApiError(500)` returns string containing "ERR-500"
- Sidebar shows loading indicator when `sidebarLoading` is true
- ErrorState emits `retry` event when button clicked
- LoadingState renders with message prop
- `useEventSource` returns reactive status ref
- `useEventSource` calls `source.close()` on unmount

**Level 2 proxy metrics:**
- OpenAPI spec has `summary` on >90% of paths
- Zero `console.warn` in catch blocks that handle user-visible operations
- `useConversation.connectToStream` delegates to `useEventSource`
- `useAiChat.connectStream` delegates to `useEventSource`

**Level 3 deferred items:**
- Full manual walkthrough of all views under slow network (Chrome DevTools throttling)
- E2E test: network error during API call shows toast with error code
- E2E test: component crash shows ErrorBoundary fallback, not blank screen

## Production Considerations (from KNOWHOW.md)

KNOWHOW.md is a placeholder with no production notes. The following considerations are derived from codebase analysis:

### Known Failure Modes

- **Sidebar fails silently:** All 6 sidebar `loadX()` functions catch errors with `console.warn` only. If the backend is down or returns 401, the sidebar shows stale data from a previous load (or empty arrays on first load) with no visual indicator of failure. Users may not realize data is stale.
  - Prevention: Replace `console.warn` with error state tracking per section; show retry indicator
  - Detection: Monitor browser console for `[Sidebar] Failed to load` warnings

- **SSE connection leak on rapid navigation:** If a user navigates between views that use SSE (e.g., SuperAgentPlayground -> ProjectDashboard -> back), multiple SSE connections may accumulate if `onUnmounted` cleanup does not fire fast enough.
  - Prevention: The shared `useEventSource` composable must call `close()` before opening a new connection (`closeStream()` pattern already exists in `useAiChat`)
  - Detection: Chrome DevTools Network tab showing multiple open EventSource connections

### Scaling Concerns

- **At current scale:** The sidebar fires 7 concurrent API calls on every page load. With <100 users this is fine.
  - At production scale: Consider caching sidebar data with a 30-second TTL or using a WebSocket for push updates instead of polling.

- **At current scale:** Environment validation adds ~50ms to dev server startup. Negligible.
  - At production scale: Build-time validation has zero runtime cost. No concern.

### Common Implementation Traps

- **Trap: Wrapping entire App.vue in ErrorBoundary instead of just router-view**
  - What goes wrong: An error in the sidebar or toast system crashes everything, including the error boundary itself
  - Correct approach: Place ErrorBoundary around `<router-view>` only. The sidebar and toast container remain outside the boundary. If the sidebar fails, it degrades gracefully (shows error per section). If the toast system fails, errors go to console but the app stays functional.

- **Trap: Making ErrorBoundary catch async errors via `app.config.errorHandler`**
  - What goes wrong: `app.config.errorHandler` is global and cannot trigger component-local state changes in the ErrorBoundary
  - Correct approach: Use `app.config.errorHandler` for logging/telemetry only. Component-level try/catch + `handleApiError` for user-facing error messages.

## Code Examples

Verified patterns from official sources and codebase analysis:

### ErrorBoundary Component (Vue 3 onErrorCaptured)
```vue
<!-- Source: Vue 3 Composition API docs + codebase conventions -->
<script setup lang="ts">
import { ref, onErrorCaptured } from 'vue';

defineProps<{
  fallbackTitle?: string;
}>();

const hasError = ref(false);
const errorMessage = ref('');
const recoveryKey = ref(0);

onErrorCaptured((err: Error, _instance, info: string) => {
  hasError.value = true;
  errorMessage.value = `${err.message} (in ${info})`;
  // Return false to stop propagation -- prevents SPA crash
  return false;
});

function recover() {
  hasError.value = false;
  errorMessage.value = '';
  recoveryKey.value++;
}
</script>

<template>
  <div v-if="hasError" class="error-boundary-fallback" role="alert">
    <div class="error-boundary-icon">!</div>
    <h2>{{ fallbackTitle || 'Something went wrong' }}</h2>
    <p class="error-boundary-message">{{ errorMessage }}</p>
    <button class="btn btn-primary" @click="recover">Try Again</button>
  </div>
  <component :is="'div'" v-else :key="recoveryKey">
    <slot />
  </component>
</template>
```

### Centralized handleApiError Usage
```typescript
// Source: Codebase convention -- replaces scattered try/catch patterns
import { handleApiError } from '../services/api/error-handler';
import { useToast } from '../composables/useToast';

// In a view component:
const showToast = useToast();

async function loadAgents() {
  isLoading.value = true;
  loadError.value = null;
  try {
    const data = await agentApi.list();
    agents.value = data.agents || [];
  } catch (e) {
    loadError.value = handleApiError(e, showToast, 'Failed to load agents');
  } finally {
    isLoading.value = false;
  }
}
```

### Sidebar Loading Coordination
```typescript
// Source: Promise.allSettled pattern for concurrent fetch coordination
const sidebarLoading = ref(true);
const sidebarErrors = ref<Record<string, string | null>>({
  triggers: null, projects: null, products: null,
  teams: null, plugins: null, backends: null, version: null,
});

async function loadSidebarData() {
  sidebarLoading.value = true;

  const loaders = [
    { key: 'triggers', fn: loadTriggers },
    { key: 'projects', fn: loadProjects },
    { key: 'products', fn: loadProducts },
    { key: 'teams', fn: loadTeams },
    { key: 'plugins', fn: loadPlugins },
    { key: 'backends', fn: loadSidebarBackends },
    { key: 'version', fn: loadVersion },
  ];

  const results = await Promise.allSettled(loaders.map(l => l.fn()));

  loaders.forEach((loader, i) => {
    const result = results[i];
    sidebarErrors.value[loader.key] =
      result.status === 'rejected' ? (result.reason?.message || 'Load failed') : null;
  });

  sidebarLoading.value = false;
}
```

### Environment Validation (Vite Plugin + Zod)
```typescript
// Source: @julr/vite-plugin-validate-env docs
// env.ts
import { defineConfig } from '@julr/vite-plugin-validate-env';
import { z } from 'zod';

export default defineConfig({
  VITE_ALLOWED_HOSTS: z.string().optional().default(''),
  // Add future required vars here:
  // VITE_API_BASE_URL: z.string().url(),
});
```

```typescript
// vite.config.ts
import ValidateEnv from '@julr/vite-plugin-validate-env';

export default defineConfig({
  plugins: [vue(), ValidateEnv()],
  // ... rest of config
});
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| React-style ErrorBoundary class component | Vue 3 `onErrorCaptured` composition hook | Vue 3.0 (2020) | Simpler, composable, no class component needed |
| Native EventSource | `@microsoft/fetch-event-source` | 2022 | Supports custom headers, POST, auth tokens |
| Per-component error strings | Centralized error catalog with codes | Industry pattern | Consistent UX, easier localization, better debugging |
| Global spinners | Skeleton screens + progressive loading | 2019 (Google research) | Better perceived performance, reduced layout shift |
| Runtime env checks | Build-time validation plugins | Vite ecosystem 2023+ | Fail-fast in CI, not in production |

**Deprecated/outdated:**
- Native `EventSource`: Cannot send custom headers (X-API-Key). Not viable for this project's auth model.
- Vue 2 `errorCaptured` option: Replaced by `onErrorCaptured` composition hook in Vue 3.
- `vue-error-boundary` npm package: Most packages target Vue 2 or wrap trivial Vue 3 code. Hand-rolling is simpler.

## Open Questions

1. **Should the error boundary also log to a telemetry service?**
   - What we know: The codebase has no telemetry/error reporting service (no Sentry, DataDog, etc.)
   - What's unclear: Whether the team plans to add error tracking in the future
   - Recommendation: Add a `console.error` call in the ErrorBoundary for now. If telemetry is added later, the boundary is the natural place to hook it in.

2. **How many env vars will need validation?**
   - What we know: Currently only `VITE_ALLOWED_HOSTS` exists (optional). The backend has ~5 env vars (`SECRET_KEY`, `CORS_ALLOWED_ORIGINS`, `AGENTED_API_KEY`, `FORCE_HTTPS`, `CLAUDE_PLUGIN_ROOT`).
   - What's unclear: Whether frontend will gain more env vars in future phases
   - Recommendation: Install the validation plugin now with a minimal schema. It costs nothing and provides the infrastructure for future vars.

3. **Should useEventSource handle seq-based deduplication?**
   - What we know: `useAiChat` tracks `lastSeq` for deduplication. `useConversation` deduplicates by content/timestamp comparison. `useProjectSession` has no deduplication.
   - What's unclear: Whether seq tracking belongs in the shared composable or the consumer
   - Recommendation: Keep seq tracking in consumers. The shared composable handles connection lifecycle only. Deduplication is protocol-specific (state_delta uses seq; conversation protocol uses content matching).

## Sources

### Primary (HIGH confidence)
- Vue 3 Official Docs: [onErrorCaptured](https://vuejs.org/api/composition-api-lifecycle.html#onerrorcaptured) -- error boundary lifecycle hook specification
- Vue 3 Official Docs: [Suspense](https://vuejs.org/guide/built-ins/suspense) -- async component loading orchestration
- Codebase analysis: `frontend/src/services/api/client.ts` -- existing `createAuthenticatedEventSource` implementation
- Codebase analysis: `frontend/src/composables/useConversation.ts` -- SSE setup pattern to extract
- Codebase analysis: `frontend/src/composables/useAiChat.ts` -- SSE setup pattern to extract
- Codebase analysis: `frontend/src/composables/useProjectSession.ts` -- SSE setup pattern to extract
- Codebase analysis: `frontend/src/App.vue` -- sidebar loading pattern and toast system
- Codebase analysis: `frontend/src/components/base/ErrorState.vue` -- existing error state component
- Codebase analysis: `frontend/src/components/base/LoadingState.vue` -- existing loading state component

### Secondary (MEDIUM confidence)
- [VueUse useEventSource](https://vueuse.org/core/useeventsource/) -- SSE composable reference design
- [@julr/vite-plugin-validate-env](https://github.com/Julien-R44/vite-plugin-validate-env) -- build-time env validation
- [Vue School: Error Boundary Component](https://vueschool.io/articles/vuejs-tutorials/what-is-a-vue-js-error-boundary-component/) -- error boundary pattern tutorial
- [LogRocket: Skeleton Loading Screen Design](https://blog.logrocket.com/ux-design/skeleton-loading-screen-design/) -- skeleton screen UX research

### Tertiary (LOW confidence)
- Web search results on centralized API error handling patterns -- community patterns, not peer-reviewed

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all recommendations use existing libraries or trivial additions
- Architecture: HIGH -- patterns are well-established Vue 3 idioms verified against official docs
- Pitfalls: HIGH -- derived from direct codebase analysis of existing patterns and their gaps
- Experiment design: MEDIUM -- metrics are qualitative/checklist-based rather than quantitative (appropriate for UX polish)

**Research date:** 2026-03-04
**Valid until:** 2026-04-04 (stable -- Vue 3 patterns are mature and unlikely to change)
