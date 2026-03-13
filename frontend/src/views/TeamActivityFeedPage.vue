<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { auditApi } from '../services/api';
import type { AuditEvent } from '../services/api';

const router = useRouter();

type ActivityType = 'execution' | 'config_change' | 'bot_created' | 'bot_deleted' | 'trigger_added' | 'member_joined' | 'execution_failed';

interface ActivityEvent {
  id: string;
  type: ActivityType;
  actor: string;
  summary: string;
  detail: string;
  timestamp: string;
  botId?: string;
  link?: string;
}

function mapAuditEvent(ev: AuditEvent): ActivityEvent {
  let type: ActivityType;
  const action = ev.action ?? '';
  const outcome = ev.outcome ?? '';

  if (action.startsWith('execution.') || action === 'execution') {
    type = outcome === 'failure' || outcome === 'failed' ? 'execution_failed' : 'execution';
  } else if (action.startsWith('bot.create') || action === 'bot_created') {
    type = 'bot_created';
  } else if (action.startsWith('bot.delete') || action === 'bot_deleted') {
    type = 'bot_deleted';
  } else if (action.startsWith('trigger.') || action === 'trigger_added') {
    type = 'trigger_added';
  } else if (action.startsWith('member.') || action === 'member_joined') {
    type = 'member_joined';
  } else {
    type = 'config_change';
  }

  const summary = `${action}${ev.entity_id ? ` on ${ev.entity_id}` : ''}`;
  const detail = ev.details ? JSON.stringify(ev.details) : '';

  return {
    id: `${ev.ts}-${ev.entity_id}`,
    type,
    actor: ev.actor ?? 'system',
    summary,
    detail,
    timestamp: ev.ts,
    botId: ev.entity_type === 'bot' ? ev.entity_id : undefined,
  };
}

const allEvents = ref<ActivityEvent[]>([]);

onMounted(async () => {
  try {
    const result = await auditApi.getEvents(200);
    allEvents.value = result.events.map(mapAuditEvent);
  } catch {
    // keep empty on error
  }
});

const filterType = ref<ActivityType | 'all'>('all');
const filterActor = ref('');
const searchText = ref('');

const filteredEvents = computed(() => {
  return allEvents.value.filter(ev => {
    if (filterType.value !== 'all' && ev.type !== filterType.value) return false;
    if (filterActor.value && !ev.actor.includes(filterActor.value)) return false;
    if (searchText.value && !ev.summary.toLowerCase().includes(searchText.value.toLowerCase()) && !ev.detail.toLowerCase().includes(searchText.value.toLowerCase())) return false;
    return true;
  });
});

const typeOptions: { value: ActivityType | 'all'; label: string }[] = [
  { value: 'all', label: 'All Events' },
  { value: 'execution', label: 'Executions' },
  { value: 'execution_failed', label: 'Failures' },
  { value: 'config_change', label: 'Config Changes' },
  { value: 'bot_created', label: 'Bot Created' },
  { value: 'bot_deleted', label: 'Bot Deleted' },
  { value: 'trigger_added', label: 'Trigger Added' },
  { value: 'member_joined', label: 'Member Joined' },
];

function typeIcon(type: ActivityType): string {
  const icons: Record<ActivityType, string> = {
    execution: '▶',
    execution_failed: '✕',
    config_change: '✎',
    bot_created: '+',
    bot_deleted: '−',
    trigger_added: '⚡',
    member_joined: '👤',
  };
  return icons[type] ?? '•';
}

function typeColor(type: ActivityType): string {
  const colors: Record<ActivityType, string> = {
    execution: 'var(--accent-cyan)',
    execution_failed: '#ef4444',
    config_change: '#fbbf24',
    bot_created: '#34d399',
    bot_deleted: '#f87171',
    trigger_added: '#818cf8',
    member_joined: '#a78bfa',
  };
  return colors[type] ?? 'var(--text-muted)';
}

