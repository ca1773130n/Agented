<script setup lang="ts">
/**
 * Application root.
 *
 * Owns the tour state machine, all `provide()` calls (so deep
 * `inject()` consumers continue to resolve), and the welcome-vs-shell
 * cross-fade. Layout, toast rendering, and boot sequencing have been
 * split out into focused composables/components (v0.7.5d):
 *
 *   - useToastSystem  — toasts state + showToast/dismissToast
 *   - useAppLayout    — isWelcomePage / isFullBleed
 *   - useAppBoot      — auth check, ?tour=start watcher, mount hooks
 *   - AppShell        — header + sidebar + main content frame
 *   - AppToastHost    — teleported toast stack
 */
import { ref, watch, provide, computed, getCurrentInstance } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';
import { useTourMachine } from './composables/useTourMachine';
import TourOverlay from './components/tour/TourOverlay.vue';
import TourCompletionScreen from './components/tour/TourCompletionScreen.vue';
import { TOUR_STEP_MAP, TOTAL_TOUR_STEPS } from './constants/tourSteps';
import AppShell from './components/layout/AppShell.vue';
import AppToastHost from './components/layout/AppToastHost.vue';
import ErrorBoundary from './components/base/ErrorBoundary.vue';
import { registerGenericTools } from './webmcp/generic-tools';
import { useSidebarCollapse } from './composables/useSidebarCollapse';
import { useSidebarData } from './composables/useSidebarData';
import { useHealthPolling } from './composables/useHealthPolling';
import { useAppLayout } from './composables/useAppLayout';
import { useToastSystem } from './composables/useToastSystem';
import { useAppBoot } from './composables/useAppBoot';

const router = useRouter();
const { t } = useI18n();

// Layout / route state
const { isWelcomePage, isAuthPage, isFullBleed } = useAppLayout();

// Tour state machine — owned here so `provide()` chain stays rooted in App.vue
const tour = useTourMachine();

// ---------------------------------------------------------------------------
// Tour step metadata — derived from shared TOUR_STEP_DEFINITIONS
// ---------------------------------------------------------------------------

const tourActive = computed(() => tour.isActive.value && !isWelcomePage.value && !isAuthPage.value);

const tourStep = computed(() => {
  const meta = TOUR_STEP_MAP[tour.currentStep.value];
  if (!meta) return null;
  const lk = meta.localeKey;
  const title = t(`tour.steps.${lk}.title`, meta.title);
  const message = t(`tour.steps.${lk}.message`, meta.message);
  return { target: meta.target, title, message, skippable: meta.skippable };
});

const tourStepNumber = computed(() => TOUR_STEP_MAP[tour.currentStep.value]?.stepNumber ?? 1);

const tourSubstepLabel = computed(() => TOUR_STEP_MAP[tour.currentStep.value]?.substepLabel ?? null);

// Dynamic guide message — components can override the default step message
const tourGuideOverride = ref<string | null>(null);
provide('setTourGuide', (msg: string | null) => { tourGuideOverride.value = msg; });

// Dynamic title override — sub-step components (e.g. AccountWizard) can
// replace the static tour-step title (e.g. "AI backend account") with a
// per-substep title ("Pick subscription", "Sign in", "Save the account")
// so the tooltip header reflects what the user is actually doing.
const tourTitleOverride = ref<string | null>(null);
provide('setTourTitle', (title: string | null) => { tourTitleOverride.value = title; });

// Dynamic target override — components (e.g. AccountWizard) can redirect the spotlight
const tourTargetOverride = ref<string | null>(null);
provide('setTourTarget', (selector: string | null) => { tourTargetOverride.value = selector; });

// Reset overrides when step changes
watch(() => tour.currentStep.value, () => {
  tourGuideOverride.value = null;
  tourTitleOverride.value = null;
  tourTargetOverride.value = null;
});

const tourStepWithGuide = computed(() => {
  if (!tourStep.value) return null;
  if (!tourGuideOverride.value && !tourTitleOverride.value) return tourStep.value;
  return {
    ...tourStep.value,
    message: tourGuideOverride.value ?? tourStep.value.message,
    title: tourTitleOverride.value ?? tourStep.value.title,
  };
});

// Tour completion screen
const tourComplete = computed(() => tour.state.value === 'complete');

function handleTourDone() {
  tour.restartTour(); // Resets machine to idle, clears localStorage
  router.push('/');
}

/** User clicked the X on the tour bar — exit the tour without resuming.
 *  Same effect as completing it (clears state + lands on home). The tour
 *  can be re-launched from Settings → Setup Guide → Restart Setup Guide. */
function handleTourDismiss() {
  if (typeof window !== 'undefined') {
    const ok = window.confirm(
      'Exit the setup tour? You can restart it from Settings → Setup Guide.',
    );
    if (!ok) return;
  }
  tour.restartTour();
}

/** Navigate to the route for a given tour step (deduplicates against current route) */
function navigateToTourStep(step: string) {
  const meta = TOUR_STEP_MAP[step];
  if (!meta) return;
  // Exact match or already on a sub-route (e.g. /products/prod-xxx matches /products)
  const route = router.currentRoute.value;
  const alreadyOnRoute = route.path === meta.route || route.path.startsWith(meta.route + '/');
  if (alreadyOnRoute && (!meta.routeHash || route.hash === meta.routeHash)) return;
  const target = meta.routeHash ? { path: meta.route, hash: meta.routeHash } : { path: meta.route };
  router.push(target);
}

// Navigate to correct route when machine state changes
watch(() => tour.currentStep.value, (step) => {
  navigateToTourStep(step);
});

// Modal coordination during tour (OB-44) — lives here so child modals can `inject('setTourModalOpen')`
const modalOpenDuringTour = ref(false);
provide('setTourModalOpen', (open: boolean) => {
  modalOpenDuringTour.value = open;
});
watch(tourActive, (active) => {
  if (!active) modalOpenDuringTour.value = false;
  // Toggle body class so teleported modals can be styled above tour overlay
  document.body.classList.toggle('tour-active', active);
});

// Register WebMCP generic verification tools (app-lifetime, no-ops in non-Canary browsers)
registerGenericTools();

