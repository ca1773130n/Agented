<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import LoadingState from '../components/base/LoadingState.vue';

const router = useRouter();

const isLoading = ref(true);

interface AgentCapability {
  name: string;
  category: 'tool' | 'skill' | 'permission';
  description: string;
}

interface Agent {
  id: string;
  name: string;
  team: string;
  capabilities: string[];
  status: 'active' | 'idle' | 'error';
}

const agents = ref<Agent[]>([]);
const allCapabilities = ref<AgentCapability[]>([]);
const filterCategory = ref<string>('all');
const filterTeam = ref<string>('all');
const searchQuery = ref('');

async function loadData() {
  try {
    const res = await fetch('/admin/agents/capabilities');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    agents.value = data.agents ?? [];
    allCapabilities.value = data.capabilities ?? [];
  } catch {
    allCapabilities.value = [
      { name: 'code_review', category: 'skill', description: 'Review pull request code quality' },
      { name: 'security_scan', category: 'skill', description: 'Scan for security vulnerabilities' },
      { name: 'test_generation', category: 'skill', description: 'Generate unit and integration tests' },
      { name: 'github_read', category: 'permission', description: 'Read GitHub repositories' },
      { name: 'github_write', category: 'permission', description: 'Write to GitHub repositories' },
      { name: 'slack_notify', category: 'tool', description: 'Send Slack notifications' },
      { name: 'jira_create', category: 'tool', description: 'Create Jira issues' },
      { name: 'file_system', category: 'permission', description: 'Access local file system' },
      { name: 'web_search', category: 'tool', description: 'Search the web for information' },
      { name: 'dependency_check', category: 'skill', description: 'Analyze project dependencies' },
      { name: 'docs_generation', category: 'skill', description: 'Generate documentation' },
      { name: 'lint_fix', category: 'tool', description: 'Run linter and fix issues' },
    ];
    agents.value = [
      { id: 'agent-sec01', name: 'Security Auditor', team: 'Security', capabilities: ['security_scan', 'github_read', 'jira_create', 'web_search'], status: 'active' },
      { id: 'agent-rev01', name: 'Code Reviewer', team: 'Platform', capabilities: ['code_review', 'github_read', 'github_write', 'slack_notify', 'lint_fix'], status: 'active' },
      { id: 'agent-tst01', name: 'Test Generator', team: 'QA', capabilities: ['test_generation', 'github_read', 'github_write', 'file_system'], status: 'idle' },
      { id: 'agent-doc01', name: 'Docs Writer', team: 'Platform', capabilities: ['docs_generation', 'github_read', 'github_write', 'file_system'], status: 'idle' },
      { id: 'agent-dep01', name: 'Dep Inspector', team: 'Security', capabilities: ['dependency_check', 'github_read', 'web_search', 'jira_create'], status: 'active' },
      { id: 'agent-err01', name: 'Build Watcher', team: 'QA', capabilities: ['github_read', 'slack_notify', 'lint_fix'], status: 'error' },
    ];
  } finally {
    isLoading.value = false;
  }
}

const teams = computed(() => ['all', ...new Set(agents.value.map(a => a.team))]);

const filteredCapabilities = computed(() => {
  let caps = allCapabilities.value;
  if (filterCategory.value !== 'all') caps = caps.filter(c => c.category === filterCategory.value);
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase();
    caps = caps.filter(c => c.name.includes(q) || c.description.toLowerCase().includes(q));
  }
  return caps;
});

const filteredAgents = computed(() => {
  if (filterTeam.value === 'all') return agents.value;
  return agents.value.filter(a => a.team === filterTeam.value);
});

function hasCapability(agent: Agent, capName: string): boolean {
  return agent.capabilities.includes(capName);
}

function capabilityCount(capName: string): number {
  return filteredAgents.value.filter(a => a.capabilities.includes(capName)).length;
}

const gapCapabilities = computed(() =>
  filteredCapabilities.value.filter(c => capabilityCount(c.name) === 0)
);

function categoryColor(cat: AgentCapability['category']): string {
  return { tool: 'var(--accent-cyan)', skill: 'var(--accent-violet)', permission: 'var(--accent-amber)' }[cat];
}

onMounted(loadData);
</script>

