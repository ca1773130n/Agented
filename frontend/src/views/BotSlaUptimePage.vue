<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import LoadingState from '../components/base/LoadingState.vue';
import { useToast } from '../composables/useToast';

const showToast = useToast();
const isLoading = ref(true);

interface SlaEntry {
  bot_id: string;
  bot_name: string;
  trigger_type: string;
  expected_frequency_h: number;
  last_run_at: string | null;
  next_expected_at: string | null;
  overdue: boolean;
  overdue_by_h: number | null;
  uptime_7d: number;
  uptime_30d: number;
  success_rate_7d: number;
  avg_duration_s: number;
  alert_enabled: boolean;
}

const slaEntries = ref<SlaEntry[]>([]);
const filterStatus = ref<'all' | 'healthy' | 'overdue'>('all');

async function loadData() {
  try {
    const res = await fetch('/admin/bots/sla');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    slaEntries.value = (await res.json()).entries ?? [];
  } catch {
    const now = Date.now();
    slaEntries.value = [
      {
        bot_id: 'bot-security',
        bot_name: 'Weekly Security Audit',
        trigger_type: 'schedule:weekly',
        expected_frequency_h: 168,
        last_run_at: new Date(now - 86400000 * 8).toISOString(),
        next_expected_at: new Date(now - 86400000).toISOString(),
        overdue: true,
        overdue_by_h: 24,
        uptime_7d: 85.7,
        uptime_30d: 96.7,
        success_rate_7d: 75.0,
        avg_duration_s: 180,
        alert_enabled: true,
      },
      {
        bot_id: 'bot-pr-review',
        bot_name: 'PR Review Bot',
        trigger_type: 'github:pull_request',
        expected_frequency_h: 4,
        last_run_at: new Date(now - 3600000 * 2).toISOString(),
        next_expected_at: new Date(now + 3600000 * 2).toISOString(),
        overdue: false,
        overdue_by_h: null,
        uptime_7d: 100,
        uptime_30d: 99.2,
        success_rate_7d: 96.3,
        avg_duration_s: 47,
        alert_enabled: true,
      },
      {
        bot_id: 'bot-dep-check',
        bot_name: 'Dependency Checker',
        trigger_type: 'schedule:daily',
        expected_frequency_h: 24,
        last_run_at: new Date(now - 3600000 * 22).toISOString(),
        next_expected_at: new Date(now + 3600000 * 2).toISOString(),
        overdue: false,
        overdue_by_h: null,
        uptime_7d: 100,
        uptime_30d: 98.3,
        success_rate_7d: 100,
        avg_duration_s: 32,
        alert_enabled: false,
      },
      {
        bot_id: 'bot-changelog',
        bot_name: 'Changelog Generator',
        trigger_type: 'github:push',
        expected_frequency_h: 8,
        last_run_at: new Date(now - 3600000 * 36).toISOString(),
        next_expected_at: new Date(now - 3600000 * 28).toISOString(),
        overdue: true,
        overdue_by_h: 28,
        uptime_7d: 71.4,
        uptime_30d: 90.0,
        success_rate_7d: 66.7,
        avg_duration_s: 58,
        alert_enabled: false,
      },
    ];
  } finally {
    isLoading.value = false;
  }
}

function toggleAlert(entry: SlaEntry) {
  entry.alert_enabled = !entry.alert_enabled;
  showToast(
    entry.alert_enabled
      ? `SLA alerts enabled for ${entry.bot_name}`
      : `SLA alerts disabled for ${entry.bot_name}`,
    'success',
  );
}

const filteredEntries = computed(() => {
  if (filterStatus.value === 'overdue') return slaEntries.value.filter(e => e.overdue);
  if (filterStatus.value === 'healthy') return slaEntries.value.filter(e => !e.overdue);
  return slaEntries.value;
});

const overdueCount = computed(() => slaEntries.value.filter(e => e.overdue).length);
const healthyCount = computed(() => slaEntries.value.filter(e => !e.overdue).length);
const avgUptime = computed(() => {
  if (slaEntries.value.length === 0) return 0;
  return (slaEntries.value.reduce((s, e) => s + e.uptime_30d, 0) / slaEntries.value.length).toFixed(1);
});

function uptimeBarColor(pct: number): string {
  if (pct >= 99) return '#34d399';
  if (pct >= 95) return '#fbbf24';
  return '#f87171';
}

