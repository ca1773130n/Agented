<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';

interface LogLine {
  id: number;
  text: string;
  type: 'stdout' | 'stderr' | 'system';
  timestamp: string;
}

interface Section {
  id: number;
  label: string;
  startLine: number;
  collapsed: boolean;
}

const executionId = ref('exec-abc123');
const botName = ref('PR Review Bot');
const status = ref<'idle' | 'running' | 'completed' | 'failed'>('running');
const searchQuery = ref('');
const showSearch = ref(false);
const autoScroll = ref(true);
const terminalRef = ref<HTMLElement | null>(null);
const inputText = ref('');
let lineCounter = 0;

const sections = ref<Section[]>([
  { id: 1, label: 'Initialization', startLine: 0, collapsed: false },
  { id: 2, label: 'Fetching PR context', startLine: 5, collapsed: false },
  { id: 3, label: 'Running analysis', startLine: 10, collapsed: false },
]);

const allLines = ref<LogLine[]>([
  { id: lineCounter++, text: '=== Agented Execution Terminal ===', type: 'system', timestamp: '14:23:00' },
  { id: lineCounter++, text: 'Bot: PR Review Bot | Execution: exec-abc123', type: 'system', timestamp: '14:23:00' },
  { id: lineCounter++, text: '', type: 'stdout', timestamp: '14:23:00' },
  { id: lineCounter++, text: '[init] Loading bot configuration...', type: 'stdout', timestamp: '14:23:01' },
  { id: lineCounter++, text: '[init] Model: claude-sonnet-4-6 | Max tokens: 8192', type: 'stdout', timestamp: '14:23:01' },
  { id: lineCounter++, text: '', type: 'stdout', timestamp: '14:23:01' },
  { id: lineCounter++, text: '[fetch] Connecting to GitHub API...', type: 'stdout', timestamp: '14:23:02' },
  { id: lineCounter++, text: '[fetch] PR #312: feat: add execution queue with rate limiting', type: 'stdout', timestamp: '14:23:02' },
  { id: lineCounter++, text: '[fetch] Changed files: 7 | Additions: +342 | Deletions: -18', type: 'stdout', timestamp: '14:23:02' },
  { id: lineCounter++, text: '[fetch] Diff downloaded (28.4 KB)', type: 'stdout', timestamp: '14:23:03' },
  { id: lineCounter++, text: '', type: 'stdout', timestamp: '14:23:03' },
  { id: lineCounter++, text: '[analysis] Sending prompt to Claude...', type: 'stdout', timestamp: '14:23:04' },
  { id: lineCounter++, text: '[analysis] Token usage: 4,217 input tokens', type: 'stdout', timestamp: '14:23:04' },
  { id: lineCounter++, text: '\x1b[33m[warn] Large diff — truncating to 15,000 chars\x1b[0m', type: 'stderr', timestamp: '14:23:04' },
  { id: lineCounter++, text: '[analysis] Streaming response...', type: 'stdout', timestamp: '14:23:05' },
]);

const filteredLines = computed(() => {
  if (!searchQuery.value) return allLines.value;
  const q = searchQuery.value.toLowerCase();
  return allLines.value.filter((l) => l.text.toLowerCase().includes(q));
});

const stats = computed(() => ({
  total: allLines.value.length,
  errors: allLines.value.filter((l) => l.type === 'stderr').length,
}));

