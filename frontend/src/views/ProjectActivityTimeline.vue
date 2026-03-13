<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { activityFeedApi } from '../services/api/activity-feed';
const router = useRouter();

type ActivityType = 'bot_run' | 'trigger_fired' | 'config_changed' | 'team_action' | 'execution_failed' | 'approval';

interface Activity {
  id: string;
  type: ActivityType;
  title: string;
  description: string;
  actor: string;
  timestamp: string;
  projectId: string;
  metadata?: Record<string, string | number>;
}

const activities = ref<Activity[]>([]);

onMounted(async () => {
  try {
    const response = await activityFeedApi.list({ limit: 200 });
    activities.value = response.activities as Activity[];
  } catch {
    // Leave activities empty on error; the empty-state UI will display
  }
});

const filterType = ref<ActivityType | ''>('');
const filterProject = ref('');
const searchText = ref('');

const projects = computed(() => [...new Set(activities.value.map(a => a.projectId))]);

const filtered = computed(() => activities.value.filter(a => {
  if (filterType.value && a.type !== filterType.value) return false;
  if (filterProject.value && a.projectId !== filterProject.value) return false;
  if (searchText.value && !a.title.toLowerCase().includes(searchText.value.toLowerCase()) && !a.description.toLowerCase().includes(searchText.value.toLowerCase())) return false;
  return true;
}));

const activityTypes: { value: ActivityType, label: string }[] = [
  { value: 'bot_run', label: 'Bot Runs' },
  { value: 'trigger_fired', label: 'Triggers' },
  { value: 'config_changed', label: 'Config Changes' },
  { value: 'team_action', label: 'Team Actions' },
  { value: 'execution_failed', label: 'Failures' },
  { value: 'approval', label: 'Approvals' },
];

function typeIcon(t: ActivityType) {
  return { bot_run: '⚡', trigger_fired: '🔔', config_changed: '⚙️', team_action: '👥', execution_failed: '❌', approval: '⏸' }[t];
}

function typeColor(t: ActivityType) {
  return { bot_run: 'var(--accent-cyan)', trigger_fired: '#a78bfa', config_changed: '#fbbf24', team_action: '#60a5fa', execution_failed: '#ef4444', approval: '#f59e0b' }[t];
}

function formatDate(ts: string) {
  return new Date(ts).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function groupByDate(items: Activity[]) {
  const groups: { date: string; items: Activity[] }[] = [];
  const seen = new Map<string, Activity[]>();
  for (const item of items) {
    const date = new Date(item.timestamp).toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });
    if (!seen.has(date)) { seen.set(date, []); groups.push({ date, items: seen.get(date)! }); }
    seen.get(date)!.push(item);
  }
  return groups;
}

const groupedActivities = computed(() => groupByDate(filtered.value));
</script>