// Global Vue error handler — report unhandled errors to the system error API
const appInstance = getCurrentInstance()?.appContext.app;
if (appInstance) {
  appInstance.config.errorHandler = (err, _instance, info) => {
    console.error('Vue error:', err);
    try {
      import('./services/api/system').then(({ systemErrorApi }) => {
        systemErrorApi.reportError({
          source: 'frontend',
          category: 'frontend_error',
          message: err instanceof Error ? err.message : String(err),
          stack_trace: err instanceof Error ? err.stack : undefined,
          context_json: JSON.stringify({ component: info, url: window.location.href }),
        }).catch(() => {});
      }).catch(() => {});
    } catch { /* ignore */ }
  };
}

// Sidebar collapse / mobile state
const { isCollapsed, isMobileOpen, isMobile, toggleCollapse, toggleMobile, closeMobile } =
  useSidebarCollapse();

// Toast system — defined before useSidebarData since it consumes showToast
const { toasts, showToast, dismissToast } = useToastSystem(tour);
provide('showToast', showToast);

// Sidebar data (triggers, projects, products, teams, plugins, backends, version)
const {
  customTriggers,
  products,
  projects,
  teams,
  plugins,
  sidebarBackends,
  appVersion,
  sidebarLoading,
  sidebarErrors,
  loadSidebarData,
  retrySidebarSection,
  refreshTriggers,
  loadPlugins,
} = useSidebarData(showToast);

provide('retrySidebarSection', retrySidebarSection);
provide('refreshTriggers', refreshTriggers);

// Health polling
const { activeExecutionCount, healthColor, healthTooltip, startPolling, stopPolling } =
  useHealthPolling();

// Boot flow — auth check, ?tour=start watcher, onMounted/onUnmounted
const { showApiKeyBanner, appReady, onAuthenticated, handleTourRetry } = useAppBoot({
  tour,
  loadSidebarData,
  loadPlugins,
  startPolling,
  stopPolling,
  showToast,
  navigateToTourStep,
});
</script>

<template>
  <div v-if="appReady" :class="['app-layout', { 'sidebar-collapsed': isCollapsed && !isMobile, 'sidebar-mobile': isMobile }]">
    <a href="#main-content" class="skip-to-content">Skip to content</a>

    <div v-if="isWelcomePage || isAuthPage" class="welcome-fullscreen">
      <ErrorBoundary>
        <router-view />
      </ErrorBoundary>
    </div>

    <AppShell
      v-else
      :is-collapsed="isCollapsed"
      :is-mobile="isMobile"
      :is-mobile-open="isMobileOpen"
      :app-version="appVersion"
      :health-color="healthColor"
      :health-tooltip="healthTooltip"
      :active-execution-count="activeExecutionCount"
      :custom-triggers="customTriggers"
      :products="products"
      :projects="projects"
      :teams="teams"
      :plugins="plugins"
      :sidebar-backends="sidebarBackends"
      :sidebar-loading="sidebarLoading"
      :sidebar-errors="sidebarErrors"
      :show-api-key-banner="showApiKeyBanner"
      :is-full-bleed="isFullBleed"
      @toggle-sidebar="toggleMobile"
      @toggle-collapse="toggleCollapse"
      @close-mobile="closeMobile"
      @authenticated="onAuthenticated"
      @retry-sidebar-section="retrySidebarSection"
    >
      <ErrorBoundary>
        <router-view />
      </ErrorBoundary>
    </AppShell>

    <AppToastHost :toasts="toasts" @dismiss="dismissToast" />

    <TourOverlay
      :active="tourActive"
      :step="tourStepWithGuide"
      :effective-target="tourTargetOverride ? { target: tourTargetOverride } : null"
      :substep-label="tourSubstepLabel"
      :step-number="tourStepNumber"
      :total-steps="TOTAL_TOUR_STEPS"
      :is-modal-open="modalOpenDuringTour"
      @next="tour.nextStep"
      @skip="tour.skipStep"
      @retry="handleTourRetry"
      @dismiss="handleTourDismiss"
    />

    <Teleport to="body">
      <TourCompletionScreen
        v-if="tourComplete"
        :completed-steps="tour.context.value.completedSteps"
        @done="handleTourDone"
      />
    </Teleport>
  </div>
</template>

<style>
@import './assets/global-spinner.css';
@import './assets/markdown-content.css';
/*
 * [08.L2] Geist / Geist Mono are now SELF-HOSTED via @fontsource (imported in
 * main.ts) — no runtime third-party request to the Google Fonts CDN, and the
 * strict CSP needs no external font/style origins.
 */

/*
 * Canonical page-header typography — every content page's title/subtitle the
 * same size. Applies to the standard page-header conventions; scoped page
 * styles inherit these unless they set their own font-size. Modals, auth
 * screens, and wizards use different header classes and are unaffected.
 */
.page-header h1,
.header-title h1,
.page-title h1 {
  font-size: 18px;
  font-weight: 600;
}
.page-subtitle,
.header-title p,
.page-title p {
  font-size: 13px;
  color: var(--text-tertiary);
}