function ansiToHtml(text: string) {
  return text
    .replace(/\x1b\[33m/g, '<span style="color:#f0a500">')
    .replace(/\x1b\[31m/g, '<span style="color:var(--color-error)">')
    .replace(/\x1b\[32m/g, '<span style="color:var(--color-success)">')
    .replace(/\x1b\[36m/g, '<span style="color:#38bdf8">')
    .replace(/\x1b\[0m/g, '</span>')
    .replace(/\x1b\[\d+m/g, '');
}

function lineClass(line: LogLine) {
  if (line.type === 'system') return 'line-system';
  if (line.type === 'stderr') return 'line-stderr';
  return 'line-stdout';
}

function scrollToBottom() {
  nextTick(() => {
    if (terminalRef.value && autoScroll.value) {
      terminalRef.value.scrollTop = terminalRef.value.scrollHeight;
    }
  });
}

function sendInput() {
  if (!inputText.value.trim()) return;
  allLines.value.push({
    id: lineCounter++,
    text: `> ${inputText.value}`,
    type: 'system',
    timestamp: new Date().toLocaleTimeString('en-GB', { hour12: false }),
  });
  inputText.value = '';
  scrollToBottom();
}

function toggleSection(id: number) {
  const s = sections.value.find((s) => s.id === id);
  if (s) s.collapsed = !s.collapsed;
}

function clearTerminal() {
  allLines.value = [];
}

let intervalId: number | undefined;

onMounted(() => {
  scrollToBottom();
  if (status.value === 'running') {
    const mockLines = [
      '[analysis] > Reviewing logic in ExecutionQueueService...',
      '[analysis] > Checking for rate limit handling...',
      '[analysis] > Verifying queue drain behavior...',
      '[analysis] ✓ No blocking anti-patterns found',
      '[output] Posting review comment to PR #312...',
      '[output] ✓ Review posted successfully',
      '[done] Execution completed in 8.3s | Cost: $0.042',
    ];
    let i = 0;
    intervalId = window.setInterval(() => {
      if (i < mockLines.length) {
        allLines.value.push({
          id: lineCounter++,
          text: mockLines[i],
          type: mockLines[i].includes('✓') ? 'stdout' : 'stdout',
          timestamp: new Date().toLocaleTimeString('en-GB', { hour12: false }),
        });
        i++;
        scrollToBottom();
      } else {
        status.value = 'completed';
        clearInterval(intervalId);
      }
    }, 600);
  }
});

onUnmounted(() => {
  if (intervalId) clearInterval(intervalId);
});
</script>

<template>
  <div class="live-terminal-page">
    <AppBreadcrumb :items="[{ label: 'Executions' }, { label: 'Live Terminal' }]" />
    <PageHeader
      title="Live Execution Terminal"
      subtitle="Interactive ANSI-aware terminal view with search, collapsible sections, and mid-execution input"
    />

    <div class="terminal-wrapper">
      <div class="terminal-topbar">
        <div class="exec-info">
          <span class="bot-name">{{ botName }}</span>
          <code class="exec-id">{{ executionId }}</code>
          <span class="status-badge" :class="status">{{ status }}</span>
        </div>
        <div class="toolbar">
          <span class="stat">{{ stats.total }} lines</span>
          <span v-if="stats.errors > 0" class="stat error">{{ stats.errors }} warnings</span>
          <button class="tool-btn" :class="{ active: showSearch }" @click="showSearch = !showSearch" title="Search">
            &#128269;
          </button>
          <button class="tool-btn" :class="{ active: autoScroll }" @click="autoScroll = !autoScroll" title="Auto-scroll">
            &#8595;
          </button>
          <button class="tool-btn" @click="clearTerminal" title="Clear">&#10005;</button>
        </div>
      </div>

      <div v-if="showSearch" class="search-bar">
        <input
          v-model="searchQuery"
          placeholder="Search output..."
          class="search-input"
          autofocus
        />
        <span v-if="searchQuery" class="search-count">
          {{ filteredLines.length }} match{{ filteredLines.length !== 1 ? 'es' : '' }}
        </span>
      </div>

      <div class="sections-bar">
        <button
          v-for="s in sections"
          :key="s.id"
          class="section-btn"
          :class="{ collapsed: s.collapsed }"
          @click="toggleSection(s.id)"
        >
          {{ s.collapsed ? '▶' : '▼' }} {{ s.label }}
        </button>
      </div>

      <div class="terminal" ref="terminalRef" @scroll="autoScroll = false">
        <div
          v-for="line in filteredLines"
          :key="line.id"
          class="log-line"
          :class="lineClass(line)"
        >
          <span class="ts">{{ line.timestamp }}</span>
          <span class="line-text" v-html="ansiToHtml(line.text) || '&nbsp;'" />
        </div>
        <div v-if="status === 'running'" class="cursor-line">
          <span class="ts">{{ new Date().toLocaleTimeString('en-GB', { hour12: false }) }}</span>
          <span class="cursor">▮</span>
        </div>
      </div>

      <div v-if="status === 'running'" class="input-bar">
        <span class="input-prompt">$</span>
        <input
          v-model="inputText"
          placeholder="Send input to running bot..."
          class="terminal-input"
          @keydown.enter="sendInput"
        />
        <button class="send-btn" @click="sendInput">Send</button>
      </div>

      <div v-else class="exit-bar">
        <span class="exit-status" :class="status">
          Process exited — status: {{ status }}
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.live-terminal-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 0 1.5rem 3rem;
}

.terminal-wrapper {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  overflow: hidden;
  background: #0d0d0d;
  font-family: 'Geist Mono', 'JetBrains Mono', monospace;
}

.terminal-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.6rem 1rem;
  background: #1a1a1a;
  border-bottom: 1px solid #333;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.exec-info {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.bot-name {
  font-size: 0.875rem;
  font-weight: 600;
  color: #e2e8f0;
}

.exec-id {
  font-size: 0.75rem;
  color: #64748b;
}

.status-badge {
  font-size: 0.7rem;
  padding: 0.15rem 0.5rem;
  border-radius: 10px;
  font-weight: 600;
  text-transform: uppercase;
}

.status-badge.running {
  background: color-mix(in srgb, #f0a500 20%, transparent);
  color: #f0a500;
}

.status-badge.completed {
  background: color-mix(in srgb, #22c55e 20%, transparent);
  color: #22c55e;
}

.status-badge.failed {
  background: color-mix(in srgb, #ef4444 20%, transparent);
  color: #ef4444;
}

.status-badge.idle {
  background: color-mix(in srgb, #94a3b8 20%, transparent);
  color: #94a3b8;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.stat {
  font-size: 0.75rem;
  color: #64748b;
}

.stat.error {
  color: #f87171;
}

.tool-btn {
  width: 28px;
  height: 28px;
  border-radius: 4px;
  border: 1px solid #333;
  background: transparent;
  color: #94a3b8;
  cursor: pointer;
  font-size: 0.875rem;
  display: flex;
  align-items: center;
  justify-content: center;
}

.tool-btn.active {
  background: #1e3a5f;
  border-color: #3b82f6;
  color: #60a5fa;
}

.tool-btn:hover {
  background: #1f1f1f;
}

.search-bar {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 1rem;
  background: #111;
  border-bottom: 1px solid #333;
}

.search-input {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  color: #e2e8f0;
  font-family: monospace;
  font-size: 0.875rem;
}

.search-count {
  font-size: 0.75rem;
  color: #64748b;
}

.sections-bar {
  display: flex;
  gap: 0.25rem;
  padding: 0.4rem 0.75rem;
  background: #111;
  border-bottom: 1px solid #222;
  overflow-x: auto;
}

.section-btn {
  padding: 0.2rem 0.6rem;
  border-radius: 4px;
  border: 1px solid #333;
  background: transparent;
  color: #64748b;
  cursor: pointer;
  font-size: 0.7rem;
  white-space: nowrap;
}

.section-btn:hover {
  background: #1f1f1f;
  color: #94a3b8;
}

.section-btn.collapsed {
  opacity: 0.6;
}

.terminal {
  height: 420px;
  overflow-y: auto;
  padding: 0.75rem 0;
  scrollbar-width: thin;
  scrollbar-color: #333 transparent;
}

.log-line {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
  padding: 0.1rem 1rem;
  min-height: 1.4rem;
  font-size: 0.82rem;
  line-height: 1.5;
}

.log-line:hover {
  background: rgba(255, 255, 255, 0.03);
}

.ts {
  color: #475569;
  font-size: 0.7rem;
  flex-shrink: 0;
  width: 56px;
}

.line-text {
  color: #cbd5e1;
  word-break: break-all;
  flex: 1;
}

.line-system .line-text {
  color: #94a3b8;
}

.line-stderr .line-text {
  color: #fbbf24;
}

.cursor-line {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.1rem 1rem;
}

.cursor {
  color: #60a5fa;
  animation: blink 1s step-end infinite;
}

@keyframes blink {
  50% { opacity: 0; }
}

.input-bar {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.6rem 1rem;
  background: #111;
  border-top: 1px solid #333;
}

.input-prompt {
  color: #22c55e;
  font-size: 0.875rem;
}

.terminal-input {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  color: #e2e8f0;
  font-family: monospace;
  font-size: 0.875rem;
}

.send-btn {
  padding: 0.3rem 0.75rem;
  background: #1e3a5f;
  border: 1px solid #3b82f6;
  border-radius: 4px;
  color: #60a5fa;
  cursor: pointer;
  font-size: 0.8rem;
}

.exit-bar {
  padding: 0.6rem 1rem;
  background: #111;
  border-top: 1px solid #333;
}

.exit-status {
  font-size: 0.8rem;
  font-weight: 500;
}

.exit-status.completed {
  color: #22c55e;
}

.exit-status.failed {
  color: #ef4444;
}
</style>
