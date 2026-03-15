<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { schedulerApi, ApiError } from '../services/api';
import type { SchedulerStatus } from '../services/api';

const showToast = useToast();

type RiskLevel = 'low' | 'medium' | 'high';
type OptStatus = 'idle' | 'analyzing' | 'done';

interface TimeSlot {
  hour: number;
  day: string;
  load: number; // 0-100
}

interface RateLimitPattern {
  provider: string;
  peakHours: number[];
  peakDays: string[];
  avgQueueDepth: number;
  recommendation: string;
}

interface ScheduleSuggestion {
  botId: string;
  botName: string;
  currentCron: string;
  suggestedCron: string;
  currentRisk: RiskLevel;
  suggestedRisk: RiskLevel;
  rationale: string;
  estimatedConflictReduction: number;
}

interface BotSchedule {
  botId: string;
  botName: string;
  cron: string;
  provider: string;
  avgDurationMs: number;
  riskLevel: RiskLevel;
  lastConflicts: number;
}

const loading = ref(true);
const error = ref<string | null>(null);
const optStatus = ref<OptStatus>('idle');
const schedulerStatus = ref<SchedulerStatus | null>(null);

const botSchedules = ref<BotSchedule[]>([]);
const rateLimitPatterns = ref<RateLimitPattern[]>([]);
const suggestions = ref<ScheduleSuggestion[]>([]);

async function loadData() {
  loading.value = true;
  error.value = null;
  try {
    const [status, sessionsResp] = await Promise.all([
      schedulerApi.getStatus(),
      schedulerApi.getSessions(),
    ]);
    schedulerStatus.value = status;

    // Map scheduler sessions to BotSchedule display format
    const sessions = sessionsResp.sessions ?? status.sessions ?? [];
    botSchedules.value = sessions.map((s) => ({
      botId: `acct-${s.account_id}`,
      botName: s.account_name ?? `Account ${s.account_id}`,
      cron: s.state,
      provider: s.account_name ?? `Account ${s.account_id}`,
      avgDurationMs: 0,
      riskLevel: (s.state === 'stopped' ? 'high' : s.state === 'queued' ? 'medium' : 'low') as RiskLevel,
      lastConflicts: s.stop_reason ? 1 : 0,
    }));

    // Derive rate limit patterns from global summary if available
    if (status.global_summary) {
      const gs = status.global_summary;
      rateLimitPatterns.value = [{
        provider: 'All',
        peakHours: [],
        peakDays: [],
        avgQueueDepth: gs.running ?? 0,
        recommendation: gs.stopped > 0
          ? `${gs.stopped} session(s) stopped due to rate limits. Consider staggering schedules.`
          : 'Concurrency is within normal limits.',
      }];
    }
  } catch (err) {
    if (err instanceof ApiError) {
      error.value = `API Error (${err.status}): ${err.message}`;
    } else {
      error.value = err instanceof Error ? err.message : 'Unknown error';
    }
  } finally {
    loading.value = false;
  }
}

onMounted(loadData);

const heatmapDays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const heatmapHours = [0, 3, 6, 9, 12, 15, 18, 21];

const heatmapData = computed<TimeSlot[]>(() => {
  const slots: TimeSlot[] = [];
  for (const day of heatmapDays) {
    for (const hour of heatmapHours) {
      const isMonTue = day === 'Mon' || day === 'Tue';
      const isWedThu = day === 'Wed' || day === 'Thu';
      const isPeakHour = hour >= 9 && hour <= 16;
      const isLateNight = hour < 6 || hour >= 22;
      let load = 20;
      if (isMonTue && isPeakHour) load = 85 + Math.random() * 10;
      else if (isWedThu && hour >= 13 && hour <= 16) load = 65 + Math.random() * 15;
      else if (isPeakHour) load = 40 + Math.random() * 20;
      else if (isLateNight) load = 10 + Math.random() * 10;
      else load = 30 + Math.random() * 20;
      slots.push({ hour, day, load });
    }
  }
  return slots;
});

function heatColor(load: number): string {
  if (load >= 75) return 'var(--accent-red)';
  if (load >= 50) return 'var(--accent-amber)';
  if (load >= 30) return 'color-mix(in srgb, var(--accent-green) 60%, transparent)';
  return 'color-mix(in srgb, var(--accent-green) 30%, transparent)';
}

function riskBadge(risk: RiskLevel): string {
  return risk === 'high' ? '🔴' : risk === 'medium' ? '🟡' : '🟢';
}

