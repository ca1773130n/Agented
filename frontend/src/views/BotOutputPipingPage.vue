<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';

const router = useRouter();

interface Pipe {
  id: string;
  name: string;
  sourceBot: string;
  destBot: string;
  transform: 'passthrough' | 'trim' | 'json-extract';
  enabled: boolean;
}

interface PipeExecution {
  id: string;
  pipeName: string;
  triggeredAt: string;
  sourcePreview: string;
  destinationStatus: 'success' | 'running' | 'failed' | 'pending';
}

const pipes = ref<Pipe[]>([
  { id: 'pipe-1', name: 'Security Scan → Slack Notify', sourceBot: 'bot-security', destBot: 'bot-slack-notify', transform: 'trim', enabled: true },
  { id: 'pipe-2', name: 'PR Review → Jira Ticket', sourceBot: 'bot-pr-review', destBot: 'bot-jira', transform: 'json-extract', enabled: true },
  { id: 'pipe-3', name: 'Dep Audit → Summary Bot', sourceBot: 'bot-dep-audit', destBot: 'bot-summary', transform: 'passthrough', enabled: false },
]);

const executions = ref<PipeExecution[]>([
  { id: 'exec-1', pipeName: 'Security Scan → Slack Notify', triggeredAt: '3 minutes ago', sourcePreview: 'Found 2 critical CVEs in lodash@4.17.20 and follow-redirects@1.14.8...', destinationStatus: 'success' },
  { id: 'exec-2', pipeName: 'PR Review → Jira Ticket', triggeredAt: '18 minutes ago', sourcePreview: 'PR #412: Missing null check in auth middleware. Severity: medium...', destinationStatus: 'running' },
  { id: 'exec-3', pipeName: 'Security Scan → Slack Notify', triggeredAt: '1 hour ago', sourcePreview: 'No critical findings. 3 low-severity advisories noted.', destinationStatus: 'success' },
  { id: 'exec-4', pipeName: 'Dep Audit → Summary Bot', triggeredAt: '2 hours ago', sourcePreview: 'Dependency tree audit complete. 47 packages scanned, 0 critical...', destinationStatus: 'failed' },
]);

const selectedPipeId = ref<string>('pipe-1');

const selectedPipe = computed(() => pipes.value.find(p => p.id === selectedPipeId.value) ?? pipes.value[0]);

function transformLabel(t: Pipe['transform']): string {
  if (t === 'passthrough') return 'Passthrough';
  if (t === 'trim') return 'Trim Whitespace';
  if (t === 'json-extract') return 'JSON Extract';
  return t;
}

function togglePipe(pipe: Pipe) {
  pipe.enabled = !pipe.enabled;
}
</script>

