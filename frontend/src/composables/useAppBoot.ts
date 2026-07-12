/**
 * Application boot flow extracted from App.vue (v0.7.5d).
 *
 * Owns auth status check, ?tour=start watcher, bundle install, and
 * onMounted/onUnmounted hooks. The tour machine and sidebar/health
 * helpers are passed in so the parent (App.vue) keeps ownership of the
 * tour state and `provide()` chain.
 */
import { onMounted, onUnmounted, ref, watch, type Ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { setupApi, healthApi } from '../services/api';
import { getApiKey } from '../services/api/client';
import { useAuth } from './useAuth';
import { prefetchTourRoutes, type useTourMachine } from './useTourMachine';

type TourMachine = ReturnType<typeof useTourMachine>;
type ShowToast = (message: string, type?: 'success' | 'error' | 'info' | 'infrastructure', duration?: number) => void;

export interface UseAppBootOptions {
  tour: TourMachine;
  loadSidebarData: () => void;
  loadPlugins: () => void;
  startPolling: (interval: number) => void;
  stopPolling: () => void;
  showToast: ShowToast;
  navigateToTourStep: (step: string) => void;
}

export interface UseAppBoot {
  showApiKeyBanner: Ref<boolean>;
  appReady: Ref<boolean>;
  onAuthenticated: () => void;
  handleTourRetry: () => void;
}

export function useAppBoot(opts: UseAppBootOptions): UseAppBoot {
  const route = useRoute();
  const router = useRouter();
  const { tour, loadSidebarData, loadPlugins, startPolling, stopPolling, showToast, navigateToTourStep } = opts;

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
      // Authenticated (or auth not required): make sure any stale banner is
      // cleared — checkAuthStatus is authoritative for banner visibility.
      showApiKeyBanner.value = false;
      return true;
    } catch {
      return false;
    }
  }

  function beginTourIfRequested(): boolean {
    if (route.query.tour !== 'start' || tour.isActive.value) return false;
    router.replace({ query: {} });
    tour.startTour();
    tour.nextStep(); // welcome -> workspace (welcome page already shown)
    prefetchTourRoutes(); // OB-42: fire-and-forget route prefetch
    return true;
  }

  function onAuthenticated() {
    showApiKeyBanner.value = false;
    loadSidebarData();
    beginTourIfRequested();
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
        await new Promise((r) => setTimeout(r, 500));
        showToast(`Installed ${displayNames[name] || name} plugin`, 'success');
      }
      loadPlugins();
    } catch {
      // Bundle install failed — will retry on next launch
    }
  }

  // The api-key banner is decided ONCE at boot (checkAuthStatus in onMounted).
  // A user who signs in on the /login page — where the guard sends unauthenticated
  // visitors — never triggers the banner's own @authenticated reset, so without
  // this the stale "API key required" banner from the pre-auth boot carries into
  // the app: the double-prompt (enter the key on /login AND again on the banner).
  // When we navigate while the banner is still up, re-verify auth: hide it at once
  // if a key is now present (no flash), then confirm and load the sidebar data the
  // pre-auth boot skipped.
  watch(
    () => route.fullPath,
    async () => {
      if (!showApiKeyBanner.value) return;
      if (getApiKey()) showApiKeyBanner.value = false;
      const ok = await checkAuthStatus();
      if (ok) {
        loadSidebarData();
        beginTourIfRequested();
      }
    },
  );

  // Watch for ?tour=start query param (set by WelcomePage after key generation)
  watch(
    () => route.query.tour,
    (tourQuery) => {
      if (tourQuery === 'start') {
        loadSidebarData();
        beginTourIfRequested();
      }
    },
  );

  onMounted(async () => {
    startPolling(10000);
    // Wave 35: rehydrate session from localStorage before the auth-status
    // check so the app boots into "logged in" without a flash of /login.
    await useAuth().restore();
    const isReady = await checkAuthStatus();
    appReady.value = true;
    if (isReady) {
      loadSidebarData();
      beginTourIfRequested();
      runBundleInstall();
    }
  });

  onUnmounted(() => {
    stopPolling();
  });

  return { showApiKeyBanner, appReady, onAuthenticated, handleTourRetry };
}