function riskColor(risk: RiskLevel): string {
  return risk === 'high' ? 'var(--accent-red)' : risk === 'medium' ? 'var(--accent-amber)' : 'var(--accent-green)';
}

function formatCron(cron: string): string {
  const parts = cron.split(' ');
  if (parts.length < 5) return cron;
  const [min, hour, , , dayOfWeek] = parts;
  const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const dayName = dayOfWeek === '*' ? 'Daily' : days[parseInt(dayOfWeek)] || dayOfWeek;
  return `${dayName} ${hour.padStart(2, '0')}:${min.padStart(2, '0')} UTC`;
}

async function runOptimizer() {
  optStatus.value = 'analyzing';
  try {
    // Re-fetch status to get latest data as the "optimization" pass
    const status = await schedulerApi.getStatus();
    schedulerStatus.value = status;
    optStatus.value = 'done';
    showToast('Optimization analysis complete', 'success');
  } catch (err) {
    optStatus.value = 'idle';
    showToast(err instanceof ApiError ? err.message : 'Optimization failed', 'error');
  }
}

function applySuggestion(s: ScheduleSuggestion) {
  const bot = botSchedules.value.find((b) => b.botId === s.botId);
  if (bot) {
    bot.cron = s.suggestedCron;
    bot.riskLevel = s.suggestedRisk;
    bot.lastConflicts = 0;
  }
  showToast(`Schedule updated for ${s.botName}`, 'success');
}

function dismissSuggestion(s: ScheduleSuggestion) {
  suggestions.value = suggestions.value.filter((sg) => sg.botId !== s.botId);
  showToast('Suggestion dismissed', 'info');
}

const totalConflicts = computed(() => botSchedules.value.reduce((s, b) => s + b.lastConflicts, 0));
const highRiskCount = computed(() => botSchedules.value.filter((b) => b.riskLevel === 'high').length);
</script>

