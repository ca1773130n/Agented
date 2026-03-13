<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { agentApi, agentConversationApi, ApiError } from '../services/api';
import type { Agent, AgentConversation } from '../services/api';

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

interface SessionData {
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
const loadError = ref<string | null>(null);
const agents = ref<Agent[]>([]);
const selectedAgentId = ref<string | null>(null);
const conversation = ref<AgentConversation | null>(null);

const session = ref<SessionData>({
  executionId: '',
  botName: '',
  startedAt: '',
  completedAt: '',
  totalTokens: 0,
  totalTurns: 0,
  outcome: 'success',
  turns: [],
});

onMounted(async () => {
  try {
    const resp = await agentApi.list();
    agents.value = resp.agents;

    if (agents.value.length > 0) {
      selectedAgentId.value = agents.value[0].id;
      await loadConversationForAgent(agents.value[0]);
    }
  } catch (err) {
    if (err instanceof ApiError) {
      loadError.value = `Failed to load agents: ${err.message}`;
    } else {
      loadError.value = 'An unexpected error occurred.';
    }
  } finally {
    isLoading.value = false;
  }
});

async function loadConversationForAgent(agent: Agent) {
  selectedAgentId.value = agent.id;
  isLoading.value = true;
  loadError.value = null;

  try {
    // Try to get conversation data if the agent has a creation_conversation_id
    if (agent.creation_conversation_id) {
      const convData = await agentConversationApi.get(agent.creation_conversation_id);
      conversation.value = convData;

      // Map conversation messages to turns
      const messages = convData.messages || convData.messages_parsed || [];
      const turns: ConversationTurn[] = messages.map((msg, idx) => ({
        id: `t-${idx}`,
        role: (msg.role === 'user' ? 'user' : msg.role === 'assistant' ? 'assistant' : 'assistant') as TurnRole,
        content: msg.content || '',
        timestamp: msg.timestamp || new Date().toISOString(),
      }));

      session.value = {
        executionId: agent.creation_conversation_id,
        botName: agent.name,
        startedAt: convData.created_at || new Date().toISOString(),
        completedAt: convData.updated_at || convData.created_at || new Date().toISOString(),
        totalTokens: 0,
        totalTurns: turns.length,
        outcome: convData.status === 'completed' ? 'success' : convData.status === 'abandoned' ? 'failure' : 'partial',
        turns,
      };
    } else {
      // No conversation available, show agent info as placeholder
      session.value = {
        executionId: agent.id,
        botName: agent.name,
        startedAt: agent.created_at || new Date().toISOString(),
        completedAt: agent.updated_at || agent.created_at || new Date().toISOString(),
        totalTokens: 0,
        totalTurns: 0,
        outcome: 'success',
        turns: [],
      };
      conversation.value = null;
    }
  } catch (err) {
    // Conversation may not exist — show agent info only
    session.value = {
      executionId: agent.id,
      botName: agent.name,
      startedAt: agent.created_at || new Date().toISOString(),
      completedAt: agent.updated_at || agent.created_at || new Date().toISOString(),
      totalTokens: 0,
      totalTurns: 0,
      outcome: 'success',
      turns: [],
    };
    conversation.value = null;
  } finally {
    isLoading.value = false;
  }
}

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
  if (!session.value.startedAt || !session.value.completedAt) return '0m 0s';
  const start = new Date(session.value.startedAt).getTime();
  const end = new Date(session.value.completedAt).getTime();
  const sec = Math.round((end - start) / 1000);
  if (isNaN(sec) || sec < 0) return '0m 0s';
  return `${Math.floor(sec / 60)}m ${sec % 60}s`;
});
</script>

<template>
  <div class="page-container">
    <AppBreadcrumb :items="[{ label: 'Agents' }, { label: 'Conversation History' }]" />
    <PageHeader
      title="Conversation History Viewer"
      subtitle="Full multi-turn AI conversation with tool calls for any agent"
    />

    <!-- Loading state -->
    <div v-if="isLoading && agents.length === 0" class="empty-state">
      <p>Loading agents...</p>
    </div>

    <!-- Error state -->
    <div v-else-if="loadError && agents.length === 0" class="empty-state" style="color: #ef4444;">
      <p>{{ loadError }}</p>
    </div>

    <!-- Empty state -->
    <div v-else-if="agents.length === 0" class="empty-state">
      <p>No agents found. Create an agent to view conversation history.</p>
    </div>

    <template v-else>
      <!-- Agent selector -->
      <div class="controls-bar">
        <select
          :value="selectedAgentId"
          class="filter-select"
          @change="loadConversationForAgent(agents.find(a => a.id === ($event.target as HTMLSelectElement).value)!)"
        >
          <option v-for="agent in agents" :key="agent.id" :value="agent.id">
            {{ agent.name }} ({{ agent.id }})
          </option>
        </select>
      </div>

      <!-- Search & filter -->
      <div class="controls-bar">
        <input
          v-model="searchQuery"
          class="search-input"
          placeholder="Search turns, tool names, content..."
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
              <span class="meta-key">Agent</span>
              <span class="meta-val">{{ session.botName }}</span>
            </div>
            <div class="meta-row">
              <span class="meta-key">ID</span>
              <span class="meta-val mono">{{ session.executionId }}</span>
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
              <span class="meta-key">Outcome</span>
              <span class="meta-val" :style="{ color: outcomeColor(session.outcome) }">
                {{ session.outcome }}
              </span>
            </div>
            <div class="meta-row">
              <span class="meta-key">Started</span>
              <span class="meta-val">{{ session.startedAt ? new Date(session.startedAt).toLocaleString() : '-' }}</span>
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
          <div v-if="isLoading" class="empty-state">
            <p>Loading conversation...</p>
          </div>

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
              <span class="turn-time">{{ turn.timestamp ? new Date(turn.timestamp).toLocaleTimeString() : '' }}</span>
              <button class="copy-btn" :title="`Copy turn ${turn.id}`" @click.stop="copyContent(turn)">&#9112;</button>
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

          <div v-if="!isLoading && filteredTurns.length === 0" class="empty-state">
            <p v-if="session.turns.length === 0">No conversation history available for this agent.</p>
            <p v-else>No turns match your filter.</p>
          </div>
        </div>
      </div>
    </template>
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