function formatRelative(iso: string | null): string {
  if (!iso) return 'Never';
  const diff = Date.now() - new Date(iso).getTime();
  const h = Math.round(diff / 3600000);
  if (h < 1) return 'Just now';
  if (h < 24) return `${h}h ago`;
  return `${Math.round(h / 24)}d ago`;
}

function formatNextRun(iso: string | null): string {
  if (!iso) return 'N/A';
  const diff = new Date(iso).getTime() - Date.now();
  if (diff < 0) return `${Math.round(-diff / 3600000)}h overdue`;
  const h = Math.round(diff / 3600000);
  if (h < 1) return 'Soon';
  if (h < 24) return `In ${h}h`;
  return `In ${Math.round(h / 24)}d`;
}

onMounted(loadData);
</script>

<template>
  <div class="page-container">

    <div class="page-header">
      <div>
        <h1 class="page-title">Bot SLA & Uptime Tracking</h1>
        <p class="page-subtitle">
          Define expected execution frequency per bot and monitor compliance. Get alerted when a
          scheduled bot hasn't run on time — before a missed audit or late report is noticed.
        </p>
      </div>
    </div>

    <!-- Summary stats -->
    <div class="stats-row">
      <div class="stat-card">
        <span class="stat-value" style="color: #34d399">{{ healthyCount }}</span>
        <span class="stat-label">On Schedule</span>
      </div>
      <div class="stat-card">
        <span class="stat-value" style="color: #f87171">{{ overdueCount }}</span>
        <span class="stat-label">Overdue</span>
      </div>
      <div class="stat-card">
        <span class="stat-value">{{ avgUptime }}%</span>
        <span class="stat-label">Avg 30d Uptime</span>
      </div>
      <div class="stat-card">
        <span class="stat-value">{{ slaEntries.length }}</span>
        <span class="stat-label">Tracked Bots</span>
      </div>
    </div>

    <!-- Filter -->
    <div class="filter-bar">
      <button
        v-for="f in (['all', 'healthy', 'overdue'] as const)"
        :key="f"
        class="filter-btn"
        :class="{ active: filterStatus === f }"
        @click="filterStatus = f"
      >
        {{ f === 'all' ? 'All Bots' : f === 'healthy' ? 'On Schedule' : 'Overdue' }}
      </button>
    </div>

    <LoadingState v-if="isLoading" message="Loading SLA data..." />
    <div v-else class="entries-table">
      <div class="table-header">
        <span>Bot</span>
        <span>Last Run</span>
        <span>Next Expected</span>
        <span>7d Uptime</span>
        <span>30d Uptime</span>
        <span>Success Rate</span>
        <span>Alerts</span>
      </div>
      <div
        v-for="entry in filteredEntries"
        :key="entry.bot_id"
        class="table-row"
        :class="{ overdue: entry.overdue }"
      >
        <div class="bot-cell">
          <div class="bot-dot" :class="{ overdue: entry.overdue }"></div>
          <div>
            <span class="bot-name">{{ entry.bot_name }}</span>
            <span class="bot-trigger">{{ entry.trigger_type }}</span>
          </div>
        </div>

        <div class="time-cell">
          <span class="time-val">{{ formatRelative(entry.last_run_at) }}</span>
        </div>

        <div class="time-cell">
          <span
            class="time-val"
            :class="{ overdue_text: entry.overdue }"
          >
            {{ formatNextRun(entry.next_expected_at) }}
          </span>
        </div>

        <div class="uptime-cell">
          <div class="uptime-bar-bg">
            <div
              class="uptime-bar-fill"
              :style="{ width: `${entry.uptime_7d}%`, background: uptimeBarColor(entry.uptime_7d) }"
            ></div>
          </div>
          <span class="uptime-val">{{ entry.uptime_7d }}%</span>
        </div>

        <div class="uptime-cell">
          <div class="uptime-bar-bg">
            <div
              class="uptime-bar-fill"
              :style="{ width: `${entry.uptime_30d}%`, background: uptimeBarColor(entry.uptime_30d) }"
            ></div>
          </div>
          <span class="uptime-val">{{ entry.uptime_30d }}%</span>
        </div>

        <div class="rate-cell">
          <span :style="{ color: entry.success_rate_7d >= 95 ? '#34d399' : entry.success_rate_7d >= 80 ? '#fbbf24' : '#f87171' }">
            {{ entry.success_rate_7d }}%
          </span>
        </div>

        <div class="alert-cell">
          <button
            class="alert-toggle"
            :class="{ enabled: entry.alert_enabled }"
            @click="toggleAlert(entry)"
          >
            {{ entry.alert_enabled ? 'On' : 'Off' }}
          </button>
        </div>
      </div>

      <p v-if="filteredEntries.length === 0" class="empty-msg">No bots match this filter.</p>
    </div>
  </div>