:root {
  /* Base colors */
  --bg-primary: #0a0a0f;
  --bg-secondary: #12121a;
  --bg-tertiary: #1a1a24;
  --bg-elevated: #22222e;

  /* Border colors */
  --border-subtle: rgba(255, 255, 255, 0.06);
  --border-default: rgba(255, 255, 255, 0.1);
  --border-strong: rgba(255, 255, 255, 0.15);

  /* Text colors */
  --text-primary: #f0f0f5;
  --text-secondary: #a0a0b0;
  --text-tertiary: #606070;
  --text-muted: #404050;

  /* Accent colors */
  --accent-cyan: #00d4ff;
  --accent-cyan-dim: rgba(0, 212, 255, 0.15);
  --accent-emerald: #00ff88;
  --accent-emerald-dim: rgba(0, 255, 136, 0.15);
  --accent-amber: #ffaa00;
  --accent-amber-dim: rgba(255, 170, 0, 0.15);
  --accent-crimson: #ff3366;
  --accent-crimson-dim: rgba(255, 51, 102, 0.15);
  --accent-violet: #8855ff;
  --accent-violet-dim: rgba(136, 85, 255, 0.15);

  /* Functional colors */
  --success: var(--accent-emerald);
  --warning: var(--accent-amber);
  --danger: var(--accent-crimson);
  --info: var(--accent-cyan);
  --text-on-accent: #1a1a1a;
  --accent-amber-strong: #d97706;
  --accent-amber-muted: #92400e;

  /* Spacing */
  --sidebar-width: 240px;
  --sidebar-width-collapsed: 60px;
  --content-padding: 32px;

  /* Typography */
  --font-sans: 'Geist Sans', 'Geist', -apple-system, BlinkMacSystemFont, sans-serif;
  --font-mono: 'Geist Mono', 'SF Mono', 'Monaco', monospace;

  /* Shadows */
  --shadow-sm: 0 2px 8px rgba(0, 0, 0, 0.3);
  --shadow-md: 0 4px 16px rgba(0, 0, 0, 0.4);
  --shadow-lg: 0 8px 32px rgba(0, 0, 0, 0.5);
  --shadow-glow-cyan: 0 0 20px rgba(0, 212, 255, 0.3);
  --shadow-glow-emerald: 0 0 20px rgba(0, 255, 136, 0.3);

  /* Transitions */
  --transition-fast: 150ms ease;
  --transition-normal: 250ms ease;
  --transition-slow: 400ms ease;

  /* Tour z-index scale — Phase 1 foundation (OB-43) */
  --z-tour-overlay: 10000;
  --z-tour-spotlight: 10001;
  --z-tour-tooltip: 10002;
  --z-tour-controls: 10003;
  --z-tour-progress: 10004;
  --z-toast: 10005;

  /* Tour visual layer */
  --tour-overlay-dim: rgba(0, 0, 0, 0.7);
  --tour-spotlight-radius: 8px;
  --tour-spotlight-padding: 8px;
  --tour-glow-color: var(--accent-cyan);
  --tour-glow-dim: rgba(0, 212, 255, 0.3);
  /* OB-13: completion-screen success-pulse tokens (Phase 2 plan 02-01).
   * Both colors use the existing accent green so the pulse matches the rest
   * of the success affordance (icon ring border, check glyph). */
  --tour-success-pulse-from: rgba(0, 255, 136, 0);
  --tour-success-pulse-to: rgba(0, 255, 136, 0.4);
  --tour-glow-bright: rgba(0, 212, 255, 0.5);
  --tour-transition-speed: 200ms;
}

* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

html {
  font-size: 14px;
}

body {
  font-family: var(--font-sans);
  background: var(--bg-primary);
  color: var(--text-primary);
  min-height: 100vh;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* Scrollbar styling */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: var(--bg-primary);
}

::-webkit-scrollbar-thumb {
  background: var(--border-strong);
  border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
  background: var(--text-tertiary);
}

