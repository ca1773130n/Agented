<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { analyticsApi } from '../services/api/analytics';
import type { TeamInsightData, OrgFindingData, RepoRiskData } from '../services/api/types';

const showToast = useToast();

type RiskLevel = 'critical' | 'high' | 'medium' | 'low';
type SortKey = 'executions' | 'findings' | 'successRate' | 'riskScore';

// Keep local interface aliases for template compatibility
type TeamInsight = TeamInsightData;
type OrgFinding = OrgFindingData & { severity: RiskLevel };
type RepoRisk = RepoRiskData;

const sortKey = ref<SortKey>('executions');
const selectedTeamId = ref<string | null>(null);

const teams = ref<TeamInsight[]>([]);
const orgFindings = ref<OrgFinding[]>([]);
const topRiskyRepos = ref<RepoRisk[]>([]);

onMounted(async () => {
  try {
    const data = await analyticsApi.fetchCrossTeamInsights();
    teams.value = data.teams;
    orgFindings.value = data.org_findings as OrgFinding[];
    topRiskyRepos.value = data.top_risky_repos;
  } catch {
    showToast('Failed to load cross-team insights', 'error');
  }
});

const sortedTeams = computed(() => {
  const sorted = [...teams.value];
  if (sortKey.value === 'executions') sorted.sort((a, b) => b.totalExecutions - a.totalExecutions);
  else if (sortKey.value === 'findings') sorted.sort((a, b) => b.findingsCount - a.findingsCount);
  else if (sortKey.value === 'successRate') sorted.sort((a, b) => b.successRate - a.successRate);
  else if (sortKey.value === 'riskScore') sorted.sort((a, b) => b.riskScore - a.riskScore);
  return sorted;
});

const orgTotals = computed(() => ({
  executions: teams.value.reduce((s, t) => s + t.totalExecutions, 0),
  findings: teams.value.reduce((s, t) => s + t.findingsCount, 0),
  critical: teams.value.reduce((s, t) => s + t.criticalFindings, 0),
  avgSuccess: teams.value.length
    ? teams.value.reduce((s, t) => s + t.successRate, 0) / teams.value.length
    : 0,
}));

function riskColor(score: number): string {
  if (score >= 70) return 'var(--accent-red)';
  if (score >= 40) return 'var(--accent-amber)';
  return 'var(--accent-green)';
}

