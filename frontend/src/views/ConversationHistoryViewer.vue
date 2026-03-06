<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';

const showToast = useToast();

type TurnRole = 'user' | 'assistant' | 'tool_result' | 'tool_call';

interface ToolCall {
  name: string;
  input: Record<string, unknown>;
}

interface ConversationTurn {
  id: string;
  role: TurnRole;
  content: string;
  toolCall?: ToolCall;
  toolResultFor?: string;
  timestamp: string;
  tokenCount?: number;
  durationMs?: number;
}

interface ConversationSession {
  executionId: string;
  botName: string;
  startedAt: string;
  completedAt: string;
  totalTokens: number;
  totalTurns: number;
  outcome: 'success' | 'failure' | 'partial';
  turns: ConversationTurn[];
}

const searchQuery = ref('');
const filterRole = ref<TurnRole | 'all'>('all');
const selectedTurnId = ref<string | null>(null);
const isLoading = ref(true);

const session = ref<ConversationSession>({
  executionId: 'exec-demo-001',
  botName: 'bot-security',
  startedAt: '2026-03-06T09:00:00Z',
  completedAt: '2026-03-06T09:04:23Z',
  totalTokens: 14250,
  totalTurns: 12,
  outcome: 'success',
  turns: [
    {
      id: 't-001',
      role: 'user',
      content:
        'You are a security auditor. Review the following repository for vulnerabilities. Focus on authentication, input validation, and dependency issues. Repository: agented/backend',
      timestamp: '2026-03-06T09:00:00Z',
      tokenCount: 320,
    },
    {
      id: 't-002',
      role: 'assistant',
      content: "I'll start by reading the project structure and key entry points to understand the codebase before diving into security analysis.",
      timestamp: '2026-03-06T09:00:03Z',
      tokenCount: 48,
      durationMs: 3100,
    },
    {
      id: 't-003',
      role: 'tool_call',
      content: '',
      toolCall: {
        name: 'list_directory',
        input: { path: 'backend/app' },
      },
      timestamp: '2026-03-06T09:00:04Z',
    },
    {
      id: 't-004',
      role: 'tool_result',
      content:
        'routes/\nservices/\nmodels/\ndatabase.py\n__init__.py\nconfig.py\nmiddleware.py\nlogging_config.py',
      toolResultFor: 't-003',
      timestamp: '2026-03-06T09:00:05Z',
      durationMs: 800,
    },
    {
      id: 't-005',
      role: 'tool_call',
      content: '',
      toolCall: {
        name: 'read_file',
        input: { path: 'backend/app/middleware.py' },
      },
      timestamp: '2026-03-06T09:00:06Z',
    },
    {
      id: 't-006',
      role: 'tool_result',
      content:
        '# middleware.py\nfrom functools import wraps\nfrom flask import request, g\n\ndef require_auth(f):\n    @wraps(f)\n    def decorated(*args, **kwargs):\n        token = request.headers.get("Authorization")\n        if not token:\n            return {"error": "Unauthorized"}, 401\n        # TODO: validate token signature\n        g.user_id = token.split("|")[1] if "|" in token else None\n        return f(*args, **kwargs)\n    return decorated',
      toolResultFor: 't-005',
      timestamp: '2026-03-06T09:00:07Z',
      durationMs: 620,
    },
    {
      id: 't-007',
      role: 'assistant',
      content:
        'I found a critical issue in middleware.py: the `require_auth` decorator is splitting the token on `|` and trusting the user_id directly without signature verification. This is a JWT bypass vulnerability — any client can forge their user_id by crafting a token like `anything|target_user_id`. Let me check more routes.',
      timestamp: '2026-03-06T09:00:12Z',
      tokenCount: 112,
      durationMs: 5200,
    },
    {
      id: 't-008',
      role: 'tool_call',
      content: '',
      toolCall: {
        name: 'read_file',
        input: { path: 'backend/app/routes/executions.py', start_line: 1, end_line: 80 },
      },
      timestamp: '2026-03-06T09:00:13Z',
    },
    {
      id: 't-009',
      role: 'tool_result',
      content:
        'from flask_openapi3 import APIBlueprint\nfrom app.database import get_connection\nimport subprocess\n\n@executions_bp.route("/api/executions", methods=["POST"])\ndef run_execution():\n    payload = request.json\n    cmd = payload.get("command")\n    result = subprocess.run(cmd, shell=True, capture_output=True)\n    return {"output": result.stdout.decode()}',
      toolResultFor: 't-008',
      timestamp: '2026-03-06T09:00:14Z',
      durationMs: 540,
    },
    {
      id: 't-010',
      role: 'assistant',
      content:
        'Critical finding #2: `shell=True` with user-controlled `cmd` enables OS command injection. An attacker can pass `; rm -rf /` as the command. This needs immediate remediation — replace with a hardened subprocess call using a list argument and no shell interpolation.',
      timestamp: '2026-03-06T09:00:19Z',
      tokenCount: 96,
      durationMs: 4800,
    },
    {
      id: 't-011',
      role: 'tool_call',
      content: '',
      toolCall: {
        name: 'run_bash',
        input: { command: 'grep -r "eval\\|exec\\|__import__" backend/app --include="*.py" -l' },
      },
      timestamp: '2026-03-06T09:00:20Z',
    },
    {
      id: 't-012',
      role: 'tool_result',
      content: 'backend/app/routes/utility.py\nbackend/app/services/execution_service.py',
      toolResultFor: 't-011',
      timestamp: '2026-03-06T09:00:21Z',
      durationMs: 310,
    },
  ],
});