function formatDate(ts: string): string {
  const d = new Date(ts);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffH = Math.floor(diffMs / 3600000);
  if (diffH < 1) return 'just now';
  if (diffH < 24) return `${diffH}h ago`;
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function actorInitials(actor: string): string {
  if (actor === 'system') return 'SYS';
  return actor.split('@')[0].slice(0, 2).toUpperCase();
}
</script>

<template>
  <div class="team-activity">
    <AppBreadcrumb :items="[
      { label: 'Teams', action: () => router.push({ name: 'teams' }) },
      { label: 'Activity Feed' },
    ]" />

    <PageHeader
      title="Team Activity Feed"
      subtitle="A real-time chronological feed of all bot runs, configuration changes, and team actions."
    />

    <!-- Filters -->
    <div class="filters card">
      <div class="filter-inner">
        <input
          v-model="searchText"
          class="search-input"
          placeholder="Search events..."
        />
        <select v-model="filterType" class="select">
          <option v-for="opt in typeOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
        </select>
        <input v-model="filterActor" class="input" placeholder="Filter by actor..." />
        <span class="event-count">{{ filteredEvents.length }} events</span>
      </div>
    </div>

    <!-- Feed -->
    <div class="feed">
      <div
        v-for="event in filteredEvents"
        :key="event.id"
        class="feed-item"
      >
        <div class="feed-timeline">
          <div class="type-icon" :style="{ background: typeColor(event.type) + '22', color: typeColor(event.type) }">
            {{ typeIcon(event.type) }}
          </div>
          <div class="timeline-line"></div>
        </div>
        <div class="feed-card card">
          <div class="feed-header">
            <div class="actor-avatar">{{ actorInitials(event.actor) }}</div>
            <div class="feed-main">
              <div class="feed-summary">{{ event.summary }}</div>
              <div class="feed-meta">
                <span class="actor-name">{{ event.actor }}</span>
                <span class="sep">·</span>
                <span class="event-type-label" :style="{ color: typeColor(event.type) }">{{ event.type.replace(/_/g, ' ') }}</span>
                <template v-if="event.botId">
                  <span class="sep">·</span>
                  <span class="bot-id">{{ event.botId }}</span>
                </template>
              </div>
            </div>
            <span class="feed-time">{{ formatDate(event.timestamp) }}</span>
          </div>
          <div class="feed-detail">{{ event.detail }}</div>
        </div>
      </div>

      <div v-if="filteredEvents.length === 0" class="empty-state">
        No events match the current filters.
      </div>
    </div>
  </div>
</template>

<style scoped>
.team-activity { display: flex; flex-direction: column; gap: 20px; animation: fadeIn 0.4s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

.card { background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 12px; overflow: hidden; }

.filters { padding: 16px 20px; }
.filter-inner { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.search-input { flex: 1; min-width: 160px; padding: 8px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 7px; color: var(--text-primary); font-size: 0.875rem; }
.search-input:focus { outline: none; border-color: var(--accent-cyan); }
.select { padding: 8px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 7px; color: var(--text-primary); font-size: 0.875rem; cursor: pointer; }
.select:focus { outline: none; border-color: var(--accent-cyan); }
.input { padding: 8px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 7px; color: var(--text-primary); font-size: 0.875rem; }
.input:focus { outline: none; border-color: var(--accent-cyan); }
.event-count { font-size: 0.78rem; color: var(--text-tertiary); white-space: nowrap; }

.feed { display: flex; flex-direction: column; gap: 0; }

.feed-item { display: flex; gap: 0; align-items: stretch; }

.feed-timeline { display: flex; flex-direction: column; align-items: center; width: 44px; flex-shrink: 0; }

.type-icon {
  width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
  font-size: 0.85rem; font-weight: 700; flex-shrink: 0; margin-top: 16px;
}

.timeline-line { flex: 1; width: 2px; background: var(--border-subtle); margin: 4px 0; }
.feed-item:last-child .timeline-line { display: none; }

.feed-card { flex: 1; margin: 12px 0 0 0; }

.feed-header { display: flex; align-items: flex-start; gap: 10px; padding: 14px 16px 8px; }

.actor-avatar {
  width: 26px; height: 26px; border-radius: 50%; background: var(--bg-elevated); border: 1px solid var(--border-default);
  display: flex; align-items: center; justify-content: center; font-size: 0.6rem; font-weight: 700; color: var(--text-secondary);
  flex-shrink: 0; margin-top: 2px;
}

.feed-main { flex: 1; }
.feed-summary { font-size: 0.875rem; font-weight: 500; color: var(--text-primary); }
.feed-meta { display: flex; align-items: center; gap: 6px; font-size: 0.72rem; color: var(--text-muted); margin-top: 2px; flex-wrap: wrap; }
.actor-name { color: var(--text-secondary); }
.event-type-label { text-transform: capitalize; font-weight: 500; }
.bot-id { font-family: monospace; color: var(--text-muted); }
.sep { opacity: 0.5; }
.feed-time { font-size: 0.72rem; color: var(--text-muted); white-space: nowrap; padding-top: 2px; }
.feed-detail { padding: 0 16px 14px; font-size: 0.8rem; color: var(--text-tertiary); }

.empty-state { text-align: center; padding: 40px; color: var(--text-muted); font-size: 0.875rem; }
</style>
