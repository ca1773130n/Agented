<script setup lang="ts">
/**
 * SuperAgent sessions tied to a project.
 *
 * Renders on the ProjectManagementPage's Sessions tab above the
 * existing GRD-driven ProjectSessionPanel so users see the SA
 * sessions created by /sketch routing — without this panel, sketches
 * appeared to "disappear" because the GRD panel only knows about
 * interactive ``claude -p`` sessions, not the super-agent work done
 * by routing.
 *
 * Each row links to that SA's playground so the user can read the
 * conversation. We also surface the per-SA "working / active" pill
 * from the v0.7.25 activity-status endpoint so it's obvious which
 * SA is currently producing output.
 */
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { useI18n } from 'vue-i18n';
import type { SuperAgent, SuperAgentActivityStatus } from '../../services/api';

const { t } = useI18n();
import { projectApi, superAgentApi } from '../../services/api';
import { safeFormatDateTime } from '../../utils/datetime';

interface SuperAgentSessionRow {
  id: string;
  super_agent_id: string;
  status: string;
  started_at?: string;
  ended_at?: string | null;
  worktree_path?: string | null;
  branch_name?: string | null;
  title?: string | null;
  session_type?: string | null;
  token_count?: number;
}

const props = defineProps<{
  projectId: string;
}>();

const sessions = ref<SuperAgentSessionRow[]>([]);
const superAgents = ref<Record<string, SuperAgent>>({});
const activity = ref<Record<string, SuperAgentActivityStatus>>({});
const isLoading = ref(true);
const loadError = ref<string | null>(null);
let pollHandle: ReturnType<typeof setInterval> | null = null;

const activeSessions = computed(() =>
  sessions.value.filter((s) => s.status === 'active'),
);
const otherSessions = computed(() =>
  sessions.value.filter((s) => s.status !== 'active'),
);

async function loadSessions() {
  try {
    const data = await projectApi.listSuperAgentSessions(props.projectId);
    sessions.value = data.sessions || [];

    // Resolve SA names + activity for every unique SA referenced.
    const saIds = Array.from(new Set(sessions.value.map((s) => s.super_agent_id)));
    if (saIds.length > 0) {
      // The SA list endpoint is cheaper than N gets; filter client-side.
      const all = await superAgentApi.list();
      const map: Record<string, SuperAgent> = {};
      for (const sa of all.super_agents || []) {
        if (saIds.includes(sa.id)) map[sa.id] = sa;
      }
      superAgents.value = map;
    }

    await loadActivity();
    loadError.value = null;
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : t('projectSuperAgentSessions.loadError');
  } finally {
    isLoading.value = false;
  }
}

async function loadActivity() {
  try {
    const data = await superAgentApi.activityStatus();
    activity.value = data.statuses || {};
  } catch {
    // Silent — activity is a nice-to-have, never block the session list.
  }
}

function agentName(saId: string): string {
  return superAgents.value[saId]?.name || saId;
}

function isWorking(saId: string): boolean {
  return Boolean(activity.value[saId]?.is_streaming);
}

function statusBadgeClass(status: string): string {
  switch (status) {
    case 'active': return 'badge badge--active';
    case 'paused': return 'badge badge--paused';
    case 'completed': return 'badge badge--completed';
    case 'failed': return 'badge badge--failed';
    default: return 'badge';
  }
}

function playgroundLinkFor(s: SuperAgentSessionRow) {
  return {
    name: 'super-agent-playground',
    params: { superAgentId: s.super_agent_id },
  };
}

onMounted(() => {
  loadSessions();
  // Refresh on the same 7s cadence as the SA list page so a /sketch
  // routed in another tab surfaces here within one tick.
  pollHandle = setInterval(loadSessions, 7000);
});

onUnmounted(() => {
  if (pollHandle) {
    clearInterval(pollHandle);
    pollHandle = null;
  }
});
</script>

