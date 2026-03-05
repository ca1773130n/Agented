<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';

const router = useRouter();
const showToast = useToast();

interface QueuedExecution {
  id: string;
  bot: string;
  trigger: string;
  priority: 'critical' | 'normal' | 'batch';
  status: 'pending' | 'running';
  queuedAt: string;
  estimatedDuration: number;
  position: number;
}

const queue = ref<QueuedExecution[]>([
  { id: 'ex-001', bot: 'bot-security', trigger: 'webhook/github', priority: 'critical', status: 'running', queuedAt: '2 min ago', estimatedDuration: 240, position: 1 },
  { id: 'ex-002', bot: 'bot-pr-review', trigger: 'webhook/github', priority: 'critical', status: 'running', queuedAt: '3 min ago', estimatedDuration: 120, position: 2 },
  { id: 'ex-003', bot: 'bot-pr-review', trigger: 'webhook/github', priority: 'normal', status: 'pending', queuedAt: '4 min ago', estimatedDuration: 90, position: 3 },
  { id: 'ex-004', bot: 'bot-security', trigger: 'schedule/daily', priority: 'normal', status: 'pending', queuedAt: '5 min ago', estimatedDuration: 300, position: 4 },
  { id: 'ex-005', bot: 'bot-changelog', trigger: 'manual', priority: 'batch', status: 'pending', queuedAt: '6 min ago', estimatedDuration: 60, position: 5 },
  { id: 'ex-006', bot: 'bot-dep-scan', trigger: 'schedule/weekly', priority: 'batch', status: 'pending', queuedAt: '7 min ago', estimatedDuration: 180, position: 6 },
]);

const isDragging = ref<string | null>(null);
const dragOverId = ref<string | null>(null);
let refreshInterval: ReturnType<typeof setInterval> | null = null;

const criticalQueue = computed(() => queue.value.filter(e => e.priority === 'critical'));
const normalQueue = computed(() => queue.value.filter(e => e.priority === 'normal'));
const batchQueue = computed(() => queue.value.filter(e => e.priority === 'batch'));

const stats = computed(() => ({
  running: queue.value.filter(e => e.status === 'running').length,
  pending: queue.value.filter(e => e.status === 'pending').length,
  total: queue.value.length,
}));

function handleDragStart(id: string) {
  isDragging.value = id;
}

function handleDragOver(id: string) {
  dragOverId.value = id;
}

function handleDrop(targetId: string) {
  if (!isDragging.value || isDragging.value === targetId) {
    isDragging.value = null;
    dragOverId.value = null;
    return;
  }
  const fromIdx = queue.value.findIndex(e => e.id === isDragging.value);
  const toIdx = queue.value.findIndex(e => e.id === targetId);
  if (fromIdx === -1 || toIdx === -1) return;

  const item = queue.value.splice(fromIdx, 1)[0];
  queue.value.splice(toIdx, 0, item);
  queue.value.forEach((e, i) => { e.position = i + 1; });
  showToast('Queue order updated', 'info');
  isDragging.value = null;
  dragOverId.value = null;
}

function priorityColor(p: string): string {
  const map: Record<string, string> = { critical: '#ef4444', normal: '#3b82f6', batch: '#6b7280' };
  return map[p] ?? '#6b7280';
}

function statusColor(s: string): string {
  return s === 'running' ? '#34d399' : '#f59e0b';
}

function formatDuration(secs: number): string {
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

function simulateProgress() {
  // Occasionally advance queue
  const running = queue.value.filter(e => e.status === 'running');
  if (running.length > 0 && Math.random() > 0.7) {
    const finished = running[Math.floor(Math.random() * running.length)];
    queue.value = queue.value.filter(e => e.id !== finished.id);
    const next = queue.value.find(e => e.status === 'pending');
    if (next) { next.status = 'running'; }
  }
}

onMounted(() => {
  refreshInterval = setInterval(simulateProgress, 5000);
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
      subtitle="Monitor and reprioritize the execution queue in real time."
    />

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
        <span class="stat-num">{{ stats.total }}</span>
        <span class="stat-lbl">Total</span>
      </div>
      <div class="stat-card">
        <span class="stat-num" style="color: var(--accent-cyan)">Live</span>
        <span class="stat-lbl">Auto-refresh 5s</span>
      </div>
    </div>

    <div class="lanes">
      <div v-for="[laneKey, laneLabel, laneQueue] in [['critical', 'Critical', criticalQueue], ['normal', 'Normal', normalQueue], ['batch', 'Batch', batchQueue]]" :key="(laneKey as string)" class="lane">
        <div class="lane-header" :style="{ borderBottomColor: priorityColor(laneKey as string) }">
          <div class="lane-dot" :style="{ background: priorityColor(laneKey as string) }"></div>
          <span class="lane-label">{{ laneLabel }}</span>
          <span class="lane-count">{{ (laneQueue as QueuedExecution[]).length }}</span>
        </div>

        <div class="lane-items">
          <div
            v-for="ex in (laneQueue as QueuedExecution[])"
            :key="ex.id"
            class="queue-item"
            :class="{
              'is-running': ex.status === 'running',
              'is-dragging': isDragging === ex.id,
              'is-drag-over': dragOverId === ex.id,
            }"
            draggable="true"
            @dragstart="handleDragStart(ex.id)"
            @dragover.prevent="handleDragOver(ex.id)"
            @drop.prevent="handleDrop(ex.id)"
            @dragend="isDragging = null; dragOverId = null"
          >
            <div class="item-drag-handle">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
                <line x1="8" y1="6" x2="21" y2="6"/>
                <line x1="8" y1="12" x2="21" y2="12"/>
                <line x1="8" y1="18" x2="21" y2="18"/>
                <line x1="3" y1="6" x2="3.01" y2="6"/>
                <line x1="3" y1="12" x2="3.01" y2="12"/>
                <line x1="3" y1="18" x2="3.01" y2="18"/>
              </svg>
            </div>
            <div class="item-pos">#{{ ex.position }}</div>
            <div class="item-info">
              <div class="item-bot">{{ ex.bot }}</div>
              <div class="item-trigger">{{ ex.trigger }}</div>
            </div>
            <div class="item-right">
              <span class="item-status" :style="{ color: statusColor(ex.status), background: statusColor(ex.status) + '20' }">
                {{ ex.status }}
              </span>
              <span class="item-est">~{{ formatDuration(ex.estimatedDuration) }}</span>
            </div>
            <div v-if="ex.status === 'running'" class="item-progress">
              <div class="progress-bar">
                <div class="progress-fill running-anim"></div>
              </div>
            </div>
          </div>

          <div v-if="(laneQueue as QueuedExecution[]).length === 0" class="lane-empty">
            No {{ laneKey }} executions
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