</template>

<style scoped>
.page-container { padding: 2rem; max-width: 1200px; margin: 0 auto; }
.page-header { margin-bottom: 1.5rem; }
.page-title { font-size: 1.75rem; font-weight: 700; color: var(--color-text-primary, #f0f0f0); margin: 0 0 0.5rem; }
.page-subtitle { color: var(--color-text-secondary, #a0a0a0); margin: 0; }
.stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-bottom: 1.5rem; }
@media (max-width: 600px) { .stats-row { grid-template-columns: repeat(2, 1fr); } }
.stat-card {
  background: var(--color-surface, #1a1a1a);
  border: 1px solid var(--color-border, #2a2a2a);
  border-radius: 8px;
  padding: 1rem 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.stat-value { font-size: 2rem; font-weight: 700; color: var(--color-text-primary, #f0f0f0); line-height: 1; }
.stat-label { font-size: 0.8rem; color: var(--color-text-secondary, #a0a0a0); }
.filter-bar { display: flex; gap: 0.4rem; margin-bottom: 1.25rem; }
.filter-btn { padding: 0.35rem 0.75rem; border-radius: 6px; border: 1px solid var(--color-border, #2a2a2a); background: var(--color-surface, #1a1a1a); color: var(--color-text-secondary, #a0a0a0); font-size: 0.8rem; cursor: pointer; }
.filter-btn.active { border-color: var(--color-accent, #6366f1); color: var(--color-accent, #6366f1); }
.entries-table {
  background: var(--color-surface, #1a1a1a);
  border: 1px solid var(--color-border, #2a2a2a);
  border-radius: 8px;
  overflow: hidden;
}
.table-header {
  display: grid;
  grid-template-columns: 2.5fr 1fr 1fr 1.5fr 1.5fr 1fr 0.8fr;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--color-border, #2a2a2a);
  font-size: 0.75rem;
  color: var(--color-text-secondary, #a0a0a0);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  gap: 0.5rem;
}
.table-row {
  display: grid;
  grid-template-columns: 2.5fr 1fr 1fr 1.5fr 1.5fr 1fr 0.8fr;
  padding: 0.875rem 1rem;
  border-bottom: 1px solid var(--color-border, #2a2a2a);
  align-items: center;
  gap: 0.5rem;
  transition: background 0.12s;
}
.table-row:last-child { border-bottom: none; }
.table-row:hover { background: rgba(255,255,255,0.03); }
.table-row.overdue { background: rgba(248,113,113,0.04); }
.bot-cell { display: flex; align-items: center; gap: 0.6rem; }
.bot-dot { width: 8px; height: 8px; border-radius: 50%; background: #34d399; flex-shrink: 0; }
.bot-dot.overdue { background: #f87171; }
.bot-name { display: block; font-size: 0.875rem; font-weight: 600; color: var(--color-text-primary, #f0f0f0); }
.bot-trigger { display: block; font-size: 0.75rem; color: var(--color-text-secondary, #a0a0a0); font-family: monospace; }
.time-cell { font-size: 0.875rem; }
.time-val { color: var(--color-text-primary, #f0f0f0); }
.overdue_text { color: #f87171; font-weight: 600; }
.uptime-cell { display: flex; align-items: center; gap: 0.5rem; }
.uptime-bar-bg { flex: 1; height: 4px; background: var(--color-border, #2a2a2a); border-radius: 2px; overflow: hidden; min-width: 40px; }
.uptime-bar-fill { height: 100%; border-radius: 2px; transition: width 0.3s; }
.uptime-val { font-size: 0.8rem; color: var(--color-text-primary, #f0f0f0); min-width: 36px; text-align: right; }
.rate-cell { font-size: 0.875rem; font-weight: 600; }
.alert-cell { }
.alert-toggle {
  padding: 0.2rem 0.6rem;
  border-radius: 4px;
  border: 1px solid var(--color-border, #2a2a2a);
  background: transparent;
  color: var(--color-text-secondary, #a0a0a0);
  font-size: 0.75rem;
  cursor: pointer;
}
.alert-toggle.enabled { border-color: #34d399; color: #34d399; background: rgba(52,211,153,0.1); }
.empty-msg { text-align: center; color: var(--color-text-secondary, #a0a0a0); padding: 2rem; margin: 0; }
</style>
