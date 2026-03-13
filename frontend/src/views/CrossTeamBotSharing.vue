<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { teamApi, triggerApi, ApiError } from '../services/api';
import type { Team, Trigger } from '../services/api';

const router = useRouter();

const tab = ref<'browse' | 'mine'>('browse');
const searchQuery = ref('');
const isLoading = ref(true);
const loadError = ref<string | null>(null);

const teams = ref<Team[]>([]);
const triggers = ref<Trigger[]>([]);

interface TriggerWithTeam {
  trigger: Trigger;
  teamName: string;
  teamId: string | null;
}

onMounted(async () => {
  try {
    const [tResp, trResp] = await Promise.all([
      teamApi.list(),
      triggerApi.list(),
    ]);
    teams.value = tResp.teams;
    triggers.value = trResp.triggers;
  } catch (err) {
    if (err instanceof ApiError) {
      loadError.value = `Failed to load: ${err.message}`;
    } else {
      loadError.value = 'An unexpected error occurred while loading data.';
    }
  } finally {
    isLoading.value = false;
  }
});

const triggersWithTeams = computed<TriggerWithTeam[]>(() => {
  return triggers.value.map((trigger) => {
    const team = teams.value.find((t) => t.id === trigger.team_id);
    return {
      trigger,
      teamName: team?.name || 'Unassigned',
      teamId: trigger.team_id || null,
    };
  });
});

const filtered = computed(() => {
  const q = searchQuery.value.toLowerCase();
  if (!q) return triggersWithTeams.value;
  return triggersWithTeams.value.filter(
    (item) =>
      item.trigger.name.toLowerCase().includes(q) ||
      item.teamName.toLowerCase().includes(q) ||
      (item.trigger.trigger_source || '').toLowerCase().includes(q)
  );
});

const myTeamTriggers = computed(() => {
  // Group triggers by team
  const grouped = new Map<string, { team: Team; triggers: Trigger[] }>();
  for (const team of teams.value) {
    grouped.set(team.id, { team, triggers: [] });
  }
  for (const trigger of triggers.value) {
    if (trigger.team_id && grouped.has(trigger.team_id)) {
      grouped.get(trigger.team_id)!.triggers.push(trigger);
    }
  }
  return Array.from(grouped.values()).filter((g) => g.triggers.length > 0);
});
</script>

<template>
  <div class="bot-sharing">
    <AppBreadcrumb :items="[
      { label: 'Bots', action: () => router.push({ name: 'bots' }) },
      { label: 'Bot Sharing' },
    ]" />

    <PageHeader
      title="Cross-Team Bot Sharing"
      subtitle="Browse triggers assigned to teams across your organization."
    />

    <!-- Loading state -->
    <div v-if="isLoading" class="card" style="padding: 48px; text-align: center;">
      <span style="color: var(--text-tertiary); font-size: 0.85rem;">Loading teams and triggers...</span>
    </div>

    <!-- Error state -->
    <div v-else-if="loadError" class="card" style="padding: 48px; text-align: center;">
      <span style="color: #ef4444; font-size: 0.85rem;">{{ loadError }}</span>
    </div>

    <template v-else>
      <div class="tab-bar">
        <button class="tab-btn" :class="{ active: tab === 'browse' }" @click="tab = 'browse'">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          Browse Triggers
        </button>
        <button class="tab-btn" :class="{ active: tab === 'mine' }" @click="tab = 'mine'">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
            <circle cx="12" cy="7" r="4"/><path d="M5 21v-2a7 7 0 0 1 14 0v2"/>
          </svg>
          Team Assignments
        </button>
      </div>

      <template v-if="tab === 'browse'">
        <div class="search-row">
          <input
            v-model="searchQuery"
            type="text"
            class="search-input"
            placeholder="Search by trigger name, team, or source..."
          />
          <span class="search-count">{{ filtered.length }} trigger{{ filtered.length !== 1 ? 's' : '' }}</span>
        </div>

        <!-- Empty state -->
        <div v-if="filtered.length === 0" class="card" style="padding: 48px; text-align: center;">
          <span style="color: var(--text-tertiary); font-size: 0.85rem;">No triggers match your search.</span>
        </div>

        <div v-else class="bots-grid">
          <div v-for="item in filtered" :key="item.trigger.id" class="card bot-card">
            <div class="bot-card-header">
              <div class="bot-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="20" height="20">
                  <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                  <path d="M9 9h6M9 12h6M9 15h4"/>
                </svg>
              </div>
              <div class="bot-title-area">
                <h3 class="bot-card-name">{{ item.trigger.name }}</h3>
                <span class="bot-team">{{ item.teamName }}</span>
              </div>
              <span class="bot-version">{{ item.trigger.trigger_source || 'manual' }}</span>
            </div>

            <p class="bot-desc">
              Backend: {{ item.trigger.backend_type || 'claude' }}
              <template v-if="item.trigger.model"> | Model: {{ item.trigger.model }}</template>
            </p>

            <div class="bot-tags">
              <span class="tag">{{ item.trigger.trigger_source || 'manual' }}</span>
              <span v-if="item.trigger.enabled" class="tag">enabled</span>
              <span v-else class="tag" style="color: #ef4444;">disabled</span>
              <span v-if="item.trigger.execution_mode" class="tag">{{ item.trigger.execution_mode }}</span>
            </div>

            <div class="bot-stats">
              <span class="stat">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                {{ item.trigger.trigger_source || 'manual' }}
              </span>
              <span class="stat-date">ID: {{ item.trigger.id }}</span>
            </div>
          </div>
        </div>
      </template>

      <template v-else>
        <!-- Empty state for team assignments -->
        <div v-if="myTeamTriggers.length === 0" class="card" style="padding: 48px; text-align: center;">
          <span style="color: var(--text-tertiary); font-size: 0.85rem;">No triggers are assigned to teams yet.</span>
        </div>

        <div v-for="group in myTeamTriggers" :key="group.team.id" class="card">
          <div class="card-header">
            <h3>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
                <circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/>
                <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/>
                <line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>
              </svg>
              {{ group.team.name }}
            </h3>
          </div>
          <div class="my-bots-list">
            <div v-for="trigger in group.triggers" :key="trigger.id" class="my-bot-row">
              <div class="my-bot-info">
                <span class="my-bot-name">{{ trigger.name }}</span>
                <span class="my-bot-subs">{{ trigger.trigger_source || 'manual' }} trigger</span>
              </div>
              <div class="my-bot-shared">
                <span class="shared-tag">{{ trigger.backend_type || 'claude' }}</span>
                <span v-if="trigger.enabled" class="shared-tag">enabled</span>
                <span v-else class="not-shared">disabled</span>
              </div>
              <div class="my-bot-actions">
                <button
                  class="btn btn-sm btn-secondary"
                  @click="router.push({ name: 'trigger-detail', params: { id: trigger.id } })"
                >
                  View
                </button>
              </div>
            </div>
          </div>
        </div>
      </template>
    </template>
  </div>
