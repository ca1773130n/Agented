<!-- v0.7.0: Per-bot success-rate / latency / status rollup at /bots/health. -->
<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { botHealthApi } from '../services/api';
import type { BotHealthRollup } from '../services/api';

const rollups = ref<BotHealthRollup[]>([]);
const loading = ref(true);
const error = ref<string | null>(null);
const windowDays = ref(7);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const r = await botHealthApi.list(windowDays.value);
    rollups.value = r.rollups;
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

onMounted(load);

function pillLabel(status: BotHealthRollup['status_pill']): string {
  return {
    healthy: 'Healthy',
    degraded: 'Degraded',
    down: 'Down',
    no_recent_runs: 'No recent runs',
  }[status];
}
</script>

<template>
  <div class="bot-health-page">
    <header class="bot-health-page__header">
      <h1>Bot Health</h1>
      <select
        v-model.number="windowDays"
        class="bot-health-page__window"
        data-testid="window-select"
        @change="load"
      >
        <option :value="1">Last 24h</option>
        <option :value="7">Last 7 days</option>
        <option :value="30">Last 30 days</option>
        <option :value="90">Last 90 days</option>
      </select>
    </header>

    <div v-if="loading" class="bot-health-page__loading" data-testid="loading">
      Loading…
    </div>
    <div v-else-if="error" class="bot-health-page__error" data-testid="error">
      {{ error }}
      <button @click="load">Retry</button>
    </div>
    <div v-else-if="rollups.length === 0" class="bot-health-page__empty" data-testid="empty">
      No bots yet.
    </div>
    <div v-else class="bot-health-page__grid" data-testid="grid">
      <article
        v-for="r in rollups"
        :key="r.bot_id"
        class="bh-card"
        :data-status="r.status_pill"
      >
        <header class="bh-card__head">
          <h2 class="bh-card__name">{{ r.bot_name }}</h2>
          <span class="bh-card__pill" :data-status="r.status_pill">
            {{ pillLabel(r.status_pill) }}
          </span>
        </header>
        <dl class="bh-card__metrics">
          <div>
            <dt>Success rate</dt>
            <dd>{{ r.success_rate === null ? '—' : `${(r.success_rate * 100).toFixed(0)}%` }}</dd>
          </div>
          <div>
            <dt>p95 latency</dt>
            <dd>{{ r.p95_duration_ms === null ? '—' : `${r.p95_duration_ms} ms` }}</dd>
          </div>
          <div>
            <dt>Runs</dt>
            <dd>{{ r.success_count + r.fail_count }}</dd>
          </div>
        </dl>
        <p
          v-if="r.last_failure_message"
          class="bh-card__failure"
          :title="r.last_failure_at ?? ''"
        >
          Last failure: {{ r.last_failure_message.slice(0, 120) }}
        </p>
      </article>
    </div>
  </div>
</template>

<style scoped>
.bot-health-page { padding: 24px; max-width: 1280px; margin: 0 auto; }
.bot-health-page__header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 16px;
}
.bot-health-page__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}
.bh-card {
  padding: 16px;
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.1));
  border-radius: 8px;
  background: var(--surface-1, rgba(255, 255, 255, 0.03));
}
.bh-card__head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 12px;
}
.bh-card__name { font-size: 14px; font-weight: 600; margin: 0; }
.bh-card__pill {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.bh-card__pill[data-status='healthy'] { background: rgba(34, 197, 94, 0.15); color: #22c55e; }
.bh-card__pill[data-status='degraded'] { background: rgba(245, 158, 11, 0.15); color: #f59e0b; }
.bh-card__pill[data-status='down'] { background: rgba(239, 68, 68, 0.15); color: #ef4444; }
.bh-card__pill[data-status='no_recent_runs'] {
  background: rgba(113, 113, 122, 0.15);
  color: #71717a;
}
.bh-card__metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin: 0;
}
.bh-card__metrics dt {
  font-size: 11px;
  color: var(--text-tertiary, rgba(255, 255, 255, 0.5));
  margin-bottom: 2px;
}
.bh-card__metrics dd { font-size: 16px; font-weight: 600; margin: 0; }
.bh-card__failure {
  margin-top: 12px;
  font-size: 12px;
  color: var(--accent-crimson, #ef4444);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
