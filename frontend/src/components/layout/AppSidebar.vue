<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';
import type { Trigger, Product, Project, Team, Plugin, AIBackend, ProjectSAInstance } from '../../services/api';
import { projectInstanceApi } from '../../services/api';
import { useWebMcpTool } from '../../composables/useWebMcpTool';
import { useTourChecklist } from '../../composables/useTourChecklist';
import SidebarSectionLabel from './SidebarSectionLabel.vue';
import SidebarGroupToggle from './SidebarGroupToggle.vue';
import SidebarFlatLink from './SidebarFlatLink.vue';
import SidebarSetupChecklist from './SidebarSetupChecklist.vue';

const { t } = useI18n();

const route = useRoute();
const router = useRouter();

const { checklistItems, completedCount, totalCount, showChecklist } = useTourChecklist();

const props = withDefaults(defineProps<{
  appVersion: string;
  healthColor: string;
  healthTooltip: string;
  activeExecutionCount: number;
  customTriggers: Trigger[];
  products: Product[];
  projects: Project[];
  teams: Team[];
  plugins: Plugin[];
  sidebarBackends: AIBackend[];
  collapsed?: boolean;
  isMobile?: boolean;
  mobileOpen?: boolean;
  sidebarLoading?: boolean;
  sidebarErrors?: Record<string, string | null>;
}>(), {
  collapsed: false,
  isMobile: false,
  mobileOpen: false,
  sidebarLoading: false,
  sidebarErrors: () => ({}),
});

const emit = defineEmits<{
  closeMobile: [];
  retrySidebarSection: [key: string];
}>();

// Collapsible sidebar sections -- derived from route state
const expandedSections = ref<Record<string, boolean>>({
  dashboards: false,
  history: false,
  usage: false,
  skills: false,
  plugins: false,
  mcpServers: false,
  projects: false,
  products: false,
  teams: false,
  agents: false,
  superAgents: false,
  hooks: false,
  commands: false,
  rules: false,
  watchTower: false,
  aiBackends: false,
  workflows: false,
  triggers: false,
  platform: false,
  // PR-J2 — System analytics dashboards group.
  analytics: false,
});

function toggleSection(section: string) {
  expandedSections.value[section] = !expandedSections.value[section];
}

// Auto-expand the section matching the current route on initial load and route changes
function autoExpandForRoute() {
  const name = String(route.name || '');
  if (['dashboards', 'dashboards-quality', 'dashboards-cost', 'dashboards-health', 'dashboards-activity', 'security-dashboard', 'pr-review-dashboard', 'trigger-dashboard', 'token-usage', 'products-summary', 'projects-summary', 'teams-summary', 'agents-summary', 'analytics-dashboard', 'health-dashboard', 'team-impact-report', 'cross-team-insights', 'execution-queue-dashboard', 'execution-anomaly-detection', 'bot-health', 'service-health'].includes(name)) {
    expandedSections.value.dashboards = true;
    expandedSections.value.watchTower = true;
  }
  if (['trigger-history', 'audit-detail'].includes(name)) {
    expandedSections.value.history = true;
  }
  if (name === 'usage-history') {
    expandedSections.value.usage = true;
  }
  if (['skills-playground', 'skill-create', 'my-skills', 'skill-detail', 'explore-skills', 'skill-version-pinning'].includes(name)) {
    expandedSections.value.skills = true;
  }
  if (['plugins', 'plugin-design', 'harness-integration', 'explore-plugins', 'plugin-detail'].includes(name)) {
    expandedSections.value.plugins = true;
  }
  if (['mcp-servers', 'mcp-server-detail', 'explore-mcp-servers'].includes(name)) {
    expandedSections.value.mcpServers = true;
  }
  if (['projects', 'project-dashboard', 'project-settings', 'project-management', 'project-planning', 'project-instance-playground'].includes(name)) {
    expandedSections.value.projects = true;
  }
  if (['products', 'product-dashboard', 'product-settings'].includes(name)) {
    expandedSections.value.products = true;
  }
  if (['teams', 'team-dashboard', 'team-settings', 'team-builder'].includes(name)) {
    expandedSections.value.teams = true;
  }
  if (['agents', 'agent-create', 'agent-design', 'conversation-history-viewer'].includes(name)) {
    expandedSections.value.agents = true;
  }
  if (['super-agents', 'super-agent-playground', 'explore-super-agents'].includes(name)) {
    expandedSections.value.superAgents = true;
  }
  if (['hooks', 'hook-design'].includes(name)) {
    expandedSections.value.hooks = true;
  }
  if (['commands', 'command-design'].includes(name)) {
    expandedSections.value.commands = true;
  }
  if (['rules', 'rule-design'].includes(name)) {
    expandedSections.value.rules = true;
  }
  if (['workflows', 'workflow-builder', 'workflow-playground'].includes(name)) {
    expandedSections.value.workflows = true;
  }
  if (['ai-backends', 'backend-detail', 'service-health'].includes(name)) {
    expandedSections.value.aiBackends = true;
  }
  // Auto-expand only for sidebar-visible Triggers children; URL-only
  // routes (still reachable, just not in this submenu) don't trigger expand.
  if (['triggers', 'bot-templates', 'trigger-tools', 'pr-auto-assignment', 'pr-review-learning-loop', 'prompt-snippets', 'bot-output-webhook-forwarding'].includes(name)) {
    expandedSections.value.triggers = true;
  }
  // PR-J2 — Analytics dashboards (System).
  if (['ai-cost-dashboard', 'traces-list', 'trace-detail'].includes(name)) {
    expandedSections.value.analytics = true;
  }
  if (['secrets-vault', 'rbac-settings', 'sso-settings', 'team-budgets', 'audit-history', 'findings-triage-board'].includes(name)) {
    expandedSections.value.platform = true;
  }
}

// Auto-expand on mount
autoExpandForRoute();

// Auto-close mobile sidebar on any navigation
router.afterEach(() => {
  emit('closeMobile');
  autoExpandForRoute();
});

