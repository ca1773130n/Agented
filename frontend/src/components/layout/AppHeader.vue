<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue';
import { useRoute, useRouter, type RouteLocationRaw } from 'vue-router';
import { productApi, projectApi, teamApi, agentApi } from '../../services/api';
import { useToast } from '../../composables/useToast';
import CommandPalette from './CommandPalette.vue';

const emit = defineEmits<{
  toggleSidebar: [];
}>();

const route = useRoute();
const router = useRouter();
const showToast = useToast();

// --- Dropdowns ---
const showProfileDropdown = ref(false);
const showNotificationDropdown = ref(false);
const showCommandPalette = ref(false);

const profileDropdownRef = ref<HTMLElement | null>(null);
const notificationDropdownRef = ref<HTMLElement | null>(null);

function toggleProfileDropdown() {
  showProfileDropdown.value = !showProfileDropdown.value;
  showNotificationDropdown.value = false;
}

function toggleNotificationDropdown() {
  showNotificationDropdown.value = !showNotificationDropdown.value;
  showProfileDropdown.value = false;
}

function handleClickOutside(e: MouseEvent) {
  const target = e.target as Node;
  if (profileDropdownRef.value && !profileDropdownRef.value.contains(target)) {
    showProfileDropdown.value = false;
  }
  if (notificationDropdownRef.value && !notificationDropdownRef.value.contains(target)) {
    showNotificationDropdown.value = false;
  }
}

function navigateToSettings() {
  router.push({ name: 'settings' });
  showProfileDropdown.value = false;
}

function handleSignOut() {
  // No-op
  showProfileDropdown.value = false;
}

// --- Command Palette keyboard shortcut ---
function handleKeydown(e: KeyboardEvent) {
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
    e.preventDefault();
    showCommandPalette.value = !showCommandPalette.value;
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside);
  document.addEventListener('keydown', handleKeydown);
});

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside);
  document.removeEventListener('keydown', handleKeydown);
});

// --- Theme toggle ---
function handleThemeToggle() {
  showToast('Light theme coming soon', 'info');
}

// --- Entity name resolution ---
const entityNameCache = ref(new Map<string, string>());

async function resolveEntityName(entityType: string, entityId: string): Promise<void> {
  const cacheKey = `${entityType}:${entityId}`;
  if (entityNameCache.value.has(cacheKey)) return;

  try {
    let name = entityId;
    if (entityType === 'productId') {
      const product = await productApi.get(entityId);
      name = product.name;
    } else if (entityType === 'projectId') {
      const project = await projectApi.get(entityId);
      name = project.name;
    } else if (entityType === 'teamId') {
      const team = await teamApi.get(entityId);
      name = team.name;
    } else if (entityType === 'agentId') {
      const agent = await agentApi.get(entityId);
      name = agent.name;
    }
    entityNameCache.value.set(cacheKey, name);
  } catch {
    entityNameCache.value.set(cacheKey, entityId);
  }
}

// Watch route params and resolve entity names
watch(
  () => route.params,
  (params) => {
    const knownParams = ['productId', 'projectId', 'teamId', 'agentId'] as const;
    for (const paramName of knownParams) {
      const paramValue = params[paramName];
      if (paramValue && typeof paramValue === 'string') {
        resolveEntityName(paramName, paramValue);
      }
    }
  },
  { immediate: true }
);

function getEntityDisplayName(entityType: string, entityId: string): string {
  const cacheKey = `${entityType}:${entityId}`;
  return entityNameCache.value.get(cacheKey) || entityId;
}

// --- Breadcrumb ---
interface BreadcrumbSegment {
  label: string;
  to?: RouteLocationRaw;
}

const navigationTargets: Record<string, RouteLocationRaw | null> = {
  'Home': { name: 'dashboards' },
  'Organization': null,
  'Dashboards': { name: 'dashboards' },
  'Products': { name: 'products' },
  'Projects': { name: 'projects' },
  'Teams': { name: 'teams' },
  'Agents': { name: 'agents' },
  'Super Agents': { name: 'super-agents' },
  'Workflows': { name: 'workflows' },
  'Skills': { name: 'my-skills' },
  'Plugins': { name: 'plugins' },
  'MCP Servers': { name: 'mcp-servers' },
  'Triggers': { name: 'triggers' },
  'System': null,
};

function makeSegment(label: string, isLast: boolean): BreadcrumbSegment {
  if (isLast) return { label };
  const target = navigationTargets[label];
  if (target === null) return { label };
  if (target !== undefined) return { label, to: target };
  return { label };
}

function resolveParamSegment(paramName: string): string {
  const paramValue = route.params[paramName];
  if (!paramValue || typeof paramValue !== 'string') return paramName;
  return getEntityDisplayName(paramName, paramValue);
}

