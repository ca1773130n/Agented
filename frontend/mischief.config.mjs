/**
 * Mischief — random-click QA against a LOCAL Agented.
 *
 * Point this at `just deploy` on a database you are willing to destroy. Two
 * mutators write (invalidInput submits garbage forms, uploadRandomFile uploads),
 * and the destructive-click guardrail matches a control's VISIBLE LABEL — an
 * icon-only delete button is invisible to it. `allowedHosts` is fail-closed;
 * if you ever reach for `--allow-prod`, stop and ask.
 */

export default {
  baseUrl: 'http://127.0.0.1:3000',

  browser: { channel: 'chrome' },

  /**
   * Routes read out of frontend/src/router/, NOT guessed — a path the app does
   * not serve manufactures a finding on run one.
   *
   * `requiresAuth` is the field that decides whether this run means anything.
   * router/guards.ts fails toward /login for anything that is not public, so a
   * gated route left unmarked would have the monkey clicking the login page and
   * reporting it as coverage. Only /login, /welcome and /forgot-password are
   * public.
   *
   * `waitFor: '.sidebar-nav'` is the arrival proof for every gated route:
   * App.vue renders AppShell (which owns .sidebar-nav) ONLY when the page is
   * neither the welcome nor an auth page, so that selector cannot appear on the
   * sign-in screen. Without it a guard that swaps the page after load is
   * indistinguishable from a slow render — which is the false green this
   * package exists to prevent.
   *
   * Parameterised routes (/agents/:id, …) are deliberately absent: they need a
   * real id, and a 404 shell is not worth a finding. Add them with a concrete id
   * once the local DB has fixtures.
   */
  routes: [
    // --- public ---
    { path: '/login', waitFor: '.login-form' },
    { path: '/welcome', waitFor: '.welcome-fullscreen' },

    // --- gated: core objects ---
    { path: '/', requiresAuth: true, waitFor: '.sidebar-nav' },
    { path: '/products', requiresAuth: true, waitFor: '.sidebar-nav' },
    { path: '/projects', requiresAuth: true, waitFor: '.sidebar-nav' },
    { path: '/agents', requiresAuth: true, waitFor: '.sidebar-nav' },
    { path: '/executions', requiresAuth: true, waitFor: '.sidebar-nav' },
    { path: '/dashboards', requiresAuth: true, waitFor: '.sidebar-nav' },

    // --- gated: platform surfaces ---
    { path: '/backends', requiresAuth: true, waitFor: '.sidebar-nav' },
    { path: '/plugins', requiresAuth: true, waitFor: '.sidebar-nav' },
    { path: '/commands', requiresAuth: true, waitFor: '.sidebar-nav' },
    { path: '/hooks', requiresAuth: true, waitFor: '.sidebar-nav' },
    { path: '/policies', requiresAuth: true, waitFor: '.sidebar-nav' },
    { path: '/mcp-servers', requiresAuth: true, waitFor: '.sidebar-nav' },
    { path: '/marketplace', requiresAuth: true, waitFor: '.sidebar-nav' },
    { path: '/integrations', requiresAuth: true, waitFor: '.sidebar-nav' },
    { path: '/harness', requiresAuth: true, waitFor: '.sidebar-nav' },
    { path: '/council', requiresAuth: true, waitFor: '.sidebar-nav' },
    { path: '/decisions', requiresAuth: true, waitFor: '.sidebar-nav' },
    { path: '/activity-summary', requiresAuth: true, waitFor: '.sidebar-nav' },
    { path: '/audit-history', requiresAuth: true, waitFor: '.sidebar-nav' },
    { path: '/bot-templates', requiresAuth: true, waitFor: '.sidebar-nav' },
    { path: '/execution-search', requiresAuth: true, waitFor: '.sidebar-nav' },
    { path: '/help', requiresAuth: true, waitFor: '.sidebar-nav' },
  ],

  /**
   * Agented is THREE origins: the SPA on :3000, the Litestar backend on :20000
   * and the ai-accounts sidecar on :20001. Vite proxies to them, so their
   * failures are same-origin in the browser — but list them explicitly anyway.
   * The documented failure mode is a second-origin API whose 4xx/5xx are counted
   * as third-party noise, producing "zero network findings" while the backend
   * 500s on every call.
   */
  network: {
    watchOrigins: [
      'http://127.0.0.1:3000',
      'http://127.0.0.1:20000',
      'http://127.0.0.1:20001',
    ],
    // Vue + Vite toolchain noise, so framework chatter does not drown real errors.
    consoleIgnore: ['vite', 'vue', 'vueI18n'],
  },

  /**
   * Gated routes need a session. The guard accepts an X-API-Key bearer session
   * OR a cookie session; `storageState` captures whichever the browser holds.
   *
   * `auth.from` IS A CREDENTIAL — it is gitignored below. Regenerate it with a
   * real login rather than committing one.
   */
  auth: {
    strategy: 'storageState',
    from: '.mischief-auth.json',
  },

  // ponytail: guardrails left ON. Turning one off to make a run go green is
  // falsifying the result — an exit 3 on a thin database is the gate working.
};