onMounted(() => {
  setTimeout(() => {
    isLoading.value = false;
  }, 300);
});

const filteredTurns = computed(() => {
  let turns = session.value.turns;
  if (filterRole.value !== 'all') {
    turns = turns.filter((t) => t.role === filterRole.value);
  }
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.toLowerCase();
    turns = turns.filter(
      (t) =>
        t.content.toLowerCase().includes(q) ||
        t.toolCall?.name.toLowerCase().includes(q) ||
        JSON.stringify(t.toolCall?.input || {}).toLowerCase().includes(q)
    );
  }
  return turns;
});

function roleLabel(role: TurnRole): string {
  const labels: Record<TurnRole, string> = {
    user: 'System Prompt',
    assistant: 'Model',
    tool_call: 'Tool Call',
    tool_result: 'Tool Result',
  };
  return labels[role];
}

function roleColor(role: TurnRole): string {
  const colors: Record<TurnRole, string> = {
    user: 'var(--accent-blue)',
    assistant: 'var(--accent-green)',
    tool_call: 'var(--accent-amber)',
    tool_result: 'var(--text-secondary)',
  };
  return colors[role];
}

function roleBg(role: TurnRole): string {
  const colors: Record<TurnRole, string> = {
    user: 'var(--accent-blue)',
    assistant: 'var(--accent-green)',
    tool_call: 'var(--accent-amber)',
    tool_result: 'transparent',
  };
  return colors[role] + '18';
}

function outcomeColor(outcome: string): string {
  return outcome === 'success' ? 'var(--accent-green)' : outcome === 'failure' ? 'var(--accent-red)' : 'var(--accent-amber)';
}

function formatDuration(ms?: number): string {
  if (!ms) return '';
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
}

function copyContent(turn: ConversationTurn) {
  const text = turn.toolCall ? JSON.stringify(turn.toolCall, null, 2) : turn.content;
  navigator.clipboard.writeText(text).then(() => showToast('Copied to clipboard', 'success'));
}

const totalDuration = computed(() => {
  const start = new Date(session.value.startedAt).getTime();
  const end = new Date(session.value.completedAt).getTime();
  const sec = Math.round((end - start) / 1000);
  return `${Math.floor(sec / 60)}m ${sec % 60}s`;
});
</script>