<template>
  <div class="bot-output-piping">
    <AppBreadcrumb :items="[
      { label: 'Bots', action: () => router.push({ name: 'bots' }) },
      { label: 'Output Piping' },
    ]" />

    <PageHeader
      title="Bot Output Piping"
      subtitle="Chain bot executions sequentially — the output of one bot becomes the input context for the next."
    />

    <!-- Pipe List -->
    <div class="card">
      <div class="card-header">
        <h3>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
            <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>
          </svg>
          Configured Pipes
        </h3>
        <button class="btn btn-primary">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
            <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
          </svg>
          Create New Pipe
        </button>
      </div>
      <div class="pipes-list">
        <div
          v-for="pipe in pipes"
          :key="pipe.id"
          class="pipe-row"
          :class="{ 'is-selected': selectedPipeId === pipe.id }"
          @click="selectedPipeId = pipe.id"
        >
          <div class="pipe-info">
            <span class="pipe-name">{{ pipe.name }}</span>
            <div class="pipe-meta">
              <span class="pipe-bot source">{{ pipe.sourceBot }}</span>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12" style="color: var(--text-muted)">
                <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>
              </svg>
              <span class="pipe-bot dest">{{ pipe.destBot }}</span>
            </div>
          </div>
          <div class="pipe-transform">
            <span class="transform-badge" :class="pipe.transform">{{ transformLabel(pipe.transform) }}</span>
          </div>
          <div class="pipe-toggle" @click.stop="togglePipe(pipe)">
            <div class="toggle" :class="{ active: pipe.enabled }">
              <div class="toggle-thumb" />
            </div>
            <span class="toggle-label" :class="pipe.enabled ? 'text-green' : 'text-muted'">
              {{ pipe.enabled ? 'Enabled' : 'Disabled' }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- Pipe Diagram -->
    <div class="card">
      <div class="card-header">
        <h3>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
            <rect x="2" y="7" width="6" height="10" rx="1"/>
            <rect x="9" y="9" width="6" height="6" rx="1"/>
            <rect x="16" y="7" width="6" height="10" rx="1"/>
          </svg>
          Pipe Diagram
        </h3>
        <span class="pipe-title-badge">{{ selectedPipe?.name }}</span>
      </div>
      <div class="diagram-area">
        <div class="diagram-node source-node">
          <div class="node-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="20" height="20">
              <circle cx="12" cy="12" r="3"/>
              <path d="M12 2v3M12 19v3M4.22 4.22l2.12 2.12M17.66 17.66l2.12 2.12M2 12h3M19 12h3M4.22 19.78l2.12-2.12M17.66 6.34l2.12-2.12"/>
            </svg>
          </div>
          <div class="node-label">Source Bot</div>
          <div class="node-value">{{ selectedPipe?.sourceBot }}</div>
          <div class="node-sublabel">stdout captured</div>
        </div>

        <div class="diagram-arrow">
          <svg viewBox="0 0 80 24" fill="none" xmlns="http://www.w3.org/2000/svg" width="80" height="24">
            <line x1="0" y1="12" x2="60" y2="12" stroke="var(--accent-cyan)" stroke-width="1.5" stroke-dasharray="4 3"/>
            <polyline points="54,6 62,12 54,18" stroke="var(--accent-cyan)" stroke-width="1.5" fill="none"/>
          </svg>
        </div>

        <div class="diagram-node transform-node">
          <div class="node-icon transform-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="20" height="20">
              <polyline points="16 3 21 3 21 8"/><line x1="4" y1="20" x2="21" y2="3"/>
              <polyline points="21 16 21 21 16 21"/><line x1="15" y1="15" x2="21" y2="21"/>
            </svg>
          </div>
          <div class="node-label">Transform</div>
          <div class="node-value">{{ transformLabel(selectedPipe?.transform ?? 'passthrough') }}</div>
          <div class="node-sublabel">output processed</div>
        </div>

        <div class="diagram-arrow">
          <svg viewBox="0 0 80 24" fill="none" xmlns="http://www.w3.org/2000/svg" width="80" height="24">
            <line x1="0" y1="12" x2="60" y2="12" stroke="var(--accent-cyan)" stroke-width="1.5" stroke-dasharray="4 3"/>
            <polyline points="54,6 62,12 54,18" stroke="var(--accent-cyan)" stroke-width="1.5" fill="none"/>
          </svg>
        </div>

        <div class="diagram-node dest-node">
          <div class="node-icon dest-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="20" height="20">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
              <polyline points="22 4 12 14.01 9 11.01"/>
            </svg>
          </div>
          <div class="node-label">Destination Bot</div>
          <div class="node-value">{{ selectedPipe?.destBot }}</div>
          <div class="node-sublabel">stdin injected</div>
        </div>
      </div>
    </div>

    <!-- Recent Executions -->
    <div class="card">
      <div class="card-header">
        <h3>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
          </svg>
          Recent Pipe Executions
        </h3>
      </div>
      <div class="exec-table">
        <div class="exec-thead">
          <span>Pipe</span>
          <span>Triggered</span>
          <span>Source Preview</span>
          <span>Destination Status</span>
        </div>
        <div v-for="exec in executions" :key="exec.id" class="exec-row">
          <span class="exec-pipe">{{ exec.pipeName }}</span>
          <span class="exec-time">{{ exec.triggeredAt }}</span>
          <span class="exec-preview">{{ exec.sourcePreview }}</span>
          <span class="exec-status">
            <span :class="['status-dot', exec.destinationStatus]" />
            <span :class="['status-text', exec.destinationStatus]">{{ exec.destinationStatus }}</span>
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.bot-output-piping {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-default);
}

.card-header h3 {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.card-header h3 svg { color: var(--accent-cyan); }

.pipe-title-badge {
  font-size: 0.78rem;
  font-weight: 500;
  padding: 4px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-secondary);
}

/* Pipe List */
.pipes-list {
  display: flex;
  flex-direction: column;
}

.pipe-row {
  display: grid;
  grid-template-columns: 1fr auto auto;
  gap: 20px;
  align-items: center;
  padding: 14px 24px;
  border-bottom: 1px solid var(--border-subtle);
  cursor: pointer;
  transition: background 0.1s;
}

.pipe-row:hover { background: var(--bg-tertiary); }
.pipe-row:last-child { border-bottom: none; }

.pipe-row.is-selected {
  background: rgba(0, 212, 255, 0.04);
  border-left: 2px solid var(--accent-cyan);
  padding-left: 22px;
}

.pipe-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.pipe-name {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-primary);
}

.pipe-meta {
  display: flex;
  align-items: center;
  gap: 6px;
}

