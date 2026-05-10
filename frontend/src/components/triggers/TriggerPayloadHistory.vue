<script setup lang="ts">
/**
 * v0.7.1: Trigger Payload Inspector — recent inbound trigger events
 * with click-to-expand JSON and a guarded Replay action.
 *
 * Backed by triggerEventApi:
 *   - GET /admin/triggers/{trigger_id}/events
 *   - POST /admin/triggers/events/{event_id}/replay
 */
import { ref, onMounted, watch } from 'vue';
import { triggerEventApi, ApiError } from '../../services/api';
import type { TriggerEvent } from '../../services/api';
import { safeFormatDateTime } from '../../utils/datetime';
import { useToast } from '../../composables/useToast';

const props = defineProps<{
  triggerId: string;
}>();

const showToast = useToast();

const events = ref<TriggerEvent[]>([]);
const isLoading = ref(false);
const error = ref<string | null>(null);
const expandedId = ref<number | null>(null);
const confirmReplayId = ref<number | null>(null);
const isReplaying = ref(false);

async function loadEvents() {
  if (!props.triggerId) return;
  isLoading.value = true;
  error.value = null;
  try {
    const res = await triggerEventApi.list(props.triggerId, 50);
    events.value = res.events || [];
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : 'Failed to load trigger events';
  } finally {
    isLoading.value = false;
  }
}

function toggleExpand(id: number) {
  expandedId.value = expandedId.value === id ? null : id;
}

function requestReplay(id: number) {
  confirmReplayId.value = id;
}

function cancelReplay() {
  confirmReplayId.value = null;
}

async function confirmReplay(eventId: number) {
  isReplaying.value = true;
  try {
    const res = await triggerEventApi.replay(eventId);
    showToast(
      res.fired ? 'Trigger replayed successfully' : 'Replay accepted but trigger did not fire',
      res.fired ? 'success' : 'info',
    );
    confirmReplayId.value = null;
    await loadEvents();
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to replay trigger event';
    showToast(message, 'error');
  } finally {
    isReplaying.value = false;
  }
}

