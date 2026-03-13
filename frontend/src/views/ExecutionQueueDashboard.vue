<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { executionApi, triggerApi, ApiError } from '../services/api';
import type { Execution, Trigger } from '../services/api';

const router = useRouter();
const showToast = useToast();

interface QueueEntry {
  trigger_id: string;
  pending: number;
  dispatching: number;
}

const queueSummary = ref<QueueEntry[]>([]);
const totalPending = ref(0);
const runningExecutions = ref<Execution[]>([]);
const pendingExecutions = ref<Execution[]>([]);
const triggers = ref<Map<string, Trigger>>(new Map());
const isLoading = ref(true);
const loadError = ref('');
const cancellingIds = ref<Set<string>>(new Set());

let refreshInterval: ReturnType<typeof setInterval> | null = null;

// Combine running and pending for display
const allExecutions = computed(() => {
  const items = [
    ...runningExecutions.value.map((ex, i) => ({
      id: ex.execution_id,
      triggerName: triggers.value.get(ex.trigger_id)?.name ?? ex.trigger_id,
      triggerType: ex.trigger_type ?? 'unknown',
      status: ex.status as 'running' | 'pending' | 'paused',
      startedAt: ex.started_at,
      position: i + 1,
    })),
    ...pendingExecutions.value.map((ex, i) => ({
      id: ex.execution_id,
      triggerName: triggers.value.get(ex.trigger_id)?.name ?? ex.trigger_id,
      triggerType: ex.trigger_type ?? 'unknown',
      status: 'pending' as const,
      startedAt: ex.started_at,
      position: runningExecutions.value.length + i + 1,
    })),
  ];
  return items;
});

const runningQueue = computed(() => allExecutions.value.filter(e => e.status === 'running' || e.status === 'paused'));
const pendingQueue = computed(() => allExecutions.value.filter(e => e.status === 'pending'));

const stats = computed(() => ({
  running: runningExecutions.value.length,
  pending: totalPending.value,
  dispatching: queueSummary.value.reduce((sum, q) => sum + q.dispatching, 0),
  total: runningExecutions.value.length + totalPending.value,
}));

// Drag-and-drop state (visual only since backend queue is FIFO)
const isDragging = ref<string | null>(null);
const dragOverId = ref<string | null>(null);

function handleDragStart(id: string) {
  isDragging.value = id;
}

function handleDragOver(id: string) {
  dragOverId.value = id;
}

function handleDrop(_targetId: string) {
  isDragging.value = null;
  dragOverId.value = null;
  showToast('Queue order is managed by the backend (FIFO with priority)', 'info');
}

function statusColor(s: string): string {
  const map: Record<string, string> = {
    running: '#34d399',
    pending: '#f59e0b',
    paused: '#a78bfa',
    dispatching: '#3b82f6',
  };
  return map[s] ?? '#6b7280';
}

function formatTimeAgo(dateStr: string): string {
  if (!dateStr) return 'unknown';
  const diff = Date.now() - new Date(dateStr).getTime();
  const secs = Math.floor(diff / 1000);
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  return `${hours}h ago`;
}

async function loadTriggers() {
  const res = await triggerApi.list();
  const map = new Map<string, Trigger>();
  for (const t of res.triggers ?? []) {
    map.set(t.id, t);
  }
  triggers.value = map;
}

async function loadQueueData() {
  try {
    const [queueRes, runningRes, pendingRes] = await Promise.all([
      executionApi.getQueueStatus(),
      executionApi.listAll({ limit: 50, status: 'running' }),
      executionApi.listAll({ limit: 50, status: 'pending' }),
    ]);

    queueSummary.value = queueRes.queue;
    totalPending.value = queueRes.total_pending;
    runningExecutions.value = runningRes.executions ?? [];
    pendingExecutions.value = pendingRes.executions ?? [];
    loadError.value = '';
  } catch (err) {
    loadError.value = err instanceof ApiError ? err.message : 'Failed to load queue data';
  } finally {
    isLoading.value = false;
  }
}