.pipe-bot {
  font-size: 0.72rem;
  font-family: 'Geist Mono', monospace;
  padding: 2px 7px;
  border-radius: 4px;
}

.pipe-bot.source {
  background: rgba(99, 102, 241, 0.15);
  color: #818cf8;
}

.pipe-bot.dest {
  background: rgba(52, 211, 153, 0.12);
  color: #34d399;
}

.pipe-transform {
  display: flex;
  align-items: center;
}

.transform-badge {
  font-size: 0.7rem;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.transform-badge.passthrough {
  background: rgba(148, 163, 184, 0.15);
  color: var(--text-secondary);
}

.transform-badge.trim {
  background: rgba(251, 191, 36, 0.15);
  color: #fbbf24;
}

.transform-badge.json-extract {
  background: rgba(0, 212, 255, 0.12);
  color: var(--accent-cyan);
}

.pipe-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.toggle {
  width: 34px;
  height: 18px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 9px;
  position: relative;
  transition: background 0.2s, border-color 0.2s;
}

.toggle.active {
  background: rgba(0, 212, 255, 0.2);
  border-color: var(--accent-cyan);
}

.toggle-thumb {
  width: 12px;
  height: 12px;
  background: var(--text-muted);
  border-radius: 50%;
  position: absolute;
  top: 2px;
  left: 2px;
  transition: transform 0.2s, background 0.2s;
}

.toggle.active .toggle-thumb {
  transform: translateX(16px);
  background: var(--accent-cyan);
}

.toggle-label {
  font-size: 0.78rem;
  font-weight: 500;
  min-width: 52px;
}

.text-green { color: #34d399; }
.text-muted { color: var(--text-muted); }

/* Diagram */
.diagram-area {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0;
  padding: 40px 32px;
  flex-wrap: wrap;
}

.diagram-node {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 20px 24px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 10px;
  min-width: 160px;
  text-align: center;
  transition: border-color 0.2s;
}

.source-node { border-color: rgba(99, 102, 241, 0.4); }
.transform-node { border-color: rgba(251, 191, 36, 0.3); }
.dest-node { border-color: rgba(52, 211, 153, 0.3); }

.node-icon {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(99, 102, 241, 0.15);
  border-radius: 8px;
  color: #818cf8;
  margin-bottom: 4px;
}

.transform-icon {
  background: rgba(251, 191, 36, 0.12);
  color: #fbbf24;
}

.dest-icon {
  background: rgba(52, 211, 153, 0.12);
  color: #34d399;
}

.node-label {
  font-size: 0.68rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-tertiary);
}

.node-value {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--text-primary);
  font-family: 'Geist Mono', monospace;
}

.node-sublabel {
  font-size: 0.7rem;
  color: var(--text-muted);
}

.diagram-arrow {
  display: flex;
  align-items: center;
  padding: 0 4px;
}

/* Executions Table */
.exec-table {
  display: flex;
  flex-direction: column;
}

.exec-thead {
  display: grid;
  grid-template-columns: 220px 130px 1fr 130px;
  gap: 16px;
  padding: 10px 24px;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-tertiary);
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-tertiary);
}

.exec-row {
  display: grid;
  grid-template-columns: 220px 130px 1fr 130px;
  gap: 16px;
  align-items: center;
  padding: 13px 24px;
  border-bottom: 1px solid var(--border-subtle);
  font-size: 0.85rem;
  transition: background 0.1s;
}

.exec-row:hover { background: var(--bg-tertiary); }
.exec-row:last-child { border-bottom: none; }

.exec-pipe {
  font-weight: 500;
  color: var(--text-primary);
}

.exec-time {
  color: var(--text-tertiary);
  font-size: 0.78rem;
  white-space: nowrap;
}

.exec-preview {
  color: var(--text-secondary);
  font-size: 0.8rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.exec-status {
  display: flex;
  align-items: center;
  gap: 6px;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-dot.success { background: #34d399; }
.status-dot.running { background: #fbbf24; animation: pulse 1.2s ease-in-out infinite; }
.status-dot.failed { background: #ef4444; }
.status-dot.pending { background: var(--text-muted); }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.status-text {
  font-size: 0.78rem;
  font-weight: 500;
  text-transform: capitalize;
}

.status-text.success { color: #34d399; }
.status-text.running { color: #fbbf24; }
.status-text.failed { color: #ef4444; }
.status-text.pending { color: var(--text-muted); }

/* Button */
.btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border-radius: 7px;
  font-size: 0.82rem;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}

.btn-primary {
  background: var(--accent-cyan);
  color: #000;
}

.btn-primary:hover { opacity: 0.85; }
</style>
