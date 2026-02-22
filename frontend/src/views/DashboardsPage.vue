<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import type { Trigger } from '../services/api';
import { triggerApi, productApi, projectApi, teamApi, agentApi, ApiError } from '../services/api';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import LoadingState from '../components/base/LoadingState.vue';
import EmptyState from '../components/base/EmptyState.vue';
import { useToast } from '../composables/useToast';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const router = useRouter();
const showToast = useToast();
const triggers = ref<Trigger[]>([]);
const isLoading = ref(true);

interface TriggerDashConfig {
  icon: string;
  gradient: string;
  accentColor: string;
  description: string;
  dashboardPage: string | null;
}

const triggerDashboardConfig: Record<string, TriggerDashConfig> = {
  'bot-security': {
    icon: '\u2B21',
    gradient: 'linear-gradient(135deg, var(--accent-crimson), var(--accent-amber))',
    accentColor: 'var(--accent-crimson)',
    description: 'Monitor security vulnerabilities across your projects. Run automated scans, view findings by severity, and resolve issues with AI assistance.',
    dashboardPage: 'security-dashboard',
  },
  'bot-pr-review': {
    icon: '\u21C4',
    gradient: 'linear-gradient(135deg, var(--accent-violet), var(--accent-cyan))',
    accentColor: 'var(--accent-violet)',
    description: 'Review pull requests across all GitHub projects. View PR status, run AI-powered code reviews, and track review outcomes.',
    dashboardPage: 'pr-review-dashboard',
  },
};

const defaultTriggerConfig: TriggerDashConfig = {
  icon: '\u25C8',
  gradient: 'linear-gradient(135deg, var(--accent-cyan), var(--accent-violet))',
  accentColor: 'var(--accent-cyan)',
  description: 'Custom trigger dashboard for monitoring and running automated tasks.',
  dashboardPage: 'trigger-dashboard',
};

function getTriggerConfig(triggerId: string): TriggerDashConfig {
  return triggerDashboardConfig[triggerId] || defaultTriggerConfig;
}

// Entity counts for Organization Overview
const entityCounts = ref<Record<string, number>>({
  products: 0,
  projects: 0,
  teams: 0,
  agents: 0,
});
const entityCountsLoading = ref(true);
const entityCountsError = ref<string | null>(null);

interface EntityDashConfig {
  name: string;
  key: string;
  icon: string;
  gradient: string;
  accentColor: string;
  description: string;
  viewName: string;
}

const entityDashboards: EntityDashConfig[] = [
  {
    name: 'Products',
    key: 'products',
    icon: '\u25A1',
    gradient: 'linear-gradient(135deg, var(--accent-emerald), var(--accent-cyan))',
    accentColor: 'var(--accent-emerald)',
    description: 'Overview of all products and their project assignments.',
    viewName: 'products-summary',
  },
  {
    name: 'Projects',
    key: 'projects',
    icon: '\u25B3',
    gradient: 'linear-gradient(135deg, var(--accent-cyan), var(--accent-violet))',
    accentColor: 'var(--accent-cyan)',
    description: 'Overview of all projects, repositories, and team assignments.',
    viewName: 'projects-summary',
  },
  {
    name: 'Teams',
    key: 'teams',
    icon: '\u25CE',
    gradient: 'linear-gradient(135deg, var(--accent-violet), var(--accent-amber))',
    accentColor: 'var(--accent-violet)',
    description: 'Overview of all teams, member counts, and operational status.',
    viewName: 'teams-summary',
  },
  {
    name: 'Agents',
    key: 'agents',
    icon: '\u25C6',
    gradient: 'linear-gradient(135deg, var(--accent-amber), var(--accent-crimson))',
    accentColor: 'var(--accent-amber)',
    description: 'Overview of all agents, their backends, and availability.',
    viewName: 'agents-summary',
  },
];