useWebMcpTool({
  name: 'agented_sidebar_get_state',
  description: 'Returns the current state of the AppSidebar',
  page: 'AppSidebar',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        component: 'AppSidebar',
        collapsed: props.collapsed,
        currentRoute: route.name,
        isMobile: props.isMobile,
        mobileOpen: props.mobileOpen,
        expandedSections: expandedSections.value,
        activeExecutionCount: props.activeExecutionCount,
      }),
    }],
  }),
});

// Active state derived from route
const currentRouteName = computed(() => String(route.name || ''));

function sidebarActive(page: string): boolean {
  return currentRouteName.value === page;
}

function isDashboardSectionActive(): boolean {
  return ['dashboards', 'dashboards-quality', 'dashboards-cost', 'dashboards-health', 'dashboards-activity', 'security-dashboard', 'pr-review-dashboard', 'trigger-dashboard', 'token-usage', 'products-summary', 'projects-summary', 'teams-summary', 'agents-summary', 'analytics-dashboard', 'health-dashboard', 'team-impact-report', 'cross-team-insights', 'execution-queue-dashboard', 'execution-anomaly-detection', 'bot-health', 'service-health'].includes(currentRouteName.value);
}

function isHistorySectionActive(): boolean {
  return ['trigger-history', 'audit-detail'].includes(currentRouteName.value);
}

function isSkillsSectionActive(): boolean {
  return ['skills-playground', 'skill-create', 'my-skills', 'explore-skills', 'skill-detail', 'skill-version-pinning'].includes(currentRouteName.value);
}

function isPluginsSectionActive(): boolean {
  return ['plugins', 'plugin-design', 'harness-integration', 'explore-plugins', 'plugin-detail'].includes(currentRouteName.value);
}

function isProjectsSectionActive(): boolean {
  return ['projects', 'project-dashboard', 'project-settings', 'project-management', 'project-planning', 'project-instance-playground'].includes(currentRouteName.value);
}

function isProductsSectionActive(): boolean {
  return ['products', 'product-dashboard', 'product-settings'].includes(currentRouteName.value);
}

function isTeamsSectionActive(): boolean {
  return ['teams', 'team-dashboard', 'team-settings', 'team-builder'].includes(currentRouteName.value);
}

function isAgentsSectionActive(): boolean {
  return ['agents', 'agent-create', 'agent-design', 'conversation-history-viewer'].includes(currentRouteName.value);
}

function isSuperAgentsSectionActive(): boolean {
  return ['super-agents', 'super-agent-playground', 'explore-super-agents'].includes(currentRouteName.value);
}

function isHooksSectionActive(): boolean {
  return ['hooks', 'hook-design'].includes(currentRouteName.value);
}

function isCommandsSectionActive(): boolean {
  return ['commands', 'command-design'].includes(currentRouteName.value);
}

function isRulesSectionActive(): boolean {
  return ['rules', 'rule-design'].includes(currentRouteName.value);
}

function isMcpServersSectionActive(): boolean {
  return ['mcp-servers', 'mcp-server-detail', 'explore-mcp-servers'].includes(currentRouteName.value);
}

function isWorkflowsSectionActive(): boolean {
  return ['workflows', 'workflow-builder', 'workflow-playground'].includes(currentRouteName.value);
}

function isTriggersSectionActive(): boolean {
  // Only the 21 currently-visible Triggers children. URL-only routes
  // (still reachable) don't paint this toggle active.
  return ['triggers', 'bot-templates', 'trigger-tools', 'pr-auto-assignment', 'pr-review-learning-loop', 'prompt-snippets', 'bot-output-webhook-forwarding'].includes(currentRouteName.value);
}

// PR-J2 — Analytics dashboards group under System.
function isAnalyticsSectionActive(): boolean {
  return ['ai-cost-dashboard', 'traces-list', 'trace-detail'].includes(currentRouteName.value);
}

function isPlatformSectionActive(): boolean {
  return ['secrets-vault', 'rbac-settings', 'sso-settings', 'team-budgets', 'audit-history', 'findings-triage-board', 'system-errors'].includes(currentRouteName.value);
}

// Helper: navigate via router (mobile auto-close handled by router.afterEach)
function navTo(routeName: string) {
  router.push({ name: routeName });
}

function navToTriggerDashboard(triggerId: string) {
  router.push({ name: 'trigger-dashboard', params: { triggerId } });
}

function navToTriggerHistory(triggerId: string) {
  router.push({ name: 'trigger-history', params: { triggerId } });
}

function navToProductDashboard(productId: string) {
  router.push({ name: 'product-dashboard', params: { productId } });
}

function navToProductSettings(productId: string) {
  router.push({ name: 'product-settings', params: { productId } });
}

function navToProjectDashboard(projectId: string) {
  router.push({ name: 'project-dashboard', params: { projectId } });
}

function navToProjectSettings(projectId: string) {
  router.push({ name: 'project-settings', params: { projectId } });
}

function navToTeamDashboard(teamId: string) {
  router.push({ name: 'team-dashboard', params: { teamId } });
}

function navToTeamSettings(teamId: string) {
  router.push({ name: 'team-settings', params: { teamId } });
}

function navToPluginDetail(pluginId: string) {
  router.push({ name: 'plugin-detail', params: { pluginId } });
}

function navToBackendDetail(backendId: string) {
  router.push({ name: 'backend-detail', params: { backendId } });
}

function navToAgentCreate() {
  router.push({ name: 'agent-create' });
}

// Project instance cache: keyed by project ID, cleared when project list changes
const projectInstancesCache = ref<Record<string, ProjectSAInstance[]>>({});
const expandedProjectInstances = ref<Record<string, boolean>>({});

watch(() => props.projects, () => {
  projectInstancesCache.value = {};
});

function toggleProjectInstances(projectId: string) {
  expandedProjectInstances.value[projectId] = !expandedProjectInstances.value[projectId];
  if (expandedProjectInstances.value[projectId] && !projectInstancesCache.value[projectId]) {
    loadProjectInstances(projectId);
  }
}

async function loadProjectInstances(projectId: string) {
  try {
    const data = await projectInstanceApi.list(projectId);
    projectInstancesCache.value[projectId] = data.instances || [];
  } catch {
    projectInstancesCache.value[projectId] = [];
  }
}

function navToInstancePlayground(projectId: string, instanceId: string) {
  router.push({
    name: 'project-instance-playground',
    params: { projectId, instanceId },
  });
}