/* App Layout */
.app-layout {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

.welcome-fullscreen {
  position: fixed;
  inset: 0;
  z-index: 100;
  overflow-y: auto;
}

.app-body {
  display: flex;
  flex: 1;
  position: relative;
}

/* Sidebar */
.sidebar {
  width: var(--sidebar-width);
  background: var(--bg-secondary);
  border-right: 1px solid var(--border-subtle);
  position: sticky;
  top: 48px;
  height: calc(100vh - 48px);
  display: flex;
  flex-direction: column;
  z-index: 100;
  transition: width var(--transition-normal);
  flex-shrink: 0;
}

.sidebar.collapsed {
  width: var(--sidebar-width-collapsed);
}

.sidebar.collapsed .nav-text,
.sidebar.collapsed .chevron-icon,
.sidebar.collapsed .version-tag,
.sidebar.collapsed .health-indicator,
.sidebar.collapsed .active-badge,
.sidebar.collapsed .logo-text,
.sidebar.collapsed .nav-section-label,
.sidebar.collapsed .external-icon {
  display: none;
}

.sidebar.collapsed .nav-submenu {
  display: none;
}

.sidebar.collapsed .sidebar-header {
  justify-content: center;
  padding: 24px 12px;
}

.sidebar.collapsed .sidebar-nav button,
.sidebar.collapsed .sidebar-nav a {
  justify-content: center;
  padding: 10px 0;
  margin: 2px 6px;
}

.sidebar-header {
  padding: 24px 20px;
  border-bottom: 1px solid var(--border-subtle);
  display: flex;
  align-items: center;
  gap: 12px;
}

.logo-mark {
  width: 36px;
  height: 36px;
  background: linear-gradient(135deg, var(--accent-cyan) 0%, var(--accent-violet) 100%);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.logo-mark svg {
  width: 20px;
  height: 20px;
  color: var(--bg-primary);
}

.logo-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.logo-line-2 {
  display: flex;
  align-items: center;
  gap: 8px;
}

.logo-line-2 > span:first-child {
  font-family: var(--font-mono);
  font-size: 1.25rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: var(--text-primary);
}

.logo-text .version-tag {
  font-family: var(--font-mono);
  font-size: 0.65rem;
  color: var(--accent-cyan);
  background: var(--accent-cyan-dim);
  padding: 2px 6px;
  border-radius: 4px;
}

.health-indicator {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-left: 4px;
  vertical-align: middle;
  transition: background-color 0.3s ease;
}

.active-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 9px;
  background: rgba(59, 130, 246, 0.8);
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  margin-left: 4px;
  vertical-align: middle;
}

.sidebar-nav {
  flex: 1;
  padding: 16px 0;
  overflow-y: auto;
}

.nav-section-label {
  font-size: 0.65rem;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.1em;
  padding: 16px 20px 8px;
}

.sidebar-nav a {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 20px;
  color: var(--text-secondary);
  text-decoration: none;
  transition: all var(--transition-fast);
  position: relative;
  margin: 2px 8px;
  border-radius: 6px;
}

.sidebar-nav a:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.sidebar-nav a.active {
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
}

.sidebar-nav a.active .nav-indicator {
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 20px;
  background: var(--accent-cyan);
  border-radius: 0 2px 2px 0;
}

/* Button styles in sidebar-nav (converted from anchor tags) */
.sidebar-nav button {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 20px;
  color: var(--text-secondary);
  background: none;
  border: none;
  text-align: left;
  width: 100%;
  font-family: inherit;
  cursor: pointer;
  transition: all var(--transition-fast);
  position: relative;
  margin: 2px 8px;
  border-radius: 6px;
}

.sidebar-nav button:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.sidebar-nav button.active {
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
}

.sidebar-nav button.active .nav-indicator {
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 20px;
  background: var(--accent-cyan);
  border-radius: 0 2px 2px 0;
}

.submenu-item {
  background: none;
  border: none;
  text-align: left;
  width: 100%;
  font: inherit;
  cursor: pointer;
}

.submenu-settings-btn {
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
}

.nav-icon {
  width: 18px;
  height: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.nav-icon svg {
  width: 18px;
  height: 18px;
}

.nav-text {
  font-size: 0.9rem;
  font-weight: 500;
}

/* Nav group toggle & submenu */
.nav-group-toggle {
  position: relative;
}

.chevron-icon {
  width: 14px;
  height: 14px;
  margin-left: auto;
  opacity: 0.5;
  transition: transform var(--transition-fast);
}

.chevron-icon.expanded {
  transform: rotate(90deg);
}

.nav-submenu {
  padding: 2px 0 4px 0;
  margin-left: 28px;
  border-left: 1px solid var(--border-subtle);
}

.submenu-item {
  display: block;
  padding: 7px 20px 7px 22px;
  font-size: 0.8rem;
  color: var(--text-tertiary);
  text-decoration: none;
  transition: all var(--transition-fast);
  border-radius: 4px;
  margin: 1px 8px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.submenu-item:hover {
  color: var(--text-primary);
  background: var(--bg-tertiary);
}

.submenu-item.active {
  color: var(--accent-cyan);
  background: var(--accent-cyan-dim);
}

.submenu-item-row {
  position: relative;
}

.submenu-item-row .submenu-settings-btn {
  position: absolute;
  right: 12px;
  top: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  padding: 0;
  color: var(--text-muted);
  opacity: 0;
  transition: all 0.15s ease;
  border-radius: 4px;
}

.submenu-item-row:hover .submenu-settings-btn {
  opacity: 1;
}

.submenu-item-row .submenu-settings-btn:hover {
  color: var(--accent-cyan);
}

.submenu-item-row .submenu-settings-btn svg {
  width: 14px;
  height: 14px;
}

.external-link {
  opacity: 0.7;
}

.external-link:hover {
  opacity: 1;
}

.external-icon {
  width: 12px;
  height: 12px;
  margin-left: auto;
  opacity: 0.5;
}

/* Main Content */
.main-content {
  flex: 1;
  min-height: calc(100vh - 48px);
  min-width: 0;
  background: var(--bg-primary);
}

/* Mobile sidebar styles */
.app-layout.sidebar-mobile .sidebar {
  display: none;
}

.app-layout.sidebar-mobile .sidebar.mobile-open {
  display: flex;
  position: fixed;
  top: 48px;
  z-index: 200;
  width: var(--sidebar-width);
  height: calc(100vh - 48px);
}

/* Mobile backdrop */
.sidebar-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 199;
}

/* Collapse toggle button */
.collapse-toggle {
  position: absolute;
  bottom: 16px;
  left: calc(var(--sidebar-width) - 14px);
  z-index: 101;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  color: var(--text-tertiary);
  cursor: pointer;
  padding: 4px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--transition-normal);
}

.app-layout.sidebar-collapsed .collapse-toggle {
  left: calc(var(--sidebar-width-collapsed) - 14px);
}

.collapse-toggle:hover {
  color: var(--text-primary);
  background: var(--bg-tertiary);
}

.collapse-toggle svg {
  width: 16px;
  height: 16px;
}

.content-wrapper {
  padding: var(--content-padding);
  min-height: 100vh;
}

.content-wrapper.full-bleed {
  padding: 0;
  height: calc(100vh - 48px);
  overflow: hidden;
}

/* Page Transitions */
.fade-enter-active,
.fade-leave-active {
  transition: opacity var(--transition-normal), transform var(--transition-normal);
}

.fade-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.fade-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

/* Toast Notifications */
.toast-container {
  position: fixed;
  bottom: 24px;
  right: 24px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  z-index: var(--z-toast);
  pointer-events: none;
}

.toast {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: var(--bg-elevated);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  box-shadow: var(--shadow-lg);
  pointer-events: auto;
  backdrop-filter: blur(8px);
}

.toast-icon {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
}

.toast-icon svg {
  width: 20px;
  height: 20px;
}

.toast.success {
  border-color: var(--accent-emerald);
}

.toast.success .toast-icon {
  color: var(--accent-emerald);
}

.toast.error {
  border-color: var(--accent-crimson);
}

.toast.error .toast-icon {
  color: var(--accent-crimson);
}

.toast.info {
  border-color: var(--accent-cyan);
}

.toast.info .toast-icon {
  color: var(--accent-cyan);
}

.toast.infrastructure {
  background: rgba(245, 158, 11, 0.95);
  color: var(--text-on-accent);
  border-left: 4px solid var(--accent-amber-strong);
  border-color: var(--accent-amber-strong);
}

.toast.infrastructure .toast-icon {
  color: var(--text-on-accent);
}

.toast.infrastructure .toast-message {
  color: var(--text-on-accent);
}

.toast.infrastructure.recovered {
  background: rgba(245, 158, 11, 0.3);
  border-left-color: var(--accent-amber-muted);
  color: var(--text-primary);
}

.toast.infrastructure.recovered .toast-icon {
  color: var(--accent-amber);
}

.toast.infrastructure.recovered .toast-message {
  color: var(--text-primary);
}

.toast-message {
  font-size: 0.875rem;
  color: var(--text-primary);
}

.toast-dismiss {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  margin-left: auto;
  padding: 0;
  background: transparent;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  opacity: 0.6;
  transition: opacity var(--transition-fast);
  flex-shrink: 0;
}

.toast-dismiss:hover {
  opacity: 1;
}

.toast-dismiss svg {
  width: 14px;
  height: 14px;
}

.toast.infrastructure .toast-dismiss {
  color: var(--text-on-accent);
}

.toast-enter-active,
.toast-leave-active {
  transition: all var(--transition-normal);
}

.toast-enter-from {
  opacity: 0;
  transform: translateX(100%);
}

.toast-leave-to {
  opacity: 0;
  transform: translateX(100%);
}

/* Utility Classes */
.text-mono {
  font-family: var(--font-mono);
}

.entity-link {
  cursor: pointer;
  transition: color 0.15s;
}

.entity-link:hover {
  color: var(--accent-cyan, #00d4ff);
  text-decoration: underline;
}

/* ===== Shared Utility Classes ===== */
/* Migrated from list-page.css and design-page.css */
/* Global definitions — components override via scoped styles as needed */

/* --- 1. Buttons --- */
.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.btn:hover {
  background: var(--bg-elevated, var(--bg-tertiary));
  color: var(--text-primary);
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn svg {
  width: 16px;
  height: 16px;
}

.btn-primary {
  background: var(--accent-cyan);
  color: #000;
}

.btn-primary:hover {
  background: #00c4ee;
  color: #000;
}

.btn-sm {
  padding: 6px 12px;
  font-size: 13px;
}

.btn-sm svg {
  width: 14px;
  height: 14px;
}

.btn-danger {
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
}

.btn-danger:hover {
  background: rgba(255, 51, 102, 0.25);
}

.btn-icon {
  padding: 6px;
  border-radius: 6px;
}

.btn-secondary {
  background: var(--accent-violet-dim, rgba(136, 85, 255, 0.15));
  color: var(--accent-violet, #8855ff);
}

.btn-secondary:hover {
  background: rgba(136, 85, 255, 0.25);
}

.btn-ai {
  background: linear-gradient(135deg, rgba(136, 85, 255, 0.2), rgba(0, 212, 255, 0.2));
  color: var(--accent-cyan);
  border: 1px solid rgba(0, 212, 255, 0.3);
}

.btn-ai:hover {
  background: linear-gradient(135deg, rgba(136, 85, 255, 0.3), rgba(0, 212, 255, 0.3));
  border-color: rgba(0, 212, 255, 0.5);
  color: var(--accent-cyan);
}

.ai-badge {
  font-size: 10px;
  font-weight: 700;
  background: var(--accent-cyan);
  color: #000;
  padding: 1px 5px;
  border-radius: 3px;
  letter-spacing: 0.05em;
}

/* --- 2. Cards --- */
.card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
}

/* --- 3. Entity Grid --- */
.entity-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 20px;
}

@media (max-width: 480px) {
  .entity-grid {
    grid-template-columns: 1fr;
  }
}

.entity-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 20px;
  transition: border-color 0.2s;
}

.entity-card:hover {
  border-color: var(--border-strong);
}

.entity-card.disabled {
  opacity: 0.6;
}

/* --- 4. Modals --- */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

/* When tour is active, modals must appear above the tour spotlight (z-index 10001) */
body.tour-active .modal-overlay {
  z-index: 10005;
}

.modal {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 24px;
  max-width: 600px;
  width: 90%;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.modal h2 {
  margin: 0 0 20px 0;
  font-size: 18px;
  color: var(--text-primary);
}

.modal p {
  color: var(--text-secondary);
  margin: 0 0 12px 0;
}

.modal .warning {
  color: var(--accent-amber);
  font-size: 13px;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  flex-shrink: 0;
}

.modal-body {
  margin-bottom: 20px;
  overflow-y: auto;
  flex: 1 1 auto;
  min-height: 0;
}

.modal-footer,
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 24px;
  flex-shrink: 0;
}

/* --- 5. Forms --- */
.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  margin-bottom: 6px;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 500;
}

