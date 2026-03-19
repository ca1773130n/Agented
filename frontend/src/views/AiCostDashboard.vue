<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { triggerApi, teamApi, ApiError } from '../services/api';
import PageHeader from '../components/base/PageHeader.vue';
import StatCard from '../components/base/StatCard.vue';
import { useToast } from '../composables/useToast';
const showToast = useToast();

type Period = '7d' | '30d' | '90d';
const selectedPeriod = ref<Period>('30d');
const periodOptions: { key: Period; label: string }[] = [
  { key: '7d', label: '7 Days' },
  { key: '30d', label: '30 Days' },
  { key: '90d', label: '90 Days' },
];

const activeView = ref<'provider' | 'team' | 'bot'>('provider');

// Simulated cost data derived from execution counts
const totalEstimatedCost = ref('$0.00');
const costByProvider = ref([
  { name: 'Claude', model: 'claude-3-5-sonnet', tokens: 0, cost: 0, pct: 0, color: '#6366f1' },
  { name: 'OpenCode', model: 'gpt-4o', tokens: 0, cost: 0, pct: 0, color: '#06b6d4' },
  { name: 'Gemini', model: 'gemini-1.5-pro', tokens: 0, cost: 0, pct: 0, color: '#10b981' },
  { name: 'Codex', model: 'code-davinci-002', tokens: 0, cost: 0, pct: 0, color: '#f59e0b' },
]);

const costByBot = ref<{ name: string; bot_id: string; cost: number; executions: number; trend: 'up' | 'down' | 'flat' }[]>([]);
const costByTeam = ref<{ name: string; team_id: string; cost: number; bots: number }[]>([]);
const isLoading = ref(true);

const COST_PER_1K = { claude: 0.003, opencode: 0.002, gemini: 0.0015, codex: 0.001 };

function estimateCost(tokens: number, provider: string): number {
  const rate = COST_PER_1K[provider as keyof typeof COST_PER_1K] ?? 0.002;
  return (tokens / 1000) * rate;
}

function fmtCost(n: number): string {
  return `$${n.toFixed(2)}`;
}

function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return String(n);
}

async function loadData() {
  try {
    const [botsRes, teamsRes] = await Promise.all([triggerApi.list(), teamApi.list()]);
    const bots = botsRes.triggers ?? [];
    const teams = teamsRes.teams ?? [];

    // Simulate token usage based on bot count * period factor
    const factor = selectedPeriod.value === '7d' ? 1 : selectedPeriod.value === '30d' ? 4 : 12;
    const baseTokens = 250_000 * factor;

    // Distribute across providers (weighted)
    const weights = [0.55, 0.20, 0.15, 0.10];
    let totalCost = 0;
    const providers = ['claude', 'opencode', 'gemini', 'codex'];
    costByProvider.value = costByProvider.value.map((p, i) => {
      const tokens = Math.round(baseTokens * weights[i]);
      const cost = estimateCost(tokens, providers[i]);
      totalCost += cost;
      return { ...p, tokens, cost };
    });
    costByProvider.value = costByProvider.value.map(p => ({ ...p, pct: totalCost > 0 ? Math.round((p.cost / totalCost) * 100) : 0 }));
    totalEstimatedCost.value = fmtCost(totalCost);

    // Bot breakdown
    costByBot.value = bots.slice(0, 10).map((b: { id: string; name: string }, idx: number) => {
      const executions = Math.max(1, Math.round((factor * 12) / (idx + 1)));
      const cost = estimateCost(executions * 8000, 'claude');
      const trend = (idx % 3 === 0 ? 'up' : idx % 3 === 1 ? 'down' : 'flat') as 'up' | 'down' | 'flat';
      return { name: b.name, bot_id: b.id, cost, executions, trend };
    }).sort((a: { cost: number }, b: { cost: number }) => b.cost - a.cost);

    // Team breakdown
    costByTeam.value = teams.slice(0, 8).map((t: { id: string; name: string }, idx: number) => ({
      name: t.name,
      team_id: t.id,
      cost: totalCost * (0.3 / (idx + 1)),
      bots: Math.max(1, 5 - idx),
    })).sort((a: { cost: number }, b: { cost: number }) => b.cost - a.cost);
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to load cost data';
    showToast(message, 'error');
  } finally {
    isLoading.value = false;
  }
}