<template>
  <div class="activity-timeline">
    <AppBreadcrumb :items="[
      { label: 'Projects', action: () => router.push({ name: 'projects' }) },
      { label: 'Activity Timeline' },
    ]" />

    <PageHeader
      title="Project Activity Timeline"
      subtitle="Unified chronological feed of bot runs, trigger firings, config changes, and team actions."
    />

    <!-- Filters -->
    <div class="filters-bar card">
      <div class="filter-row">
        <input v-model="searchText" class="search-input" placeholder="Search activities..." />
        <select v-model="filterProject" class="select-input">
          <option value="">All projects</option>
          <option v-for="p in projects" :key="p" :value="p">{{ p }}</option>
        </select>
        <button
          v-if="filterType || filterProject || searchText"
          class="btn btn-ghost btn-sm"
          @click="filterType = ''; filterProject = ''; searchText = '';"
        >Clear</button>
      </div>
      <div class="type-pills">
        <button
          :class="['type-pill', { active: filterType === '' }]"
          @click="filterType = ''"
        >All</button>
        <button
          v-for="t in activityTypes"
          :key="t.value"
          :class="['type-pill', { active: filterType === t.value }]"
          @click="filterType = t.value"
        >{{ t.label }}</button>
      </div>
    </div>

    <!-- Timeline -->
    <div class="timeline">
      <div v-if="filtered.length === 0" class="empty-state card">
        <p>No activities match your filters.</p>
      </div>

      <div v-for="group in groupedActivities" :key="group.date" class="date-group">
        <div class="date-separator">{{ group.date }}</div>

        <div class="activities-list">
          <div v-for="activity in group.items" :key="activity.id" class="activity-item card">
            <div class="activity-icon" :style="{ background: `${typeColor(activity.type)}15`, color: typeColor(activity.type) }">
              {{ typeIcon(activity.type) }}
            </div>
            <div class="activity-content">
              <div class="activity-title">{{ activity.title }}</div>
              <div class="activity-desc">{{ activity.description }}</div>
              <div class="activity-meta">
                <span class="activity-actor">{{ activity.actor }}</span>
                <span class="activity-time">{{ formatDate(activity.timestamp) }}</span>
                <span class="activity-project">{{ activity.projectId }}</span>
              </div>
            </div>
            <div class="activity-type-badge" :style="{ background: `${typeColor(activity.type)}15`, color: typeColor(activity.type) }">
              {{ activity.type.replace('_', ' ') }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.activity-timeline { display: flex; flex-direction: column; gap: 20px; animation: fadeIn 0.4s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

.card { background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 12px; overflow: hidden; }

.filters-bar { padding: 16px 20px; display: flex; flex-direction: column; gap: 12px; }
.filter-row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.search-input { flex: 1; min-width: 200px; padding: 7px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 7px; color: var(--text-primary); font-size: 0.82rem; }
.search-input:focus { outline: none; border-color: var(--accent-cyan); }
.search-input::placeholder { color: var(--text-muted); }
.select-input { padding: 7px 10px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 7px; color: var(--text-primary); font-size: 0.8rem; }
.type-pills { display: flex; gap: 6px; flex-wrap: wrap; }
.type-pill { padding: 5px 12px; border-radius: 16px; font-size: 0.75rem; font-weight: 500; border: 1px solid var(--border-default); background: var(--bg-tertiary); color: var(--text-secondary); cursor: pointer; transition: all 0.15s; }
.type-pill.active { background: var(--accent-cyan); color: #000; border-color: var(--accent-cyan); }
.type-pill:hover:not(.active) { border-color: var(--accent-cyan); color: var(--accent-cyan); }

.timeline { display: flex; flex-direction: column; gap: 16px; }

.date-separator { font-size: 0.78rem; font-weight: 600; color: var(--text-tertiary); padding: 4px 0; border-bottom: 1px solid var(--border-subtle); margin-bottom: 8px; }

.activities-list { display: flex; flex-direction: column; gap: 8px; }

.activity-item { display: flex; align-items: flex-start; gap: 14px; padding: 14px 16px; }
.activity-icon { width: 36px; height: 36px; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 1rem; flex-shrink: 0; }
.activity-content { flex: 1; min-width: 0; }
.activity-title { font-size: 0.85rem; font-weight: 600; color: var(--text-primary); margin-bottom: 3px; }
.activity-desc { font-size: 0.78rem; color: var(--text-secondary); margin-bottom: 6px; line-height: 1.4; }
.activity-meta { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.activity-actor { font-size: 0.72rem; color: var(--text-tertiary); font-weight: 500; }
.activity-time { font-size: 0.7rem; color: var(--text-muted); }
.activity-project { font-size: 0.7rem; color: var(--text-muted); font-family: monospace; }
.activity-type-badge { font-size: 0.68rem; font-weight: 700; padding: 3px 8px; border-radius: 4px; flex-shrink: 0; text-transform: capitalize; }

.empty-state { padding: 48px 24px; text-align: center; }
.empty-state p { font-size: 0.875rem; color: var(--text-tertiary); margin: 0; }

.btn { display: flex; align-items: center; padding: 6px 12px; border-radius: 6px; font-size: 0.78rem; font-weight: 500; cursor: pointer; border: none; transition: all 0.15s; }
.btn-ghost { background: var(--bg-tertiary); border: 1px solid var(--border-default); color: var(--text-secondary); }
.btn-ghost:hover { border-color: var(--accent-cyan); color: var(--accent-cyan); }
.btn-sm { padding: 5px 10px; font-size: 0.75rem; }

.date-group { }
</style>