/* All text-like input types — NOT just type="text". A bare type="url"/"email"/
   "number"/etc. would otherwise fall through to the raw browser default (white
   box, inset border) and break the dark theme. checkbox/radio/range/file are
   intentionally excluded (they need their own treatment). */
.form-group input:not([type="checkbox"]):not([type="radio"]):not([type="range"]):not([type="file"]):not([type="color"]),
.form-group select,
.form-group textarea {
  width: 100%;
  padding: 10px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 14px;
  font-family: inherit;
  box-sizing: border-box;
}

.form-group textarea {
  font-family: var(--font-mono);
  resize: vertical;
}

.form-group input:focus,
.form-group select:focus,
.form-group textarea:focus {
  border-color: var(--accent-cyan);
}
.form-group input:focus-visible,
.form-group select:focus-visible,
.form-group textarea:focus-visible {
  outline: 2px solid var(--accent-cyan);
  outline-offset: 2px;
}

.checkbox-group label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.checkbox-group input[type="checkbox"] {
  width: 16px;
  height: 16px;
}

.form-hint {
  margin: 6px 0 0 0;
  font-size: 12px;
  color: var(--text-tertiary);
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 24px;
  padding-top: 24px;
  border-top: 1px solid var(--border-subtle, var(--border-default));
}

/* --- 6. States --- */
.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  text-align: center;
}

.loading-state .spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border-default);
  border-top-color: var(--accent-cyan);
  border-radius: 50%;
  animation: global-spin 1s linear infinite;
  margin-bottom: 16px;
}

@keyframes global-spin {
  to { transform: rotate(360deg); }
}

.empty-state .empty-icon {
  width: 80px;
  height: 80px;
  background: var(--bg-tertiary);
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 24px;
}

.empty-state .empty-icon svg {
  width: 40px;
  height: 40px;
  color: var(--text-tertiary);
}

.empty-state h3 {
  margin: 0 0 8px 0;
  color: var(--text-primary);
}

.empty-state p {
  color: var(--text-secondary);
  margin: 0 0 24px 0;
}

.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  text-align: center;
  color: var(--accent-crimson);
}

