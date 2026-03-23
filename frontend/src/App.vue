<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, provide, computed, getCurrentInstance } from 'vue';
import { useI18n } from 'vue-i18n';
import { setupApi, healthApi } from './services/api';
import { useRoute, useRouter } from 'vue-router';
import { useTourMachine, prefetchTourRoutes } from './composables/useTourMachine';
import TourOverlay from './components/tour/TourOverlay.vue';
import TourCompletionScreen from './components/tour/TourCompletionScreen.vue';
import { TOUR_STEP_MAP, TOTAL_TOUR_STEPS } from './constants/tourSteps';
import AppSidebar from './components/layout/AppSidebar.vue';
import AppHeader from './components/layout/AppHeader.vue';
import ApiKeyBanner from './components/layout/ApiKeyBanner.vue';
import ErrorBoundary from './components/base/ErrorBoundary.vue';
import { registerGenericTools } from './webmcp/generic-tools';
import { useSidebarCollapse } from './composables/useSidebarCollapse';
import { useSidebarData } from './composables/useSidebarData';
import { useHealthPolling } from './composables/useHealthPolling';

// Route state for layout decisions
const route = useRoute();
const router = useRouter();
const { t } = useI18n();
const isFullBleed = computed(() => route.meta.fullBleed === true);
const isWelcomePage = computed(() => route.name === 'welcome');
const tour = useTourMachine();

// ---------------------------------------------------------------------------
// Tour step metadata — derived from shared TOUR_STEP_DEFINITIONS
// ---------------------------------------------------------------------------

const tourActive = computed(() => tour.isActive.value && !isWelcomePage.value);

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

// Tour completion screen
const tourComplete = computed(() => tour.state.value === 'complete');

function handleTourDone() {
  tour.restartTour(); // Resets machine to idle, clears localStorage
  router.push('/');
}

/** Navigate to the route for a given tour step (deduplicates against current route) */
function navigateToTourStep(step: string) {
  const meta = TOUR_STEP_MAP[step];
  if (!meta) return;
  if (route.path === meta.route && (!meta.routeHash || route.hash === meta.routeHash)) return;
  const target = meta.routeHash ? { path: meta.route, hash: meta.routeHash } : { path: meta.route };
  router.push(target);
}

// Navigate to correct route when machine state changes
watch(() => tour.currentStep.value, (step) => {
  navigateToTourStep(step);
});

// Toast notification system
type ToastType = 'success' | 'error' | 'info' | 'infrastructure';

interface Toast {
  id: number;
  message: string;
  type: ToastType;
}

const toasts = ref<Toast[]>([]);
let toastId = 0;

function showToast(message: string, type: ToastType = 'info', duration?: number) {
  const id = ++toastId;
  const defaultDuration = type === 'infrastructure' ? 8000 : type === 'error' ? 8000 : 4000;
  toasts.value.push({ id, message, type });
  setTimeout(() => {
    toasts.value = toasts.value.filter(t => t.id !== id);
  }, duration ?? defaultDuration);

  // Auto-advance tour when a success toast matches the current step's trigger
  // Skip auto-advance for backend account steps — the AccountWizard controls advancement
  if (type === 'success' && tour.isActive.value) {
    const step = tour.currentStep.value;
    const isBackendStep = step.startsWith('backends.');
    if (!isBackendStep) {
      const meta = TOUR_STEP_MAP[step];
      if (meta?.autoAdvanceOnToast && message.includes(meta.autoAdvanceOnToast)) {
        setTimeout(() => tour.nextStep(), 800);
      }
    }
  }
}

function dismissToast(id: number) {
  toasts.value = toasts.value.filter(t => t.id !== id);
}

provide('showToast', showToast);

