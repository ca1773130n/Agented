// [08.L2] Self-host Geist / Geist Mono via @fontsource instead of the Google
// Fonts CDN — removes a third-party request + privacy/availability dependency.
import '@fontsource/geist-sans/400.css'
import '@fontsource/geist-sans/500.css'
import '@fontsource/geist-sans/600.css'
import '@fontsource/geist-sans/700.css'
import '@fontsource/geist-mono/400.css'
import '@fontsource/geist-mono/500.css'
import '@fontsource/geist-mono/600.css'
import '@fontsource/geist-mono/700.css'
import { createApp } from 'vue'
import './style.css'
import '@ai-accounts/vue-styled/styles.css'
import App from './App.vue'
import { router } from './router'
import { i18n, loadInitialLocale } from './i18n'
import { AiAccountsClient, type AiAccountsEvent } from '@ai-accounts/ts-core'
import { aiAccountsPlugin } from '@ai-accounts/vue-headless'
import { notifyAiAccountsEvent } from './composables/useTourMachine'
import { getApiKey } from './services/api/client'

const app = createApp(App)
app.use(router)
app.use(i18n)

/**
 * ai-accounts shared client + Vue plugin.
 *
 * The Litestar sidecar listens on :20001; Vite proxies /api/v1/* to it so
 * relative URLs work in both dev and production. The plugin's `onEvent`
 * forwards every event to the Agented tour state machine via
 * `notifyAiAccountsEvent`, which currently treats events as observational
 * only — tour advancement past a backend step happens exclusively via
 * the wizard's "다음 백엔드" button (`onWizardDone → tourMachine.nextStep()`).
 * Earlier versions auto-advanced on `login.completed` / `wizard.account.created`
 * and that is exactly what caused the "skips to next backend after paste
 * code" bug, so do NOT reintroduce auto-advance in that bridge.
 *
 * The `token` is sourced from sessionStorage via `getApiKey()` ([08.H1-residual]
 * moved it off localStorage). Pass the function (not its result) so the client
 * re-reads storage on every request — capturing at construction time leaves the client permanently
 * unauthenticated when boot races the welcome-page key generation, which
 * surfaced as a single ``GET /api/v1/backends/_meta 401`` immediately
 * after onboarding.
 */
const aiAccountsClient = new AiAccountsClient({
  baseUrl: '',
  token: () => getApiKey() ?? undefined,
})

// eslint-disable-next-line @typescript-eslint/no-explicit-any
app.use(aiAccountsPlugin as any, {
  client: aiAccountsClient,
  onEvent: (event: AiAccountsEvent) => {
    try {
      notifyAiAccountsEvent(event)
    } catch (err) {
      // Tour bridging is best-effort; never let it break the wizard.
      // [08.L1] Diagnostic only — gate behind DEV so prod doesn't log raw errors.
      if (import.meta.env.DEV) {
        console.warn('[ai-accounts] tour bridge error', err)
      }
    }
  },
})

/**
 * Global Vue error handler.
 * Logs full context to the console and surfaces a toast notification to the user
 * so that uncaught component errors are never silently swallowed.
 */
app.config.errorHandler = (err, instance, info) => {
  // [08.L1] Diagnostic logging is DEV-only — prod must not dump raw error
  // objects to the console. The user-facing toast below always fires.
  if (import.meta.env.DEV) {
    const componentName = instance?.$options?.name || instance?.$options?.__name || 'anonymous';
    console.error(
      `[Vue Error] ${err}\n  Component: ${componentName}\n  Info: ${info}`,
      err,
    );
  }

  // Surface a user-visible toast when the app's provide/inject toast system is available.
  // Because errorHandler fires outside the component tree, we reach into the app context.
  try {
    const showToast = instance?.$.appContext.config.globalProperties?.$showToast
      ?? instance?.$.appContext.app._context.provides?.showToast;
    if (typeof showToast === 'function') {
      showToast('An unexpected error occurred. Please try again.', 'error');
    }
  } catch {
    // Toast delivery is best-effort; logging above is the primary path.
  }
};

/**
 * Global Vue warning handler (development only).
 * Surfaces Vue runtime warnings in the console with structured context.
 */
if (import.meta.env.DEV) {
  app.config.warnHandler = (msg, instance, trace) => {
    const componentName = instance?.$options?.name || instance?.$options?.__name || 'anonymous';
    console.warn(
      `[Vue Warn] ${msg}\n  Component: ${componentName}\n  Trace: ${trace}`,
    );
  };
}

// Load non-English locale before mounting, then wait for router
loadInitialLocale()
  .then(() => router.isReady())
  .then(() => app.mount('#app'))
  .then(() => {
    // WebMCP is an agent-automation surface, never first-paint critical.
    // Defer the ~440 KB @mcp-b/global polyfill (it installs
    // navigator.modelContext as an import side effect) until AFTER mount so it
    // stays off the boot path. App.vue's registerGenericTools() no-ops when the
    // polyfill isn't present yet; we (re)register here once it's installed.
    import('@mcp-b/global')
      .then(() => import('./webmcp/generic-tools'))
      .then(({ registerGenericTools }) => registerGenericTools())
      .catch(() => {
        /* WebMCP is optional; never block the app if it fails to load. */
      })
  })
