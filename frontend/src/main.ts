import '@mcp-b/global'
import { createApp } from 'vue'
import './style.css'
import App from './App.vue'
import { router } from './router'
import { i18n } from './i18n'

const app = createApp(App)
app.use(router)
app.use(i18n)

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

// Wait for initial navigation (including async auth guard) before mounting
// This prevents the dashboard from flashing before redirect to /welcome
router.isReady().then(() => app.mount('#app'))
