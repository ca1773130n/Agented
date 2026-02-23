<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import type { Trigger, Product, Project, Team, Plugin, AIBackend } from '../../services/api';
import { useWebMcpTool } from '../../composables/useWebMcpTool';

const route = useRoute();
const router = useRouter();

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
}>(), {
  collapsed: false,
  isMobile: false,
  mobileOpen: false,
});

const emit = defineEmits<{
  closeMobile: [];
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
});

function toggleSection(section: string) {
  expandedSections.value[section] = !expandedSections.value[section];
}

// Auto-expand the section matching the current route on initial load and route changes
function autoExpandForRoute() {
  const name = String(route.name || '');
  if (['dashboards', 'security-dashboard', 'pr-review-dashboard', 'trigger-dashboard', 'token-usage', 'products-summary', 'projects-summary', 'teams-summary', 'agents-summary', 'rotation-dashboard'].includes(name)) {
    expandedSections.value.dashboards = true;
    expandedSections.value.watchTower = true;
  }
  if (['security-history', 'trigger-history', 'audit-detail'].includes(name)) {
    expandedSections.value.history = true;
  }
  if (name === 'usage-history') {
    expandedSections.value.usage = true;
  }
  if (['skills-playground', 'skill-create', 'my-skills', 'skill-detail', 'explore-skills'].includes(name)) {
    expandedSections.value.skills = true;
  }
  if (['plugins', 'plugin-design', 'harness-integration', 'explore-plugins', 'plugin-detail'].includes(name)) {
    expandedSections.value.plugins = true;
  }
  if (['mcp-servers', 'mcp-server-detail', 'explore-mcp-servers'].includes(name)) {
    expandedSections.value.mcpServers = true;
  }
  if (['projects', 'project-dashboard', 'project-settings', 'project-management'].includes(name)) {
    expandedSections.value.projects = true;
  }
  if (['products', 'product-dashboard', 'product-settings'].includes(name)) {
    expandedSections.value.products = true;
  }
  if (['teams', 'team-dashboard', 'team-settings', 'team-builder'].includes(name)) {
    expandedSections.value.teams = true;
  }
  if (['agents', 'agent-create', 'agent-design'].includes(name)) {
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
  if (['triggers'].includes(name)) {
    expandedSections.value.watchTower = true;
  }
  if (['ai-backends', 'backend-detail', 'service-health'].includes(name)) {
    expandedSections.value.aiBackends = true;
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
  return ['dashboards', 'security-dashboard', 'pr-review-dashboard', 'trigger-dashboard', 'token-usage', 'products-summary', 'projects-summary', 'teams-summary', 'agents-summary', 'rotation-dashboard'].includes(currentRouteName.value);
}

function isHistorySectionActive(): boolean {
  return ['security-history', 'trigger-history', 'audit-detail'].includes(currentRouteName.value);
}

function isSkillsSectionActive(): boolean {
  return ['skills-playground', 'skill-create', 'my-skills', 'explore-skills', 'skill-detail'].includes(currentRouteName.value);
}

function isPluginsSectionActive(): boolean {
  return ['plugins', 'plugin-design', 'harness-integration', 'explore-plugins', 'plugin-detail'].includes(currentRouteName.value);
}

function isProjectsSectionActive(): boolean {
  return ['projects', 'project-dashboard', 'project-settings', 'project-management'].includes(currentRouteName.value);
}

function isProductsSectionActive(): boolean {
  return ['products', 'product-dashboard', 'product-settings'].includes(currentRouteName.value);
}

function isTeamsSectionActive(): boolean {
  return ['teams', 'team-dashboard', 'team-settings', 'team-builder'].includes(currentRouteName.value);
}

function isAgentsSectionActive(): boolean {
  return ['agents', 'agent-create', 'agent-design'].includes(currentRouteName.value);
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

function navToSecurityHistory() {
  router.push({ name: 'security-history' });
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
    :class="['sidebar', { collapsed: isCollapsedDesktop(), 'mobile-open': props.isMobile && props.mobileOpen }]"
    aria-label="Main navigation"
    @keydown="handleSidebarKeydown"
  >
    <div class="sidebar-header">
      <div class="logo-mark">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
        </svg>
      </div>
      <div class="logo-text">
        <div class="logo-line-2">
          <span>Agented</span>
          <span class="version-tag">{{ props.appVersion }}</span>
          <span class="health-indicator" :style="{ backgroundColor: props.healthColor }" :title="props.healthTooltip"></span>
          <span v-if="props.activeExecutionCount > 0" class="active-badge" :title="`${props.activeExecutionCount} execution(s) running`">
            {{ props.activeExecutionCount }}
          </span>
        </div>
      </div>
    </div>

    <div class="sidebar-nav">
      <div class="nav-section-label">Watch Tower</div>

      <!-- Dashboards (expandable) -->
      <button type="button" class="nav-group-toggle" :class="{ active: isDashboardSectionActive() }" :aria-expanded="expandedSections.dashboards" :aria-current="isDashboardSectionActive() ? 'page' : undefined" :title="isCollapsedDesktop() ? 'Dashboards' : undefined" @click="toggleSection( 'dashboards')">
        <span class="nav-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <rect x="3" y="3" width="7" height="9" rx="1"/>
            <rect x="14" y="3" width="7" height="5" rx="1"/>
            <rect x="14" y="12" width="7" height="9" rx="1"/>
            <rect x="3" y="16" width="7" height="5" rx="1"/>
          </svg>
        </span>
        <span class="nav-text">Dashboards</span>
        <svg class="chevron-icon" :class="{ expanded: expandedSections.dashboards }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="9,18 15,12 9,6"/>
        </svg>
        <span class="nav-indicator"></span>
      </button>
      <div v-show="expandedSections.dashboards" class="nav-submenu" role="region" aria-label="Dashboards">
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('dashboards') }" :aria-current="sidebarActive('dashboards') ? 'page' : undefined" @click="navTo('dashboards')">
          All Dashboards
        </button>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('security-dashboard') }" :aria-current="sidebarActive('security-dashboard') ? 'page' : undefined" @click="navTo('security-dashboard')">
          Security Scan
        </button>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('pr-review-dashboard') }" :aria-current="sidebarActive('pr-review-dashboard') ? 'page' : undefined" @click="navTo('pr-review-dashboard')">
          PR Review
        </button>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('token-usage') }" :aria-current="sidebarActive('token-usage') ? 'page' : undefined" @click="navTo('token-usage')">
          Token Usage
        </button>
        <button type="button" class="submenu-item"
          :class="{ active: sidebarActive('rotation-dashboard') }"
          :aria-current="sidebarActive('rotation-dashboard') ? 'page' : undefined"
          @click="navTo('rotation-dashboard')">
          Scheduling
        </button>
        <button v-for="b in props.customTriggers" :key="b.id" type="button" class="submenu-item"
          :class="{ active: currentRouteName === 'trigger-dashboard' && route.params.triggerId === b.id }"
          :aria-current="(currentRouteName === 'trigger-dashboard' && route.params.triggerId === b.id) ? 'page' : undefined"
          @click="navToTriggerDashboard(b.id)">
          {{ b.name }}
        </button>
      </div>

      <div class="nav-section-label">Work</div>
      <button type="button" :class="{ active: sidebarActive('sketch-chat') }" :aria-current="sidebarActive('sketch-chat') ? 'page' : undefined" :title="isCollapsedDesktop() ? 'Sketch' : undefined" @click="navTo('sketch-chat')">
        <span class="nav-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
          </svg>
        </span>
        <span class="nav-text">Sketch</span>
        <span class="nav-indicator"></span>
      </button>

      <div class="nav-section-label">Organization</div>
      <!-- Products (expandable) -->
      <button type="button" class="nav-group-toggle" :class="{ active: isProductsSectionActive() }" :aria-expanded="expandedSections.products" :aria-current="isProductsSectionActive() ? 'page' : undefined" :title="isCollapsedDesktop() ? 'Products' : undefined" @click="toggleSection( 'products')">
        <span class="nav-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
            <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
            <line x1="12" y1="22.08" x2="12" y2="12"/>
          </svg>
        </span>
        <span class="nav-text">Products</span>
        <svg class="chevron-icon" :class="{ expanded: expandedSections.products }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="9,18 15,12 9,6"/>
        </svg>
        <span class="nav-indicator"></span>
      </button>
      <div v-show="expandedSections.products" class="nav-submenu" role="region" aria-label="Products">
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('products') }" :aria-current="sidebarActive('products') ? 'page' : undefined" @click="navTo('products')">
          All Products
        </button>
        <div v-for="product in props.products" :key="product.id" class="submenu-item-row">
          <button type="button" class="submenu-item"
            :class="{ active: (currentRouteName === 'product-dashboard' || currentRouteName === 'product-settings') && route.params.productId === product.id }"
            :aria-current="((currentRouteName === 'product-dashboard' || currentRouteName === 'product-settings') && route.params.productId === product.id) ? 'page' : undefined"
            @click="navToProductDashboard(product.id)">
            {{ product.name }}
          </button>
          <button type="button" class="submenu-settings-btn" title="Settings" @click="navToProductSettings(product.id)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <circle cx="12" cy="12" r="3"/>
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
            </svg>
          </button>
        </div>
      </div>
      <!-- Projects (expandable) -->
      <button type="button" class="nav-group-toggle" :class="{ active: isProjectsSectionActive() }" :aria-expanded="expandedSections.projects" :aria-current="isProjectsSectionActive() ? 'page' : undefined" :title="isCollapsedDesktop() ? 'Projects' : undefined" @click="toggleSection( 'projects')">
        <span class="nav-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
          </svg>
        </span>
        <span class="nav-text">Projects</span>
        <svg class="chevron-icon" :class="{ expanded: expandedSections.projects }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="9,18 15,12 9,6"/>
        </svg>
        <span class="nav-indicator"></span>
      </button>
      <div v-show="expandedSections.projects" class="nav-submenu" role="region" aria-label="Projects">
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('projects') }" :aria-current="sidebarActive('projects') ? 'page' : undefined" @click="navTo('projects')">
          All Projects
        </button>
        <div v-for="project in props.projects" :key="project.id" class="submenu-item-row">
          <button type="button" class="submenu-item"
            :class="{ active: (currentRouteName === 'project-dashboard' || currentRouteName === 'project-settings') && route.params.projectId === project.id }"
            :aria-current="((currentRouteName === 'project-dashboard' || currentRouteName === 'project-settings') && route.params.projectId === project.id) ? 'page' : undefined"
            @click="navToProjectDashboard(project.id)">
            {{ project.name }}
          </button>
          <button type="button" class="submenu-settings-btn" title="Settings" @click="navToProjectSettings(project.id)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <circle cx="12" cy="12" r="3"/>
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
            </svg>
          </button>
        </div>
      </div>
      <!-- Teams (expandable) -->
      <button type="button" class="nav-group-toggle" :class="{ active: isTeamsSectionActive() }" :aria-expanded="expandedSections.teams" :aria-current="isTeamsSectionActive() ? 'page' : undefined" :title="isCollapsedDesktop() ? 'Teams' : undefined" @click="toggleSection( 'teams')">
        <span class="nav-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
            <circle cx="9" cy="7" r="4"/>
            <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
            <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
          </svg>
        </span>
        <span class="nav-text">Teams</span>
        <svg class="chevron-icon" :class="{ expanded: expandedSections.teams }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="9,18 15,12 9,6"/>
        </svg>
        <span class="nav-indicator"></span>
      </button>
      <div v-show="expandedSections.teams" class="nav-submenu" role="region" aria-label="Teams">
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('teams') }" :aria-current="sidebarActive('teams') ? 'page' : undefined" @click="navTo('teams')">
          All Teams
        </button>
        <div v-for="team in props.teams" :key="team.id" class="submenu-item-row">
          <button type="button" class="submenu-item"
            :class="{ active: (currentRouteName === 'team-dashboard' || currentRouteName === 'team-settings' || currentRouteName === 'team-builder') && route.params.teamId === team.id }"
            :aria-current="((currentRouteName === 'team-dashboard' || currentRouteName === 'team-settings' || currentRouteName === 'team-builder') && route.params.teamId === team.id) ? 'page' : undefined"
            @click="navToTeamDashboard(team.id)">
            {{ team.name }}
          </button>
          <button type="button" class="submenu-settings-btn" title="Settings" @click="navToTeamSettings(team.id)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <circle cx="12" cy="12" r="3"/>
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
            </svg>
          </button>
        </div>
      </div>
      <!-- Agents (expandable) -->
      <button type="button" class="nav-group-toggle" :class="{ active: isAgentsSectionActive() }" :aria-expanded="expandedSections.agents" :aria-current="isAgentsSectionActive() ? 'page' : undefined" :title="isCollapsedDesktop() ? 'Agents' : undefined" @click="toggleSection( 'agents')">
        <span class="nav-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="12" cy="8" r="4"/>
            <path d="M6 21v-2a4 4 0 014-4h4a4 4 0 014 4v2"/>
            <circle cx="12" cy="8" r="2" fill="currentColor"/>
            <path d="M17 3l2 2-2 2M7 3l-2 2 2 2"/>
          </svg>
        </span>
        <span class="nav-text">Agents</span>
        <svg class="chevron-icon" :class="{ expanded: expandedSections.agents }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M9 18l6-6-6-6"/>
        </svg>
        <span class="nav-indicator"></span>
      </button>
      <div v-show="expandedSections.agents" class="nav-submenu" role="region" aria-label="Agents">
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('agents') }" :aria-current="sidebarActive('agents') ? 'page' : undefined" @click="navTo('agents')">
          All Agents
        </button>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('agent-create') }" :aria-current="sidebarActive('agent-create') ? 'page' : undefined" @click="navToAgentCreate()">
          Design an Agent
        </button>
      </div>

      <!-- SuperAgents (expandable) -->
      <button type="button" class="nav-group-toggle" :class="{ active: isSuperAgentsSectionActive() }" :aria-expanded="expandedSections.superAgents" :aria-current="isSuperAgentsSectionActive() ? 'page' : undefined" :title="isCollapsedDesktop() ? 'SuperAgents' : undefined" @click="toggleSection( 'superAgents')">
        <span class="nav-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M12 2L4 6.5v5c0 5.5 3.4 10.3 8 11.5 4.6-1.2 8-6 8-11.5v-5L12 2z"/>
            <path d="M14.5 8.5c-1-.6-2.5-.4-3.2.4-.5.6-.2 1.2.4 1.6l1.6 1c.6.4.7 1.1.1 1.7-.8.8-2.2.6-3-.2" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </span>
        <span class="nav-text">SuperAgents</span>
        <svg class="chevron-icon" :class="{ expanded: expandedSections.superAgents }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M9 18l6-6-6-6"/>
        </svg>
        <span class="nav-indicator"></span>
      </button>
      <div v-show="expandedSections.superAgents" class="nav-submenu" role="region" aria-label="SuperAgents">
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('super-agents') }" :aria-current="sidebarActive('super-agents') ? 'page' : undefined" @click="navTo('super-agents')">
          All SuperAgents
        </button>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('explore-super-agents') }" :aria-current="sidebarActive('explore-super-agents') ? 'page' : undefined" @click="navTo('explore-super-agents')">
          Explore
        </button>
      </div>

      <div class="nav-section-label">Forge</div>

      <!-- Workflows (expandable) -->
      <button type="button" class="nav-group-toggle" :class="{ active: isWorkflowsSectionActive() }" :aria-expanded="expandedSections.workflows" :aria-current="isWorkflowsSectionActive() ? 'page' : undefined" :title="isCollapsedDesktop() ? 'Workflows' : undefined" @click="toggleSection( 'workflows')">
        <span class="nav-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <rect x="8" y="2" width="8" height="5" rx="1"/>
            <rect x="8" y="10" width="8" height="5" rx="1"/>
            <rect x="8" y="18" width="8" height="5" rx="1"/>
            <line x1="12" y1="7" x2="12" y2="10"/>
            <line x1="12" y1="15" x2="12" y2="18"/>
          </svg>
        </span>
        <span class="nav-text">Workflows</span>
        <svg class="chevron-icon" :class="{ expanded: expandedSections.workflows }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M9 18l6-6-6-6"/>
        </svg>
        <span class="nav-indicator"></span>
      </button>
      <div v-show="expandedSections.workflows" class="nav-submenu" role="region" aria-label="Workflows">
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('workflows') }" :aria-current="sidebarActive('workflows') ? 'page' : undefined" @click="navTo('workflows')">
          All Workflows
        </button>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('workflow-playground') }" :aria-current="sidebarActive('workflow-playground') ? 'page' : undefined" @click="navTo('workflow-playground')">
          Playground
        </button>
      </div>

      <!-- Plugins (expandable) -->
      <button type="button" class="nav-group-toggle" :class="{ active: isPluginsSectionActive() }" :aria-expanded="expandedSections.plugins" :aria-current="isPluginsSectionActive() ? 'page' : undefined" :title="isCollapsedDesktop() ? 'Plugins' : undefined" @click="toggleSection( 'plugins')">
        <span class="nav-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
          </svg>
        </span>
        <span class="nav-text">Plugins</span>
        <svg class="chevron-icon" :class="{ expanded: expandedSections.plugins }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="9,18 15,12 9,6"/>
        </svg>
        <span class="nav-indicator"></span>
      </button>
      <div v-show="expandedSections.plugins" class="nav-submenu" role="region" aria-label="Plugins">
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('plugins') }" :aria-current="sidebarActive('plugins') ? 'page' : undefined" @click="navTo('plugins')">
          All Plugins
        </button>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('plugin-design') }" :aria-current="sidebarActive('plugin-design') ? 'page' : undefined" @click="navTo('plugin-design')">
          Design a Plugin
        </button>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('explore-plugins') }" :aria-current="sidebarActive('explore-plugins') ? 'page' : undefined" @click="navTo('explore-plugins')">
          Explore
        </button>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('harness-integration') }" :aria-current="sidebarActive('harness-integration') ? 'page' : undefined" @click="navTo('harness-integration')">
          Harness Integration
        </button>
        <button v-for="plugin in props.plugins" :key="plugin.id" type="button" class="submenu-item"
          :class="{ active: currentRouteName === 'plugin-detail' && route.params.pluginId === plugin.id }"
          :aria-current="(currentRouteName === 'plugin-detail' && route.params.pluginId === plugin.id) ? 'page' : undefined"
          @click="navToPluginDetail(plugin.id)">
          {{ plugin.name }}
        </button>
      </div>

      <!-- MCP Servers (expandable) -->
      <button type="button" class="nav-group-toggle" :class="{ active: isMcpServersSectionActive() }" :aria-expanded="expandedSections.mcpServers" :aria-current="isMcpServersSectionActive() ? 'page' : undefined" :title="isCollapsedDesktop() ? 'MCP Servers' : undefined" @click="toggleSection( 'mcpServers')">
        <span class="nav-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <rect x="2" y="2" width="20" height="8" rx="2"/>
            <rect x="2" y="14" width="20" height="8" rx="2"/>
            <circle cx="6" cy="6" r="1" fill="currentColor"/>
            <circle cx="6" cy="18" r="1" fill="currentColor"/>
          </svg>
        </span>
        <span class="nav-text">MCP Servers</span>
        <svg class="chevron-icon" :class="{ expanded: expandedSections.mcpServers }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="9,18 15,12 9,6"/>
        </svg>
        <span class="nav-indicator"></span>
      </button>
      <div v-show="expandedSections.mcpServers" class="nav-submenu" role="region" aria-label="MCP Servers">
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('mcp-servers') }" :aria-current="sidebarActive('mcp-servers') ? 'page' : undefined" @click="navTo('mcp-servers')">
          All MCP Servers
        </button>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('explore-mcp-servers') }" :aria-current="sidebarActive('explore-mcp-servers') ? 'page' : undefined" @click="navTo('explore-mcp-servers')">
          Explore
        </button>
      </div>

      <!-- Skills (expandable) -->
      <button type="button" class="nav-group-toggle" :class="{ active: isSkillsSectionActive() }" :aria-expanded="expandedSections.skills" :aria-current="isSkillsSectionActive() ? 'page' : undefined" :title="isCollapsedDesktop() ? 'Skills' : undefined" @click="toggleSection( 'skills')">
        <span class="nav-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M12 2L2 7l10 5 10-5-10-5z"/>
            <path d="M2 17l10 5 10-5"/>
            <path d="M2 12l10 5 10-5"/>
          </svg>
        </span>
        <span class="nav-text">Skills</span>
        <svg class="chevron-icon" :class="{ expanded: expandedSections.skills }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="9,18 15,12 9,6"/>
        </svg>
        <span class="nav-indicator"></span>
      </button>
      <div v-show="expandedSections.skills" class="nav-submenu" role="region" aria-label="Skills">
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('skills-playground') }" :aria-current="sidebarActive('skills-playground') ? 'page' : undefined" @click="navTo('skills-playground')">
          Playground
        </button>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('skill-create') }" :aria-current="sidebarActive('skill-create') ? 'page' : undefined" @click="navTo('skill-create')">
          Design a Skill
        </button>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('my-skills') }" :aria-current="sidebarActive('my-skills') ? 'page' : undefined" @click="navTo('my-skills')">
          Skill Library
        </button>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('explore-skills') }" :aria-current="sidebarActive('explore-skills') ? 'page' : undefined" @click="navTo('explore-skills')">
          Explore
        </button>
      </div>

      <!-- Commands (expandable) -->
      <button type="button" class="nav-group-toggle" :class="{ active: isCommandsSectionActive() }" :aria-expanded="expandedSections.commands" :aria-current="isCommandsSectionActive() ? 'page' : undefined" :title="isCollapsedDesktop() ? 'Commands' : undefined" @click="toggleSection( 'commands')">
        <span class="nav-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <polyline points="4 17 10 11 4 5"/>
            <line x1="12" y1="19" x2="20" y2="19"/>
          </svg>
        </span>
        <span class="nav-text">Commands</span>
        <svg class="chevron-icon" :class="{ expanded: expandedSections.commands }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M9 18l6-6-6-6"/>
        </svg>
        <span class="nav-indicator"></span>
      </button>
      <div v-show="expandedSections.commands" class="nav-submenu" role="region" aria-label="Commands">
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('commands') }" :aria-current="sidebarActive('commands') ? 'page' : undefined" @click="navTo('commands')">
          All Commands
        </button>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('command-design') }" :aria-current="sidebarActive('command-design') ? 'page' : undefined" @click="navTo('command-design')">
          Design a Command
        </button>
      </div>

      <!-- Hooks (expandable) -->
      <button type="button" class="nav-group-toggle" :class="{ active: isHooksSectionActive() }" :aria-expanded="expandedSections.hooks" :aria-current="isHooksSectionActive() ? 'page' : undefined" :title="isCollapsedDesktop() ? 'Hooks' : undefined" @click="toggleSection( 'hooks')">
        <span class="nav-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
            <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
          </svg>
        </span>
        <span class="nav-text">Hooks</span>
        <svg class="chevron-icon" :class="{ expanded: expandedSections.hooks }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M9 18l6-6-6-6"/>
        </svg>
        <span class="nav-indicator"></span>
      </button>
      <div v-show="expandedSections.hooks" class="nav-submenu" role="region" aria-label="Hooks">
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('hooks') }" :aria-current="sidebarActive('hooks') ? 'page' : undefined" @click="navTo('hooks')">
          All Hooks
        </button>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('hook-design') }" :aria-current="sidebarActive('hook-design') ? 'page' : undefined" @click="navTo('hook-design')">
          Design a Hook
        </button>
      </div>

      <!-- Rules (expandable) -->
      <button type="button" class="nav-group-toggle" :class="{ active: isRulesSectionActive() }" :aria-expanded="expandedSections.rules" :aria-current="isRulesSectionActive() ? 'page' : undefined" :title="isCollapsedDesktop() ? 'Rules' : undefined" @click="toggleSection( 'rules')">
        <span class="nav-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M12 2L2 7l10 5 10-5-10-5z"/>
            <path d="M2 17l10 5 10-5"/>
            <path d="M2 12l10 5 10-5"/>
            <circle cx="12" cy="12" r="3"/>
          </svg>
        </span>
        <span class="nav-text">Rules</span>
        <svg class="chevron-icon" :class="{ expanded: expandedSections.rules }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M9 18l6-6-6-6"/>
        </svg>
        <span class="nav-indicator"></span>
      </button>
      <div v-show="expandedSections.rules" class="nav-submenu" role="region" aria-label="Rules">
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('rules') }" :aria-current="sidebarActive('rules') ? 'page' : undefined" @click="navTo('rules')">
          All Rules
        </button>
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('rule-design') }" :aria-current="sidebarActive('rule-design') ? 'page' : undefined" @click="navTo('rule-design')">
          Design a Rule
        </button>
      </div>

      <!-- Triggers (flat link) -->
      <button type="button" :class="{ active: sidebarActive('triggers') }" :aria-current="sidebarActive('triggers') ? 'page' : undefined" :title="isCollapsedDesktop() ? 'Triggers' : undefined" @click="navTo('triggers')">
        <span class="nav-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
          </svg>
        </span>
        <span class="nav-text">Triggers</span>
        <span class="nav-indicator"></span>
      </button>

      <div class="nav-section-label">History</div>
      <!-- Triggers History (expandable) -->
      <button type="button" class="nav-group-toggle" :class="{ active: isHistorySectionActive() }" :aria-expanded="expandedSections.history" :aria-current="isHistorySectionActive() ? 'page' : undefined" :title="isCollapsedDesktop() ? 'Triggers' : undefined" @click="toggleSection( 'history')">
        <span class="nav-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="12" cy="12" r="10"/>
            <polyline points="12,6 12,12 16,14"/>
          </svg>
        </span>
        <span class="nav-text">Triggers</span>
        <svg class="chevron-icon" :class="{ expanded: expandedSections.history }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="9,18 15,12 9,6"/>
        </svg>
        <span class="nav-indicator"></span>
      </button>
      <div v-show="expandedSections.history" class="nav-submenu" role="region" aria-label="Trigger History">
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('security-history') }" :aria-current="sidebarActive('security-history') ? 'page' : undefined" @click="navToSecurityHistory()">
          Security Scan
        </button>
        <button v-for="b in props.customTriggers" :key="b.id" type="button" class="submenu-item"
          :class="{ active: currentRouteName === 'trigger-history' && route.params.triggerId === b.id }"
          :aria-current="(currentRouteName === 'trigger-history' && route.params.triggerId === b.id) ? 'page' : undefined"
          @click="navToTriggerHistory(b.id)">
          {{ b.name }}
        </button>
      </div>

      <!-- Usage History (expandable) -->
      <button type="button" class="nav-group-toggle" :class="{ active: currentRouteName === 'usage-history' }" :aria-expanded="expandedSections.usage" :aria-current="sidebarActive('usage-history') ? 'page' : undefined" :title="isCollapsedDesktop() ? 'Usage' : undefined" @click="toggleSection( 'usage')">
        <span class="nav-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <rect x="3" y="12" width="4" height="9" rx="1"/>
            <rect x="10" y="6" width="4" height="15" rx="1"/>
            <rect x="17" y="3" width="4" height="18" rx="1"/>
          </svg>
        </span>
        <span class="nav-text">Usage</span>
        <svg class="chevron-icon" :class="{ expanded: expandedSections.usage }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="9,18 15,12 9,6"/>
        </svg>
        <span class="nav-indicator"></span>
      </button>
      <div v-show="expandedSections.usage" class="nav-submenu" role="region" aria-label="Usage">
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('usage-history') }" :aria-current="sidebarActive('usage-history') ? 'page' : undefined" @click="navTo('usage-history')">
          Token Usage
        </button>
      </div>

      <div class="nav-section-label">Resources</div>
      <a href="/docs" target="_blank" class="external-link">
        <span class="nav-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
            <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/>
          </svg>
        </span>
        <span class="nav-text">API Docs</span>
        <svg class="external-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3"/>
        </svg>
      </a>

      <div class="nav-section-label">System</div>
      <!-- AI Backends (expandable) -->
      <button type="button" class="nav-group-toggle" :class="{ active: currentRouteName === 'ai-backends' || currentRouteName === 'backend-detail' }" :aria-expanded="expandedSections.aiBackends" :aria-current="(currentRouteName === 'ai-backends' || currentRouteName === 'backend-detail') ? 'page' : undefined" :title="isCollapsedDesktop() ? 'AI Backends' : undefined" @click="toggleSection( 'aiBackends')">
        <span class="nav-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="12" cy="12" r="3"/>
            <path d="M12 2v4m0 12v4M2 12h4m12 0h4"/>
            <path d="M4.93 4.93l2.83 2.83m8.48 8.48l2.83 2.83M4.93 19.07l2.83-2.83m8.48-8.48l2.83-2.83"/>
          </svg>
        </span>
        <span class="nav-text">AI Backends</span>
        <svg class="chevron-icon" :class="{ expanded: expandedSections.aiBackends }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="9,18 15,12 9,6"/>
        </svg>
        <span class="nav-indicator"></span>
      </button>
      <div v-show="expandedSections.aiBackends" class="nav-submenu" role="region" aria-label="AI Backends">
        <button type="button" class="submenu-item" :class="{ active: sidebarActive('ai-backends') }" :aria-current="sidebarActive('ai-backends') ? 'page' : undefined" @click="navTo('ai-backends')">
          All Backends
        </button>
        <button v-for="b in props.sidebarBackends" :key="b.id" type="button" class="submenu-item"
          :class="{ active: currentRouteName === 'backend-detail' && route.params.backendId === b.id }"
          :aria-current="(currentRouteName === 'backend-detail' && route.params.backendId === b.id) ? 'page' : undefined"
          @click="navToBackendDetail(b.id)">
          {{ b.name }}
        </button>
      </div>
      <!-- Settings (flat link) -->
      <button type="button" :class="{ active: sidebarActive('settings') }" :aria-current="sidebarActive('settings') ? 'page' : undefined" :title="isCollapsedDesktop() ? 'Settings' : undefined" @click="navTo('settings')">
        <span class="nav-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="12" cy="12" r="3"/>
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
          </svg>
        </span>
        <span class="nav-text">Settings</span>
        <span class="nav-indicator"></span>
      </button>
    </div>
  </nav>
</template>