async function cancelExecution(executionId: string) {
  if (cancellingIds.value.has(executionId)) return;
  cancellingIds.value.add(executionId);
  try {
    await executionApi.cancel(executionId);
    showToast('Execution cancellation initiated', 'success');
    await loadQueueData();
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to cancel execution';
    showToast(message, 'error');
  } finally {
    cancellingIds.value.delete(executionId);
  }
}

async function cancelQueueForTrigger(triggerId: string) {
  try {
    const res = await executionApi.cancelQueueForTrigger(triggerId);
    showToast(`Cancelled ${res.cancelled} pending entries`, 'success');
    await loadQueueData();
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to cancel queue entries';
    showToast(message, 'error');
  }
}

onMounted(async () => {
  await Promise.all([loadTriggers().catch(() => {}), loadQueueData()]);
  refreshInterval = setInterval(loadQueueData, 5000);
});

onUnmounted(() => {
  if (refreshInterval) clearInterval(refreshInterval);
});
</script>

<template>
  <div class="exec-queue">
    <AppBreadcrumb :items="[
      { label: 'Executions', action: () => router.push({ name: 'executions' }) },
      { label: 'Queue Dashboard' },
    ]" />

    <PageHeader
      title="Execution Queue Dashboard"
      subtitle="Monitor and manage the execution queue in real time."
    />

    <!-- Loading state -->
    <div v-if="isLoading" class="loading-state">
      <div class="loading-spinner"></div>
      <span>Loading queue data...</span>
    </div>

    <!-- Error state -->
    <div v-else-if="loadError" class="error-state">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20">
        <circle cx="12" cy="12" r="10"/>
        <line x1="12" y1="8" x2="12" y2="12"/>
        <line x1="12" y1="16" x2="12.01" y2="16"/>
      </svg>
      <span>{{ loadError }}</span>
      <button class="btn btn-secondary" @click="loadQueueData">Retry</button>
    </div>

    <template v-else>
      <div class="stats-bar">
        <div class="stat-card">
          <span class="stat-num" style="color: #34d399">{{ stats.running }}</span>
          <span class="stat-lbl">Running</span>
        </div>
        <div class="stat-card">
          <span class="stat-num" style="color: #f59e0b">{{ stats.pending }}</span>
          <span class="stat-lbl">Pending</span>
        </div>
        <div class="stat-card">
          <span class="stat-num" style="color: #3b82f6">{{ stats.dispatching }}</span>
          <span class="stat-lbl">Dispatching</span>
        </div>
        <div class="stat-card">
          <span class="stat-num">{{ stats.total }}</span>
          <span class="stat-lbl">Total</span>
        </div>
        <div class="stat-card">
          <span class="stat-num" style="color: var(--accent-cyan)">Live</span>
          <span class="stat-lbl">Auto-refresh 5s</span>
        </div>
      </div>

      <div class="lanes">
        <!-- Running Lane -->
        <div class="lane">
          <div class="lane-header" style="border-bottom-color: #34d399">
            <div class="lane-dot" style="background: #34d399"></div>
            <span class="lane-label">Running</span>
            <span class="lane-count">{{ runningQueue.length }}</span>
          </div>
          <div class="lane-items">
            <div
              v-for="ex in runningQueue"
              :key="ex.id"
              class="queue-item is-running"
              draggable="true"
              @dragstart="handleDragStart(ex.id)"
              @dragover.prevent="handleDragOver(ex.id)"
              @drop.prevent="handleDrop(ex.id)"
              @dragend="isDragging = null; dragOverId = null"
              :class="{ 'is-dragging': isDragging === ex.id, 'is-drag-over': dragOverId === ex.id }"
            >
              <div class="item-drag-handle">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
                  <line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/>
                  <line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>
                </svg>
              </div>
              <div class="item-pos">#{{ ex.position }}</div>
              <div class="item-info">
                <div class="item-bot">{{ ex.triggerName }}</div>
                <div class="item-trigger">{{ ex.triggerType }} | {{ ex.id }}</div>
              </div>
              <div class="item-right">
                <span class="item-status" :style="{ color: statusColor(ex.status), background: statusColor(ex.status) + '20' }">
                  {{ ex.status }}
                </span>
                <span class="item-est">{{ formatTimeAgo(ex.startedAt) }}</span>
              </div>
              <button
                class="cancel-btn"
                :disabled="cancellingIds.has(ex.id)"
                @click.stop="cancelExecution(ex.id)"
                title="Cancel execution"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              </button>
              <div class="item-progress">
                <div class="progress-bar">
                  <div class="progress-fill running-anim"></div>
                </div>
              </div>
            </div>
            <div v-if="runningQueue.length === 0" class="lane-empty">
              No running executions
            </div>
          </div>
        </div>

        <!-- Pending Lane -->
        <div class="lane">
          <div class="lane-header" style="border-bottom-color: #f59e0b">
            <div class="lane-dot" style="background: #f59e0b"></div>
            <span class="lane-label">Pending</span>
            <span class="lane-count">{{ pendingQueue.length }}</span>
          </div>
          <div class="lane-items">
            <div
              v-for="ex in pendingQueue"
              :key="ex.id"
              class="queue-item"
              draggable="true"
              @dragstart="handleDragStart(ex.id)"
              @dragover.prevent="handleDragOver(ex.id)"
              @drop.prevent="handleDrop(ex.id)"
              @dragend="isDragging = null; dragOverId = null"
              :class="{ 'is-dragging': isDragging === ex.id, 'is-drag-over': dragOverId === ex.id }"
            >
              <div class="item-drag-handle">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
                  <line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/>
                  <line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>
                </svg>
              </div>
              <div class="item-pos">#{{ ex.position }}</div>
              <div class="item-info">
                <div class="item-bot">{{ ex.triggerName }}</div>
                <div class="item-trigger">{{ ex.triggerType }} | {{ ex.id }}</div>
              </div>
              <div class="item-right">
                <span class="item-status" :style="{ color: statusColor(ex.status), background: statusColor(ex.status) + '20' }">
                  {{ ex.status }}
                </span>
                <span class="item-est">{{ formatTimeAgo(ex.startedAt) }}</span>
              </div>
              <button
                class="cancel-btn"
                :disabled="cancellingIds.has(ex.id)"
                @click.stop="cancelExecution(ex.id)"
                title="Cancel execution"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              </button>
            </div>
            <div v-if="pendingQueue.length === 0" class="lane-empty">
              No pending executions
            </div>
          </div>
        </div>

        <!-- Per-Trigger Queue Summary Lane -->
        <div class="lane">
          <div class="lane-header" style="border-bottom-color: #6b7280">
            <div class="lane-dot" style="background: #6b7280"></div>
            <span class="lane-label">Queue by Trigger</span>
            <span class="lane-count">{{ queueSummary.length }}</span>
          </div>
          <div class="lane-items">
            <div
              v-for="entry in queueSummary"
              :key="entry.trigger_id"
              class="queue-item"
            >
              <div class="item-info">
                <div class="item-bot">{{ triggers.get(entry.trigger_id)?.name ?? entry.trigger_id }}</div>
                <div class="item-trigger">{{ entry.trigger_id }}</div>
              </div>
              <div class="item-right">
                <span class="item-status" :style="{ color: '#f59e0b', background: '#f59e0b20' }">
                  {{ entry.pending }} pending
                </span>
                <span v-if="entry.dispatching > 0" class="item-status" :style="{ color: '#3b82f6', background: '#3b82f620' }" style="margin-top: 3px">
                  {{ entry.dispatching }} dispatching
                </span>
              </div>
              <button
                v-if="entry.pending > 0"
                class="cancel-btn"
                @click.stop="cancelQueueForTrigger(entry.trigger_id)"
                title="Cancel all pending for this trigger"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              </button>
            </div>
            <div v-if="queueSummary.length === 0" class="lane-empty">
              No queued triggers
            </div>
          </div>
        </div>
      </div>

      <div class="drag-hint">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14">
          <polyline points="5 9 2 12 5 15"/><polyline points="9 5 12 2 15 5"/>
          <polyline points="15 19 12 22 9 19"/><polyline points="19 9 22 12 19 15"/>
          <line x1="2" y1="12" x2="22" y2="12"/><line x1="12" y1="2" x2="12" y2="22"/>
        </svg>
        Drag executions to reprioritize within the queue
      </div>
    </template>
  </div>