/* --- 7. Tags and Badges --- */
.tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.badge {
  display: inline-block;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

/* --- 8. Highlight Animation --- */
.highlight-pulse {
  animation: highlightPulse 2s ease-out;
}

@keyframes highlightPulse {
  0% { box-shadow: 0 0 0 3px var(--accent-cyan, #00d4ff); }
  100% { box-shadow: 0 0 0 0 transparent; }
}

/* --- 9. Design Page Layout --- */
.design-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  max-height: 100vh;
  overflow: hidden;
}

.design-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 24px;
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-secondary);
}

.btn-back {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.15s;
}
.btn-back:hover { background: var(--bg-tertiary); color: var(--text-primary); }
.btn-back svg { width: 18px; height: 18px; }

.header-title { flex: 1; }
.header-title h1 { margin: 0; font-size: 18px; color: var(--text-primary); }
.header-title p { margin: 4px 0 0 0; font-size: 13px; color: var(--text-tertiary); }
.btn-finalize { padding: 10px 20px; }

.design-content {
  display: grid;
  grid-template-columns: 1fr 400px;
  gap: 32px;
  padding: 24px;
  flex: 1;
  overflow-y: auto;
}

.design-form {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 24px;
}

.form-section h3 { margin: 0 0 20px 0; font-size: 16px; font-weight: 600; color: var(--text-primary); }

.design-preview { position: sticky; top: 0; }
.design-preview h3 { margin: 0 0 16px 0; font-size: 14px; font-weight: 600; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.05em; }

.preview-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 20px;
}
.preview-name { font-weight: 600; color: var(--text-primary); }
.preview-description { color: var(--text-secondary); font-size: 14px; margin: 0 0 12px 0; }

.design-body { display: flex; flex: 1; overflow: hidden; }

.config-field { display: flex; flex-direction: column; gap: 6px; }
.config-label { font-size: 11px; font-weight: 600; text-transform: uppercase; color: var(--text-tertiary); letter-spacing: 0.5px; }
.config-value { font-size: 14px; color: var(--text-primary); }
.config-description { color: var(--text-secondary); font-size: 13px; line-height: 1.5; }

.config-code {
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  padding: 12px;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 200px;
  overflow-y: auto;
}

.enabled-badge { display: inline-block; padding: 3px 10px; border-radius: 4px; font-size: 12px; font-weight: 600; }
.enabled-badge.yes { background: var(--accent-emerald-dim); color: var(--accent-emerald); }
.enabled-badge.no { background: var(--accent-crimson-dim); color: var(--accent-crimson); }

/* --- 10. Page Header --- */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
}

.page-header .header-content h1 {
  font-size: 28px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 8px 0;
}

.page-header .subtitle {
  color: var(--text-secondary);
  margin: 0;
}

.page-header .header-actions {
  display: flex;
  gap: 12px;
}

/* --- 11. Screen Reader Only --- */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border-width: 0;
}

/* --- 12. Filters --- */
.filters-bar {
  display: flex;
  gap: 24px;
  margin-bottom: 24px;
  padding: 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
}

.filter-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.filter-group label {
  color: var(--text-secondary);
  font-size: 13px;
}

.filter-group select {
  padding: 6px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 13px;
}

/* -- Global Loading / Error / Empty State Pattern -- */
.state-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  text-align: center;
  gap: 12px;
}

.state-container .state-icon {
  width: 48px;
  height: 48px;
  color: var(--text-muted);
  margin-bottom: 8px;
}

.state-container .state-title {
  font-size: 16px;
  font-weight: 500;
  color: var(--text-primary);
}

.state-container .state-message {
  font-size: 13px;
  color: var(--text-secondary);
  max-width: 400px;
}

.state-container.state-error .state-icon {
  color: var(--accent-crimson);
}

.state-container.state-error .state-title {
  color: var(--accent-crimson);
}

.state-container.state-empty .state-icon {
  color: var(--text-muted);
}

.state-container .state-action {
  margin-top: 8px;
}

.state-container .btn-retry {
  padding: 8px 20px;
  background: transparent;
  border: 1px solid var(--accent-cyan);
  border-radius: 6px;
  color: var(--accent-cyan);
  font-size: 13px;
  cursor: pointer;
  transition: background var(--transition-fast);
}

.state-container .btn-retry:hover {
  background: rgba(0, 212, 255, 0.1);
}

.state-container .btn-create {
  padding: 8px 20px;
  background: var(--accent-cyan);
  border: none;
  border-radius: 6px;
  color: var(--bg-primary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity var(--transition-fast);
}

.state-container .btn-create:hover {
  opacity: 0.85;
}

/* -- Async View Loading Spinner -- */
.view-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  min-height: 50vh;
}

.view-loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border-default);
  border-top-color: var(--accent-cyan);
  border-radius: 50%;
  animation: global-spin 1s linear infinite;
  margin-bottom: 16px;
}

.view-loading-text {
  color: var(--text-tertiary);
  font-size: 14px;
}

/* --- Skip-to-content link --- */
.skip-to-content {
  position: absolute;
  left: -9999px;
  top: auto;
  width: 1px;
  height: 1px;
  overflow: hidden;
  z-index: 9999;
  padding: 12px 24px;
  background: var(--accent-cyan);
  color: #000;
  font-weight: 600;
  font-size: 14px;
  text-decoration: none;
  border-radius: 0 0 8px 0;
}
.skip-to-content:focus {
  position: fixed;
  left: 0;
  top: 0;
  width: auto;
  height: auto;
  overflow: visible;
}

/* --- Global focus-visible ring --- */
:focus-visible {
  outline: 2px solid var(--accent-cyan);
  outline-offset: 2px;
}

:focus:not(:focus-visible) {
  outline: none;
}

/* --- Responsive Layout --- */
@media (max-width: 768px) {
  .design-content {
    grid-template-columns: 1fr;
  }

  .filters-bar {
    flex-direction: column;
    gap: 12px;
  }

  .page-header {
    flex-direction: column;
    gap: 12px;
  }

  .page-header .header-actions {
    flex-wrap: wrap;
  }

  .content-wrapper {
    padding: 16px;
  }
}

@media (max-width: 480px) {
  .modal {
    width: 95%;
    max-width: none;
  }
}

/* --- Prefers reduced motion --- */
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }

  :root {
    --tour-transition-speed: 0ms;
  }
}