useWebMcpTool({
  name: 'hive_dashboards_get_state',
  description: 'Returns the current state of the DashboardsPage',
  page: 'DashboardsPage',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'DashboardsPage',
        triggerCount: triggers.value.length,
        isLoading: isLoading.value,
        entityCounts: entityCounts.value,
        entityCountsLoading: entityCountsLoading.value,
        entityCountsError: entityCountsError.value,
      }),
    }],
  }),
  deps: [triggers, isLoading, entityCounts, entityCountsLoading, entityCountsError],
});

async function loadTriggers() {
  isLoading.value = true;
  try {
    const data = await triggerApi.list();
    triggers.value = data.triggers || [];
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to load triggers';
    showToast(message, 'error');
  } finally {
    isLoading.value = false;
  }
}

async function loadEntityCounts() {
  entityCountsLoading.value = true;
  try {
    entityCountsError.value = null;
    const [productsData, projectsData, teamsData, agentsData] = await Promise.all([
      productApi.list(),
      projectApi.list(),
      teamApi.list(),
      agentApi.list(),
    ]);
    entityCounts.value = {
      products: productsData.products?.length || 0,
      projects: projectsData.projects?.length || 0,
      teams: teamsData.teams?.length || 0,
      agents: agentsData.agents?.length || 0,
    };
  } catch (err) {
    entityCountsError.value = err instanceof Error ? err.message : 'Failed to load entity counts';
    // Keep entityCounts at their default zero values as fallback
  } finally {
    entityCountsLoading.value = false;
  }
}

async function retryEntityCounts() {
  entityCountsError.value = null;
  await loadEntityCounts();
}

function openDashboard(triggerId: string) {
  const config = getTriggerConfig(triggerId);
  if (config.dashboardPage && config.dashboardPage !== 'trigger-dashboard') {
    // Specialized dashboard (security, pr-review, etc.)
    router.push({ name: config.dashboardPage });
  } else if (config.dashboardPage) {
    router.push({ name: 'trigger-dashboard', params: { triggerId } });
  }
}

onMounted(() => {
  Promise.all([loadTriggers(), loadEntityCounts()]);
});
</script>

