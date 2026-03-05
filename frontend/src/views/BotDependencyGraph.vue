<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';

const router = useRouter();

interface Node {
  id: string;
  label: string;
  type: 'bot' | 'trigger' | 'team' | 'agent';
  x: number;
  y: number;
  color: string;
}

interface Edge {
  id: string;
  from: string;
  to: string;
  label: string;
  isCircular: boolean;
}

const nodes = ref<Node[]>([
  { id: 'bot-security', label: 'bot-security', type: 'bot', x: 300, y: 120, color: '#ef4444' },
  { id: 'bot-pr-review', label: 'bot-pr-review', type: 'bot', x: 600, y: 120, color: '#3b82f6' },
  { id: 'bot-deploy', label: 'bot-deploy', type: 'bot', x: 450, y: 280, color: '#8b5cf6' },
  { id: 'trig-github', label: 'GitHub Webhook', type: 'trigger', x: 150, y: 50, color: '#f59e0b' },
  { id: 'trig-schedule', label: 'Schedule (daily)', type: 'trigger', x: 450, y: 40, color: '#f59e0b' },
  { id: 'team-security', label: 'Security Team', type: 'team', x: 100, y: 220, color: '#06b6d4' },
  { id: 'team-platform', label: 'Platform Team', type: 'team', x: 700, y: 220, color: '#06b6d4' },
  { id: 'agent-main', label: 'Main Agent', type: 'agent', x: 450, y: 420, color: '#34d399' },
]);

const edges = ref<Edge[]>([
  { id: 'e1', from: 'trig-github', to: 'bot-security', label: 'fires', isCircular: false },
  { id: 'e2', from: 'trig-github', to: 'bot-pr-review', label: 'fires', isCircular: false },
  { id: 'e3', from: 'trig-schedule', to: 'bot-security', label: 'fires', isCircular: false },
  { id: 'e4', from: 'bot-security', to: 'bot-deploy', label: 'triggers', isCircular: false },
  { id: 'e5', from: 'team-security', to: 'bot-security', label: 'owns', isCircular: false },
  { id: 'e6', from: 'team-platform', to: 'bot-pr-review', label: 'owns', isCircular: false },
  { id: 'e7', from: 'bot-deploy', to: 'agent-main', label: 'uses', isCircular: false },
]);

const selectedNode = ref<Node | null>(null);
const hasCircularDeps = ref(false);
const showLegend = ref(true);


function getNodeById(id: string): Node | undefined {
  return nodes.value.find(n => n.id === id);
}

function handleNodeClick(node: Node) {
  selectedNode.value = selectedNode.value?.id === node.id ? null : node;
}

function getConnectedEdges(nodeId: string): Edge[] {
  return edges.value.filter(e => e.from === nodeId || e.to === nodeId);
}

function typeLabel(type: string): string {
  const map: Record<string, string> = { bot: 'Bot', trigger: 'Trigger', team: 'Team', agent: 'Agent' };
  return map[type] ?? type;
}

const viewBox = '0 0 800 480';
</script>