<template>
  <div class="capability-matrix-page">

    <LoadingState v-if="isLoading" message="Loading capability matrix..." />

    <template v-else>
      <div class="page-header">
        <div class="page-title">
          <div class="title-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/>
              <rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>
            </svg>
          </div>
          <div>
            <h1>Agent Capability Matrix</h1>
            <p>Which agents have which skills, tools, and permissions — gaps highlighted</p>
          </div>
        </div>
        <div class="summary-badges">
          <span class="badge badge-tool">{{ allCapabilities.filter(c => c.category === 'tool').length }} Tools</span>
          <span class="badge badge-skill">{{ allCapabilities.filter(c => c.category === 'skill').length }} Skills</span>
          <span class="badge badge-perm">{{ allCapabilities.filter(c => c.category === 'permission').length }} Permissions</span>
        </div>
      </div>

      <div class="card filters-card">
        <div class="filters-row">
          <input v-model="searchQuery" type="text" class="search-input" placeholder="Search capabilities..." />
          <select v-model="filterCategory" class="filter-select">
            <option value="all">All categories</option>
            <option value="tool">Tools</option>
            <option value="skill">Skills</option>
            <option value="permission">Permissions</option>
          </select>
          <select v-model="filterTeam" class="filter-select">
            <option v-for="t in teams" :key="t" :value="t">{{ t === 'all' ? 'All teams' : t }}</option>
          </select>
        </div>
      </div>

      <div class="card matrix-card">
        <div class="matrix-wrapper">
          <table class="matrix-table">
            <thead>
              <tr>
                <th class="cap-header">Capability</th>
                <th class="cat-header">Type</th>
                <th v-for="agent in filteredAgents" :key="agent.id" class="agent-header">
                  <div class="agent-col">
                    <span class="agent-name">{{ agent.name }}</span>
                    <span class="agent-team">{{ agent.team }}</span>
                    <span class="status-dot" :class="agent.status">{{ agent.status }}</span>
                  </div>
                </th>
                <th class="coverage-header">Coverage</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="cap in filteredCapabilities" :key="cap.name" :class="{ 'gap-row': capabilityCount(cap.name) === 0 }">
                <td class="cap-cell">
                  <span class="cap-name">{{ cap.name }}</span>
                  <span class="cap-desc">{{ cap.description }}</span>
                </td>
                <td class="cat-cell">
                  <span class="cat-badge" :style="{ color: categoryColor(cap.category), borderColor: categoryColor(cap.category) }">
                    {{ cap.category }}
                  </span>
                </td>
                <td v-for="agent in filteredAgents" :key="agent.id" class="check-cell">
                  <svg v-if="hasCapability(agent, cap.name)" class="check-yes" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                    <path d="M20 6L9 17l-5-5"/>
                  </svg>
                  <span v-else class="check-no">—</span>
                </td>
                <td class="coverage-cell">
                  <div class="coverage-bar-wrap">
                    <div class="coverage-bar" :style="{
                      width: filteredAgents.length ? (capabilityCount(cap.name) / filteredAgents.length * 100) + '%' : '0%',
                      background: capabilityCount(cap.name) === 0 ? 'var(--accent-crimson)' : 'var(--accent-emerald)'
                    }"></div>
                  </div>
                  <span class="coverage-label">{{ capabilityCount(cap.name) }}/{{ filteredAgents.length }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-if="gapCapabilities.length > 0" class="card gap-card">
        <div class="gap-header">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          <h3>Capability Gaps ({{ gapCapabilities.length }})</h3>
        </div>
        <p class="gap-subtitle">No agent currently covers these capabilities:</p>
        <div class="gap-list">
          <div v-for="cap in gapCapabilities" :key="cap.name" class="gap-item">
            <span class="cat-badge" :style="{ color: categoryColor(cap.category), borderColor: categoryColor(cap.category) }">{{ cap.category }}</span>
            <span class="gap-name">{{ cap.name }}</span>
            <span class="gap-desc">{{ cap.description }}</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.capability-matrix-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
  width: 100%;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.card { padding: 24px; }

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.page-title {
  display: flex;
  align-items: flex-start;
  gap: 16px;
}

.title-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  background: var(--bg-elevated);
  border: 1px solid var(--border-default);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.title-icon svg { width: 22px; height: 22px; color: var(--accent-violet); }

.page-title h1 { font-size: 1.2rem; font-weight: 600; color: var(--text-primary); margin-bottom: 4px; }
.page-title p { font-size: 0.85rem; color: var(--text-tertiary); }

.summary-badges { display: flex; gap: 8px; flex-wrap: wrap; align-items: flex-start; }

.badge {
  font-size: 0.75rem;
  font-weight: 600;
  padding: 4px 10px;
  border-radius: 20px;
  border: 1px solid;
}

.badge-tool { color: var(--accent-cyan); border-color: var(--accent-cyan); }
.badge-skill { color: var(--accent-violet); border-color: var(--accent-violet); }
.badge-perm { color: var(--accent-amber); border-color: var(--accent-amber); }

.filters-card { padding: 16px 24px; }
.filters-row { display: flex; gap: 12px; flex-wrap: wrap; }

.search-input, .filter-select {
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid var(--border-default);
  background: var(--bg-tertiary);
  color: var(--text-primary);
  font-size: 0.85rem;
  outline: none;
}

.search-input { flex: 1; min-width: 180px; }
.search-input:focus, .filter-select:focus { border-color: var(--accent-cyan); }

.matrix-card { padding: 0; overflow: hidden; }
.matrix-wrapper { overflow-x: auto; }

.matrix-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
}