function formatDate(dateStr: string): string {
  return safeFormatDateTime(dateStr, '-', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function formatJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

/** Parse the raw JSON-encoded `payload` string from the DB row.
 * Falls back to the raw string when JSON.parse fails (e.g. a row with
 * a serialization-error placeholder). */
function parsedPayload(raw: string): unknown {
  if (raw == null) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return raw;
  }
}

function statusClass(status: string): string {
  return `status-${status}`;
}

onMounted(loadEvents);
watch(() => props.triggerId, loadEvents);
</script>

<template>
  <div class="payload-history" data-testid="trigger-payload-history">
    <div class="section-header">
      <h3>Recent Trigger Events</h3>
      <span v-if="events.length" class="entry-count">{{ events.length }} events</span>
    </div>

    <div v-if="isLoading" class="loading-state" data-testid="loading">
      <span class="spinner"></span>
      Loading trigger events...
    </div>

    <div v-else-if="error" class="error-state" data-testid="error">
      <p>{{ error }}</p>
      <button class="retry-btn" @click="loadEvents">Retry</button>
    </div>

    <div v-else-if="events.length === 0" class="empty-state" data-testid="empty">
      <div class="empty-icon">&#9671;</div>
      <p>No trigger events yet</p>
      <span>Events will appear here as they arrive.</span>
    </div>

    <div v-else class="event-list">
      <div
        v-for="event in events"
        :key="event.id"
        class="event-entry"
        :data-testid="`event-${event.id}`"
      >
        <div class="event-header" @click="toggleExpand(event.id)">
          <div class="event-info">
            <span class="event-date">{{ formatDate(event.received_at) }}</span>
            <span class="event-source">{{ event.matched ? 'matched' : 'unmatched' }}</span>
            <span class="status-pill" :class="statusClass(event.dispatch_status)">{{
              event.dispatch_status
            }}</span>
          </div>
          <div class="event-actions">
            <button
              class="replay-btn"
              data-testid="replay-btn"
              @click.stop="requestReplay(event.id)"
              :disabled="confirmReplayId !== null"
            >
              Replay
            </button>
            <span class="expand-chevron" :class="{ expanded: expandedId === event.id }">▾</span>
          </div>
        </div>

        <div
          v-if="confirmReplayId === event.id"
          class="confirm-row"
          data-testid="confirm-replay"
        >
          <span>Re-fire this payload through the trigger?</span>
          <div class="confirm-actions">
            <button
              class="btn-secondary"
              data-testid="cancel-replay"
              :disabled="isReplaying"
              @click="cancelReplay"
            >
              Cancel
            </button>
            <button
              class="btn-primary"
              data-testid="confirm-replay-btn"
              :disabled="isReplaying"
              @click="confirmReplay(event.id)"
            >
              {{ isReplaying ? 'Replaying...' : 'Confirm Replay' }}
            </button>
          </div>
        </div>

        <div
          v-if="expandedId === event.id"
          class="event-body"
          data-testid="event-body"
        >
          <div v-if="event.dispatch_error" class="error-message">
            <strong>Error:</strong> {{ event.dispatch_error }}
          </div>
          <div class="payload-section">
            <h4>Payload</h4>
            <pre class="payload-json"><code>{{ formatJson(parsedPayload(event.payload)) }}</code></pre>
          </div>
          <div v-if="event.signature_header" class="headers-section">
            <h4>Signature</h4>
            <pre class="payload-json"><code>{{ event.signature_header }}</code></pre>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.payload-history {
  margin-top: 16px;
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.section-header h3 {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
}
.entry-count {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}
.loading-state, .error-state, .empty-state {
  text-align: center;
  padding: 24px;
  color: var(--text-tertiary);
}
.empty-icon {
  font-size: 1.5rem;
  margin-bottom: 8px;
  color: var(--text-muted);
}
.spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid var(--border-default);
  border-top-color: var(--accent-cyan);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin-right: 8px;
  vertical-align: middle;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
.retry-btn {
  margin-top: 8px;
  padding: 6px 12px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.8rem;
}
.event-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.event-entry {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  overflow: hidden;
}
.event-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  cursor: pointer;
  transition: background var(--transition-fast);
}
.event-header:hover {
  background: var(--bg-tertiary);
}
.event-info {
  display: flex;
  align-items: center;
  gap: 12px;
}
.event-date {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: var(--text-secondary);
}
.event-source {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-tertiary);
}
.status-pill {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.65rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.status-pill.status-fired,
.status-pill.status-matched {
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
}
.status-pill.status-received {
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
}
.status-pill.status-skipped {
  background: var(--accent-amber-dim);
  color: var(--accent-amber);
}
.status-pill.status-error {
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
}
.event-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.replay-btn {
  padding: 4px 10px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.75rem;
  font-weight: 500;
  transition: all var(--transition-fast);
}
.replay-btn:hover:not(:disabled) {
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
  border-color: var(--accent-cyan);
}
.replay-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.expand-chevron {
  font-size: 0.85rem;
  color: var(--text-tertiary);
  transition: transform var(--transition-fast);
}
.expand-chevron.expanded {
  transform: rotate(180deg);
}
.confirm-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: var(--accent-amber-dim);
  border-top: 1px solid var(--border-subtle);
  font-size: 0.8rem;
  color: var(--text-primary);
}
.confirm-actions {
  display: flex;
  gap: 8px;
}
.btn-primary, .btn-secondary {
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 500;
  cursor: pointer;
  border: 1px solid var(--border-default);
}
.btn-primary {
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
  border-color: var(--accent-cyan);
}
.btn-primary:disabled, .btn-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn-secondary {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}
.event-body {
  padding: 12px 14px;
  border-top: 1px solid var(--border-subtle);
  background: var(--bg-primary);
}
.event-body h4 {
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-tertiary);
  margin: 0 0 6px 0;
}
.payload-section + .headers-section {
  margin-top: 12px;
}
.payload-json {
  margin: 0;
  padding: 10px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: var(--text-secondary);
  max-height: 320px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
}
.error-message {
  padding: 8px 12px;
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
  border-radius: 6px;
  font-size: 0.8rem;
  margin-bottom: 12px;
}
</style>