function severityColor(sev: RiskLevel): string {
  const map: Record<RiskLevel, string> = {
    critical: 'var(--accent-red)',
    high: 'var(--accent-amber)',
    medium: 'var(--accent-blue)',
    low: 'var(--text-muted)',
  };
  return map[sev];
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function changeColor(pct: number): string {
  if (pct > 0) return 'var(--accent-green)';
  if (pct < 0) return 'var(--accent-red)';
  return 'var(--text-muted)';
}

function exportReport() {
  showToast('Cross-team insights report exported', 'success');
}
</script>

<template>
  <div class="page-container">
    <AppBreadcrumb :items="[{ label: 'Dashboards' }, { label: 'Cross-Team Insights' }]" />
    <PageHeader
      title="Cross-Team Insights Dashboard"
      subtitle="Org-level view of automation activity, common findings, and risk signals across all teams"
    >
      <template #actions>
        <button class="btn-secondary" @click="exportReport">↓ Export Report</button>
      </template>
    </PageHeader>

    <!-- Org-level stats -->
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-label">Total Executions</div>
        <div class="stat-value">{{ orgTotals.executions.toLocaleString() }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Total Findings</div>
        <div class="stat-value" :style="{ color: orgTotals.findings > 50 ? 'var(--accent-amber)' : 'var(--text-primary)' }">
          {{ orgTotals.findings }}
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Critical Findings</div>
        <div class="stat-value" :style="{ color: orgTotals.critical > 0 ? 'var(--accent-red)' : 'var(--accent-green)' }">
          {{ orgTotals.critical }}
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Org Success Rate</div>
        <div class="stat-value">{{ orgTotals.avgSuccess.toFixed(1) }}%</div>
      </div>
    </div>

    <!-- Team leaderboard -->
    <div class="section-card">
      <div class="section-header">
        <h3 class="section-title">Team Automation Overview</h3>
        <div class="sort-tabs">
          <span class="sort-label">Sort:</span>
          <button v-for="k in (['executions', 'findings', 'successRate', 'riskScore'] as SortKey[])" :key="k" class="sort-tab" :class="{ active: sortKey === k }" @click="sortKey = k">
            {{ k === 'executions' ? 'Activity' : k === 'findings' ? 'Findings' : k === 'successRate' ? 'Success' : 'Risk' }}
          </button>
        </div>
      </div>
      <div class="teams-grid">
        <div
          v-for="team in sortedTeams"
          :key="team.teamId"
          class="team-card"
          :class="{ selected: selectedTeamId === team.teamId }"
          @click="selectedTeamId = selectedTeamId === team.teamId ? null : team.teamId"
        >
          <div class="team-header">
            <div class="team-name">{{ team.teamName }}</div>
            <div class="team-change" :style="{ color: changeColor(team.weekOverWeekChange) }">
              {{ team.weekOverWeekChange > 0 ? '+' : '' }}{{ team.weekOverWeekChange }}% WoW
            </div>
          </div>
          <div class="team-stats">
            <div class="ts">
              <div class="ts-label">Executions</div>
              <div class="ts-val">{{ team.totalExecutions }}</div>
            </div>
            <div class="ts">
              <div class="ts-label">Bots</div>
              <div class="ts-val">{{ team.activeBots }}</div>
            </div>
            <div class="ts">
              <div class="ts-label">Findings</div>
              <div class="ts-val" :style="{ color: team.findingsCount > 30 ? 'var(--accent-amber)' : 'inherit' }">{{ team.findingsCount }}</div>
            </div>
            <div class="ts">
              <div class="ts-label">Critical</div>
              <div class="ts-val" :style="{ color: team.criticalFindings > 0 ? 'var(--accent-red)' : 'var(--accent-green)' }">{{ team.criticalFindings }}</div>
            </div>
          </div>
          <div class="team-risk-bar-wrap">
            <div class="risk-bar-label">Risk Score</div>
            <div class="risk-bar-track">
              <div
                class="risk-bar-fill"
                :style="{ width: team.riskScore + '%', background: riskColor(team.riskScore) }"
              ></div>
            </div>
            <div class="risk-score" :style="{ color: riskColor(team.riskScore) }">{{ team.riskScore }}</div>
          </div>
          <div v-if="selectedTeamId === team.teamId" class="team-detail">
            <div class="detail-row">
              <span class="detail-label">Most active bot:</span>
              <span>{{ team.mostActiveBotName }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">Top risks:</span>
            </div>
            <ul class="risk-list">
              <li v-for="r in team.topRisks" :key="r">{{ r }}</li>
            </ul>
          </div>
        </div>
      </div>
    </div>

    <!-- Common findings across org -->
    <div class="section-card">
      <div class="section-header">
        <h3 class="section-title">Common Findings Across Teams</h3>
        <span class="section-hint">Issues appearing in multiple teams' bot outputs</span>
      </div>
      <div class="findings-list">
        <div v-for="f in orgFindings" :key="f.id" class="finding-row">
          <div class="finding-severity" :style="{ color: severityColor(f.severity) }">
            ● {{ f.severity.toUpperCase() }}
          </div>
          <div class="finding-body">
            <div class="finding-title">{{ f.title }}</div>
            <div class="finding-meta">
              {{ f.count }} occurrences · {{ f.affectedTeams.join(', ') }} ·
              {{ f.affectedRepos.length }} repos · Last seen {{ formatDate(f.lastSeen) }}
            </div>
          </div>
          <div class="finding-repos">
            <span v-for="repo in f.affectedRepos.slice(0, 3)" :key="repo" class="repo-tag">{{ repo }}</span>
            <span v-if="f.affectedRepos.length > 3" class="repo-tag muted">+{{ f.affectedRepos.length - 3 }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Riskiest repos -->
    <div class="section-card">
      <div class="section-header">
        <h3 class="section-title">Highest Risk Repositories</h3>
        <span class="section-hint">Repos with most unresolved findings</span>
      </div>
      <table class="bench-table">
        <thead>
          <tr>
            <th>Repository</th>
            <th>Team</th>
            <th>Risk Score</th>
            <th>Open Findings</th>
            <th>Last Scanned</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in topRiskyRepos" :key="r.repo" class="bench-row">
            <td class="bot-name">{{ r.repo }}</td>
            <td>{{ r.team }}</td>
            <td>
              <div class="risk-inline">
                <div class="risk-bar-track small">
                  <div class="risk-bar-fill" :style="{ width: r.riskScore + '%', background: riskColor(r.riskScore) }"></div>
                </div>
                <span :style="{ color: riskColor(r.riskScore), fontWeight: '600' }">{{ r.riskScore }}</span>
              </div>
            </td>
            <td :style="{ color: r.openFindings > 10 ? 'var(--accent-red)' : r.openFindings > 5 ? 'var(--accent-amber)' : 'inherit' }">
              {{ r.openFindings }}
            </td>
            <td class="muted-text">{{ formatDate(r.lastScanned) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.page-container { padding: 24px; max-width: 1200px; }
.stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px; }
.stat-card { background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 8px; padding: 16px; text-align: center; }
.stat-label { font-size: 12px; color: var(--text-muted); margin-bottom: 6px; }
.stat-value { font-size: 24px; font-weight: 700; color: var(--text-primary); }
.section-card { background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 8px; padding: 20px; margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; flex-wrap: wrap; gap: 8px; }
.section-title { font-size: 15px; font-weight: 600; color: var(--text-primary); margin: 0; }
.section-hint { font-size: 12px; color: var(--text-muted); }
.sort-tabs { display: flex; align-items: center; gap: 4px; }
.sort-label { font-size: 12px; color: var(--text-muted); margin-right: 4px; }
.sort-tab { padding: 4px 10px; border-radius: 5px; border: 1px solid var(--border-color); background: transparent; color: var(--text-muted); cursor: pointer; font-size: 12px; }
.sort-tab.active { background: var(--accent-blue); color: white; border-color: var(--accent-blue); }
.teams-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
.team-card { background: var(--bg-primary); border: 1px solid var(--border-color); border-radius: 8px; padding: 16px; cursor: pointer; transition: border-color 0.15s; }
.team-card:hover { border-color: var(--accent-blue); }
.team-card.selected { border-color: var(--accent-blue); }
.team-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.team-name { font-size: 15px; font-weight: 700; color: var(--text-primary); }
.team-change { font-size: 12px; font-weight: 600; }
.team-stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-bottom: 12px; }
.ts { text-align: center; }
.ts-label { font-size: 10px; color: var(--text-muted); }
.ts-val { font-size: 16px; font-weight: 700; color: var(--text-primary); }
.team-risk-bar-wrap { display: flex; align-items: center; gap: 8px; }
.risk-bar-label { font-size: 11px; color: var(--text-muted); white-space: nowrap; }
.risk-bar-track { flex: 1; height: 6px; background: var(--bg-secondary); border-radius: 3px; overflow: hidden; }
.risk-bar-track.small { width: 60px; }
.risk-bar-fill { height: 100%; border-radius: 3px; transition: width 0.3s; }
.risk-score { font-size: 12px; font-weight: 600; }
.team-detail { margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border-color); }
.detail-row { display: flex; align-items: flex-start; gap: 8px; font-size: 13px; color: var(--text-primary); margin-bottom: 4px; }
.detail-label { color: var(--text-muted); white-space: nowrap; }
.risk-list { margin: 4px 0 0 16px; padding: 0; font-size: 12px; color: var(--text-muted); }
.risk-list li { margin-bottom: 2px; }
.findings-list { display: flex; flex-direction: column; gap: 0; }
.finding-row { display: grid; grid-template-columns: 120px 1fr auto; gap: 16px; padding: 12px 0; border-bottom: 1px solid var(--border-color); align-items: start; }
.finding-row:last-child { border-bottom: none; }
.finding-severity { font-size: 12px; font-weight: 700; }
.finding-title { font-size: 13px; font-weight: 600; color: var(--text-primary); margin-bottom: 4px; }
.finding-meta { font-size: 11px; color: var(--text-muted); }
.finding-repos { display: flex; gap: 4px; flex-wrap: wrap; }
.repo-tag { padding: 2px 8px; border-radius: 10px; background: var(--bg-secondary); font-size: 11px; color: var(--text-muted); border: 1px solid var(--border-color); }
.repo-tag.muted { opacity: 0.7; }
.bench-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.bench-table th { text-align: left; padding: 8px 12px; color: var(--text-muted); font-weight: 500; border-bottom: 1px solid var(--border-color); }
.bench-row td { padding: 10px 12px; border-bottom: 1px solid var(--border-color); }
.bench-row:hover { background: var(--bg-hover); }
.bot-name { font-weight: 600; color: var(--text-primary); }
.risk-inline { display: flex; align-items: center; gap: 8px; }
.muted-text { color: var(--text-muted); }
.btn-secondary { padding: 6px 14px; border-radius: 6px; border: 1px solid var(--border-color); background: transparent; color: var(--text-primary); cursor: pointer; font-size: 13px; }
</style>