const breadcrumbMap: Record<string, () => string[]> = {
  'dashboards': () => ['Home'],
  'security-dashboard': () => ['Home', 'Dashboards', 'Security'],
  'pr-review-dashboard': () => ['Home', 'Dashboards', 'PR Review'],
  'products-summary': () => ['Home', 'Dashboards', 'Products Summary'],
  'projects-summary': () => ['Home', 'Dashboards', 'Projects Summary'],
  'teams-summary': () => ['Home', 'Dashboards', 'Teams Summary'],
  'agents-summary': () => ['Home', 'Dashboards', 'Agents Summary'],
  'rotation-dashboard': () => ['Home', 'Dashboards', 'Rotation'],
  'analytics-dashboard': () => ['Home', 'Dashboards', 'Analytics'],
  'health-dashboard': () => ['Home', 'Dashboards', 'Health'],
  'team-impact-report': () => ['Home', 'Dashboards', 'Team Impact'],
  'cross-team-insights': () => ['Home', 'Dashboards', 'Cross-Team Insights'],
  'execution-queue-dashboard': () => ['Home', 'Dashboards', 'Execution Queue'],
  'execution-anomaly-detection': () => ['Home', 'Dashboards', 'Anomaly Detection'],
  'team-leaderboard': () => ['Home', 'Dashboards', 'Leaderboard'],
  'trigger-dashboard': () => ['Home', 'Triggers', route.params.triggerId as string || 'Trigger'],
  'trigger-history': () => ['Home', 'Triggers', 'History'],
  'products': () => ['Home', 'Organization', 'Products'],
  'product-dashboard': () => ['Home', 'Organization', 'Products', resolveParamSegment('productId')],
  'product-settings': () => ['Home', 'Organization', 'Products', resolveParamSegment('productId'), 'Settings'],
  'projects': () => ['Home', 'Organization', 'Projects'],
  'project-dashboard': () => ['Home', 'Organization', 'Projects', resolveParamSegment('projectId')],
  'project-settings': () => ['Home', 'Organization', 'Projects', resolveParamSegment('projectId'), 'Settings'],
  'project-management': () => ['Home', 'Organization', 'Projects', resolveParamSegment('projectId'), 'Management'],
  'project-planning': () => ['Home', 'Organization', 'Projects', resolveParamSegment('projectId'), 'Planning'],
  'teams': () => ['Home', 'Organization', 'Teams'],
  'team-dashboard': () => ['Home', 'Organization', 'Teams', resolveParamSegment('teamId')],
  'team-settings': () => ['Home', 'Organization', 'Teams', resolveParamSegment('teamId'), 'Settings'],
  'team-builder': () => ['Home', 'Organization', 'Teams', resolveParamSegment('teamId'), 'Builder'],
  'agents': () => ['Home', 'Organization', 'Agents'],
  'agent-create': () => ['Home', 'Organization', 'Agents', 'Create'],
  'agent-design': () => ['Home', 'Organization', 'Agents', resolveParamSegment('agentId')],
  'super-agents': () => ['Home', 'Super Agents'],
  'explore-super-agents': () => ['Home', 'Super Agents', 'Explore'],
  'super-agent-playground': () => ['Home', 'Super Agents', 'Playground'],
  'workflows': () => ['Home', 'Workflows'],
  'workflow-playground': () => ['Home', 'Workflows', 'Playground'],
  'workflow-builder': () => ['Home', 'Workflows', 'Builder'],
  'my-skills': () => ['Home', 'Skills'],
  'skill-create': () => ['Home', 'Skills', 'Create'],
  'skills-playground': () => ['Home', 'Skills', 'Playground'],
  'explore-skills': () => ['Home', 'Skills', 'Explore'],
  'skill-detail': () => ['Home', 'Skills', route.params.skillId as string || 'Skill'],
  'plugins': () => ['Home', 'Plugins'],
  'plugin-design': () => ['Home', 'Plugins', 'Design'],
  'explore-plugins': () => ['Home', 'Plugins', 'Explore'],
  'plugin-detail': () => ['Home', 'Plugins', route.params.pluginId as string || 'Plugin'],
  'harness-integration': () => ['Home', 'Plugins', 'Harness'],
  'mcp-servers': () => ['Home', 'MCP Servers'],
  'explore-mcp-servers': () => ['Home', 'MCP Servers', 'Explore'],
  'mcp-server-detail': () => ['Home', 'MCP Servers', route.params.mcpServerId as string || 'Server'],
  'triggers': () => ['Home', 'System', 'Triggers'],
  'security-history': () => ['Home', 'System', 'Security History'],
  'audit-detail': () => ['Home', 'System', 'Audit', route.params.auditId as string || 'Audit'],
  'execution-history': () => ['Home', 'System', 'Execution History'],
  'usage-history': () => ['Home', 'System', 'Usage History'],
  'settings': () => ['Home', 'System', 'Settings'],
  'sso-settings': () => ['Home', 'System', 'Settings', 'SSO'],
  'execution-search': () => ['Home', 'System', 'Execution Search'],
  'sketch-chat': () => ['Home', 'Sketch'],
  'ai-backends': () => ['Home', 'System', 'AI Backends'],
  'service-health': () => ['Home', 'System', 'Service Health'],
  'backend-detail': () => ['Home', 'System', 'AI Backends', route.params.backendId as string || 'Backend'],
};

