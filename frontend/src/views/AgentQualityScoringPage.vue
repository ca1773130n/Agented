<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { qualityApi } from '../services/api/quality-ratings';
import type { QualityEntry, BotQualityStats } from '../services/api/quality-ratings';

const router = useRouter();
const showToast = useToast();

const bots = ref<BotQualityStats[]>([]);
const entries = ref<QualityEntry[]>([]);
const loading = ref(false);

const selectedBotFilter = ref('all');
const pendingRatings = ref<Record<string, number>>({});
const pendingFeedback = ref<Record<string, string>>({});

const filteredEntries = computed(() =>
  selectedBotFilter.value === 'all'
    ? entries.value
    : entries.value.filter(e => e.trigger_id === selectedBotFilter.value)
);

onMounted(async () => {
  loading.value = true;
  try {
    const [statsRes, entriesRes] = await Promise.all([
      qualityApi.getStats(),
      qualityApi.listEntries({ limit: 50 }),
    ]);
    bots.value = statsRes.bots;
    entries.value = entriesRes.entries;
  } catch (err) {
    showToast('Failed to load quality data', 'error');
  } finally {
    loading.value = false;
  }
});

function setRating(execId: string, rating: number) {
  pendingRatings.value[execId] = rating;
}

async function submitRating(entry: QualityEntry) {
  const rating = pendingRatings.value[entry.execution_id];
  if (!rating) return;
  const feedback = pendingFeedback.value[entry.execution_id] ?? entry.feedback ?? '';
  try {
    const result = await qualityApi.submitRating(entry.execution_id, {
      rating,
      feedback,
      trigger_id: entry.trigger_id,
    });
    // Update local state
    const idx = entries.value.findIndex(e => e.execution_id === entry.execution_id);
    if (idx !== -1) entries.value[idx] = { ...entries.value[idx], ...result };
    delete pendingRatings.value[entry.execution_id];
    delete pendingFeedback.value[entry.execution_id];
    showToast('Rating submitted', 'success');
    // Refresh stats
    const statsRes = await qualityApi.getStats();
    bots.value = statsRes.bots;
  } catch {
    showToast('Failed to submit rating', 'error');
  }
}

function trendIcon(trend: BotQualityStats['trend']): string {
  return { up: '↑', down: '↓', stable: '→' }[trend];
}

function trendColor(trend: BotQualityStats['trend']): string {
  return { up: '#34d399', down: '#ef4444', stable: '#fbbf24' }[trend];
}

function scoreColor(score: number): string {
  if (score >= 4.5) return '#34d399';
  if (score >= 3.5) return '#fbbf24';
  return '#ef4444';
}

function formatDate(ts: string | null): string {
  if (!ts) return '—';
  return new Date(ts).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function starClass(star: number, rating: number | null, pending: number | undefined): string {
  const effective = pending ?? rating ?? 0;
  return star <= effective ? 'star-filled' : 'star-empty';
}
</script>

<template>
  <div class="quality-scoring">
    <AppBreadcrumb :items="[
      { label: 'Agents', action: () => router.push({ name: 'agents' }) },
      { label: 'Quality Scoring' },
    ]" />

    <PageHeader
      title="Agent Quality Scoring"
      subtitle="Collect feedback on bot outputs and surface per-agent quality scores with trend analysis."
    />

    <div v-if="loading" class="loading-msg">Loading quality data…</div>

    <!-- Summary cards -->
    <div v-else-if="bots.length > 0" class="bot-grid">
      <div v-for="bot in bots" :key="bot.trigger_id ?? 'unknown'" class="bot-card card" @click="selectedBotFilter = bot.trigger_id ?? 'all'">
        <div class="bot-card-header">
          <div class="bot-name">{{ bot.trigger_name ?? bot.trigger_id ?? 'Unknown Bot' }}</div>
          <span class="trend-badge" :style="{ color: trendColor(bot.trend) }">
            {{ trendIcon(bot.trend) }} {{ bot.trend }}
          </span>
        </div>
        <div class="bot-score" :style="{ color: scoreColor(bot.avg_score) }">
          {{ bot.avg_score.toFixed(1) }}
          <span class="score-max">/5</span>
        </div>
        <div class="bot-stats">
          <span class="stat-item">{{ bot.total_rated }} rated</span>
          <span class="stat-item stat-up">{{ bot.thumbs_up }} good</span>
          <span class="stat-item stat-down">{{ bot.thumbs_down }} poor</span>
        </div>
        <div class="mini-chart">
          <div
            v-for="(s, i) in bot.recent_scores"
            :key="i"
            class="mini-bar"
            :style="{ height: `${(s / 5) * 100}%`, background: scoreColor(s) }"
          ></div>
        </div>
      </div>
    </div>
    <div v-else-if="!loading" class="empty-bots">No quality ratings yet. Submit ratings below to see per-bot statistics.</div>

    <!-- Filter -->
    <div class="filter-row">
      <select v-model="selectedBotFilter" class="select">
        <option value="all">All Bots</option>
        <option v-for="bot in bots" :key="bot.trigger_id ?? 'unknown'" :value="bot.trigger_id">
          {{ bot.trigger_name ?? bot.trigger_id ?? 'Unknown' }}
        </option>
      </select>
      <span class="filter-count">{{ filteredEntries.length }} executions</span>
    </div>

    <!-- Entry list -->
    <div class="card">
      <div class="card-header">Execution Feedback</div>
      <div v-if="entries.length === 0 && !loading" class="empty-entries">No execution entries to rate yet.</div>
      <div class="entry-list">
        <div v-for="entry in filteredEntries" :key="entry.execution_id" class="entry-row">
          <div class="entry-left">
            <div class="entry-id">{{ entry.execution_id }}</div>
            <div class="entry-preview">{{ entry.output_preview || '(no output)' }}</div>
            <div class="entry-meta">
              <span class="entry-bot">{{ entry.trigger_name ?? entry.trigger_id ?? '—' }}</span>
              <span class="sep">·</span>
              <span class="entry-date">{{ formatDate(entry.timestamp) }}</span>
            </div>
            <div v-if="entry.feedback" class="entry-feedback">"{{ entry.feedback }}"</div>
          </div>
          <div class="entry-right">
            <div class="stars">
              <button
                v-for="star in 5"
                :key="star"
                :class="['star', starClass(star, entry.rating, pendingRatings[entry.execution_id])]"
                @click="setRating(entry.execution_id, star)"
              >★</button>
            </div>
            <button
              v-if="pendingRatings[entry.execution_id]"
              class="btn-submit"
              @click="submitRating(entry)"
            >Submit</button>
            <span v-else-if="entry.rating" class="rated-label">Rated</span>
            <span v-else class="unrated-label">Unrated</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.quality-scoring { display: flex; flex-direction: column; gap: 24px; animation: fadeIn 0.4s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

.loading-msg { color: var(--text-muted); font-size: 0.85rem; padding: 20px 0; }
.empty-bots { color: var(--text-muted); font-size: 0.85rem; padding: 12px 0; }
.empty-entries { color: var(--text-muted); font-size: 0.85rem; padding: 20px; text-align: center; }

.bot-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; }