<template>
  <div class="page-container">
    <AppBreadcrumb :items="[{ label: 'Executions' }, { label: 'Conversation History' }]" />
    <PageHeader
      title="Conversation History Viewer"
      subtitle="Full multi-turn AI conversation with tool calls for any execution"
    />

    <!-- Search & filter -->
    <div class="controls-bar">
      <input
        v-model="searchQuery"
        class="search-input"
        placeholder="Search turns, tool names, content…"
        type="search"
      />
      <select v-model="filterRole" class="filter-select">
        <option value="all">All turn types</option>
        <option value="user">System Prompt</option>
        <option value="assistant">Model Output</option>
        <option value="tool_call">Tool Calls</option>
        <option value="tool_result">Tool Results</option>
      </select>
    </div>

    <div class="main-layout">
      <!-- Session meta panel -->
      <aside class="session-meta">
        <div class="meta-card">
          <h3>Session</h3>
          <div class="meta-row">
            <span class="meta-key">Execution</span>
            <span class="meta-val mono">{{ session.executionId }}</span>
          </div>
          <div class="meta-row">
            <span class="meta-key">Bot</span>
            <span class="meta-val">{{ session.botName }}</span>
          </div>
          <div class="meta-row">
            <span class="meta-key">Duration</span>
            <span class="meta-val">{{ totalDuration }}</span>
          </div>
          <div class="meta-row">
            <span class="meta-key">Total Turns</span>
            <span class="meta-val">{{ session.totalTurns }}</span>
          </div>
          <div class="meta-row">
            <span class="meta-key">Tokens Used</span>
            <span class="meta-val">{{ session.totalTokens.toLocaleString() }}</span>
          </div>
          <div class="meta-row">
            <span class="meta-key">Outcome</span>
            <span class="meta-val" :style="{ color: outcomeColor(session.outcome) }">
              {{ session.outcome }}
            </span>
          </div>
          <div class="meta-row">
            <span class="meta-key">Started</span>
            <span class="meta-val">{{ new Date(session.startedAt).toLocaleString() }}</span>
          </div>
        </div>

        <div class="meta-card">
          <h3>Turn Breakdown</h3>
          <div v-for="role in (['user', 'assistant', 'tool_call', 'tool_result'] as TurnRole[])" :key="role" class="meta-row">
            <span class="role-dot" :style="{ background: roleColor(role) }"></span>
            <span class="meta-key">{{ roleLabel(role) }}</span>
            <span class="meta-val">{{ session.turns.filter((t) => t.role === role).length }}</span>
          </div>
        </div>
      </aside>

      <!-- Turn list -->
      <div class="turn-list">
        <div
          v-for="turn in filteredTurns"
          :key="turn.id"
          class="turn-item"
          :class="{ selected: selectedTurnId === turn.id }"
          :style="{ borderLeftColor: roleColor(turn.role), background: roleBg(turn.role) }"
          @click="selectedTurnId = selectedTurnId === turn.id ? null : turn.id"
        >
          <div class="turn-header">
            <span class="role-label" :style="{ color: roleColor(turn.role) }">{{ roleLabel(turn.role) }}</span>
            <span v-if="turn.toolCall" class="tool-name">{{ turn.toolCall.name }}</span>
            <span v-if="turn.durationMs" class="turn-duration">{{ formatDuration(turn.durationMs) }}</span>
            <span v-if="turn.tokenCount" class="turn-tokens">{{ turn.tokenCount }} tok</span>
            <span class="turn-time">{{ new Date(turn.timestamp).toLocaleTimeString() }}</span>
            <button class="copy-btn" :title="`Copy turn ${turn.id}`" @click.stop="copyContent(turn)">⎘</button>
          </div>

          <!-- Tool call input -->
          <div v-if="turn.toolCall" class="tool-call-block">
            <pre class="code-block">{{ JSON.stringify(turn.toolCall.input, null, 2) }}</pre>
          </div>

          <!-- Text content -->
          <div v-else-if="turn.content" class="turn-content" :class="{ truncated: !selectedTurnId || selectedTurnId !== turn.id }">
            <pre class="content-pre">{{ turn.content }}</pre>
          </div>

          <!-- Tool result for reference -->
          <div v-if="turn.toolResultFor" class="result-for">
            Result for turn {{ turn.toolResultFor }}
          </div>
        </div>

        <div v-if="filteredTurns.length === 0" class="empty-state">
          <p>No turns match your filter.</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-container {
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.controls-bar {
  display: flex;
  gap: 12px;
  align-items: center;
}

.search-input {
  flex: 1;
  background: var(--surface-2);
  border: 1px solid var(--border);
  color: var(--text-primary);
  padding: 8px 14px;
  border-radius: 6px;
  font-size: 13px;
}

.filter-select {
  background: var(--surface-2);
  border: 1px solid var(--border);
  color: var(--text-primary);
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
}

.main-layout {
  display: grid;
  grid-template-columns: 240px 1fr;
  gap: 20px;
  align-items: start;
}

.session-meta {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.meta-card {
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
}

.meta-card h3 {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-secondary);
  margin: 0 0 12px;
}

.meta-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-size: 12px;
}

.meta-key {
  color: var(--text-secondary);
  flex: 1;
}

.meta-val {
  font-weight: 500;
  text-align: right;
}

.mono {
  font-family: monospace;
  font-size: 11px;
}

.role-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.turn-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.turn-item {
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-left-width: 3px;
  border-radius: 6px;
  padding: 14px 16px;
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.turn-item:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

.turn-item.selected {
  box-shadow: 0 0 0 2px var(--accent-blue);
}

.turn-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.role-label {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.tool-name {
  font-size: 13px;
  font-weight: 600;
  font-family: monospace;
  background: var(--surface-3);
  padding: 1px 6px;
  border-radius: 4px;
}

.turn-duration,
.turn-tokens {
  font-size: 11px;
  color: var(--text-secondary);
  background: var(--surface-3);
  padding: 1px 6px;
  border-radius: 4px;
}

.turn-time {
  font-size: 11px;
  color: var(--text-secondary);
  margin-left: auto;
}

.copy-btn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 14px;
  color: var(--text-secondary);
  padding: 2px 4px;
}

.copy-btn:hover {
  color: var(--text-primary);
}

.tool-call-block {
  margin-top: 8px;
}

.code-block {
  background: var(--surface-3);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 10px 12px;
  font-size: 12px;
  font-family: monospace;
  overflow-x: auto;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}

.turn-content {
  margin-top: 4px;
}

.turn-content.truncated .content-pre {
  max-height: 60px;
  overflow: hidden;
  mask-image: linear-gradient(to bottom, black 50%, transparent 100%);
}

.content-pre {
  font-size: 13px;
  font-family: inherit;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  line-height: 1.5;
  color: var(--text-secondary);
}

.result-for {
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 6px;
  font-style: italic;
}

.empty-state {
  text-align: center;
  padding: 48px;
  color: var(--text-secondary);
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 8px;
}
</style>