.matrix-table th, .matrix-table td {
  padding: 10px 14px;
  border-bottom: 1px solid var(--border-default);
  text-align: left;
  white-space: nowrap;
}

.matrix-table thead th {
  background: var(--bg-tertiary);
  font-weight: 600;
  color: var(--text-secondary);
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.cap-header { min-width: 200px; }
.cat-header { width: 90px; }
.agent-header { text-align: center; min-width: 100px; }
.coverage-header { width: 130px; }

.agent-col { display: flex; flex-direction: column; align-items: center; gap: 3px; }
.agent-name { font-size: 0.78rem; font-weight: 600; color: var(--text-primary); }
.agent-team { font-size: 0.7rem; color: var(--text-tertiary); }

.status-dot {
  font-size: 0.65rem;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 10px;
  text-transform: uppercase;
}

.status-dot.active { background: rgba(16,185,129,0.15); color: var(--accent-emerald); }
.status-dot.idle { background: var(--bg-elevated); color: var(--text-tertiary); }
.status-dot.error { background: rgba(239,68,68,0.15); color: var(--accent-crimson); }

.cap-cell { min-width: 200px; }
.cap-name { display: block; font-weight: 500; color: var(--text-primary); }
.cap-desc { display: block; font-size: 0.75rem; color: var(--text-tertiary); white-space: normal; max-width: 240px; }

.cat-badge {
  font-size: 0.7rem;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
  border: 1px solid;
  text-transform: capitalize;
}

.check-cell { text-align: center; }

.check-yes { width: 16px; height: 16px; color: var(--accent-emerald); }
.check-no { font-size: 1rem; color: var(--text-tertiary); opacity: 0.4; }

.gap-row { background: rgba(239,68,68,0.04); }

.coverage-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}

.coverage-bar-wrap {
  flex: 1;
  height: 4px;
  background: var(--bg-elevated);
  border-radius: 2px;
  overflow: hidden;
  min-width: 50px;
}

.coverage-bar { height: 100%; border-radius: 2px; transition: width 0.3s; }
.coverage-label { font-size: 0.75rem; color: var(--text-tertiary); white-space: nowrap; }

.gap-card {
  border-color: var(--accent-crimson);
  background: rgba(239,68,68,0.04);
}

.gap-header { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
.gap-header svg { width: 18px; height: 18px; color: var(--accent-crimson); }
.gap-header h3 { font-size: 0.95rem; font-weight: 600; color: var(--accent-crimson); }
.gap-subtitle { font-size: 0.85rem; color: var(--text-tertiary); margin-bottom: 16px; }

.gap-list { display: flex; flex-direction: column; gap: 8px; }

.gap-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  background: var(--bg-tertiary);
  border-radius: 6px;
  border: 1px solid var(--border-default);
}

.gap-name { font-weight: 500; color: var(--text-primary); font-size: 0.85rem; min-width: 140px; }
.gap-desc { font-size: 0.8rem; color: var(--text-tertiary); }
</style>
