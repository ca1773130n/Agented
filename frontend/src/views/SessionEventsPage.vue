<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  sessionEventsApi,
  type SessionEvent,
  type SessionEventsFilters,
} from '../services/api/session-events';

const { t } = useI18n();

const events = ref<SessionEvent[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);

const filterUser = ref('');
const filterSession = ref('');
const filterEventType = ref('');

const EVENT_TYPES = [
  'created',
  'rotated',
  'revoked',
  'expired',
  'idle_expired',
  'used_after_revocation',
] as const;

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const filters: SessionEventsFilters = { limit: 200 };
    if (filterUser.value) filters.user_id = filterUser.value;
    if (filterSession.value) filters.session_id = filterSession.value;
    if (filterEventType.value) filters.event_type = filterEventType.value;
    const result = await sessionEventsApi.list(filters);
    events.value = result.events;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

onMounted(load);

function formatMetadata(meta: Record<string, unknown> | null): string {
  if (!meta) return '';
  return JSON.stringify(meta);
}

const eventCount = computed(() => events.value.length);
</script>

<template>
  <main class="page">
    <header class="page-header">
      <h1>{{ t('sessionEvents.title') }}</h1>
      <p class="subtitle">
        {{ t('sessionEvents.subtitle', { count: eventCount }) }}
      </p>
    </header>

    <section class="filters">
      <label>
        <span>{{ t('sessionEvents.userId') }}</span>
        <input v-model="filterUser" type="text" :placeholder="t('sessionEvents.any')" />
      </label>
      <label>
        <span>{{ t('sessionEvents.sessionId') }}</span>
        <input v-model="filterSession" type="text" :placeholder="t('sessionEvents.any')" />
      </label>
      <label>
        <span>{{ t('sessionEvents.eventType') }}</span>
        <select v-model="filterEventType">
          <option value="">{{ t('sessionEvents.any') }}</option>
          <option v-for="evtType in EVENT_TYPES" :key="evtType" :value="evtType">{{ evtType }}</option>
        </select>
      </label>
      <button type="button" :disabled="loading" @click="load">
        {{ loading ? t('sessionEvents.loadingShort') : t('sessionEvents.refresh') }}
      </button>
    </section>

    <p v-if="error" class="error">{{ error }}</p>

    <table v-else class="events-table">
      <thead>
        <tr>
          <th>{{ t('sessionEvents.cols.occurredAt') }}</th>
          <th>{{ t('sessionEvents.cols.event') }}</th>
          <th>{{ t('sessionEvents.cols.session') }}</th>
          <th>{{ t('sessionEvents.cols.user') }}</th>
          <th>{{ t('sessionEvents.cols.metadata') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="evt in events" :key="evt.id">
          <td>{{ evt.occurred_at }}</td>
          <td>{{ evt.event_type }}</td>
          <td class="mono" :title="evt.session_id">{{ evt.session_id }}</td>
          <td class="mono" :title="evt.user_id || ''">{{ evt.user_id || '—' }}</td>
          <td class="mono">{{ formatMetadata(evt.metadata) }}</td>
        </tr>
        <tr v-if="!events.length && !loading">
          <td colspan="5" class="empty">{{ t('sessionEvents.noEvents') }}</td>
        </tr>
      </tbody>
    </table>
  </main>
</template>

<style scoped>
.page {
  padding: 1.5rem;
  max-width: 100%;
}
.page-header h1 { margin: 0 0 0.25rem 0; }
.subtitle { color: var(--text-muted, #888); margin: 0 0 1rem 0; }
.filters {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
  margin-bottom: 1rem;
  align-items: flex-end;
}
.filters label {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.filters span {
  font-size: 0.85rem;
  color: var(--text-muted, #888);
}
.filters input,
.filters select {
  background: var(--surface-1, #1a1a1a);
  color: var(--text, #fff);
  border: 1px solid var(--border, #333);
  padding: 0.4rem 0.6rem;
  border-radius: 4px;
}
.filters button {
  padding: 0.5rem 1rem;
  border-radius: 4px;
  border: 1px solid var(--accent, #4a9eff);
  background: var(--accent, #4a9eff);
  color: white;
  cursor: pointer;
}
.filters button:disabled { opacity: 0.6; cursor: wait; }
.events-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
}
.events-table th,
.events-table td {
  padding: 0.5rem;
  border-bottom: 1px solid var(--border, #2a2a2a);
  text-align: left;
}
.events-table th {
  background: var(--surface-2, #1f1f1f);
  font-weight: 500;
}
.mono {
  font-family: 'Geist Mono', ui-monospace, monospace;
  font-size: 0.85rem;
}
.empty {
  text-align: center;
  color: var(--text-muted, #888);
  padding: 2rem;
}
.error {
  color: var(--danger, #f55);
  background: var(--danger-bg, #2a1414);
  padding: 0.75rem;
  border-radius: 4px;
}
</style>