<template>
  <div class="sa-sessions">
    <div class="sa-sessions__header">
      <h3 class="sa-sessions__title">{{ t('projectSuperAgentSessions.title') }}</h3>
      <span class="sa-sessions__count">
        {{ t('projectSuperAgentSessions.count', { active: activeSessions.length, total: sessions.length }) }}
      </span>
    </div>

    <div v-if="isLoading" class="state-row">{{ t('projectSuperAgentSessions.loading') }}</div>
    <div v-else-if="loadError" class="state-row error">{{ loadError }}</div>
    <div v-else-if="sessions.length === 0" class="state-row muted">
      {{ t('projectSuperAgentSessions.emptyPrefix') }}
      (<router-link :to="{ name: 'sketch-chat' }">/sketch</router-link>){{ t('projectSuperAgentSessions.emptySuffix') }}
    </div>

    <template v-else>
      <div v-if="activeSessions.length > 0" class="group">
        <div class="group__label">{{ t('projectSuperAgentSessions.active') }}</div>
        <ul class="rows">
          <li v-for="s in activeSessions" :key="s.id" class="row">
            <router-link :to="playgroundLinkFor(s)" class="row__link">
              <div class="row__top">
                <span class="row__agent">{{ agentName(s.super_agent_id) }}</span>
                <span
                  v-if="isWorking(s.super_agent_id)"
                  class="working-pill"
                  :title="t('projectSuperAgentSessions.workingTooltip')"
                >
                  <span class="working-pill__dot" />
                  {{ t('projectSuperAgentSessions.working') }}
                </span>
                <span :class="statusBadgeClass(s.status)">{{ s.status }}</span>
              </div>
              <div class="row__meta">
                <span v-if="s.title" class="row__title">{{ s.title }}</span>
                <span v-if="s.started_at" class="row__time">
                  {{ t('projectSuperAgentSessions.started', { time: safeFormatDateTime(s.started_at) }) }}
                </span>
                <span v-if="s.session_type" class="row__type">{{ s.session_type }}</span>
                <span v-if="s.worktree_path" class="row__path" :title="s.worktree_path">
                  {{ s.worktree_path.replace(/^.*\//, '') }}
                </span>
              </div>
            </router-link>
          </li>
        </ul>
      </div>

      <div v-if="otherSessions.length > 0" class="group">
        <div class="group__label">{{ t('projectSuperAgentSessions.history') }}</div>
        <ul class="rows rows--muted">
          <li v-for="s in otherSessions.slice(0, 10)" :key="s.id" class="row">
            <router-link :to="playgroundLinkFor(s)" class="row__link">
              <div class="row__top">
                <span class="row__agent">{{ agentName(s.super_agent_id) }}</span>
                <span :class="statusBadgeClass(s.status)">{{ s.status }}</span>
              </div>
              <div class="row__meta">
                <span v-if="s.title" class="row__title">{{ s.title }}</span>
                <span v-if="s.ended_at" class="row__time">
                  {{ t('projectSuperAgentSessions.ended', { time: safeFormatDateTime(s.ended_at) }) }}
                </span>
              </div>
            </router-link>
          </li>
        </ul>
      </div>
    </template>
  </div>
</template>

<style scoped>
.sa-sessions {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 16px;
}
.sa-sessions__header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 8px;
}
.sa-sessions__title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}
.sa-sessions__count {
  font-size: 11px;
  color: var(--text-muted);
}
.state-row {
  padding: 12px;
  font-size: 13px;
  color: var(--text-muted);
}
.state-row.error { color: var(--accent-red); }
.state-row.muted { color: var(--text-tertiary); }
.group { margin-top: 8px; }
.group__label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  color: var(--text-muted);
  margin-bottom: 4px;
}
.rows {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.rows--muted { opacity: 0.85; }
.row__link {
  display: block;
  padding: 8px 10px;
  border-radius: 6px;
  text-decoration: none;
  color: inherit;
  transition: background 120ms ease, border-color 120ms ease;
  border: 1px solid transparent;
}
.row__link:hover {
  background: var(--bg-tertiary);
  border-color: var(--border-subtle);
}
.row__top {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.row__agent {
  font-weight: 600;
  font-size: 13px;
  color: var(--text-primary);
}
.row__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  font-size: 11px;
  color: var(--text-muted);
}
.row__title { color: var(--text-secondary); }
.row__path { font-family: var(--font-mono, ui-monospace, monospace); }
.badge {
  display: inline-block;
  padding: 1px 7px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  background: var(--bg-tertiary);
  color: var(--text-muted);
  margin-left: auto;
}
.badge--active   { background: rgba(16, 185, 129, 0.15);  color: #10b981; }
.badge--paused   { background: rgba(245, 158, 11, 0.15);  color: #f59e0b; }
.badge--completed{ background: rgba(96, 165, 250, 0.15);  color: #60a5fa; }
.badge--failed   { background: rgba(239, 68, 68, 0.15);   color: #ef4444; }
.working-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 1px 7px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 600;
  background: rgba(245, 158, 11, 0.18);
  color: #f59e0b;
}
.working-pill__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  box-shadow: 0 0 6px currentColor;
  animation: sa-working-pulse 1.4s ease-in-out infinite;
}
@keyframes sa-working-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}
</style>