const isCollapsedDesktop = () => props.collapsed && !props.isMobile;

function handleSidebarKeydown(e: KeyboardEvent) {
  if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp' && e.key !== 'Home' && e.key !== 'End') return;
  e.preventDefault();

  const nav = e.currentTarget as HTMLElement;
  const buttons = Array.from(nav.querySelectorAll<HTMLElement>(
    'button:not([disabled]), a[href]'
  )).filter(el => el.offsetParent !== null);

  const currentIndex = buttons.indexOf(document.activeElement as HTMLElement);
  let nextIndex: number;

  switch (e.key) {
    case 'ArrowDown':
      nextIndex = currentIndex < buttons.length - 1 ? currentIndex + 1 : 0;
      break;
    case 'ArrowUp':
      nextIndex = currentIndex > 0 ? currentIndex - 1 : buttons.length - 1;
      break;
    case 'Home':
      nextIndex = 0;
      break;
    case 'End':
      nextIndex = buttons.length - 1;
      break;
    default:
      return;
  }

  buttons[nextIndex]?.focus();
}
</script>

<template>
  <nav
    id="app-sidebar-nav"
    :class="['sidebar', { collapsed: isCollapsedDesktop(), 'mobile-open': props.isMobile && props.mobileOpen }]"
    :aria-label="t('nav.mainNavigation')"
    @keydown="handleSidebarKeydown"
  >
    <div class="sidebar-nav">
      <div class="nav-section-label">{{ t('nav.sectionWork') }}</div>
      <!-- Dashboards (expandable) — PR-E: moved into the Work group so
           it sits next to Sketch and Scheduling, the other daily-Work
           surfaces. PR-F: reordered to top of Work group — Dashboards is
           the daily entry-point. -->
      <SidebarGroupToggle
        :label="t('nav.dashboards')"
        :expanded="expandedSections.dashboards"
        :active="isDashboardSectionActive()"
        :collapsed-desktop="isCollapsedDesktop()"
        @toggle="toggleSection('dashboards')"
      >
        <template #icon>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <rect x="3" y="3" width="7" height="9" rx="1"/>
            <rect x="14" y="3" width="7" height="5" rx="1"/>
            <rect x="14" y="12" width="7" height="9" rx="1"/>
            <rect x="3" y="16" width="7" height="5" rx="1"/>
          </svg>
        </template>
      </SidebarGroupToggle>
      <!-- PR-D — Dashboards submenu collapsed from 13 entries to 5
           (1 landing + 4 lanes). Old links are still reachable via
           function-form redirects on their original names. -->
      <div v-show="expandedSections.dashboards" class="nav-submenu" role="region" :aria-label="t('nav.dashboards')">
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('dashboards') }" :aria-current="sidebarActive('dashboards') ? 'page' : undefined" @click="navTo('dashboards')">
          {{ t('nav.allDashboards') }}
        </button>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('dashboards-quality') }" :aria-current="sidebarActive('dashboards-quality') ? 'page' : undefined" @click="navTo('dashboards-quality')">
          {{ t('nav.quality') }}
        </button>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('dashboards-cost') }" :aria-current="sidebarActive('dashboards-cost') ? 'page' : undefined" @click="navTo('dashboards-cost')">
          {{ t('nav.cost') }}
        </button>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('dashboards-health') }" :aria-current="sidebarActive('dashboards-health') ? 'page' : undefined" @click="navTo('dashboards-health')">
          {{ t('nav.health') }}
        </button>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('dashboards-activity') }" :aria-current="sidebarActive('dashboards-activity') ? 'page' : undefined" @click="navTo('dashboards-activity')">
          {{ t('nav.activity') }}
        </button>
        <button v-for="b in props.customTriggers" :key="b.id" type="button" class="submenu-item"
          :class="{ active: currentRouteName === 'trigger-dashboard' && route.params.triggerId === b.id }"
          :aria-current="(currentRouteName === 'trigger-dashboard' && route.params.triggerId === b.id) ? 'page' : undefined"
          @click="navToTriggerDashboard(b.id)">
          {{ b.name }}
        </button>
      </div>

      <SidebarFlatLink
        :label="t('nav.sketch')"
        :active="sidebarActive('sketch-chat')"
        :collapsed-desktop="isCollapsedDesktop()"
        @click="navTo('sketch-chat')"
      >
        <template #icon>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
          </svg>
        </template>
      </SidebarFlatLink>


      <SidebarSectionLabel
        :label="t('nav.sectionOrganization')"
        :error-keys="['products', 'projects', 'teams']"
        :errors="props.sidebarErrors"
        @retry="(k) => emit('retrySidebarSection', k)"
      />
      <!-- Products (expandable) -->
      <SidebarGroupToggle
        :label="t('nav.products')"
        :expanded="expandedSections.products"
        :active="isProductsSectionActive()"
        :collapsed-desktop="isCollapsedDesktop()"
        @toggle="toggleSection('products')"
      >
        <template #icon>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
            <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
            <line x1="12" y1="22.08" x2="12" y2="12"/>
          </svg>
        </template>
      </SidebarGroupToggle>
      <div v-show="expandedSections.products" class="nav-submenu" role="region" :aria-label="t('nav.products')">
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('products') }" :aria-current="sidebarActive('products') ? 'page' : undefined" @click="navTo('products')">
          {{ t('nav.allProducts') }}
        </button>
        <div v-for="product in props.products" :key="product.id" class="submenu-item-row">
          <button type="button" class="submenu-item"
            :class="{ active: (currentRouteName === 'product-dashboard' || currentRouteName === 'product-settings') && route.params.productId === product.id }"
            :aria-current="((currentRouteName === 'product-dashboard' || currentRouteName === 'product-settings') && route.params.productId === product.id) ? 'page' : undefined"
            @click="navToProductDashboard(product.id)">
            {{ product.name }}
          </button>
          <button type="button" class="submenu-settings-btn" :title="t('nav.settings')" @click="navToProductSettings(product.id)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <circle cx="12" cy="12" r="3"/>
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
            </svg>
          </button>
        </div>
      </div>
      <!-- Projects (expandable) -->
      <SidebarGroupToggle
        :label="t('nav.projects')"
        :expanded="expandedSections.projects"
        :active="isProjectsSectionActive()"
        :collapsed-desktop="isCollapsedDesktop()"
        @toggle="toggleSection('projects')"
      >
        <template #icon>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
          </svg>
        </template>
      </SidebarGroupToggle>
      <div v-show="expandedSections.projects" class="nav-submenu" role="region" :aria-label="t('nav.projects')">
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('projects') }" :aria-current="sidebarActive('projects') ? 'page' : undefined" @click="navTo('projects')">
          {{ t('nav.allProjects') }}
        </button>
        <div v-for="project in props.projects" :key="project.id" class="submenu-project-group">
          <div class="submenu-item-row">
            <button type="button" class="submenu-item"
              :class="{ active: (currentRouteName === 'project-dashboard' || currentRouteName === 'project-settings' || currentRouteName === 'project-planning' || currentRouteName === 'project-instance-playground') && route.params.projectId === project.id }"
              :aria-current="((currentRouteName === 'project-dashboard' || currentRouteName === 'project-settings' || currentRouteName === 'project-planning' || currentRouteName === 'project-instance-playground') && route.params.projectId === project.id) ? 'page' : undefined"
              @click="navToProjectDashboard(project.id)">
              {{ project.name }}
            </button>
            <button type="button" class="submenu-settings-btn" :title="t('nav.instances')" @click.stop="toggleProjectInstances(project.id)">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <circle cx="12" cy="8" r="4"/>
                <path d="M6 21v-2a4 4 0 014-4h4a4 4 0 014 4v2"/>
              </svg>
            </button>
            <button type="button" class="submenu-settings-btn" :title="t('nav.planning')" @click="router.push({ name: 'project-planning', params: { projectId: project.id } })">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
              </svg>
            </button>
            <button type="button" class="submenu-settings-btn" :title="t('nav.settings')" @click="navToProjectSettings(project.id)">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <circle cx="12" cy="12" r="3"/>
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
              </svg>
            </button>
          </div>
          <div v-if="expandedProjectInstances[project.id]" class="project-instances-list">
            <button
              v-for="inst in (projectInstancesCache[project.id] || [])"
              :key="inst.id"
              type="button"
              class="submenu-item instance-item"
              :class="{ active: currentRouteName === 'project-instance-playground' && route.params.instanceId === inst.id }"
              :aria-current="(currentRouteName === 'project-instance-playground' && route.params.instanceId === inst.id) ? 'page' : undefined"
              @click="navToInstancePlayground(project.id, inst.id)"
            >
              <svg class="instance-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14">
                <circle cx="12" cy="8" r="4"/>
                <path d="M6 21v-2a4 4 0 014-4h4a4 4 0 014 4v2"/>
              </svg>
              {{ inst.sa_name || inst.id }}
            </button>
          </div>
        </div>
      </div>
      <!-- Teams (expandable) -->
      <SidebarGroupToggle
        :label="t('nav.teams')"
        :expanded="expandedSections.teams"
        :active="isTeamsSectionActive()"
        :collapsed-desktop="isCollapsedDesktop()"
        @toggle="toggleSection('teams')"
      >
        <template #icon>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
            <circle cx="9" cy="7" r="4"/>
            <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
            <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
          </svg>
        </template>
      </SidebarGroupToggle>
      <div v-show="expandedSections.teams" class="nav-submenu" role="region" :aria-label="t('nav.teams')">
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('teams') }" :aria-current="sidebarActive('teams') ? 'page' : undefined" @click="navTo('teams')">
          {{ t('nav.allTeams') }}
        </button>
        <div v-for="team in props.teams" :key="team.id" class="submenu-item-row">
          <button type="button" class="submenu-item"
            :class="{ active: (currentRouteName === 'team-dashboard' || currentRouteName === 'team-settings' || currentRouteName === 'team-builder') && route.params.teamId === team.id }"
            :aria-current="((currentRouteName === 'team-dashboard' || currentRouteName === 'team-settings' || currentRouteName === 'team-builder') && route.params.teamId === team.id) ? 'page' : undefined"
            @click="navToTeamDashboard(team.id)">
            {{ team.name }}
          </button>
          <button type="button" class="submenu-settings-btn" :title="t('nav.settings')" @click="navToTeamSettings(team.id)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <circle cx="12" cy="12" r="3"/>
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
            </svg>
          </button>
        </div>
      </div>
      <!-- Agents (expandable) -->
      <SidebarGroupToggle
        :label="t('nav.agents')"
        :expanded="expandedSections.agents"
        :active="isAgentsSectionActive()"
        :collapsed-desktop="isCollapsedDesktop()"
        @toggle="toggleSection('agents')"
      >
        <template #icon>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="12" cy="8" r="4"/>
            <path d="M6 21v-2a4 4 0 014-4h4a4 4 0 014 4v2"/>
            <circle cx="12" cy="8" r="2" fill="currentColor"/>
            <path d="M17 3l2 2-2 2M7 3l-2 2 2 2"/>
          </svg>
        </template>
      </SidebarGroupToggle>
      <div v-show="expandedSections.agents" class="nav-submenu" role="region" :aria-label="t('nav.agents')">
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('agents') }" :aria-current="sidebarActive('agents') ? 'page' : undefined" @click="navTo('agents')">
          {{ t('nav.allAgents') }}
        </button>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('agent-create') }" :aria-current="sidebarActive('agent-create') ? 'page' : undefined" @click="navToAgentCreate()">
          {{ t('nav.designAnAgent') }}
        </button>
        <!-- P2: Conversation History relocated here from Platform (it views agent conversations). -->
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('conversation-history-viewer') }" :aria-current="sidebarActive('conversation-history-viewer') ? 'page' : undefined" @click="navTo('conversation-history-viewer')">
          {{ t('nav.conversationHistory') }}
        </button>
      </div>

      <!-- SuperAgents (expandable) -->
      <SidebarGroupToggle
        :label="t('nav.superAgents')"
        :expanded="expandedSections.superAgents"
        :active="isSuperAgentsSectionActive()"
        :collapsed-desktop="isCollapsedDesktop()"
        @toggle="toggleSection('superAgents')"
      >
        <template #icon>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M12 2L4 6.5v5c0 5.5 3.4 10.3 8 11.5 4.6-1.2 8-6 8-11.5v-5L12 2z"/>
            <path d="M14.5 8.5c-1-.6-2.5-.4-3.2.4-.5.6-.2 1.2.4 1.6l1.6 1c.6.4.7 1.1.1 1.7-.8.8-2.2.6-3-.2" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </template>
      </SidebarGroupToggle>
      <div v-show="expandedSections.superAgents" class="nav-submenu" role="region" :aria-label="t('nav.superAgents')">
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('super-agents') }" :aria-current="sidebarActive('super-agents') ? 'page' : undefined" @click="navTo('super-agents')">
          {{ t('nav.allSuperAgents') }}
        </button>
      </div>

      <SidebarSectionLabel
        :label="t('nav.sectionForge')"
        :error-keys="['plugins', 'triggers']"
        :errors="props.sidebarErrors"
        @retry="(k) => emit('retrySidebarSection', k)"
      />

      <!-- Workflows (expandable) -->
      <SidebarGroupToggle
        :label="t('nav.workflows')"
        :expanded="expandedSections.workflows"
        :active="isWorkflowsSectionActive()"
        :collapsed-desktop="isCollapsedDesktop()"
        @toggle="toggleSection('workflows')"
      >
        <template #icon>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <rect x="8" y="2" width="8" height="5" rx="1"/>
            <rect x="8" y="10" width="8" height="5" rx="1"/>
            <rect x="8" y="18" width="8" height="5" rx="1"/>
            <line x1="12" y1="7" x2="12" y2="10"/>
            <line x1="12" y1="15" x2="12" y2="18"/>
          </svg>
        </template>
      </SidebarGroupToggle>
      <div v-show="expandedSections.workflows" class="nav-submenu" role="region" :aria-label="t('nav.workflows')">
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('workflows') }" :aria-current="sidebarActive('workflows') ? 'page' : undefined" @click="navTo('workflows')">
          {{ t('nav.allWorkflows') }}
        </button>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('workflow-playground') }" :aria-current="sidebarActive('workflow-playground') ? 'page' : undefined" @click="navTo('workflow-playground')">
          {{ t('nav.playground') }}
        </button>
      </div>

      <!-- Triggers (expandable) — PR-F: collapsed back into Forge after operator-feel testing showed the standalone section overweighted itself. -->
      <SidebarGroupToggle
        :label="t('nav.triggers')"
        :expanded="expandedSections.triggers"
        :active="isTriggersSectionActive()"
        :collapsed-desktop="isCollapsedDesktop()"
        @toggle="toggleSection('triggers')"
      >
        <template #icon>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
          </svg>
        </template>
      </SidebarGroupToggle>
      <div v-show="expandedSections.triggers" class="nav-submenu nav-submenu-blocks" role="region" :aria-label="t('nav.triggers')">
        <div class="submenu-block-label" aria-hidden="true">{{ t('nav.blockCore') }}</div>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('triggers') }" :aria-current="sidebarActive('triggers') ? 'page' : undefined" @click="navTo('triggers')">
          {{ t('nav.triggers') }}
        </button>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('bot-templates') }" :aria-current="sidebarActive('bot-templates') ? 'page' : undefined" @click="navTo('bot-templates')">
          {{ t('nav.botTemplates') }}
        </button>

        <div class="submenu-block-label" aria-hidden="true">{{ t('nav.blockConfiguration') }}</div>
        <!-- P2: Conditions / NL / Schedule / Payload / Dry-Run folded into one Trigger Tools page. -->
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('trigger-tools') }" :aria-current="sidebarActive('trigger-tools') ? 'page' : undefined" @click="navTo('trigger-tools')">
          {{ t('nav.triggerTools') }}
        </button>

        <div class="submenu-block-label" aria-hidden="true">{{ t('nav.blockPrReview') }}</div>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('pr-auto-assignment') }" :aria-current="sidebarActive('pr-auto-assignment') ? 'page' : undefined" @click="navTo('pr-auto-assignment')">
          {{ t('nav.prAutoAssignment') }}
        </button>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('pr-review-learning-loop') }" :aria-current="sidebarActive('pr-review-learning-loop') ? 'page' : undefined" @click="navTo('pr-review-learning-loop')">
          {{ t('nav.prReviewLearning') }}
        </button>

        <div class="submenu-block-label" aria-hidden="true">{{ t('nav.blockOps') }}</div>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('bot-output-webhook-forwarding') }" :aria-current="sidebarActive('bot-output-webhook-forwarding') ? 'page' : undefined" @click="navTo('bot-output-webhook-forwarding')">
          {{ t('nav.webhookForwarding') }}
        </button>

        <div class="submenu-block-label" aria-hidden="true">{{ t('nav.blockAuthoring') }}</div>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('prompt-snippets') }" :aria-current="sidebarActive('prompt-snippets') ? 'page' : undefined" @click="navTo('prompt-snippets')">
          {{ t('nav.promptSnippets') }}
        </button>
      </div>

      <!-- Plugins (expandable) -->
      <SidebarGroupToggle
        :label="t('nav.plugins')"
        :expanded="expandedSections.plugins"
        :active="isPluginsSectionActive()"
        :collapsed-desktop="isCollapsedDesktop()"
        @toggle="toggleSection('plugins')"
      >
        <template #icon>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
          </svg>
        </template>
      </SidebarGroupToggle>
      <div v-show="expandedSections.plugins" class="nav-submenu" role="region" :aria-label="t('nav.plugins')">
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('plugins') }" :aria-current="sidebarActive('plugins') ? 'page' : undefined" @click="navTo('plugins')">
          {{ t('nav.allPlugins') }}
        </button>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('plugin-design') }" :aria-current="sidebarActive('plugin-design') ? 'page' : undefined" @click="navTo('plugin-design')">
          {{ t('nav.designAPlugin') }}
        </button>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('harness-integration') }" :aria-current="sidebarActive('harness-integration') ? 'page' : undefined" @click="navTo('harness-integration')">
          {{ t('nav.harnessIntegration') }}
        </button>
        <button v-for="plugin in props.plugins" :key="plugin.id" type="button" class="submenu-item"
          :class="{ active: currentRouteName === 'plugin-detail' && route.params.pluginId === plugin.id }"
          :aria-current="(currentRouteName === 'plugin-detail' && route.params.pluginId === plugin.id) ? 'page' : undefined"
          @click="navToPluginDetail(plugin.id)">
          {{ plugin.name }}
        </button>
      </div>

      <!-- MCPs (expandable) — PR-E: label tightened from "MCP Servers"
           to "MCPs" for parity with Plugins / Skills / Hooks / Rules /
           Commands. Route name + page title unchanged. -->
      <SidebarGroupToggle
        :label="t('nav.mcps')"
        :expanded="expandedSections.mcpServers"
        :active="isMcpServersSectionActive()"
        :collapsed-desktop="isCollapsedDesktop()"
        @toggle="toggleSection('mcpServers')"
      >
        <template #icon>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <rect x="2" y="2" width="20" height="8" rx="2"/>
            <rect x="2" y="14" width="20" height="8" rx="2"/>
            <circle cx="6" cy="6" r="1" fill="currentColor"/>
            <circle cx="6" cy="18" r="1" fill="currentColor"/>
          </svg>
        </template>
      </SidebarGroupToggle>
      <div v-show="expandedSections.mcpServers" class="nav-submenu" role="region" :aria-label="t('nav.mcps')">
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('mcp-servers') }" :aria-current="sidebarActive('mcp-servers') ? 'page' : undefined" @click="navTo('mcp-servers')">
          {{ t('nav.allMcpServers') }}
        </button>
      </div>

      <!-- Skills (expandable) -->
      <SidebarGroupToggle
        :label="t('nav.skills')"
        :expanded="expandedSections.skills"
        :active="isSkillsSectionActive()"
        :collapsed-desktop="isCollapsedDesktop()"
        @toggle="toggleSection('skills')"
      >
        <template #icon>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M12 2L2 7l10 5 10-5-10-5z"/>
            <path d="M2 17l10 5 10-5"/>
            <path d="M2 12l10 5 10-5"/>
          </svg>
        </template>
      </SidebarGroupToggle>
      <div v-show="expandedSections.skills" class="nav-submenu" role="region" :aria-label="t('nav.skills')">
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('skills-playground') }" :aria-current="sidebarActive('skills-playground') ? 'page' : undefined" @click="navTo('skills-playground')">
          {{ t('nav.playground') }}
        </button>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('skill-create') }" :aria-current="sidebarActive('skill-create') ? 'page' : undefined" @click="navTo('skill-create')">
          {{ t('nav.designASkill') }}
        </button>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('my-skills') }" :aria-current="sidebarActive('my-skills') ? 'page' : undefined" @click="navTo('my-skills')">
          {{ t('nav.skillLibrary') }}
        </button>
        <!-- P2: Version Pinning relocated here from Platform (a skill/plugin version concern). -->
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('skill-version-pinning') }" :aria-current="sidebarActive('skill-version-pinning') ? 'page' : undefined" @click="navTo('skill-version-pinning')">
          {{ t('nav.versionPinning') }}
        </button>
      </div>

      <!-- Commands (expandable) -->
      <SidebarGroupToggle
        :label="t('nav.commands')"
        :expanded="expandedSections.commands"
        :active="isCommandsSectionActive()"
        :collapsed-desktop="isCollapsedDesktop()"
        @toggle="toggleSection('commands')"
      >
        <template #icon>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <polyline points="4 17 10 11 4 5"/>
            <line x1="12" y1="19" x2="20" y2="19"/>
          </svg>
        </template>
      </SidebarGroupToggle>
      <div v-show="expandedSections.commands" class="nav-submenu" role="region" :aria-label="t('nav.commands')">
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('commands') }" :aria-current="sidebarActive('commands') ? 'page' : undefined" @click="navTo('commands')">
          {{ t('nav.allCommands') }}
        </button>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('command-design') }" :aria-current="sidebarActive('command-design') ? 'page' : undefined" @click="navTo('command-design')">
          {{ t('nav.designACommand') }}
        </button>
      </div>

      <!-- Hooks (expandable) -->
      <SidebarGroupToggle
        :label="t('nav.hooks')"
        :expanded="expandedSections.hooks"
        :active="isHooksSectionActive()"
        :collapsed-desktop="isCollapsedDesktop()"
        @toggle="toggleSection('hooks')"
      >
        <template #icon>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
            <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
          </svg>
        </template>
      </SidebarGroupToggle>
      <div v-show="expandedSections.hooks" class="nav-submenu" role="region" :aria-label="t('nav.hooks')">
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('hooks') }" :aria-current="sidebarActive('hooks') ? 'page' : undefined" @click="navTo('hooks')">
          {{ t('nav.allHooks') }}
        </button>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('hook-design') }" :aria-current="sidebarActive('hook-design') ? 'page' : undefined" @click="navTo('hook-design')">
          {{ t('nav.designAHook') }}
        </button>
      </div>

      <!-- Rules (expandable) -->
      <SidebarGroupToggle
        :label="t('nav.rules')"
        :expanded="expandedSections.rules"
        :active="isRulesSectionActive()"
        :collapsed-desktop="isCollapsedDesktop()"
        @toggle="toggleSection('rules')"
      >
        <template #icon>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M12 2L2 7l10 5 10-5-10-5z"/>
            <path d="M2 17l10 5 10-5"/>
            <path d="M2 12l10 5 10-5"/>
            <circle cx="12" cy="12" r="3"/>
          </svg>
        </template>
      </SidebarGroupToggle>
      <div v-show="expandedSections.rules" class="nav-submenu" role="region" :aria-label="t('nav.rules')">
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('rules') }" :aria-current="sidebarActive('rules') ? 'page' : undefined" @click="navTo('rules')">
          {{ t('nav.allRules') }}
        </button>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('rule-design') }" :aria-current="sidebarActive('rule-design') ? 'page' : undefined" @click="navTo('rule-design')">
          {{ t('nav.designARule') }}
        </button>
      </div>

      <!-- Marketplace (flat link) — PR-E: promoted out of Forge to its
           own top-level slot between Forge and Triggers. Forge holds
           the assets you manage locally; Marketplace is where you go to
           get more. Keeping them as siblings (not parent/child) matches
           the operator's mental model. -->
      <SidebarFlatLink
        :label="t('nav.marketplace')"
        :active="sidebarActive('marketplace')"
        :collapsed-desktop="isCollapsedDesktop()"
        @click="navTo('marketplace')"
      >
        <template #icon>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M3 9l1.5-5h15L21 9"/>
            <path d="M3 9v11a1 1 0 001 1h16a1 1 0 001-1V9"/>
            <path d="M3 9h18"/>
            <path d="M8 13h8"/>
          </svg>
        </template>
      </SidebarFlatLink>

      <div class="nav-section-label">{{ t('nav.sectionHistory') }}</div>
      <!-- Triggers History (expandable) -->
      <SidebarGroupToggle
        :label="t('nav.triggers')"
        :expanded="expandedSections.history"
        :active="isHistorySectionActive()"
        :collapsed-desktop="isCollapsedDesktop()"
        @toggle="toggleSection('history')"
      >
        <template #icon>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="12" cy="12" r="10"/>
            <polyline points="12,6 12,12 16,14"/>
          </svg>
        </template>
      </SidebarGroupToggle>
      <div v-show="expandedSections.history" class="nav-submenu" role="region" :aria-label="t('nav.triggerHistory')">
        <button v-for="b in props.customTriggers" :key="b.id" type="button" class="submenu-item"
          :class="{ active: currentRouteName === 'trigger-history' && route.params.triggerId === b.id }"
          :aria-current="(currentRouteName === 'trigger-history' && route.params.triggerId === b.id) ? 'page' : undefined"
          @click="navToTriggerHistory(b.id)">
          {{ b.name }}
        </button>
      </div>

      <!-- Audit Log Trail (standalone nav item) -->
      <SidebarFlatLink
        :label="t('nav.auditLog')"
        :active="sidebarActive('audit-history')"
        :collapsed-desktop="isCollapsedDesktop()"
        @click="navTo('audit-history')"
      >
        <template #icon>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z"/>
          </svg>
        </template>
      </SidebarFlatLink>

      <!-- Execution Tools (flat link) — P2: Search / Tagging / Replay-Diff /
           Annotations folded into one tabbed page at /execution-tools. -->
      <SidebarFlatLink
        :label="t('nav.executionTools')"
        :active="sidebarActive('execution-tools')"
        :collapsed-desktop="isCollapsedDesktop()"
        @click="navTo('execution-tools')"
      >
        <template #icon>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="11" cy="11" r="8"/>
            <line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
        </template>
      </SidebarFlatLink>

      <!-- Usage History (expandable) -->
      <button type="button" class="nav-group-toggle" :class="{ active: currentRouteName === 'usage-history' }" :aria-expanded="expandedSections.usage" :aria-current="sidebarActive('usage-history') ? 'page' : undefined" :title="isCollapsedDesktop() ? t('nav.usage') : undefined" @click="toggleSection( 'usage')">
        <span class="nav-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <rect x="3" y="12" width="4" height="9" rx="1"/>
            <rect x="10" y="6" width="4" height="15" rx="1"/>
            <rect x="17" y="3" width="4" height="18" rx="1"/>
          </svg>
        </span>
        <span class="nav-text">{{ t('nav.usage') }}</span>
        <svg class="chevron-icon" :class="{ expanded: expandedSections.usage }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="9,18 15,12 9,6"/>
        </svg>
        <span class="nav-indicator"></span>
      </button>
      <div v-show="expandedSections.usage" class="nav-submenu" role="region" :aria-label="t('nav.usage')">
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('usage-history') }" :aria-current="sidebarActive('usage-history') ? 'page' : undefined" @click="navTo('usage-history')">
          {{ t('nav.tokenUsage') }}
        </button>
      </div>

      <div class="nav-section-label">{{ t('nav.sectionResources') }}</div>
      <!-- Help — Plugin SDK + GitHub Actions docs (P2 fold). -->
      <SidebarFlatLink
        :label="t('nav.help')"
        :active="sidebarActive('help')"
        :collapsed-desktop="isCollapsedDesktop()"
        @click="navTo('help')"
      >
        <template #icon>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="12" cy="12" r="10"/>
            <path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3"/>
            <line x1="12" y1="17" x2="12.01" y2="17"/>
          </svg>
        </template>
      </SidebarFlatLink>
      <a href="/docs" target="_blank" class="external-link">
        <span class="nav-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
            <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/>
          </svg>
        </span>
        <span class="nav-text">{{ t('nav.apiDocs') }}</span>
        <svg class="external-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3"/>
        </svg>
      </a>

      <SidebarSectionLabel
        :label="t('nav.sectionSystem')"
        :error-keys="['backends']"
        :errors="props.sidebarErrors"
        @retry="(k) => emit('retrySidebarSection', k)"
      />
      <!-- AI Backends (expandable) -->
      <button type="button" class="nav-group-toggle" :class="{ active: currentRouteName === 'ai-backends' || currentRouteName === 'backend-detail' }" :aria-expanded="expandedSections.aiBackends" :aria-current="(currentRouteName === 'ai-backends' || currentRouteName === 'backend-detail') ? 'page' : undefined" :title="isCollapsedDesktop() ? t('nav.aiBackends') : undefined" @click="toggleSection( 'aiBackends')">
        <span class="nav-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="12" cy="12" r="3"/>
            <path d="M12 2v4m0 12v4M2 12h4m12 0h4"/>
            <path d="M4.93 4.93l2.83 2.83m8.48 8.48l2.83 2.83M4.93 19.07l2.83-2.83m8.48-8.48l2.83-2.83"/>
          </svg>
        </span>
        <span class="nav-text">{{ t('nav.aiBackends') }}</span>
        <svg class="chevron-icon" :class="{ expanded: expandedSections.aiBackends }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="9,18 15,12 9,6"/>
        </svg>
        <span class="nav-indicator"></span>
      </button>
      <div v-show="expandedSections.aiBackends" class="nav-submenu" role="region" :aria-label="t('nav.aiBackends')">
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('ai-backends') }" :aria-current="sidebarActive('ai-backends') ? 'page' : undefined" @click="navTo('ai-backends')">
          {{ t('nav.allBackends') }}
        </button>
        <button v-for="b in props.sidebarBackends" :key="b.id" type="button" class="submenu-item"
          :class="{ active: currentRouteName === 'backend-detail' && route.params.backendId === b.id }"
          :aria-current="(currentRouteName === 'backend-detail' && route.params.backendId === b.id) ? 'page' : undefined"
          @click="navToBackendDetail(b.id)">
          {{ b.name }}
        </button>
      </div>

      <!-- PR-J2 — Analytics (expandable, System group). Holds the three
           KEEP+WIRE observability/cost dashboards. `trace-detail` is a
           deep-link reached from `traces-list` rows. -->
      <SidebarGroupToggle
        :label="t('nav.analytics')"
        :expanded="expandedSections.analytics"
        :active="isAnalyticsSectionActive()"
        :collapsed-desktop="isCollapsedDesktop()"
        @toggle="toggleSection('analytics')"
      >
        <template #icon>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M3 3v18h18"/>
            <path d="M7 14l4-4 3 3 5-6"/>
          </svg>
        </template>
      </SidebarGroupToggle>
      <div v-show="expandedSections.analytics" class="nav-submenu" role="region" :aria-label="t('nav.analytics')">
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('ai-cost-dashboard') }" :aria-current="sidebarActive('ai-cost-dashboard') ? 'page' : undefined" @click="navTo('ai-cost-dashboard')">
          {{ t('nav.aiCost') }}
        </button>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('traces-list') }" :aria-current="sidebarActive('traces-list') ? 'page' : undefined" @click="navTo('traces-list')">
          {{ t('nav.traces') }}
        </button>
      </div>

      <!-- Integrations (flat link) — P2: Slack / Ticketing / Channels
           merged into one tabbed page at /integrations (they were three
           views over the same db_integrations table). -->
      <SidebarFlatLink
        :label="t('nav.integrations')"
        :active="sidebarActive('integrations')"
        :collapsed-desktop="isCollapsedDesktop()"
        @click="navTo('integrations')"
      >
        <template #icon>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3"/>
          </svg>
        </template>
      </SidebarFlatLink>

      <!-- Platform Admin (expandable) -->
      <SidebarGroupToggle
        :label="t('nav.platform')"
        :expanded="expandedSections.platform"
        :active="isPlatformSectionActive()"
        :collapsed-desktop="isCollapsedDesktop()"
        @toggle="toggleSection('platform')"
      >
        <template #icon>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <rect x="2" y="3" width="20" height="14" rx="2"/>
            <path d="M8 21h8M12 17v4"/>
          </svg>
        </template>
      </SidebarGroupToggle>
      <div v-show="expandedSections.platform" class="nav-submenu" role="region" :aria-label="t('nav.platform')">
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('secrets-vault') }" :aria-current="sidebarActive('secrets-vault') ? 'page' : undefined" @click="navTo('secrets-vault')">
          {{ t('nav.secretsVault') }}
        </button>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('rbac-settings') }" :aria-current="sidebarActive('rbac-settings') ? 'page' : undefined" @click="navTo('rbac-settings')">
          {{ t('nav.rbacSettings') }}
        </button>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('sso-settings') }" :aria-current="sidebarActive('sso-settings') ? 'page' : undefined" @click="navTo('sso-settings')">
          {{ t('nav.ssoSaml') }}
        </button>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('team-budgets') }" :aria-current="sidebarActive('team-budgets') ? 'page' : undefined" @click="navTo('team-budgets')">
          {{ t('nav.teamBudgets') }}
        </button>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('api-keys') }" :aria-current="sidebarActive('api-keys') ? 'page' : undefined" @click="navTo('api-keys')">
          {{ t('nav.apiKeys') }}
        </button>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('findings-triage-board') }" :aria-current="sidebarActive('findings-triage-board') ? 'page' : undefined" @click="navTo('findings-triage-board')">
          {{ t('nav.findingsTriage') }}
        </button>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('system-errors') }" :aria-current="sidebarActive('system-errors') ? 'page' : undefined" @click="navTo('system-errors')">
          {{ t('nav.systemErrors') }}
        </button>
      </div>

      <!-- OB-35: Setup checklist — visible after tour starts/completes -->
      <SidebarSetupChecklist
        v-if="showChecklist && !isCollapsedDesktop()"
        :items="checklistItems"
        :completed-count="completedCount"
        :total-count="totalCount"
        @navigate="(p) => router.push(p)"
      />

      <!-- Settings (flat link) -->
      <SidebarFlatLink
        :label="t('nav.settings')"
        :active="sidebarActive('settings')"
        :collapsed-desktop="isCollapsedDesktop()"
        @click="navTo('settings')"
      >
        <template #icon>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="12" cy="12" r="3"/>
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
          </svg>
        </template>
      </SidebarFlatLink>
    </div>
  </nav>
</template>

<style scoped>
.sidebar-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px 16px;
  color: var(--text-tertiary);
  font-size: 0.8rem;
}

.sidebar-loading-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid var(--border-default);
  border-top-color: var(--accent-cyan);
  border-radius: 50%;
  animation: sidebar-spin 0.8s linear infinite;
}

@keyframes sidebar-spin {
  to {
    transform: rotate(360deg);
  }
}

/* Triggers section visual block separators (PR-B).
 * Non-clickable labels that group the 25 trigger sub-items into 6
 * blocks. Marked aria-hidden in markup — the items themselves carry
 * meaningful labels. */
.submenu-block-label {
  padding: 10px 16px 4px;
  font-size: 0.65rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-tertiary);
  opacity: 0.65;
  pointer-events: none;
}

.nav-submenu-blocks .submenu-block-label:first-child {
  padding-top: 4px;
}

/* Project instances sub-items */
.submenu-project-group {
  display: flex;
  flex-direction: column;
}

.project-instances-list {
  padding-left: 12px;
}

.instance-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.instance-item:hover {
  color: var(--accent-cyan);
}

.instance-item.active {
  color: var(--accent-cyan);
}

.instance-icon {
  flex-shrink: 0;
  opacity: 0.7;
}
</style>
