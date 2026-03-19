<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import LoadingState from '../components/base/LoadingState.vue';
import EmptyState from '../components/base/EmptyState.vue';

const router = useRouter();

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
      { rank: 6, team_id: 'team-fe', team_name: 'Frontend', active_bots: 2, total_executions: 421, success_rate: 85.0, issues_caught: 32, cost_saved_hrs: 8, score: 2980, trend: 'same' },
      { rank: 7, team_id: 'team-ml', team_name: 'ML Research', active_bots: 1, total_executions: 198, success_rate: 72.2, issues_caught: 18, cost_saved_hrs: 5, score: 1340, trend: 'down' },
    ];
  } finally {
    isLoading.value = false;
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
  <div class="leaderboard-page">

    <LoadingState v-if="isLoading" message="Loading leaderboard..." />

    <template v-else>
      <!-- Header -->
      <div class="page-header">
        <div class="header-left">
          <div class="trophy-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M6 9H4.5a2.5 2.5 0 010-5H6M18 9h1.5a2.5 2.5 0 000-5H18M6 2h12v10a6 6 0 01-12 0V2zM6 16H4a2 2 0 00-2 2v4h20v-4a2 2 0 00-2-2h-2M9 22v-4h6v4"/>
            </svg>
          </div>
          <div>
            <h1>Team Automation Leaderboard</h1>
            <p>Which teams automate the most, catch the most issues, and have the highest reliability</p>
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
      </div>

      <!-- Empty state -->
      <EmptyState v-if="teams.length === 0" title="No team data available" description="Teams will appear here once they start running automations." />

      <!-- Top 3 Podium -->
      <div class="podium" v-if="teams.length >= 3">
        <div class="podium-slot second">
          <div class="podium-rank" :style="{ color: medalColor(2) }">2</div>
          <div class="podium-avatar">{{ teams[1].team_name.slice(0, 2).toUpperCase() }}</div>
          <div class="podium-name">{{ teams[1].team_name }}</div>
          <div class="podium-score">{{ teams[1].score.toLocaleString() }} pts</div>
          <div class="podium-platform" style="height: 80px;"></div>
        </div>
        <div class="podium-slot first">
          <div class="crown">👑</div>
          <div class="podium-rank" :style="{ color: medalColor(1) }">1</div>
          <div class="podium-avatar gold">{{ teams[0].team_name.slice(0, 2).toUpperCase() }}</div>
          <div class="podium-name">{{ teams[0].team_name }}</div>
          <div class="podium-score">{{ teams[0].score.toLocaleString() }} pts</div>
          <div class="podium-platform" style="height: 110px;"></div>
        </div>
        <div class="podium-slot third">
          <div class="podium-rank" :style="{ color: medalColor(3) }">3</div>
          <div class="podium-avatar">{{ teams[2].team_name.slice(0, 2).toUpperCase() }}</div>
          <div class="podium-name">{{ teams[2].team_name }}</div>
          <div class="podium-score">{{ teams[2].score.toLocaleString() }} pts</div>
          <div class="podium-platform" style="height: 60px;"></div>
        </div>
      </div>

      <!-- Full Ranking Table -->
      <div class="card table-card">
        <div class="table-header">
          <h3>Full Rankings</h3>
          <span class="table-badge">{{ selectedPeriod }}</span>
        </div>
        <div class="ranking-table">
          <div class="table-head">
            <span class="col-rank">Rank</span>
            <span class="col-team">Team</span>
            <span class="col-num">Bots</span>
            <span class="col-num">Executions</span>
            <span class="col-num">Success %</span>
            <span class="col-num">Issues Caught</span>
            <span class="col-num">Hours Saved</span>
            <span class="col-score">Score</span>
            <span class="col-trend">Trend</span>
          </div>
          <div v-for="team in teams" :key="team.team_id" class="table-row" @click="router.push({ name: 'team-dashboard', params: { teamId: team.team_id } })">
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
          </div>
        </div>
      </div>

      <!-- Score explanation -->
      <div class="card scoring-card">
        <h3>How Scores Are Calculated</h3>
        <div class="scoring-grid">
          <div class="scoring-item">
            <span class="scoring-label">Active bots</span>
            <span class="scoring-pts">+500 pts each</span>
          </div>
          <div class="scoring-item">
            <span class="scoring-label">Execution success</span>
            <span class="scoring-pts">+1 pt each</span>
          </div>
          <div class="scoring-item">
            <span class="scoring-label">Issues caught</span>
            <span class="scoring-pts">+10 pts each</span>
          </div>
          <div class="scoring-item">
            <span class="scoring-label">High success rate (≥95%)</span>
            <span class="scoring-pts">+2000 pts bonus</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.leaderboard-page {
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

.card { padding: 24px; }

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  flex-wrap: wrap;
}

.header-left { display: flex; align-items: flex-start; gap: 16px; }

.trophy-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  background: rgba(245,158,11,0.1);
  border: 1px solid var(--accent-amber);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.trophy-icon svg { width: 22px; height: 22px; color: var(--accent-amber); }

.header-left h1 { font-size: 1.2rem; font-weight: 600; color: var(--text-primary); margin-bottom: 4px; }
.header-left p { font-size: 0.85rem; color: var(--text-tertiary); max-width: 400px; }

.period-toggle { display: flex; border: 1px solid var(--border-default); border-radius: 6px; overflow: hidden; }
.period-btn {
  padding: 7px 14px;
  font-size: 0.82rem;
  font-weight: 500;
  background: transparent;
  color: var(--text-secondary);
  border: none;
  cursor: pointer;
  transition: all 0.15s;
}
.period-btn.active { background: var(--accent-amber); color: #000; }

/* Podium */
.podium {
  display: flex;
  align-items: flex-end;
  justify-content: center;
  gap: 0;
  padding: 32px 24px 0;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
}

.podium-slot {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 1;
  max-width: 180px;
  gap: 4px;
}

.crown { font-size: 1.4rem; margin-bottom: 4px; }

.podium-rank { font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; }

.podium-avatar {
  width: 52px;
  height: 52px;
  border-radius: 50%;
  background: var(--bg-elevated);
  border: 2px solid var(--border-default);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.9rem;
  font-weight: 700;
  color: var(--text-primary);
}

.podium-avatar.gold { border-color: var(--accent-amber); background: rgba(245,158,11,0.1); }

.podium-name { font-size: 0.85rem; font-weight: 600; color: var(--text-primary); }
.podium-score { font-size: 0.78rem; color: var(--text-secondary); margin-bottom: 8px; }

.podium-platform {
  width: 100%;
  background: var(--bg-elevated);
  border-top: 2px solid var(--border-default);
}

.podium-slot.first .podium-platform { background: rgba(245,158,11,0.1); border-color: var(--accent-amber); }
.podium-slot.second .podium-platform { background: rgba(192,192,192,0.1); border-color: #C0C0C0; }
.podium-slot.third .podium-platform { background: rgba(205,127,50,0.1); border-color: #CD7F32; }

/* Table */
.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.table-header h3 { font-size: 0.95rem; font-weight: 600; color: var(--text-primary); }
.table-badge {
  font-size: 0.72rem;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 4px;
  background: var(--bg-elevated);
  color: var(--text-tertiary);
  text-transform: uppercase;
}

.ranking-table { display: flex; flex-direction: column; }

.table-head {
  display: grid;
  grid-template-columns: 50px 1fr 60px 100px 80px 110px 90px 160px 50px;
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
  grid-template-columns: 50px 1fr 60px 100px 80px 110px 90px 160px 50px;
  gap: 8px;
  padding: 12px 12px;
  font-size: 0.85rem;
  color: var(--text-primary);
  border-bottom: 1px solid var(--border-default);
  cursor: pointer;
  transition: background 0.1s;
  align-items: center;
}

.table-row:hover { background: var(--bg-tertiary); }
.table-row:last-child { border-bottom: none; }

.col-rank { text-align: center; }
.rank-num { font-size: 1rem; }
.col-num { text-align: right; font-variant-numeric: tabular-nums; }
.col-trend { text-align: center; font-weight: 700; font-size: 1rem; }

.col-score {
  display: flex;
  align-items: center;
  gap: 8px;
}

.score-bar-wrap { flex: 1; height: 4px; background: var(--bg-elevated); border-radius: 2px; overflow: hidden; }
.score-bar { height: 100%; background: var(--accent-amber); border-radius: 2px; transition: width 0.4s; }
.score-num { font-size: 0.8rem; font-weight: 600; white-space: nowrap; min-width: 55px; text-align: right; }

/* Scoring */
.scoring-card h3 { font-size: 0.9rem; font-weight: 600; color: var(--text-primary); margin-bottom: 16px; }

.scoring-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
}

.scoring-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  background: var(--bg-tertiary);
  border-radius: 6px;
  border: 1px solid var(--border-default);
}

.scoring-label { font-size: 0.82rem; color: var(--text-secondary); }
.scoring-pts { font-size: 0.82rem; font-weight: 600; color: var(--accent-amber); }

@media (max-width: 900px) {
  .table-head, .table-row {
    grid-template-columns: 40px 1fr 60px 70px 80px 50px;
  }

  .col-num:nth-child(6), .col-num:nth-child(7), .col-score { display: none; }
}
</style>