<template>
  <div class="dashboards-page">
    <AppBreadcrumb :items="[{ label: 'Dashboards' }]" />
    <div class="page-intro">
      <div class="intro-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <rect x="3" y="3" width="7" height="9" rx="1"/>
          <rect x="14" y="3" width="7" height="5" rx="1"/>
          <rect x="14" y="12" width="7" height="9" rx="1"/>
          <rect x="3" y="16" width="7" height="5" rx="1"/>
        </svg>
      </div>
      <div class="intro-text">
        <h2>Command Center</h2>
        <p>Select a trigger dashboard to monitor operations and run automated tasks</p>
      </div>
    </div>

    <!-- Trigger Dashboards section -->
    <LoadingState v-if="isLoading" message="Loading dashboards..." />

    <EmptyState
      v-else-if="triggers.length === 0"
      title="No triggers registered"
      description="Add a trigger to see its dashboard"
    />

    <div v-else class="dashboard-grid">
      <div
        v-for="(trigger, index) in triggers"
        :key="trigger.id"
        class="dashboard-card clickable"
        :style="{ '--card-delay': `${index * 50}ms`, '--accent': getTriggerConfig(trigger.id).accentColor }"
        @click="openDashboard(trigger.id)"
      >
        <div class="card-glow"></div>
        <div class="card-content">
          <div class="card-header">
            <div class="card-icon" :style="{ background: getTriggerConfig(trigger.id).gradient }">
              {{ getTriggerConfig(trigger.id).icon }}
            </div>
            <div class="card-title-area">
              <h3 class="card-name">{{ trigger.name }}</h3>
              <div class="card-meta">
                <span class="meta-tag">Group {{ trigger.group_id }}</span>
                <span class="meta-divider">&middot;</span>
                <span class="meta-tag">{{ trigger.path_count || 0 }} project{{ (trigger.path_count || 0) !== 1 ? 's' : '' }}</span>
              </div>
            </div>
          </div>

          <p class="card-description">{{ getTriggerConfig(trigger.id).description }}</p>

          <div class="card-footer">
            <div class="status-indicator" :class="trigger.enabled ? 'active' : 'inactive'">
              <span class="status-dot"></span>
              <span>{{ trigger.enabled ? 'Active' : 'Disabled' }}</span>
            </div>
            <div class="view-action">
              <span>Open Dashboard</span>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M5 12h14M12 5l7 7-7 7"/>
              </svg>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="section-action" v-if="!isLoading && triggers.length > 0">
      <button class="link-action" @click="router.push({ name: 'triggers' })">
        View All Triggers
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M5 12h14M12 5l7 7-7 7"/>
        </svg>
      </button>
    </div>

    <!-- Monitoring section -->
    <div class="section-divider">
      <h3 class="section-title">Monitoring</h3>
    </div>

    <div class="dashboard-grid">
      <div
        class="dashboard-card clickable"
        :style="{ '--card-delay': '0ms', '--accent': 'var(--accent-emerald)' }"
        @click="router.push({ name: 'token-usage' })"
      >
        <div class="card-glow"></div>
        <div class="card-content">
          <div class="card-header">
            <div class="card-icon" style="background: linear-gradient(135deg, var(--accent-emerald), var(--accent-cyan))">
              $
            </div>
            <div class="card-title-area">
              <h3 class="card-name">Token Usage</h3>
              <div class="card-meta">
                <span class="meta-tag">Cost Tracking</span>
              </div>
            </div>
          </div>

          <p class="card-description">Monitor token consumption, cost trends, and budget limits across all AI backends and agents.</p>

          <div class="card-footer">
            <div class="status-indicator active">
              <span class="status-dot"></span>
              <span>Live</span>
            </div>
            <div class="view-action">
              <span>Open Dashboard</span>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M5 12h14M12 5l7 7-7 7"/>
              </svg>
            </div>
          </div>
        </div>
      </div>

      <div
        class="dashboard-card clickable"
        :style="{ '--card-delay': '50ms', '--accent': 'var(--accent-amber)' }"
        @click="router.push({ name: 'rotation-dashboard' })"
      >
        <div class="card-glow"></div>
        <div class="card-content">
          <div class="card-header">
            <div class="card-icon" style="background: linear-gradient(135deg, var(--accent-amber), var(--accent-emerald))">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 24px; height: 24px;">
                <circle cx="12" cy="12" r="10"/>
                <path d="M12 6v6l4 2"/>
              </svg>
            </div>
            <div class="card-title-area">
              <h3 class="card-name">Scheduling & Rotation</h3>
              <div class="card-meta">
                <span class="meta-tag">Orchestration</span>
              </div>
            </div>
          </div>

          <p class="card-description">Monitor agent execution scheduler, account rotation events, and rate limit countdowns.</p>

          <div class="card-footer">
            <div class="status-indicator active">
              <span class="status-dot"></span>
              <span>Live</span>
            </div>
            <div class="view-action">
              <span>Open Dashboard</span>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M5 12h14M12 5l7 7-7 7"/>
              </svg>
            </div>
          </div>
        </div>
      </div>

      <div
        class="dashboard-card clickable"
        :style="{ '--card-delay': '100ms', '--accent': 'var(--accent-crimson)' }"
        @click="router.push({ name: 'service-health' })"
      >
        <div class="card-glow"></div>
        <div class="card-content">
          <div class="card-header">
            <div class="card-icon" style="background: linear-gradient(135deg, var(--accent-crimson), var(--accent-violet))">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 24px; height: 24px;">
                <path d="M20.42 4.58a5.4 5.4 0 00-7.65 0l-.77.78-.77-.78a5.4 5.4 0 00-7.65 0C1.46 6.7 1.33 10.28 4 13l8 8 8-8c2.67-2.72 2.54-6.3.42-8.42z"/>
              </svg>
            </div>
            <div class="card-title-area">
              <h3 class="card-name">Account Health</h3>
              <div class="card-meta">
                <span class="meta-tag">AI Backends</span>
              </div>
            </div>
          </div>

          <p class="card-description">Monitor status and usage of all registered AI backend accounts.</p>

          <div class="card-footer">
            <div class="status-indicator active">
              <span class="status-dot"></span>
              <span>Live</span>
            </div>
            <div class="view-action">
              <span>Open Dashboard</span>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M5 12h14M12 5l7 7-7 7"/>
              </svg>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Organization Overview section -->
    <div class="section-divider">
      <h3 class="section-title">Organization</h3>
    </div>

    <div v-if="entityCountsError" class="entity-counts-error">
      <span>Failed to load counts</span>
      <button class="btn-retry" @click="retryEntityCounts">Retry</button>
    </div>

    <!-- Skeleton cards while entity counts are loading -->
    <div v-if="entityCountsLoading && !entityCountsError" class="dashboard-grid">
      <div
        v-for="(entity, index) in entityDashboards"
        :key="'skeleton-' + entity.viewName"
        class="dashboard-card skeleton"
        :style="{ '--card-delay': `${index * 50}ms` }"
      >
        <div class="card-content">
          <div class="card-header">
            <div class="skeleton-icon skeleton-pulse"></div>
            <div class="card-title-area">
              <div class="skeleton-line skeleton-pulse" style="width: 60%; height: 16px;"></div>
              <div class="skeleton-line skeleton-pulse" style="width: 40%; height: 12px; margin-top: 8px;"></div>
            </div>
          </div>
          <div class="skeleton-line skeleton-pulse" style="width: 80%; height: 12px; margin-bottom: 8px;"></div>
          <div class="skeleton-line skeleton-pulse" style="width: 65%; height: 12px; margin-bottom: 20px;"></div>
          <div class="card-footer">
            <div class="skeleton-line skeleton-pulse" style="width: 30%; height: 12px;"></div>
            <div class="skeleton-line skeleton-pulse" style="width: 25%; height: 12px;"></div>
          </div>
        </div>
      </div>
    </div>

    <!-- Actual entity cards when loaded -->
    <div v-else-if="!entityCountsError" class="dashboard-grid">
      <div
        v-for="(entity, index) in entityDashboards"
        :key="entity.viewName"
        class="dashboard-card clickable"
        :style="{ '--card-delay': `${index * 50}ms`, '--accent': entity.accentColor }"
        @click="router.push({ name: entity.viewName })"
      >
        <div class="card-glow"></div>
        <div class="card-content">
          <div class="card-header">
            <div class="card-icon" :style="{ background: entity.gradient }">
              {{ entity.icon }}
            </div>
            <div class="card-title-area">
              <h3 class="card-name">{{ entity.name }}</h3>
              <div class="card-meta">
                <span class="meta-tag">{{ entityCounts[entity.key] }} {{ entity.name.toLowerCase() }}</span>
              </div>
            </div>
          </div>

          <p class="card-description">{{ entity.description }}</p>

          <div class="card-footer">
            <div class="status-indicator active">
              <span class="status-dot"></span>
              <span>{{ entityCounts[entity.key] }} total</span>
            </div>
            <div class="view-action">
              <span>Open Dashboard</span>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M5 12h14M12 5l7 7-7 7"/>
              </svg>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dashboards-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
  width: 100%;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.page-intro {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 24px 28px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
}