</template>

<style scoped>
.exec-queue {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 60px 20px;
  color: var(--text-tertiary);
  font-size: 0.9rem;
}

.loading-spinner {
  width: 20px;
  height: 20px;
  border: 2px solid var(--border-default);
  border-top-color: var(--accent-cyan);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.error-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 40px 20px;
  color: #ef4444;
  font-size: 0.9rem;
}

.btn-secondary {
  padding: 6px 14px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-secondary:hover {
  border-color: var(--accent-cyan);
  color: var(--text-primary);
}

.stats-bar {
  display: flex;
  gap: 16px;
}

.stat-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 14px 20px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 10px;
}

.stat-num {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.stat-lbl {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  font-weight: 500;
}

.lanes {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  align-items: start;
}

.lane {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
}

.lane-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 18px;
  border-bottom: 2px solid transparent;
}

.lane-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.lane-label {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-primary);
  flex: 1;
}

.lane-count {
  font-size: 0.75rem;
  font-weight: 700;
  color: var(--text-tertiary);
  background: var(--bg-tertiary);
  padding: 2px 8px;
  border-radius: 10px;
}

.lane-items {
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: 8px;
}

.queue-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  cursor: grab;
  transition: all 0.15s;
  user-select: none;
  position: relative;
}

.queue-item:hover { border-color: var(--border-default); background: var(--bg-elevated); }
.queue-item.is-running { border-color: rgba(52, 211, 153, 0.3); background: rgba(52, 211, 153, 0.05); }
.queue-item.is-dragging { opacity: 0.4; cursor: grabbing; }
.queue-item.is-drag-over { border-color: var(--accent-cyan); background: rgba(6, 182, 212, 0.06); }