function titleCase(str: string): string {
  return str.charAt(0).toUpperCase() + str.slice(1);
}

const breadcrumbLabels = computed<string[]>(() => {
  const routeName = route.name as string | undefined;
  if (!routeName) return ['Home'];

  const mapFn = breadcrumbMap[routeName];
  if (mapFn) return mapFn();

  // Fallback: split route name on '-', title-case each word, prepend Home
  const parts = routeName.split('-').map(titleCase);
  return ['Home', ...parts];
});

const breadcrumbSegments = computed<BreadcrumbSegment[]>(() => {
  const labels = breadcrumbLabels.value;
  return labels.map((label, i) => makeSegment(label, i === labels.length - 1));
});

// Desktop overflow: collapse middle if > 4 segments
const desktopSegments = computed<BreadcrumbSegment[]>(() => {
  const segs = breadcrumbSegments.value;
  if (segs.length <= 4) return segs;
  const first = segs[0];
  const collapsed: BreadcrumbSegment = { label: '\u2026' };
  const lastTwo = segs.slice(-2);
  return [first, collapsed, ...lastTwo];
});

const fullBreadcrumbTitle = computed(() => {
  return breadcrumbLabels.value.join(' / ');
});

// Mobile: only last 2 segments
const mobileSegments = computed<BreadcrumbSegment[]>(() => {
  const segs = breadcrumbSegments.value;
  if (segs.length <= 2) return segs;
  return segs.slice(-2);
});
</script>

<template>
  <header class="app-header">
    <!-- Mobile hamburger -->
    <button class="header-hamburger" @click="emit('toggleSidebar')" aria-label="Toggle sidebar">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="3" y1="6" x2="21" y2="6" />
        <line x1="3" y1="12" x2="21" y2="12" />
        <line x1="3" y1="18" x2="21" y2="18" />
      </svg>
    </button>

    <!-- Logo -->
    <div class="header-logo">
      <div class="header-logo-mark">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
        </svg>
      </div>
      <span class="header-logo-text">Agented</span>
    </div>

    <!-- Separator -->
    <div class="header-separator" />

    <!-- Breadcrumb (desktop) -->
    <nav class="header-breadcrumb breadcrumb-desktop" :title="fullBreadcrumbTitle">
      <template v-for="(seg, i) in desktopSegments" :key="i">
        <span v-if="i > 0" class="breadcrumb-sep">/</span>
        <template v-if="i === desktopSegments.length - 1">
          <span class="breadcrumb-current">{{ seg.label }}</span>
        </template>
        <template v-else-if="seg.to">
          <router-link :to="seg.to">{{ seg.label }}</router-link>
        </template>
        <template v-else>
          <span class="breadcrumb-label">{{ seg.label }}</span>
        </template>
      </template>
    </nav>

    <!-- Breadcrumb (mobile) -->
    <nav class="header-breadcrumb breadcrumb-mobile">
      <template v-for="(seg, i) in mobileSegments" :key="i">
        <span v-if="i > 0" class="breadcrumb-sep">/</span>
        <template v-if="i === mobileSegments.length - 1">
          <span class="breadcrumb-current">{{ seg.label }}</span>
        </template>
        <template v-else-if="seg.to">
          <router-link :to="seg.to">{{ seg.label }}</router-link>
        </template>
        <template v-else>
          <span class="breadcrumb-label">{{ seg.label }}</span>
        </template>
      </template>
    </nav>

    <!-- Spacer -->
    <div class="header-spacer" />

    <!-- Action icons -->
    <div class="header-actions">
      <!-- Search -->
      <button class="header-action-btn" @click="showCommandPalette = true" aria-label="Search" title="Search (Cmd+K)">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="11" cy="11" r="8" />
          <path d="m21 21-4.35-4.35" />
        </svg>
      </button>

      <!-- Theme toggle -->
      <button class="header-action-btn" @click="handleThemeToggle" aria-label="Toggle theme" title="Toggle theme">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
        </svg>
      </button>

      <!-- Notification bell -->
      <div ref="notificationDropdownRef" style="position: relative;">
        <button class="header-action-btn" @click.stop="toggleNotificationDropdown" aria-label="Notifications" title="Notifications">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
            <path d="M13.73 21a2 2 0 0 1-3.46 0" />
          </svg>
        </button>
        <div v-show="showNotificationDropdown" class="header-dropdown">
          <div class="notification-empty">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
              <path d="M13.73 21a2 2 0 0 1-3.46 0" />
            </svg>
            <p>No notifications</p>
            <p class="subtitle">You're all caught up</p>
          </div>
        </div>
      </div>

      <!-- Profile avatar -->
      <div ref="profileDropdownRef" style="position: relative;">
        <div class="profile-avatar" @click.stop="toggleProfileDropdown" role="button" tabindex="0" aria-label="Profile menu">
          U
        </div>
        <div v-show="showProfileDropdown" class="header-dropdown">
          <div class="dropdown-label">User</div>
          <div class="dropdown-divider" />
          <button class="dropdown-item" @click="navigateToSettings">Settings</button>
          <button class="dropdown-item" @click="handleSignOut">Sign Out</button>
        </div>
      </div>
    </div>

    <!-- Command Palette -->
    <CommandPalette v-model:open="showCommandPalette" />
  </header>