// Modal coordination during tour (OB-44)
const modalOpenDuringTour = ref(false);
provide('setTourModalOpen', (open: boolean) => {
  modalOpenDuringTour.value = open;
});
watch(tourActive, (active) => {
  if (!active) modalOpenDuringTour.value = false;
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

// Sidebar collapse/mobile state
const { isCollapsed, isMobileOpen, isMobile, toggleCollapse, toggleMobile, closeMobile } =
  useSidebarCollapse();

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

// API key auth state — show banner when backend requires auth and no key is stored
const showApiKeyBanner = ref(false);
const appReady = ref(false);

async function checkAuthStatus(): Promise<boolean> {
  try {
    const status = await healthApi.authStatus();
    if (status.needs_setup) {
      router.push({ name: 'welcome' });
      return false;
    } else if (status.auth_required && !status.authenticated) {
      showApiKeyBanner.value = true;
      return false;
    }
    return true;
  } catch {
    return false;
  }
}

function onAuthenticated() {
  showApiKeyBanner.value = false;
  const shouldStartTour = route.query.tour === 'start';
  loadSidebarData();
  if (shouldStartTour) {
    router.replace({ query: {} });
    tour.startTour();
    tour.nextStep(); // welcome -> workspace (welcome page already shown)
    prefetchTourRoutes(); // OB-42: fire-and-forget route prefetch
  }
}

function handleTourRetry() {
  navigateToTourStep(tour.currentStep.value);
}

async function runBundleInstall() {
  try {
    const res = await setupApi.bundleInstall();
    if (res.status === 'already_installed') return;

    if (res.marketplace_created) {
      showToast('Bundle marketplace connected', 'success');
    }
    const displayNames: Record<string, string> = { grd: 'GetResearchDone' };
    for (const name of res.plugins_installed || []) {
      await new Promise(r => setTimeout(r, 500));
      showToast(`Installed ${displayNames[name] || name} plugin`, 'success');
    }
    loadPlugins();
  } catch {
    // Bundle install failed — will retry on next launch
  }
}

// Watch for ?tour=start query param (set by WelcomePage after key generation)
watch(() => route.query.tour, (tourQuery) => {
  if (tourQuery === 'start') {
    router.replace({ query: {} });
    loadSidebarData();
    tour.startTour();
    tour.nextStep(); // welcome -> workspace
    prefetchTourRoutes(); // OB-42: fire-and-forget route prefetch
  }
});

onMounted(async () => {
  startPolling(10000);
  const isReady = await checkAuthStatus();
  appReady.value = true;
  if (isReady) {
    if (route.query.tour === 'start') {
      router.replace({ query: {} });
      loadSidebarData();
      tour.startTour();
      tour.nextStep(); // welcome -> workspace
      prefetchTourRoutes(); // OB-42: fire-and-forget route prefetch
      return;
    }
    loadSidebarData();
    runBundleInstall();
  }
});

onUnmounted(() => {
  stopPolling();
});
</script>

<template>
  <div v-if="appReady" :class="['app-layout', { 'sidebar-collapsed': isCollapsed && !isMobile, 'sidebar-mobile': isMobile }]">
    <a href="#main-content" class="skip-to-content">Skip to content</a>

    <template v-if="!isWelcomePage">
      <AppHeader @toggle-sidebar="toggleMobile" />

      <ApiKeyBanner
        v-if="showApiKeyBanner"
        @authenticated="onAuthenticated"
      />
    </template>

    <div v-if="isWelcomePage" class="welcome-fullscreen">
      <ErrorBoundary>
        <router-view />
      </ErrorBoundary>
    </div>

    <div v-else class="app-body">
      <!-- Mobile backdrop overlay -->
      <div v-if="isMobile && isMobileOpen" class="sidebar-backdrop" @click="closeMobile"></div>

      <!-- Desktop collapse toggle -->
      <button v-if="!isMobile" class="collapse-toggle" :aria-label="isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'" @click="toggleCollapse">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline v-if="isCollapsed" points="9,18 15,12 9,6"/>
          <polyline v-else points="15,18 9,12 15,6"/>
        </svg>
      </button>

      <AppSidebar
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
        :collapsed="isCollapsed"
        :is-mobile="isMobile"
        :mobile-open="isMobileOpen"
        :sidebar-loading="sidebarLoading"
        :sidebar-errors="sidebarErrors"
        @close-mobile="closeMobile"
        @retry-sidebar-section="retrySidebarSection"
      />

      <main id="main-content" class="main-content" tabindex="-1">
        <div class="content-wrapper" :class="{ 'full-bleed': isFullBleed }">
          <ErrorBoundary>
            <router-view />
          </ErrorBoundary>
        </div>
      </main>
    </div>

    <!-- Toast Notifications -->
    <Teleport to="body">
      <div class="toast-container" role="status" aria-live="polite">
        <TransitionGroup name="toast">
          <div
            v-for="toast in toasts"
            :key="toast.id"
            :class="['toast', toast.type]"
          >
            <div class="toast-icon">
              <svg v-if="toast.type === 'success'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M20 6L9 17l-5-5"/>
              </svg>
              <svg v-else-if="toast.type === 'error'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"/>
                <path d="M15 9l-6 6M9 9l6 6"/>
              </svg>
              <svg v-else-if="toast.type === 'infrastructure'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
                <line x1="12" y1="9" x2="12" y2="13"/>
                <line x1="12" y1="17" x2="12.01" y2="17"/>
              </svg>
              <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"/>
                <path d="M12 16v-4M12 8h.01"/>
              </svg>
            </div>
            <span class="toast-message">{{ toast.message }}</span>
            <button class="toast-dismiss" @click="dismissToast(toast.id)" aria-label="Dismiss notification">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M18 6L6 18M6 6l12 12"/>
              </svg>
            </button>
          </div>
        </TransitionGroup>
      </div>
    </Teleport>

    <TourOverlay
      :active="tourActive"
      :step="tourStep"
      :effective-target="null"
      :substep-label="tourSubstepLabel"
      :step-number="tourStepNumber"
      :total-steps="TOTAL_TOUR_STEPS"
      :is-modal-open="modalOpenDuringTour"
      @next="tour.nextStep"
      @skip="tour.skipStep"
      @retry="handleTourRetry"
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
@import url('https://fonts.googleapis.com/css2?family=Geist+Mono:wght@400;500;600;700&family=Geist:wght@400;500;600;700&display=swap');

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
  --font-sans: 'Geist', -apple-system, BlinkMacSystemFont, sans-serif;
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

.form-group input[type="text"],
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
</style>