.item-drag-handle {
  color: var(--text-muted);
  flex-shrink: 0;
}

.item-pos {
  font-size: 0.72rem;
  font-weight: 700;
  color: var(--text-muted);
  min-width: 20px;
}

.item-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.item-bot {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-family: monospace;
}

.item-trigger {
  font-size: 0.72rem;
  color: var(--text-tertiary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.item-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 3px;
}

.item-status {
  font-size: 0.65rem;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 3px;
  text-transform: uppercase;
}

.item-est {
  font-size: 0.68rem;
  color: var(--text-muted);
  font-family: monospace;
}

.cancel-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 4px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 4px;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.15s;
  flex-shrink: 0;
}

.cancel-btn:hover {
  color: #ef4444;
  border-color: rgba(239, 68, 68, 0.3);
  background: rgba(239, 68, 68, 0.1);
}

.cancel-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.item-progress {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 2px;
}

.progress-bar {
  height: 100%;
  background: var(--bg-tertiary);
  border-radius: 0 0 6px 6px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: #34d399;
}

.running-anim {
  animation: progress 3s ease-in-out infinite;
}

@keyframes progress {
  0% { width: 20%; }
  50% { width: 70%; }
  100% { width: 90%; }
}

.lane-empty {
  padding: 24px 12px;
  text-align: center;
  font-size: 0.8rem;
  color: var(--text-muted);
}

.drag-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.78rem;
  color: var(--text-muted);
  justify-content: center;
}

@media (max-width: 900px) {
  .lanes { grid-template-columns: 1fr; }
}
</style>