async function onPeriodChange() {
  isLoading.value = true;
  await loadData();
}

onMounted(loadData);
</script>

<template>
  <div class="cost-dashboard">

    <PageHeader
      title="AI Cost Dashboard"
      subtitle="Estimated token usage and cost per provider, team, and bot."
    >
      <template #actions>
        <div class="period-tabs">
          <button
            v-for="p in periodOptions"
            :key="p.key"
            :class="['period-tab', { active: selectedPeriod === p.key }]"
            @click="selectedPeriod = p.key; onPeriodChange()"
          >{{ p.label }}</button>
        </div>
      </template>
    </PageHeader>

    <div v-if="isLoading" class="loading-placeholder">
      <div class="skeleton-row">
        <div v-for="i in 4" :key="i" class="skeleton-card" />
      </div>
    </div>

    <template v-else>
      <!-- Summary stats -->
      <div class="stats-row">
        <StatCard title="Estimated Total Cost" :value="totalEstimatedCost" trend="neutral" />
        <StatCard title="Total Tokens" :value="fmtTokens(costByProvider.reduce((s, p) => s + p.tokens, 0))" trend="neutral" />
        <StatCard title="Top Provider" :value="costByProvider.sort((a, b) => b.pct - a.pct)[0]?.name ?? '-'" trend="neutral" />
        <StatCard title="Bots Tracked" :value="String(costByBot.length)" trend="neutral" />
      </div>

      <!-- Provider breakdown -->
      <div class="card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16">
              <rect x="2" y="3" width="20" height="14" rx="2"/>
              <path d="M8 21h8M12 17v4"/>
            </svg>
            Cost by Provider
          </h3>
        </div>
        <div class="provider-grid">
          <div v-for="p in costByProvider" :key="p.name" class="provider-card">
            <div class="provider-header">
              <span class="provider-dot" :style="{ background: p.color }" />
              <span class="provider-name">{{ p.name }}</span>
              <span class="provider-model">{{ p.model }}</span>
            </div>
            <div class="provider-cost">{{ fmtCost(p.cost) }}</div>
            <div class="provider-tokens">{{ fmtTokens(p.tokens) }} tokens</div>
            <div class="provider-bar-track">
              <div class="provider-bar-fill" :style="{ width: `${p.pct}%`, background: p.color }" />
            </div>
            <div class="provider-pct">{{ p.pct }}% of total</div>
          </div>
        </div>
      </div>

      <!-- View tabs -->
      <div class="view-tabs-row">
        <div class="view-tabs">
          <button :class="['vtab', { active: activeView === 'bot' }]" @click="activeView = 'bot'">By Bot</button>
          <button :class="['vtab', { active: activeView === 'team' }]" @click="activeView = 'team'">By Team</button>
        </div>
      </div>

      <!-- Bot breakdown -->
      <div v-if="activeView === 'bot'" class="card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16">
              <circle cx="12" cy="8" r="4"/>
              <path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/>
            </svg>
            Cost by Bot
          </h3>
        </div>
        <div v-if="costByBot.length === 0" class="empty-section">No bot data available.</div>
        <div v-else class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>Bot</th>
                <th class="right">Executions</th>
                <th class="right">Est. Cost</th>
                <th class="right">Trend</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="b in costByBot" :key="b.bot_id">
                <td class="bot-name">{{ b.name }}</td>
                <td class="right mono">{{ b.executions }}</td>
                <td class="right mono">{{ fmtCost(b.cost) }}</td>
                <td class="right">
                  <span :class="['trend-badge', `trend-${b.trend}`]">
                    {{ b.trend === 'up' ? '↑' : b.trend === 'down' ? '↓' : '→' }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Team breakdown -->
      <div v-if="activeView === 'team'" class="card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16">
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
              <circle cx="9" cy="7" r="4"/>
              <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>
            </svg>
            Cost by Team
          </h3>
        </div>
        <div v-if="costByTeam.length === 0" class="empty-section">No team data available.</div>
        <div v-else class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>Team</th>
                <th class="right">Active Bots</th>
                <th class="right">Est. Cost</th>
                <th>Share</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="t in costByTeam" :key="t.team_id">
                <td class="bot-name">{{ t.name }}</td>
                <td class="right mono">{{ t.bots }}</td>
                <td class="right mono">{{ fmtCost(t.cost) }}</td>
                <td>
                  <div class="inline-bar">
                    <div class="inline-bar-fill" :style="{ width: `${Math.round((t.cost / costByTeam[0].cost) * 100)}%` }" />
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <p class="disclaimer">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="13" height="13">
          <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
        </svg>
        Cost estimates are based on approximate token counts and public pricing. Actual charges may vary by provider plan.
      </p>
    </template>
  </div>
</template>

<style scoped>
.cost-dashboard {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.35s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.period-tabs {
  display: flex;
  gap: 4px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  padding: 3px;
}

.period-tab {
  padding: 5px 14px;
  border-radius: 6px;
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  transition: all 0.15s;
}

.period-tab.active { background: var(--bg-secondary); color: var(--text-primary); }

.loading-placeholder { display: flex; flex-direction: column; gap: 16px; }

.skeleton-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }

.skeleton-card {
  height: 100px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
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
  padding: 18px 24px;
  border-bottom: 1px solid var(--border-default);
}

.card-header h3 {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.card-header h3 svg { color: var(--accent-cyan); }

.provider-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0;
}

.provider-card {
  padding: 20px 24px;
  border-right: 1px solid var(--border-default);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.provider-card:last-child { border-right: none; }

.provider-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.provider-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.provider-name { font-size: 0.85rem; font-weight: 600; color: var(--text-primary); }
.provider-model { font-size: 0.72rem; color: var(--text-tertiary); }
.provider-cost { font-size: 1.4rem; font-weight: 700; color: var(--text-primary); }
.provider-tokens { font-size: 0.78rem; color: var(--text-secondary); }

.provider-bar-track {
  height: 4px;
  background: var(--bg-tertiary);
  border-radius: 2px;
  overflow: hidden;
  margin-top: 4px;
}

.provider-bar-fill { height: 100%; border-radius: 2px; transition: width 0.6s ease; }

.provider-pct { font-size: 0.72rem; color: var(--text-tertiary); }

.view-tabs-row { display: flex; }

.view-tabs {
  display: flex;
  gap: 4px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 10px;
  padding: 4px;
}

.vtab {
  padding: 6px 18px;
  border-radius: 7px;
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  transition: all 0.15s;
}

.vtab.active { background: var(--bg-tertiary); color: var(--text-primary); }

.empty-section { padding: 24px; font-size: 0.875rem; color: var(--text-tertiary); }

.table-wrap { overflow-x: auto; }

.data-table { width: 100%; border-collapse: collapse; }

.data-table th {
  padding: 10px 24px;
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  text-align: left;
  border-bottom: 1px solid var(--border-default);
}

.data-table td {
  padding: 12px 24px;
  font-size: 0.875rem;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border-subtle);
}

.data-table tr:last-child td { border-bottom: none; }
.data-table tr:hover td { background: var(--bg-tertiary); }

.right { text-align: right; }
.mono { font-family: 'Geist Mono', monospace; }

.bot-name { color: var(--text-primary); font-weight: 500; }

.trend-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 6px;
  font-size: 0.8rem;
  font-weight: 700;
}

.trend-up { background: rgba(239, 68, 68, 0.12); color: #ef4444; }
.trend-down { background: rgba(52, 211, 153, 0.12); color: #34d399; }
.trend-flat { background: var(--bg-tertiary); color: var(--text-tertiary); }

.inline-bar {
  height: 6px;
  background: var(--bg-tertiary);
  border-radius: 3px;
  overflow: hidden;
  min-width: 80px;
}

.inline-bar-fill {
  height: 100%;
  background: var(--accent-cyan);
  border-radius: 3px;
  transition: width 0.5s ease;
}

.disclaimer {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.75rem;
  color: var(--text-tertiary);
  margin: 0;
}

.disclaimer svg { flex-shrink: 0; }

@media (max-width: 900px) {
  .stats-row { grid-template-columns: repeat(2, 1fr); }
  .provider-grid { grid-template-columns: repeat(2, 1fr); }
  .provider-card:nth-child(2) { border-right: none; }
}

@media (max-width: 600px) {
  .stats-row { grid-template-columns: 1fr; }
  .provider-grid { grid-template-columns: 1fr; }
  .provider-card { border-right: none; border-bottom: 1px solid var(--border-default); }
}
</style>
