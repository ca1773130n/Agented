import { ref, computed } from 'vue';
import type { Trigger, Project, Product, Team, Plugin, AIBackend } from '../services/api';
import {
  triggerApi,
  projectApi,
  productApi,
  teamApi,
  pluginApi,
  backendApi,
  versionApi,
} from '../services/api';
import { handleApiError } from '../services/api/error-handler';

type ShowToastFn = (message: string, type?: 'success' | 'error' | 'info' | 'infrastructure', duration?: number) => void;

export function useSidebarData(showToast: ShowToastFn) {
  const triggers = ref<Trigger[]>([]);
  const projects = ref<Project[]>([]);
  const products = ref<Product[]>([]);
  const teams = ref<Team[]>([]);
  const plugins = ref<Plugin[]>([]);
  const sidebarBackends = ref<AIBackend[]>([]);
  const appVersion = ref('...');

  const customTriggers = computed(() => triggers.value.filter(t => !t.is_predefined));

  const sidebarLoading = ref(true);
  const sidebarErrors = ref<Record<string, string | null>>({
    triggers: null,
    projects: null,
    products: null,
    teams: null,
    plugins: null,
    backends: null,
    version: null,
  });

  async function loadTriggers() {
    try {
      const data = await triggerApi.list();
      triggers.value = data.triggers || [];
    } catch (err) {
      handleApiError(err, showToast, 'Failed to load triggers');
      throw err;
    }
  }

  async function loadProjects() {
    try {
      const data = await projectApi.list();
      projects.value = data.projects || [];
    } catch (err) {
      handleApiError(err, showToast, 'Failed to load projects');
      throw err;
    }
  }

  async function loadProducts() {
    try {
      const data = await productApi.list();
      products.value = data.products || [];
    } catch (err) {
      handleApiError(err, showToast, 'Failed to load products');
      throw err;
    }
  }

  async function loadTeams() {
    try {
      const data = await teamApi.list();
      teams.value = data.teams || [];
    } catch (err) {
      handleApiError(err, showToast, 'Failed to load teams');
      throw err;
    }
  }

  async function loadPlugins() {
    try {
      const data = await pluginApi.list();
      plugins.value = data.plugins || [];
    } catch (err) {
      handleApiError(err, showToast, 'Failed to load plugins');
      throw err;
    }
  }

  async function loadSidebarBackends() {
    try {
      const data = await backendApi.list();
      sidebarBackends.value = data.backends || [];
    } catch (err) {
      handleApiError(err, showToast, 'Failed to load backends');
      throw err;
    }
  }

  async function loadVersion() {
    try {
      const res = await versionApi.get();
      appVersion.value = res.version || 'unknown';
    } catch {
      appVersion.value = 'unknown';
    }
  }

  const sidebarLoaders: { key: string; fn: () => Promise<void> }[] = [
    { key: 'triggers', fn: loadTriggers },
    { key: 'projects', fn: loadProjects },
    { key: 'products', fn: loadProducts },
    { key: 'teams', fn: loadTeams },
    { key: 'plugins', fn: loadPlugins },
    { key: 'backends', fn: loadSidebarBackends },
    { key: 'version', fn: loadVersion },
  ];

  async function loadSidebarData() {
    sidebarLoading.value = true;
    const results = await Promise.allSettled(sidebarLoaders.map(l => l.fn()));
    results.forEach((result, index) => {
      const key = sidebarLoaders[index].key;
      sidebarErrors.value[key] =
        result.status === 'rejected'
          ? result.reason instanceof Error
            ? result.reason.message
            : String(result.reason)
          : null;
    });
    sidebarLoading.value = false;
  }

  async function retrySidebarSection(key: string) {
    sidebarErrors.value[key] = null;
    const loader = sidebarLoaders.find(l => l.key === key);
    if (!loader) return;
    try {
      await loader.fn();
      sidebarErrors.value[key] = null;
    } catch (err) {
      sidebarErrors.value[key] = err instanceof Error ? err.message : String(err);
    }
  }

  async function refreshTriggers() {
    await loadTriggers();
  }

  return {
    triggers,
    projects,
    products,
    teams,
    plugins,
    sidebarBackends,
    appVersion,
    customTriggers,
    sidebarLoading,
    sidebarErrors,
    loadSidebarData,
    retrySidebarSection,
    refreshTriggers,
    loadPlugins,
  };
}