.intro-icon {
  width: 48px;
  height: 48px;
  background: var(--accent-cyan-dim);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.intro-icon svg {
  width: 24px;
  height: 24px;
  color: var(--accent-cyan);
}

.intro-text h2 {
  font-family: var(--font-mono);
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.02em;
}

.intro-text p {
  font-size: 0.9rem;
  color: var(--text-tertiary);
  margin-top: 4px;
}

.section-divider {
  margin-top: 16px;
}

.section-title {
  font-family: var(--font-mono);
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 16px;
}

.dashboard-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 20px;
}

.dashboard-card {
  position: relative;
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  overflow: hidden;
  transition: all var(--transition-normal);
  animation: cardSlideIn 0.5s ease backwards;
  animation-delay: var(--card-delay, 0ms);
}

@keyframes cardSlideIn {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

.dashboard-card.clickable {
  cursor: pointer;
}

.dashboard-card.clickable:hover {
  border-color: var(--accent);
  transform: translateY(-4px);
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.4);
}

.dashboard-card.clickable:hover .card-glow {
  opacity: 1;
}

.card-glow {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--accent), transparent);
  opacity: 0;
  transition: opacity var(--transition-normal);
}

.card-content {
  padding: 24px;
  position: relative;
}

.card-header {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 16px;
}

