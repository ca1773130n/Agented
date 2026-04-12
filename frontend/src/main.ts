import '@mcp-b/global'
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
 * `notifyAiAccountsEvent` so that advancing past the "add a Claude account"
 * tour step no longer requires a full page reload.
 *
 * The `token` is sourced from localStorage via `getApiKey()`. On first load
 * (before the welcome page generates a key) it will be undefined and the
 * sidecar's NoAuth fallback handles unauthenticated requests.
 */
const aiAccountsClient = new AiAccountsClient({
  baseUrl: '',
  token: getApiKey() ?? undefined,
})

app.use(aiAccountsPlugin, {
  client: aiAccountsClient,
  onEvent: (event: AiAccountsEvent) => {
    try {
      notifyAiAccountsEvent(event)
    } catch (err) {
      // Tour bridging is best-effort; never let it break the wizard.
      console.warn('[ai-accounts] tour bridge error', err)
    }
  },
})

/**
 * Global Vue error handler.
 * Logs full context to the console and surfaces a toast notification to the user
 * so that uncaught component errors are never silently swallowed.
 */
app.config.errorHandler = (err, instance, info) => {
  const componentName = instance?.$options?.name || instance?.$options?.__name || 'anonymous';
  console.error(
    `[Vue Error] ${err}\n  Component: ${componentName}\n  Info: ${info}`,
    err,
  );

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
loadInitialLocale().then(() => router.isReady()).then(() => app.mount('#app'))