</template>

<style scoped>
.bot-sharing {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.tab-bar {
  display: flex;
  gap: 4px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 10px;
  padding: 4px;
  width: fit-content;
}

.tab-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 16px;
  border-radius: 7px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 0.875rem;
  cursor: pointer;
  transition: all 0.15s;
}

.tab-btn.active {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.search-row {
  display: flex;
  align-items: center;
  gap: 14px;
}

.search-input {
  flex: 1;
  padding: 9px 14px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.875rem;
}

.search-input:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.search-count {
  font-size: 0.8rem;
  color: var(--text-tertiary);
  white-space: nowrap;
}

.bots-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 16px;
}

.card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-default);
}

.card-header h3 {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.card-header h3 svg { color: var(--accent-cyan); }

.bot-card {
  padding: 0;
  display: flex;
  flex-direction: column;
}

.bot-card-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 18px 18px 14px;
}

.bot-icon {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: var(--accent-cyan);
}

.bot-title-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.bot-card-name {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.bot-team {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.bot-version {
  font-size: 0.72rem;
  color: var(--text-tertiary);
  font-family: monospace;
  background: var(--bg-tertiary);
  padding: 2px 6px;
  border-radius: 4px;
}

.bot-desc {
  font-size: 0.85rem;
  color: var(--text-secondary);
  padding: 0 18px;
  margin: 0 0 12px;
  line-height: 1.5;
}

.bot-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 0 18px 12px;
}

.tag {
  font-size: 0.7rem;
  padding: 2px 8px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 4px;
  color: var(--text-tertiary);
}

.bot-stats {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 18px 12px;
}

.stat {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 0.78rem;
  color: var(--text-tertiary);
}

.stat-date {
  font-size: 0.72rem;
  color: var(--text-muted);
  margin-left: auto;
}

.my-bots-list {
  display: flex;
  flex-direction: column;
}

.my-bot-row {
  display: grid;
  grid-template-columns: 1fr 1fr auto;
  gap: 16px;
  align-items: center;
  padding: 14px 24px;
  border-bottom: 1px solid var(--border-subtle);
}

.my-bot-row:last-child { border-bottom: none; }

.my-bot-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.my-bot-name {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-primary);
}

.my-bot-subs {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.my-bot-shared {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.shared-tag {
  font-size: 0.72rem;
  padding: 2px 8px;
  background: rgba(6, 182, 212, 0.1);
  border: 1px solid rgba(6, 182, 212, 0.2);
  border-radius: 4px;
  color: var(--accent-cyan);
}

.not-shared {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.btn {
  display: flex;
  align-items: center;
  gap: 5px;
  border-radius: 6px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}

.btn-sm { padding: 6px 12px; font-size: 0.8rem; }

.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }

.btn-secondary {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
}

.btn-secondary:hover { border-color: var(--accent-cyan); color: var(--text-primary); }

.btn-subscribed {
  background: rgba(6, 182, 212, 0.1);
  border: 1px solid rgba(6, 182, 212, 0.3);
  color: var(--accent-cyan);
}

.btn-forked {
  background: rgba(52, 211, 153, 0.1);
  border: 1px solid rgba(52, 211, 153, 0.3);
  color: #34d399;
  cursor: default;
}

@media (max-width: 768px) {
  .bots-grid { grid-template-columns: 1fr; }
}
</style>