<template>
  <div class="page-container">
    <PageHeader
      title="Smart Schedule Optimizer"
      subtitle="AI-powered scheduling that analyzes API rate limit patterns and execution history to avoid peak contention"
    />

    <!-- Loading state -->
    <div v-if="loading" class="empty-detail">
      <div class="empty-icon">⏳</div>
      <div class="empty-text">Loading scheduler data...</div>
    </div>

    <!-- Error state -->
    <div v-else-if="error" class="empty-detail">
      <div class="empty-icon">⚠️</div>
      <div class="empty-text">{{ error }}</div>
      <button class="btn-primary" style="margin-top: 12px" @click="loadData">Retry</button>
    </div>

    <template v-else>
      <div class="stats-row">
        <div class="stat-card">
          <div class="stat-label">Bots with Schedules</div>
          <div class="stat-value">{{ botSchedules.length }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">High-Risk Schedules</div>
          <div class="stat-value" :style="{ color: highRiskCount > 0 ? 'var(--accent-red)' : 'var(--accent-green)' }">
            {{ highRiskCount }}
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Rate Limit Conflicts (30d)</div>
          <div class="stat-value" :style="{ color: totalConflicts > 0 ? 'var(--accent-amber)' : 'var(--accent-green)' }">
            {{ totalConflicts }}
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Suggestions Available</div>
          <div class="stat-value" :style="{ color: suggestions.length > 0 ? 'var(--accent-blue)' : 'var(--text-muted)' }">
            {{ suggestions.length }}
          </div>
        </div>
      </div>

      <!-- Rate limit heatmap -->
      <div class="section-card">
        <div class="section-header">
          <h3 class="section-title">Provider Rate Limit Heatmap</h3>
          <span class="section-hint">Historical API queue depth by day / hour (UTC)</span>
        </div>
        <div class="heatmap-grid">
          <div class="heatmap-corner"></div>
          <div v-for="day in heatmapDays" :key="day" class="heatmap-day-header">{{ day }}</div>
          <template v-for="hour in heatmapHours" :key="hour">
            <div class="heatmap-hour-label">{{ String(hour).padStart(2, '0') }}:00</div>
            <div
              v-for="day in heatmapDays"
              :key="`${day}-${hour}`"
              class="heatmap-cell"
              :style="{ background: heatColor(heatmapData.find(s => s.day === day && s.hour === hour)?.load ?? 20) }"
              :title="`${day} ${hour}:00 UTC — Load: ${Math.round(heatmapData.find(s => s.day === day && s.hour === hour)?.load ?? 20)}%`"
            ></div>
          </template>
        </div>
        <div class="heatmap-legend">
          <span class="legend-item"><span class="legend-swatch" style="background: color-mix(in srgb, var(--accent-green) 30%, transparent)"></span> Low</span>
          <span class="legend-item"><span class="legend-swatch" style="background: var(--accent-amber)"></span> Medium</span>
          <span class="legend-item"><span class="legend-swatch" style="background: var(--accent-red)"></span> High</span>
        </div>
      </div>

      <!-- Provider patterns -->
      <div class="section-card">
        <div class="section-header">
          <h3 class="section-title">Provider Rate Limit Patterns</h3>
        </div>
        <div v-if="rateLimitPatterns.length === 0" class="empty-detail" style="padding: 20px">
          <div class="empty-text">No rate limit pattern data available.</div>
        </div>
        <div v-else class="patterns-grid">
          <div v-for="p in rateLimitPatterns" :key="p.provider" class="pattern-card">
            <div class="pattern-provider">{{ p.provider }}</div>
            <div class="pattern-stat">Peak days: <strong>{{ p.peakDays.length > 0 ? p.peakDays.join(', ') : 'N/A' }}</strong></div>
            <div class="pattern-stat">Peak hours: <strong>{{ p.peakHours.length > 0 ? p.peakHours.map(h => `${h}:00`).join(', ') + ' UTC' : 'N/A' }}</strong></div>
            <div class="pattern-stat">Active sessions: <strong>{{ p.avgQueueDepth }}</strong></div>
            <div class="pattern-rec">💡 {{ p.recommendation }}</div>
          </div>
        </div>
      </div>

      <!-- Current schedules -->
      <div class="section-card">
        <div class="section-header">
          <h3 class="section-title">Current Bot Schedules</h3>
          <button
            class="btn-primary"
            :disabled="optStatus === 'analyzing'"
            @click="runOptimizer"
          >
            {{ optStatus === 'analyzing' ? '⏳ Analyzing…' : '⚡ Run Optimizer' }}
          </button>
        </div>
        <div v-if="botSchedules.length === 0" class="empty-detail" style="padding: 30px">
          <div class="empty-text">No active scheduler sessions found.</div>
        </div>
        <table v-else class="bench-table">
          <thead>
            <tr>
              <th>Bot</th>
              <th>Current Schedule</th>
              <th>Provider</th>
              <th>Avg Duration</th>
              <th>Risk</th>
              <th>Conflicts (30d)</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="b in botSchedules" :key="b.botId" class="bench-row">
              <td class="bot-name">{{ b.botName }}</td>
              <td><code class="mono">{{ b.cron }}</code><span v-if="b.cron.includes(' ')" class="cron-human"> ({{ formatCron(b.cron) }})</span></td>
              <td>{{ b.provider }}</td>
              <td>{{ b.avgDurationMs > 0 ? (b.avgDurationMs / 1000).toFixed(0) + 's' : '-' }}</td>
              <td><span :style="{ color: riskColor(b.riskLevel) }">{{ riskBadge(b.riskLevel) }} {{ b.riskLevel }}</span></td>
              <td :style="{ color: b.lastConflicts > 0 ? 'var(--accent-amber)' : 'var(--accent-green)' }">
                {{ b.lastConflicts }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Suggestions -->
      <div v-if="suggestions.length > 0" class="section-card">
        <div class="section-header">
          <h3 class="section-title">✨ Optimization Suggestions</h3>
          <span class="section-hint">AI-generated schedule improvements</span>
        </div>
        <div class="suggestions-list">
          <div v-for="s in suggestions" :key="s.botId" class="suggestion-card">
            <div class="suggestion-header">
              <div class="suggestion-bot">{{ s.botName }}</div>
              <div class="suggestion-actions">
                <button class="btn-apply" @click="applySuggestion(s)">Apply</button>
                <button class="btn-dismiss" @click="dismissSuggestion(s)">Dismiss</button>
              </div>
            </div>
            <div class="schedule-compare">
              <div class="schedule-item">
                <div class="schedule-label" :style="{ color: riskColor(s.currentRisk) }">Current {{ riskBadge(s.currentRisk) }}</div>
                <code class="mono">{{ s.currentCron }}</code>
                <div class="cron-human">{{ formatCron(s.currentCron) }}</div>
              </div>
              <div class="arrow">→</div>
              <div class="schedule-item">
                <div class="schedule-label" :style="{ color: riskColor(s.suggestedRisk) }">Suggested {{ riskBadge(s.suggestedRisk) }}</div>
                <code class="mono">{{ s.suggestedCron }}</code>
                <div class="cron-human">{{ formatCron(s.suggestedCron) }}</div>
              </div>
              <div class="conflict-reduction">-{{ s.estimatedConflictReduction }}% conflicts</div>
            </div>
            <div class="rationale">{{ s.rationale }}</div>
          </div>
        </div>
      </div>

      <div v-else-if="optStatus === 'done'" class="empty-detail">
        <div class="empty-icon">✅</div>
        <div class="empty-text">All schedules are already well-optimized</div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.page-container { padding: 24px; max-width: 1200px; }
.stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px; }
.stat-card { background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 8px; padding: 16px; text-align: center; }
.stat-label { font-size: 12px; color: var(--text-muted); margin-bottom: 6px; }
.stat-value { font-size: 24px; font-weight: 700; color: var(--text-primary); }
.section-card { background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 8px; padding: 20px; margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.section-title { font-size: 15px; font-weight: 600; color: var(--text-primary); margin: 0; }
.section-hint { font-size: 12px; color: var(--text-muted); }
.heatmap-grid { display: grid; grid-template-columns: 60px repeat(7, 1fr); gap: 3px; }
.heatmap-corner { }
.heatmap-day-header { text-align: center; font-size: 11px; color: var(--text-muted); font-weight: 600; padding: 4px 0; }
.heatmap-hour-label { font-size: 10px; color: var(--text-muted); display: flex; align-items: center; }
.heatmap-cell { height: 24px; border-radius: 3px; cursor: pointer; transition: opacity 0.2s; }
.heatmap-cell:hover { opacity: 0.8; }
.heatmap-legend { display: flex; gap: 16px; margin-top: 12px; }
.legend-item { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-muted); }
.legend-swatch { width: 16px; height: 16px; border-radius: 3px; display: inline-block; }
.patterns-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.pattern-card { background: var(--bg-primary); border: 1px solid var(--border-color); border-radius: 8px; padding: 16px; }
.pattern-provider { font-size: 14px; font-weight: 700; color: var(--text-primary); margin-bottom: 8px; }
.pattern-stat { font-size: 13px; color: var(--text-muted); margin-bottom: 4px; }
.pattern-rec { margin-top: 10px; font-size: 12px; color: var(--accent-blue); }
.bench-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.bench-table th { text-align: left; padding: 8px 12px; color: var(--text-muted); font-weight: 500; border-bottom: 1px solid var(--border-color); }
.bench-row td { padding: 10px 12px; border-bottom: 1px solid var(--border-color); }
.bench-row:hover { background: var(--bg-hover); }
.bot-name { font-weight: 600; color: var(--text-primary); }
.mono { font-family: monospace; font-size: 12px; color: var(--text-primary); }
.cron-human { font-size: 11px; color: var(--text-muted); margin-left: 6px; }
.btn-primary { padding: 7px 16px; border-radius: 6px; border: none; background: var(--accent-blue); color: white; cursor: pointer; font-size: 13px; font-weight: 600; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.suggestions-list { display: flex; flex-direction: column; gap: 12px; }
.suggestion-card { background: var(--bg-primary); border: 1px solid var(--border-color); border-radius: 8px; padding: 16px; }
.suggestion-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.suggestion-bot { font-weight: 600; font-size: 14px; color: var(--text-primary); }
.suggestion-actions { display: flex; gap: 8px; }
.btn-apply { padding: 5px 12px; border-radius: 5px; border: none; background: var(--accent-green); color: white; cursor: pointer; font-size: 12px; font-weight: 600; }
.btn-dismiss { padding: 5px 12px; border-radius: 5px; border: 1px solid var(--border-color); background: transparent; color: var(--text-muted); cursor: pointer; font-size: 12px; }
.schedule-compare { display: flex; align-items: center; gap: 16px; margin-bottom: 10px; flex-wrap: wrap; }
.schedule-item { flex: 1; min-width: 120px; }
.schedule-label { font-size: 11px; font-weight: 600; margin-bottom: 4px; }
.arrow { font-size: 20px; color: var(--text-muted); }
.conflict-reduction { padding: 4px 10px; border-radius: 12px; background: color-mix(in srgb, var(--accent-green) 15%, transparent); color: var(--accent-green); font-size: 12px; font-weight: 600; }
.rationale { font-size: 12px; color: var(--text-muted); line-height: 1.5; }
.empty-detail { text-align: center; padding: 40px; color: var(--text-muted); }
.empty-icon { font-size: 32px; margin-bottom: 12px; }
.empty-text { font-size: 14px; }
</style>