/* ───────────────────────────────────────────────────────────────────
   Tool-call chips inside ChatBubble (v0.7.51)

   ``_render_tool_use`` (backend) emits ``<details class="tool-call">``
   blocks with chip-styled ``<span class="tool-name">`` / ``<code
   class="tool-arg">`` etc. inside the summary. ``ChatBubble`` uses
   ``v-html`` to render parsed markdown, which means scoped styles
   from any parent component can't reach inside. These rules live in
   ``App.vue``'s global ``<style>`` instead.
   ─────────────────────────────────────────────────────────────────── */
.tool-call {
  margin: 8px 0;
  border: 1px solid var(--border-default);
  border-radius: 8px;
  background: var(--bg-secondary);
  overflow: hidden;
}
.tool-call > summary {
  cursor: pointer;
  padding: 8px 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  font-size: 13px;
  user-select: none;
  list-style: none;
  position: relative;
}
.tool-call > summary::-webkit-details-marker {
  display: none;
}
.tool-call > summary::before {
  content: '▶';
  display: inline-block;
  width: 12px;
  font-size: 9px;
  color: var(--text-muted);
  transition: transform 0.15s ease;
  flex-shrink: 0;
}
.tool-call[open] > summary::before {
  transform: rotate(90deg);
}
.tool-call > summary:hover {
  background: var(--bg-tertiary);
}
.tool-call[open] > summary {
  border-bottom: 1px solid var(--border-default);
}

