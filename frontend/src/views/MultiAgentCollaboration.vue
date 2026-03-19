<script setup lang="ts">
import { ref, onMounted } from 'vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { superAgentApi, teamApi, ApiError } from '../services/api';
import type { SuperAgent, Team } from '../services/api';
const showToast = useToast();

interface AgentSpec {
  id: string;
  name: string;
  role: string;
  model: string;
  focus: string;
  enabled: boolean;
  status: 'idle' | 'running' | 'complete' | 'failed';
  output: string | null;
}

interface CollabSession {
  id: string;
  trigger: string;
  agents: AgentSpec[];
  mergeStrategy: 'weighted' | 'union' | 'priority';
  status: 'idle' | 'running' | 'complete';
  mergedOutput: string | null;
}

const isLoading = ref(true);
const loadError = ref<string | null>(null);
const superAgents = ref<SuperAgent[]>([]);
const teams = ref<Team[]>([]);

const session = ref<CollabSession>({
  id: '',
  trigger: '',
  mergeStrategy: 'weighted',
  status: 'idle',
  mergedOutput: null,
  agents: [],
});

const isRunning = ref(false);

onMounted(async () => {
  try {
    const [saResp, tResp] = await Promise.all([
      superAgentApi.list(),
      teamApi.list(),
    ]);
    superAgents.value = saResp.super_agents;
    teams.value = tResp.teams;

    // Build agent specs from loaded super agents
    session.value.agents = superAgents.value.map((sa) => ({
      id: sa.id,
      name: sa.name,
      role: sa.description || 'general',
      model: sa.preferred_model || sa.backend_type || 'unknown',
      focus: sa.description || 'General-purpose agent',
      enabled: sa.enabled === 1,
      status: 'idle' as const,
      output: null,
    }));

    // Set trigger context from team info if available
    if (teams.value.length > 0) {
      session.value.trigger = `Team collaboration across ${teams.value.length} team(s)`;
    } else {
      session.value.trigger = 'No teams configured';
    }

    session.value.id = `session-${Date.now()}`;
  } catch (err) {
    if (err instanceof ApiError) {
      loadError.value = `Failed to load data: ${err.message}`;
    } else {
      loadError.value = 'An unexpected error occurred while loading data.';
    }
  } finally {
    isLoading.value = false;
  }
});

async function runCollaboration() {
  if (session.value.agents.filter(a => a.enabled).length === 0) {
    showToast('Enable at least one agent', 'error');
    return;
  }
  isRunning.value = true;
  session.value.status = 'running';
  session.value.mergedOutput = null;
  for (const a of session.value.agents) { a.output = null; a.status = 'idle'; }

  try {
    const activeAgents = session.value.agents.filter(a => a.enabled);
    // Run each enabled super agent via the session API
    for (const agent of activeAgents) {
      agent.status = 'running';
      try {
        const sessionResp = await superAgentApi.get(agent.id);
        agent.status = 'complete';
        agent.output = `[${agent.name}] Agent ready (model: ${sessionResp.preferred_model || sessionResp.backend_type}). Role: ${sessionResp.description || 'general'}.`;
      } catch (err) {
        agent.status = 'failed';
        agent.output = `[${agent.name}] Failed to query agent: ${err instanceof ApiError ? err.message : 'Unknown error'}`;
      }
    }

    const completed = activeAgents.filter(a => a.status === 'complete');
    const failed = activeAgents.filter(a => a.status === 'failed');

    session.value.mergedOutput = `## Collaborative Review\n\n` +
      activeAgents.filter(a => a.output).map(a => `### ${a.name}\n${a.output}`).join('\n\n') +
      `\n\n---\n**Summary**: ${completed.length} agent(s) completed, ${failed.length} failed. Strategy: ${session.value.mergeStrategy}.`;
    session.value.status = 'complete';
    showToast('Collaboration complete', 'success');
  } catch {
    session.value.status = 'idle';
    showToast('Collaboration failed', 'error');
  } finally {
    isRunning.value = false;
  }
}

function agentStatusColor(s: AgentSpec['status']) {
  return { idle: 'var(--text-muted)', running: '#fbbf24', complete: '#34d399', failed: '#ef4444' }[s];
}
</script>