<template>
  <div class="dep-graph">
    <AppBreadcrumb :items="[
      { label: 'Bots', action: () => router.push({ name: 'bots' }) },
      { label: 'Dependency Graph' },
    ]" />

    <PageHeader title="Bot Dependency Graph" subtitle="Visualize relationships between bots, triggers, teams, and agents.">
      <template #actions>
        <button class="btn btn-secondary" @click="showLegend = !showLegend">
          {{ showLegend ? 'Hide' : 'Show' }} Legend
        </button>
        <div v-if="hasCircularDeps" class="circular-alert">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
            <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
          </svg>
          Circular dependency detected
        </div>
      </template>
    </PageHeader>

    <div class="graph-layout">
      <div class="card graph-card">
        <svg :viewBox="viewBox" class="graph-svg" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <marker id="arrowhead" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
              <polygon points="0 0, 8 3, 0 6" fill="var(--text-tertiary)" />
            </marker>
            <marker id="arrowhead-circular" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
              <polygon points="0 0, 8 3, 0 6" fill="#ef4444" />
            </marker>
          </defs>

          <!-- Edges -->
          <g v-for="edge in edges" :key="edge.id">
            <line
              :x1="getNodeById(edge.from)?.x ?? 0"
              :y1="getNodeById(edge.from)?.y ?? 0"
              :x2="getNodeById(edge.to)?.x ?? 0"
              :y2="getNodeById(edge.to)?.y ?? 0"
              :stroke="edge.isCircular ? '#ef4444' : 'var(--border-default)'"
              stroke-width="1.5"
              :stroke-dasharray="edge.label === 'uses' ? '4,3' : 'none'"
              :marker-end="edge.isCircular ? 'url(#arrowhead-circular)' : 'url(#arrowhead)'"
              opacity="0.7"
            />
            <text
              :x="((getNodeById(edge.from)?.x ?? 0) + (getNodeById(edge.to)?.x ?? 0)) / 2"
              :y="((getNodeById(edge.from)?.y ?? 0) + (getNodeById(edge.to)?.y ?? 0)) / 2 - 6"
              class="edge-label"
              text-anchor="middle"
              font-size="9"
              fill="var(--text-muted)"
            >{{ edge.label }}</text>
          </g>

          <!-- Nodes -->
          <g
            v-for="node in nodes"
            :key="node.id"
            class="graph-node"
            :class="{ selected: selectedNode?.id === node.id }"
            @click="handleNodeClick(node)"
            style="cursor: pointer"
          >
            <circle
              :cx="node.x"
              :cy="node.y"
              r="30"
              :fill="node.color + '20'"
              :stroke="selectedNode?.id === node.id ? node.color : node.color + '80'"
              :stroke-width="selectedNode?.id === node.id ? 2.5 : 1.5"
            />
            <text
              :x="node.x"
              :y="node.y - 2"
              text-anchor="middle"
              dominant-baseline="middle"
              font-size="9"
              font-weight="600"
              :fill="node.color"
            >{{ typeLabel(node.type) }}</text>
            <text
              :x="node.x"
              :y="node.y + 44"
              text-anchor="middle"
              font-size="10"
              fill="var(--text-secondary)"
              font-weight="500"
            >{{ node.label }}</text>
          </g>
        </svg>
      </div>

      <div class="side-panel">
        <div v-if="showLegend" class="card legend-card">
          <div class="card-header-sm">Legend</div>
          <div class="legend-items">
            <div v-for="[type, color] in [['Bot', '#3b82f6'], ['Trigger', '#f59e0b'], ['Team', '#06b6d4'], ['Agent', '#34d399']]" :key="type" class="legend-item">
              <div class="legend-dot" :style="{ background: color }"></div>
              <span>{{ type }}</span>
            </div>
            <div class="legend-item">
              <div class="legend-line solid"></div>
              <span>fires / triggers</span>
            </div>
            <div class="legend-item">
              <div class="legend-line dashed"></div>
              <span>uses</span>
            </div>
          </div>
        </div>

        <div v-if="selectedNode" class="card detail-card">
          <div class="card-header-sm">Node Details</div>
          <div class="node-detail">
            <div class="nd-type" :style="{ color: selectedNode.color, background: selectedNode.color + '15' }">
              {{ typeLabel(selectedNode.type) }}
            </div>
            <div class="nd-name">{{ selectedNode.label }}</div>
            <div class="nd-edges">
              <div class="nd-edge-label">Connections</div>
              <div v-for="e in getConnectedEdges(selectedNode.id)" :key="e.id" class="nd-edge-row">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="10" height="10">
                  <line x1="5" y1="12" x2="19" y2="12"/>
                  <polyline points="12 5 19 12 12 19"/>
                </svg>
                <span>{{ e.label }} {{ e.from === selectedNode.id ? getNodeById(e.to)?.label : getNodeById(e.from)?.label }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="card stats-card">
          <div class="card-header-sm">Summary</div>
          <div class="graph-stats">
            <div class="gs-row">
              <span class="gs-label">Nodes</span>
              <span class="gs-val">{{ nodes.length }}</span>
            </div>
            <div class="gs-row">
              <span class="gs-label">Edges</span>
              <span class="gs-val">{{ edges.length }}</span>
            </div>
            <div class="gs-row">
              <span class="gs-label">Circular deps</span>
              <span class="gs-val" style="color: #34d399">None detected</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dep-graph {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.graph-layout {
  display: grid;
  grid-template-columns: 1fr 240px;
  gap: 20px;
  align-items: start;
}

.card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
}

.graph-card { padding: 16px; }

.graph-svg {
  width: 100%;
  height: auto;
  display: block;
}

.graph-node {
  transition: transform 0.1s;
}

.graph-node:hover circle {
  filter: brightness(1.2);
}

.graph-node.selected circle {
  filter: drop-shadow(0 0 6px currentColor);
}

.side-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.card-header-sm {
  padding: 12px 16px;
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-bottom: 1px solid var(--border-subtle);
}

.legend-card .legend-items {
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.82rem;
  color: var(--text-secondary);
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.legend-line {
  width: 24px;
  height: 2px;
  flex-shrink: 0;
  background: var(--border-default);
}

.legend-line.dashed {
  background: repeating-linear-gradient(90deg, var(--border-default) 0, var(--border-default) 4px, transparent 4px, transparent 7px);
}

.detail-card .node-detail {
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.nd-type {
  font-size: 0.7rem;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 4px;
  width: fit-content;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.nd-name {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-primary);
  font-family: monospace;
}

.nd-edge-label {
  font-size: 0.72rem;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 6px;
}

.nd-edge-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.8rem;
  color: var(--text-secondary);
  padding: 4px 0;
}

.stats-card .graph-stats {
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.gs-row {
  display: flex;
  justify-content: space-between;
  font-size: 0.85rem;
}

.gs-label { color: var(--text-secondary); }
.gs-val { font-weight: 600; color: var(--text-primary); }

.circular-alert {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.8rem;
  color: #ef4444;
  background: rgba(239, 68, 68, 0.1);
  padding: 6px 12px;
  border-radius: 6px;
  border: 1px solid rgba(239, 68, 68, 0.3);
}

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

.btn-secondary {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
}

.btn-secondary:hover { border-color: var(--accent-cyan); color: var(--text-primary); }

@media (max-width: 900px) {
  .graph-layout { grid-template-columns: 1fr; }
}
</style>
