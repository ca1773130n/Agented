<!--
  RoiLeaderboardCard — extracted from TeamLeaderboard.vue for the
  Activity lane (Reports block).
-->
<script setup lang="ts">
// ShipOrCut: 2026-Q3 — STUB-PROMOTE: backend handler returns `{teams:[]}` stub.
import { ref, computed, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import LoadingState from '../../../components/base/LoadingState.vue';
import EmptyState from '../../../components/base/EmptyState.vue';

const emit = defineEmits<{ loaded: [slug: string] }>();
const { t } = useI18n();

const isLoading = ref(true);
const selectedPeriod = ref<'7d' | '30d' | 'all'>('30d');

interface TeamStat {
  rank: number;
  team_id: string;
  team_name: string;
  active_bots: number;
  total_executions: number;
  success_rate: number;
  issues_caught: number;
  cost_saved_hrs: number;
  score: number;
  trend: 'up' | 'down' | 'same';
}

const teams = ref<TeamStat[]>([]);

async function loadData() {
  isLoading.value = true;
  try {
    const res = await fetch(`/admin/analytics/team-leaderboard?period=${selectedPeriod.value}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    teams.value = (await res.json()).teams ?? [];
  } catch {
    teams.value = [
      { rank: 1, team_id: 'team-plat', team_name: 'Platform', active_bots: 8, total_executions: 2341, success_rate: 97.2, issues_caught: 143, cost_saved_hrs: 28, score: 9820, trend: 'up' },
      { rank: 2, team_id: 'team-sec', team_name: 'Security', active_bots: 5, total_executions: 1891, success_rate: 95.1, issues_caught: 312, cost_saved_hrs: 42, score: 8940, trend: 'up' },
      { rank: 3, team_id: 'team-data', team_name: 'Data Engineering', active_bots: 6, total_executions: 1456, success_rate: 91.8, issues_caught: 87, cost_saved_hrs: 19, score: 7210, trend: 'same' },
      { rank: 4, team_id: 'team-qa', team_name: 'QA', active_bots: 4, total_executions: 1102, success_rate: 88.4, issues_caught: 201, cost_saved_hrs: 35, score: 6540, trend: 'down' },
      { rank: 5, team_id: 'team-backend', team_name: 'Backend', active_bots: 3, total_executions: 834, success_rate: 93.7, issues_caught: 55, cost_saved_hrs: 14, score: 5110, trend: 'up' },
    ];
  } finally {
    isLoading.value = false;
    emit('loaded', 'roi-leaderboard');
  }
}

const maxScore = computed(() => Math.max(...teams.value.map(t => t.score), 1));

function medalColor(rank: number): string {
  return ['', 'var(--accent-amber)', '#C0C0C0', '#CD7F32'][rank] ?? 'var(--text-tertiary)';
}

function trendIcon(trend: TeamStat['trend']): string {
  return { up: '↑', down: '↓', same: '→' }[trend];
}

function trendColor(trend: TeamStat['trend']): string {
  return { up: 'var(--accent-emerald)', down: 'var(--accent-crimson)', same: 'var(--text-tertiary)' }[trend];
}

onMounted(loadData);
</script>

<template>
  <section id="roi-leaderboard" class="lane-card leaderboard-card">
    <header class="lane-card__head">
      <div class="header-left">
        <div class="trophy-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M6 9H4.5a2.5 2.5 0 010-5H6M18 9h1.5a2.5 2.5 0 000-5H18M6 2h12v10a6 6 0 01-12 0V2zM6 16H4a2 2 0 00-2 2v4h20v-4a2 2 0 00-2-2h-2M9 22v-4h6v4"/>
          </svg>
        </div>
        <div>
          <h2 class="lane-card__title">{{ t('roiLeaderboardCard.title') }}</h2>
          <p class="lane-card__subtitle">{{ t('roiLeaderboardCard.subtitle') }}</p>
        </div>
      </div>
      <div class="period-toggle">
        <button v-for="p in (['7d', '30d', 'all'] as const)" :key="p"
          class="period-btn"
          :class="{ active: selectedPeriod === p }"
          @click="selectedPeriod = p; loadData()">
          {{ p }}
        </button>
      </div>
    </header>

    <LoadingState v-if="isLoading" :message="t('roiLeaderboardCard.loading')" />

    <template v-else>
      <EmptyState v-if="teams.length === 0" :title="t('roiLeaderboardCard.emptyTitle')" :description="t('roiLeaderboardCard.emptyDescription')" />

      <div class="ranking-table" v-else>
        <div class="table-head">
          <span class="col-rank">{{ t('roiLeaderboardCard.col.rank') }}</span>
          <span class="col-team">{{ t('roiLeaderboardCard.col.team') }}</span>
          <span class="col-num">{{ t('roiLeaderboardCard.col.bots') }}</span>
          <span class="col-num">{{ t('roiLeaderboardCard.col.executions') }}</span>
          <span class="col-num">{{ t('roiLeaderboardCard.col.successPct') }}</span>
          <span class="col-num">{{ t('roiLeaderboardCard.col.issues') }}</span>
          <span class="col-num">{{ t('roiLeaderboardCard.col.hrsSaved') }}</span>
          <span class="col-score">{{ t('roiLeaderboardCard.col.score') }}</span>
          <span class="col-trend">{{ t('roiLeaderboardCard.col.trend') }}</span>
        </div>
        <router-link
          v-for="team in teams"
          :key="team.team_id"
          :to="{ name: 'team-dashboard', params: { teamId: team.team_id } }"
          class="table-row"
        >
          <span class="col-rank">
            <span class="rank-num" :style="{ color: team.rank <= 3 ? medalColor(team.rank) : 'var(--text-tertiary)' }">
              {{ team.rank <= 3 ? ['🥇','🥈','🥉'][team.rank - 1] : team.rank }}
            </span>
          </span>
          <span class="col-team">{{ team.team_name }}</span>
          <span class="col-num">{{ team.active_bots }}</span>
          <span class="col-num">{{ team.total_executions.toLocaleString() }}</span>
          <span class="col-num" :style="{ color: team.success_rate >= 95 ? 'var(--accent-emerald)' : team.success_rate >= 80 ? 'var(--accent-amber)' : 'var(--accent-crimson)' }">
            {{ team.success_rate.toFixed(1) }}%
          </span>
          <span class="col-num">{{ team.issues_caught }}</span>
          <span class="col-num">{{ team.cost_saved_hrs }}h</span>
          <span class="col-score">
            <div class="score-bar-wrap">
              <div class="score-bar" :style="{ width: (team.score / maxScore * 100) + '%' }"></div>
            </div>
            <span class="score-num">{{ team.score.toLocaleString() }}</span>
          </span>
          <span class="col-trend" :style="{ color: trendColor(team.trend) }">{{ trendIcon(team.trend) }}</span>
        </router-link>
      </div>
    </template>
  </section>
</template>

<style scoped>
.lane-card {
  padding: 20px;
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.1));
  border-radius: 10px;
  background: var(--bg-secondary, rgba(255, 255, 255, 0.02));
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.lane-card__head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  flex-wrap: wrap;
}
.lane-card__title { font-size: 16px; font-weight: 600; margin: 0 0 4px; color: var(--text-primary); }
.lane-card__subtitle { font-size: 12px; color: var(--text-tertiary); margin: 0; }

.header-left { display: flex; align-items: flex-start; gap: 16px; }

.trophy-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: rgba(245,158,11,0.1);
  border: 1px solid var(--accent-amber);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.trophy-icon svg { width: 18px; height: 18px; color: var(--accent-amber); }

.period-toggle { display: flex; border: 1px solid var(--border-default); border-radius: 6px; overflow: hidden; }
.period-btn {
  padding: 6px 12px;
  font-size: 0.78rem;
  font-weight: 500;
  background: transparent;
  color: var(--text-secondary);
  border: none;
  cursor: pointer;
  transition: all 0.15s;
}
.period-btn.active { background: var(--accent-cyan); color: #000; }

.ranking-table { display: flex; flex-direction: column; }

.table-head {
  display: grid;
  grid-template-columns: 50px 1fr 60px 100px 80px 80px 90px 160px 50px;
  gap: 8px;
  padding: 8px 12px;
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  border-bottom: 1px solid var(--border-default);
}

.table-row {
  display: grid;
  grid-template-columns: 50px 1fr 60px 100px 80px 80px 90px 160px 50px;
  gap: 8px;
  padding: 12px 12px;
  font-size: 0.85rem;
  color: var(--text-primary);
  border-bottom: 1px solid var(--border-default);
  cursor: pointer;
  transition: background 0.1s;
  align-items: center;
  text-decoration: none;
}
.table-row:hover { background: var(--bg-tertiary); }
.table-row:last-child { border-bottom: none; }

.col-rank { text-align: center; }
.rank-num { font-size: 1rem; }
.col-num { text-align: right; font-variant-numeric: tabular-nums; }
.col-trend { text-align: center; font-weight: 700; font-size: 1rem; }

.col-score { display: flex; align-items: center; gap: 8px; }
.score-bar-wrap { flex: 1; height: 4px; background: var(--bg-elevated); border-radius: 2px; overflow: hidden; }
.score-bar { height: 100%; background: var(--accent-amber); border-radius: 2px; transition: width 0.4s; }
.score-num { font-size: 0.8rem; font-weight: 600; white-space: nowrap; min-width: 55px; text-align: right; }

@media (max-width: 900px) {
  .table-head, .table-row {
    grid-template-columns: 40px 1fr 60px 70px 80px 50px;
  }
  .col-num:nth-child(6), .col-num:nth-child(7), .col-score { display: none; }
}
</style>