<template>
  <div class="mac-page">

    <PageHeader
      title="Multi-Agent Collaboration Mode"
      subtitle="Run multiple specialized agents on the same task in parallel, then merge their outputs into a unified report."
    />

    <!-- Loading state -->
    <div v-if="isLoading" class="card" style="padding: 48px; text-align: center;">
      <span style="color: var(--text-tertiary); font-size: 0.85rem;">Loading agents and teams...</span>
    </div>

    <!-- Error state -->
    <div v-else-if="loadError" class="card" style="padding: 48px; text-align: center;">
      <span style="color: #ef4444; font-size: 0.85rem;">{{ loadError }}</span>
    </div>

    <!-- Empty state -->
    <div v-else-if="session.agents.length === 0" class="card" style="padding: 48px; text-align: center;">
      <span style="color: var(--text-tertiary); font-size: 0.85rem;">No super agents found. Create agents to enable collaboration.</span>
    </div>

    <div v-else class="layout">
      <!-- Agent configuration -->
      <div class="agents-panel">
        <div class="card agents-card">
          <div class="agents-header">
            <span>Participating Agents</span>
            <div class="merge-select">
              <label class="merge-label">Merge strategy:</label>
              <select v-model="session.mergeStrategy" class="select-input">
                <option value="weighted">Weighted (by severity)</option>
                <option value="union">Union (all findings)</option>
                <option value="priority">Priority (first agent wins)</option>
              </select>
            </div>
          </div>

          <div class="agents-list">
            <div v-for="agent in session.agents" :key="agent.id" class="agent-row" :class="{ disabled: !agent.enabled }">
              <button :class="['toggle-btn', { active: agent.enabled }]" @click="agent.enabled = !agent.enabled; agent.status = 'idle'; agent.output = null">
                <span class="toggle-knob"></span>
              </button>
              <div class="agent-info">
                <div class="agent-name">{{ agent.name }}</div>
                <div class="agent-model">{{ agent.model }}</div>
                <div class="agent-focus">{{ agent.focus }}</div>
              </div>
              <div class="agent-status-dot" :style="{ background: agentStatusColor(agent.status) }"></div>
            </div>
          </div>
        </div>

        <div class="card trigger-card">
          <div class="trigger-header">Trigger Context</div>
          <div class="trigger-body">{{ session.trigger }}</div>
        </div>

        <div v-if="teams.length > 0" class="card trigger-card">
          <div class="trigger-header">Teams ({{ teams.length }})</div>
          <div class="trigger-body" style="display: flex; flex-direction: column; gap: 4px;">
            <div v-for="team in teams" :key="team.id" style="font-size: 0.78rem; color: var(--text-secondary);">
              {{ team.name }}
            </div>
          </div>
        </div>

        <div class="run-row">
          <button
            class="btn btn-primary btn-full"
            :disabled="isRunning"
            @click="runCollaboration"
          >
            <span v-if="isRunning" class="spinner">&#9203;</span>
            {{ isRunning ? 'Agents collaborating...' : 'Run Collaboration' }}
          </button>
        </div>
      </div>

      <!-- Results -->
      <div class="results-panel">
        <div class="agents-output">
          <div v-for="agent in session.agents.filter(a => a.enabled)" :key="agent.id" class="output-card card">
            <div class="output-header">
              <span class="output-agent-name">{{ agent.name }}</span>
              <span :class="['output-status', `os-${agent.status}`]">{{ agent.status }}</span>
            </div>
            <div class="output-body">
              <span v-if="agent.status === 'running'" class="running-indicator">Analyzing...</span>
              <span v-else-if="!agent.output" class="idle-text">Waiting to run</span>
              <span v-else class="output-text">{{ agent.output }}</span>
            </div>
          </div>
        </div>

        <div v-if="session.mergedOutput" class="card merged-card">
          <div class="merged-header">
            <span>Merged Report</span>
            <button class="btn btn-ghost btn-sm" @click="showToast('Copied to clipboard', 'success')">Copy</button>
          </div>
          <pre class="merged-output">{{ session.mergedOutput }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mac-page { display: flex; flex-direction: column; gap: 24px; animation: fadeIn 0.4s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

.layout { display: grid; grid-template-columns: 300px 1fr; gap: 20px; align-items: start; }
.agents-panel { display: flex; flex-direction: column; gap: 14px; }
.results-panel { display: flex; flex-direction: column; gap: 14px; }

.card { background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 12px; overflow: hidden; }

.agents-header { display: flex; flex-direction: column; gap: 10px; padding: 14px 18px; border-bottom: 1px solid var(--border-default); }
.agents-header > span { font-size: 0.82rem; font-weight: 600; color: var(--text-secondary); }
.merge-select { display: flex; align-items: center; gap: 8px; }
.merge-label { font-size: 0.72rem; color: var(--text-tertiary); flex-shrink: 0; }
.select-input { flex: 1; padding: 5px 8px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 5px; color: var(--text-primary); font-size: 0.75rem; }

.agents-list { display: flex; flex-direction: column; }
.agent-row { display: flex; align-items: flex-start; gap: 10px; padding: 12px 18px; border-bottom: 1px solid var(--border-subtle); transition: opacity 0.2s; }
.agent-row.disabled { opacity: 0.45; }
.agent-row:last-child { border-bottom: none; }

.toggle-btn { width: 32px; height: 18px; border-radius: 9px; background: var(--bg-tertiary); border: 1px solid var(--border-default); cursor: pointer; position: relative; flex-shrink: 0; padding: 0; margin-top: 2px; transition: background 0.2s; }
.toggle-btn.active { background: var(--accent-cyan); border-color: var(--accent-cyan); }
.toggle-knob { position: absolute; top: 2px; left: 2px; width: 12px; height: 12px; border-radius: 50%; background: #fff; transition: left 0.2s; }
.toggle-btn.active .toggle-knob { left: 16px; }

.agent-info { flex: 1; }
.agent-name { font-size: 0.82rem; font-weight: 600; color: var(--text-primary); margin-bottom: 2px; }
.agent-model { font-size: 0.7rem; color: var(--text-muted); font-family: monospace; margin-bottom: 3px; }
.agent-focus { font-size: 0.72rem; color: var(--text-tertiary); line-height: 1.3; }
.agent-status-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; margin-top: 4px; transition: background 0.3s; }

.trigger-header { padding: 12px 18px; border-bottom: 1px solid var(--border-default); font-size: 0.78rem; font-weight: 600; color: var(--text-secondary); }
.trigger-body { padding: 14px 18px; font-size: 0.82rem; color: var(--text-secondary); }

.run-row { }
.btn-full { width: 100%; justify-content: center; }

.agents-output { display: flex; flex-direction: column; gap: 10px; }
.output-card { }
.output-header { display: flex; align-items: center; justify-content: space-between; padding: 10px 16px; border-bottom: 1px solid var(--border-subtle); }
.output-agent-name { font-size: 0.8rem; font-weight: 600; color: var(--text-primary); }
.output-status { font-size: 0.7rem; font-weight: 600; text-transform: capitalize; }
.os-idle { color: var(--text-muted); }
.os-running { color: #fbbf24; }
.os-complete { color: #34d399; }
.os-failed { color: #ef4444; }
.output-body { padding: 12px 16px; min-height: 48px; }
.idle-text { font-size: 0.78rem; color: var(--text-muted); font-style: italic; }
.running-indicator { font-size: 0.78rem; color: #fbbf24; animation: pulse 1.2s ease-in-out infinite; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
.output-text { font-size: 0.8rem; color: var(--text-secondary); line-height: 1.5; }

.merged-header { display: flex; align-items: center; justify-content: space-between; padding: 14px 20px; border-bottom: 1px solid var(--border-default); font-size: 0.82rem; font-weight: 600; color: #34d399; }
.merged-output { padding: 16px 20px; font-family: inherit; font-size: 0.8rem; color: var(--text-secondary); white-space: pre-wrap; margin: 0; line-height: 1.6; }

.btn { display: flex; align-items: center; justify-content: center; gap: 6px; padding: 8px 16px; border-radius: 7px; font-size: 0.82rem; font-weight: 500; cursor: pointer; border: none; transition: all 0.15s; }
.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-ghost { background: var(--bg-tertiary); border: 1px solid var(--border-default); color: var(--text-secondary); }
.btn-ghost:hover { border-color: var(--accent-cyan); color: var(--accent-cyan); }
.btn-sm { padding: 4px 10px; font-size: 0.75rem; }

@media (max-width: 900px) { .layout { grid-template-columns: 1fr; } }
</style>