.tool-call .tool-name {
  font-family: 'Geist Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  font-weight: 600;
  font-size: 12px;
  color: var(--accent-cyan, #00bcd4);
  background: rgba(0, 188, 212, 0.12);
  padding: 2px 8px;
  border-radius: 4px;
  letter-spacing: 0.02em;
  white-space: nowrap;
}

/* Chip baseline for arg/path/pattern. Specific variants below tweak
   color so the eye can tell apart "file path" vs "search pattern" at
   a glance. */
.tool-call .tool-arg,
.tool-call .tool-path,
.tool-call .tool-pattern {
  font-family: 'Geist Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}
.tool-call .tool-path {
  color: var(--accent-purple, #b388ff);
  background: rgba(179, 136, 255, 0.08);
  border-color: rgba(179, 136, 255, 0.2);
}
.tool-call .tool-pattern {
  color: var(--accent-yellow, #ffcc80);
  background: rgba(255, 204, 128, 0.1);
  border-color: rgba(255, 204, 128, 0.25);
}
.tool-call .tool-sep,
.tool-call .tool-meta {
  font-size: 12px;
  color: var(--text-muted);
}

.tool-call .tool-detail {
  margin: 0;
  padding: 10px 14px;
  background: var(--bg-primary);
  font-family: 'Geist Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  line-height: 1.5;
  overflow-x: auto;
  white-space: pre;
  color: var(--text-secondary);
}
.tool-call .tool-detail-empty {
  padding: 10px 14px;
  font-size: 12px;
  color: var(--text-muted);
  font-style: italic;
}

/* ───────────────────────────────────────────────────────────────────
   Inline ``<code>`` chip styling inside chat bubbles (v0.7.52)

   The ai-accounts ChatBubble renders parsed markdown via ``v-html``;
   marked turns backtick-wrapped fragments into plain ``<code>`` with
   default monospace styling. The user wanted file paths, function
   names, and other keywords to look visually distinct from prose —
   the same chip look the tool-call summary already uses. Targeting
   ``code`` inside ``.aia-bubble__content`` and excluding code blocks
   (``pre code``) gives every backtick-wrapped fragment in claude's
   replies a tag-style appearance.

   Selector specificity is high enough to override ai-accounts'
   own ChatBubble.vue ``code`` styles. ``[class*="hljs"]`` (highlighted
   code-block tokens) is excluded so syntax-highlighting inside
   fenced blocks isn't tinted by the chip background.
   ─────────────────────────────────────────────────────────────────── */
.aia-bubble__content code:not(pre code):not([class*="hljs"]) {
  font-family: 'Geist Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.86em;
  padding: 1px 8px;
  border-radius: 4px;
  background: var(--bg-tertiary);
  color: var(--accent-purple, #b388ff);
  border: 1px solid rgba(179, 136, 255, 0.18);
  white-space: nowrap;
  vertical-align: 1px;
}

/* Heuristic accent: anything that looks like a filesystem path
   (starts with ``/`` or ``./`` / ``~/``) reads as a path chip.
   Pure CSS can only check the FIRST character via ``:has()``-less
   attribute selectors when the content is in an attribute, which it
   isn't. So we rely on claude's convention (paths come backticked)
   and tint all inline code purple — same family as ``tool-path``
   inside ``<details>``. Function names / keywords come out the same
   color; that's fine — they're all "identifiers, not prose". */

/* Code blocks inside chat bubbles get a slightly elevated card look
   so multi-line snippets are clearly demarcated from prose. */
.aia-bubble__content pre {
  margin: 10px 0;
  padding: 12px 14px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  overflow-x: auto;
  line-height: 1.5;
}
.aia-bubble__content pre code {
  background: transparent;
  border: 0;
  padding: 0;
  color: var(--text-primary);
  white-space: pre;
  font-size: 0.86em;
}

/* Links inside chat bubbles look "linky" rather than blending in. */
.aia-bubble__content a {
  color: var(--accent-cyan, #00bcd4);
  text-decoration: underline;
  text-underline-offset: 2px;
  text-decoration-thickness: 1px;
}
.aia-bubble__content a:hover {
  text-decoration-thickness: 2px;
}

/* Headings inside chat bubbles. ChatBubble.vue (in @ai-accounts/vue-styled)
   ships its own scoped heading sizes that read flat: h1 1.35rem, h2 1.15rem,
   h3 1rem — only ~0.1rem apart, so a level-1 heading doesn't look "the
   biggest" relative to a level-2 next to it. Override here with a clearer
   GitHub-style scale.

   Specificity: ChatBubble's compiled scoped selector is
   ``.aia-bubble__content[data-v-XXXX] h1`` — (class + attr + el). To win
   without editing the ai-accounts package, use ``:where()``-free
   duplicate-class trick (class + class + el) AND ``!important`` as a
   belt-and-suspenders so future ai-accounts versions can't quietly out-
   specificity these again. */
.aia-bubble__content.aia-bubble__content h1,
.aia-bubble__content.aia-bubble__content h2,
.aia-bubble__content.aia-bubble__content h3,
.aia-bubble__content.aia-bubble__content h4,
.aia-bubble__content.aia-bubble__content h5,
.aia-bubble__content.aia-bubble__content h6 {
  margin: 14px 0 6px !important;
  line-height: 1.25 !important;
  font-weight: 600 !important;
  color: var(--text-primary) !important;
}
.aia-bubble__content.aia-bubble__content h1 {
  font-size: 1.85em !important;
  padding-bottom: 0.2em;
  border-bottom: 1px solid var(--border-default);
}
.aia-bubble__content.aia-bubble__content h2 {
  font-size: 1.5em !important;
  padding-bottom: 0.15em;
  border-bottom: 1px solid var(--border-default);
}
.aia-bubble__content.aia-bubble__content h3 { font-size: 1.25em !important; }
.aia-bubble__content.aia-bubble__content h4 { font-size: 1.05em !important; }
.aia-bubble__content.aia-bubble__content h5 {
  font-size: 0.9em !important;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-secondary) !important;
}
.aia-bubble__content.aia-bubble__content h6 {
  font-size: 0.85em !important;
  color: var(--text-muted) !important;
}

/* Lists need a small left indent and tighter spacing so claude's
   bulleted answers stay scannable. */
.aia-bubble__content ul,
.aia-bubble__content ol {
  margin: 6px 0;
  padding-left: 22px;
}
.aia-bubble__content li {
  margin: 2px 0;
}

/* Blockquotes get a left accent bar — same hue as the assistant
   chip — so quoted prose visually separates from the body. */
.aia-bubble__content blockquote {
  margin: 8px 0;
  padding: 4px 0 4px 12px;
  border-left: 3px solid var(--accent-cyan, #00bcd4);
  color: var(--text-secondary);
}

/* ───────────────────────────────────────────────────────────────────
   Extended-thinking blocks (v0.7.68)

   Claude with extended thinking emits a ``thinking`` content block
   that carries its reasoning. The backend lifts it into a dedicated
   SSE event; the frontend pushes a system-role message containing
   a ``<details class="thinking-block">`` widget. These styles live
   here (global, unscoped) so they cross ``v-html`` into the
   ChatBubble subtree.
   ─────────────────────────────────────────────────────────────────── */
.thinking-block {
  margin: 8px 0;
  border: 1px dashed var(--border-default);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.02);
  color: var(--text-muted);
  font-style: italic;
}
.thinking-block > summary {
  cursor: pointer;
  padding: 6px 12px;
  font-size: 12px;
  font-weight: 600;
  list-style: none;
  color: var(--text-secondary);
  font-style: normal;
  user-select: none;
}
.thinking-block > summary::-webkit-details-marker {
  display: none;
}
.thinking-block > summary::after {
  content: ' ▾';
  font-size: 10px;
  color: var(--text-muted);
}
.thinking-block[open] > summary::after {
  content: ' ▴';
}
.thinking-block > summary:hover {
  color: var(--text-primary);
}
.thinking-block .thinking-body {
  margin: 0;
  padding: 10px 14px;
  border-top: 1px dashed var(--border-default);
  font-family: 'Geist Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text-secondary);
  font-style: normal;
}

/* ───────────────────────────────────────────────────────────────────
   Hook decision badges (v0.7.66)

   ``ProjectSessionPanel`` emits a system-role message with embedded
   HTML when claude's ``PreToolUse``/``PostToolUse`` hooks return a
   permission decision. The bubble's ``v-html`` renders the markup;
   these rules give the badge a compact pill look with a kind-specific
   accent.
   ─────────────────────────────────────────────────────────────────── */
.hook-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
  font-family: 'Geist Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
}
.hook-badge .hook-icon {
  font-size: 11px;
}
.hook-badge .hook-event {
  font-weight: 600;
  color: var(--text-primary);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
.hook-badge .hook-tool {
  font-weight: 600;
  color: var(--accent-cyan, #00bcd4);
}
.hook-badge .hook-arg {
  font-family: 'Geist Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  color: var(--text-primary);
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.hook-badge .hook-decision {
  font-weight: 700;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 2px 7px;
  border-radius: 4px;
}
.hook-badge--allow {
  border-color: rgba(76, 175, 80, 0.4);
  background: rgba(76, 175, 80, 0.06);
}
.hook-badge--allow .hook-decision {
  background: rgba(76, 175, 80, 0.18);
  color: var(--accent-green, #4caf50);
}
.hook-badge--deny {
  border-color: rgba(255, 100, 100, 0.4);
  background: rgba(255, 100, 100, 0.06);
}
.hook-badge--deny .hook-decision {
  background: rgba(255, 100, 100, 0.18);
  color: var(--accent-red, #ff6464);
}
.hook-badge--ask {
  border-color: rgba(255, 200, 80, 0.4);
  background: rgba(255, 200, 80, 0.06);
}
.hook-badge--ask .hook-decision {
  background: rgba(255, 200, 80, 0.18);
  color: var(--accent-yellow, #ffcc80);
}

/* ───────────────────────────────────────────────────────────────────
   Kind-specific accent line so a glance distinguishes shell / file /
   search / web / task without reading the label.
   ─────────────────────────────────────────────────────────────────── */
.tool-call--shell > summary {
  border-left: 3px solid var(--accent-green, #4caf50);
}
.tool-call--file > summary {
  border-left: 3px solid var(--accent-purple, #b388ff);
}
.tool-call--search > summary {
  border-left: 3px solid var(--accent-yellow, #ffcc80);
}
.tool-call--web > summary {
  border-left: 3px solid var(--accent-blue, #42a5f5);
}
.tool-call--task > summary {
  border-left: 3px solid var(--accent-pink, #ec407a);
}
.tool-call--tool > summary {
  border-left: 3px solid var(--accent-cyan, #00bcd4);
}
</style>