</template>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  height: 48px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-subtle);
  padding: 0 16px;
  position: sticky;
  top: 0;
  z-index: 1001;
  gap: 12px;
}

/* Logo */
.header-logo {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.header-logo-mark {
  width: 28px;
  height: 28px;
  background: linear-gradient(135deg, var(--accent-cyan) 0%, var(--accent-violet) 100%);
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.header-logo-mark svg {
  width: 16px;
  height: 16px;
  color: var(--bg-primary);
}

.header-logo-text {
  font-family: var(--font-mono);
  font-size: 1rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: var(--text-primary);
}

/* Separator */
.header-separator {
  width: 1px;
  height: 20px;
  background: var(--border-subtle);
  flex-shrink: 0;
}

/* Breadcrumb */
.header-breadcrumb {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.85rem;
  min-width: 0;
  overflow: hidden;
}

.header-breadcrumb a {
  color: var(--text-tertiary);
  text-decoration: none;
  transition: color var(--transition-fast);
  white-space: nowrap;
}

.header-breadcrumb a:hover {
  color: var(--accent-cyan);
}

.header-breadcrumb .breadcrumb-current {
  color: var(--text-secondary);
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.header-breadcrumb .breadcrumb-sep {
  color: var(--text-muted);
  flex-shrink: 0;
}

.header-breadcrumb .breadcrumb-label {
  color: var(--text-muted);
  white-space: nowrap;
}

/* Spacer */
.header-spacer {
  flex: 1;
}

/* Action icons */
.header-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.header-action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background: transparent;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  color: var(--text-secondary);
  transition: all var(--transition-fast);
  position: relative;
}

.header-action-btn:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.header-action-btn svg {
  width: 18px;
  height: 18px;
}

/* Profile avatar */
.profile-avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--accent-violet);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity var(--transition-fast);
}

.profile-avatar:hover {
  opacity: 0.85;
}

/* Dropdowns */
.header-dropdown {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  min-width: 200px;
  background: var(--bg-elevated);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  z-index: 1002;
  overflow: hidden;
}

.dropdown-item {
  display: block;
  width: 100%;
  padding: 10px 16px;
  background: none;
  border: none;
  color: var(--text-secondary);
  font-size: 0.875rem;
  text-align: left;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.dropdown-item:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.dropdown-divider {
  height: 1px;
  background: var(--border-subtle);
  margin: 4px 0;
}

.dropdown-label {
  padding: 10px 16px;
  color: var(--text-primary);
  font-size: 0.875rem;
  font-weight: 500;
}

/* Notification empty state */
.notification-empty {
  padding: 24px 16px;
  text-align: center;
}

.notification-empty svg {
  width: 24px;
  height: 24px;
  color: var(--text-muted);
  margin-bottom: 8px;
}

.notification-empty p {
  color: var(--text-secondary);
  font-size: 0.875rem;
  margin: 0;
}

.notification-empty .subtitle {
  color: var(--text-tertiary);
  font-size: 0.8rem;
  margin-top: 4px;
}

/* Mobile hamburger in header */
.header-hamburger {
  display: none;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background: transparent;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  color: var(--text-secondary);
}

.header-hamburger svg {
  width: 20px;
  height: 20px;
}

/* Mobile responsive */
@media (max-width: 768px) {
  .header-hamburger {
    display: flex;
  }

  .header-logo-text {
    display: none;
  }

  .header-separator {
    display: none;
  }

  /* Show only last 2 breadcrumb segments on mobile */
  .breadcrumb-desktop {
    display: none;
  }
}

@media (min-width: 769px) {
  .breadcrumb-mobile {
    display: none;
  }
}
</style>