.card-icon {
  width: 52px;
  height: 52px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.5rem;
  flex-shrink: 0;
  color: var(--bg-primary);
  font-weight: 700;
}

.card-title-area {
  flex: 1;
  min-width: 0;
}

.card-name {
  font-weight: 600;
  color: var(--text-primary);
  font-size: 1.1rem;
  margin-bottom: 6px;
}

.card-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.meta-tag {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  font-family: var(--font-mono);
}

.meta-divider {
  color: var(--text-muted);
}

.card-description {
  color: var(--text-secondary);
  font-size: 0.875rem;
  line-height: 1.6;
  margin-bottom: 20px;
}

.card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 16px;
  border-top: 1px solid var(--border-subtle);
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.8rem;
  color: var(--text-tertiary);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-muted);
}

.status-indicator.active .status-dot {
  background: var(--accent-emerald);
  box-shadow: 0 0 8px var(--accent-emerald);
}

.status-indicator.active {
  color: var(--accent-emerald);
}

.status-indicator.inactive .status-dot {
  background: var(--text-muted);
}

.view-action {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.85rem;
  color: var(--accent-cyan);
  font-weight: 500;
  transition: gap var(--transition-fast);
}

.dashboard-card.clickable:hover .view-action {
  gap: 10px;
}

.view-action svg {
  width: 16px;
  height: 16px;
}

.coming-soon {
  font-size: 0.8rem;
  color: var(--text-muted);
  padding: 4px 12px;
  background: var(--bg-tertiary);
  border-radius: 4px;
}

.entity-counts-error {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: rgba(255, 51, 102, 0.1);
  border: 1px solid var(--accent-crimson);
  border-radius: 6px;
  font-size: 13px;
  color: var(--accent-crimson);
}

.btn-retry {
  padding: 4px 12px;
  background: transparent;
  border: 1px solid var(--accent-crimson);
  border-radius: 4px;
  color: var(--accent-crimson);
  cursor: pointer;
  font-size: 12px;
}

.btn-retry:hover {
  background: rgba(255, 51, 102, 0.15);
}

.section-action {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}

.link-action {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: none;
  border: none;
  color: var(--accent-cyan);
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  transition: gap var(--transition-fast);
}

.link-action:hover {
  gap: 10px;
}

.link-action svg {
  width: 16px;
  height: 16px;
}

/* Skeleton loading state for entity counts */
.dashboard-card.skeleton {
  pointer-events: none;
  cursor: default;
}

.skeleton-pulse {
  background: var(--bg-tertiary);
  animation: skeletonPulse 1.5s ease-in-out infinite;
}

@keyframes skeletonPulse {
  0%, 100% { background-color: var(--bg-tertiary); }
  50% { background-color: var(--border-subtle); }
}

.skeleton-line {
  border-radius: 6px;
  height: 14px;
}

.skeleton-icon {
  width: 52px;
  height: 52px;
  border-radius: 12px;
  flex-shrink: 0;
}
</style>