.bot-card { padding: 20px; cursor: pointer; transition: border-color 0.15s; }
.bot-card:hover { border-color: var(--accent-cyan); }

.bot-card-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.bot-name { font-size: 0.88rem; font-weight: 600; color: var(--text-primary); }
.trend-badge { font-size: 0.75rem; font-weight: 600; text-transform: capitalize; }

.bot-score { font-size: 2.2rem; font-weight: 700; line-height: 1; margin-bottom: 8px; }
.score-max { font-size: 1rem; color: var(--text-muted); font-weight: 400; }

.bot-stats { display: flex; gap: 12px; margin-bottom: 12px; }
.stat-item { font-size: 0.72rem; color: var(--text-muted); }
.stat-up { color: #34d399; }
.stat-down { color: #ef4444; }

.mini-chart { display: flex; align-items: flex-end; gap: 3px; height: 32px; }
.mini-bar { width: 8px; min-height: 4px; border-radius: 2px; opacity: 0.8; transition: opacity 0.15s; }

.card { background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 12px; overflow: hidden; }
.card-header { padding: 14px 20px; border-bottom: 1px solid var(--border-default); font-size: 0.82rem; font-weight: 600; color: var(--text-secondary); }

.filter-row { display: flex; align-items: center; gap: 12px; }
.select { padding: 8px 12px; background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 7px; color: var(--text-primary); font-size: 0.875rem; cursor: pointer; }
.select:focus { outline: none; border-color: var(--accent-cyan); }
.filter-count { font-size: 0.78rem; color: var(--text-tertiary); }

.entry-list { display: flex; flex-direction: column; }
.entry-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; padding: 16px 20px; border-bottom: 1px solid var(--border-subtle); }
.entry-row:last-child { border-bottom: none; }

.entry-left { flex: 1; display: flex; flex-direction: column; gap: 4px; }
.entry-id { font-size: 0.75rem; font-family: monospace; color: var(--text-muted); }
.entry-preview { font-size: 0.83rem; color: var(--text-secondary); font-family: monospace; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 480px; }
.entry-meta { display: flex; align-items: center; gap: 6px; font-size: 0.72rem; color: var(--text-muted); }
.entry-bot { color: var(--accent-cyan); font-family: monospace; }
.sep { opacity: 0.5; }
.entry-feedback { font-size: 0.8rem; color: var(--text-tertiary); font-style: italic; margin-top: 2px; }

.entry-right { display: flex; flex-direction: column; align-items: flex-end; gap: 8px; flex-shrink: 0; }

.stars { display: flex; gap: 2px; }
.star { background: none; border: none; font-size: 1.3rem; cursor: pointer; transition: transform 0.1s; padding: 0 1px; line-height: 1; }
.star:hover { transform: scale(1.2); }
.star-filled { color: #fbbf24; }
.star-empty { color: var(--border-default); }

.btn-submit { padding: 5px 12px; background: var(--accent-cyan); color: #000; border: none; border-radius: 5px; font-size: 0.75rem; font-weight: 600; cursor: pointer; }
.btn-submit:hover { opacity: 0.85; }
.rated-label { font-size: 0.72rem; color: #34d399; font-weight: 600; }
.unrated-label { font-size: 0.72rem; color: var(--text-muted); }

@media (max-width: 768px) { .entry-row { flex-direction: column; } .entry-preview { max-width: 100%; } }
</style>
