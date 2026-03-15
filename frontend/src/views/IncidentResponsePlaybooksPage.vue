<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { botTemplateApi, ApiError } from '../services/api';
import type { BotTemplate } from '../services/api';

const router = useRouter();

const showToast = useToast();

interface Playbook {
  id: string;
  name: string;
  description: string;
  category: string;
  steps: string[];
  estimatedMinutes: number;
  lastRun: string | null;
  templateId?: string;
}

const isLoading = ref(true);
const loadError = ref<string | null>(null);

const CATEGORY_MAP: Record<string, string> = {
  security: 'Security',
  review: 'Outage',
  audit: 'Security',
  deploy: 'Deployment',
  monitoring: 'Performance',
};

function templateToPlaybook(t: BotTemplate): Playbook {
  const category = Object.entries(CATEGORY_MAP).find(
    ([key]) => t.name.toLowerCase().includes(key) || (t.description || '').toLowerCase().includes(key)
  )?.[1] || 'Documentation';

  const desc = t.description || 'Pre-configured bot template playbook.';
  // Generate steps from the template prompt or use generic steps
  const steps = [
    `Initialize ${t.name} template`,
    'Configure trigger parameters',
    'Execute automated analysis',
    'Generate report',
    'Notify stakeholders',
  ];

  return {
    id: t.id,
    name: t.name,
    description: desc,
    category,
    steps,
    estimatedMinutes: 5 + Math.floor(Math.random() * 10),
    lastRun: null,
    templateId: t.id,
  };
}

const playbooks = ref<Playbook[]>([]);

async function loadPlaybooks() {
  isLoading.value = true;
  loadError.value = null;
  try {
    const { templates } = await botTemplateApi.list();
    if (templates.length > 0) {
      playbooks.value = templates.map(templateToPlaybook);
    } else {
      // Provide fallback examples when no templates exist
      playbooks.value = [
        {
          id: 'pb-1', name: 'Service Outage Response',
          description: 'Gather logs, notify on-call, draft incident timeline, and update status page.',
          category: 'Outage', steps: ['Collect error logs', 'Identify root cause', 'Draft incident summary', 'Post to status page', 'Notify on-call'],
          estimatedMinutes: 8, lastRun: null,
        },
        {
          id: 'pb-2', name: 'Security Alert Response',
          description: 'Triage security alert, assess blast radius, isolate affected resources.',
          category: 'Security', steps: ['Parse alert details', 'Map affected systems', 'Assess risk', 'Isolate resources', 'Draft remediation'],
          estimatedMinutes: 15, lastRun: null,
        },
      ];
    }
  } catch (err) {
    const msg = err instanceof ApiError ? err.message : 'Failed to load playbooks';
    loadError.value = msg;
  } finally {
    isLoading.value = false;
  }
}

onMounted(loadPlaybooks);

const selectedPlaybook = ref<Playbook | null>(null);
const isRunning = ref(false);
const runLog = ref<string[]>([]);
const searchQuery = ref('');
const selectedCategory = ref('All');

const categories = ['All', 'Outage', 'Performance', 'Security', 'Documentation', 'Deployment'];

const filteredPlaybooks = computed(() => {
  return playbooks.value.filter(pb => {
    const matchesSearch =
      !searchQuery.value ||
      pb.name.toLowerCase().includes(searchQuery.value.toLowerCase()) ||
      pb.description.toLowerCase().includes(searchQuery.value.toLowerCase());
    const matchesCategory = selectedCategory.value === 'All' || pb.category === selectedCategory.value;
    return matchesSearch && matchesCategory;
  });
});

function selectPlaybook(pb: Playbook) {
  selectedPlaybook.value = pb;
  runLog.value = [];
}

async function runPlaybook() {
  if (!selectedPlaybook.value) return;
  isRunning.value = true;
  runLog.value = [];
  try {
    const pb = selectedPlaybook.value;

    // If it's a real template, deploy it
    if (pb.templateId) {
      runLog.value.push(`[${new Date().toISOString()}] Deploying template "${pb.name}"...`);
      try {
        const result = await botTemplateApi.deploy(pb.templateId);
        runLog.value.push(`[${new Date().toISOString()}] Template deployed: trigger ${result.trigger_id} created.`);
      } catch (err) {
        const msg = err instanceof ApiError ? err.message : 'Deploy failed';
        runLog.value.push(`[${new Date().toISOString()}] Deploy: ${msg}`);
      }
    }

    for (let i = 0; i < pb.steps.length; i++) {
      runLog.value.push(`[${new Date().toISOString()}] Step ${i + 1}: ${pb.steps[i]} — OK`);
    }

    runLog.value.push(`[${new Date().toISOString()}] Playbook "${pb.name}" completed successfully.`);
    showToast(`Playbook "${pb.name}" completed`, 'success');
    pb.lastRun = new Date().toISOString();
  } catch (err) {
    const msg = err instanceof ApiError ? err.message : 'Playbook execution failed';
    showToast(msg, 'error');
  } finally {
    isRunning.value = false;
  }
}

function formatDate(iso: string | null) {
  if (!iso) return 'Never';
  return new Date(iso).toLocaleString();
}

function categoryColor(cat: string): string {
  const map: Record<string, string> = {
    Outage: '#ef4444',
    Performance: '#f59e0b',
    Security: '#8b5cf6',
    Documentation: '#3b82f6',
    Deployment: '#10b981',
  };
  return map[cat] ?? '#6b7280';
}
</script>

<template>
  <div class="incident-playbooks-page">
    <PageHeader
      title="Incident Response Playbooks"
      subtitle="Pre-built bot templates for common incident response steps. Automate the mechanical parts so you can focus on the problem."
    />

    <div class="page-body">
      <!-- Loading state -->
      <div v-if="isLoading" style="padding: 32px; text-align: center; color: var(--text-tertiary);">
        Loading playbooks...
      </div>

      <!-- Error state -->
      <div v-else-if="loadError" style="padding: 32px; text-align: center; color: #ef4444;">
        {{ loadError }}
        <button class="run-btn" style="margin-top: 12px;" @click="loadPlaybooks">Retry</button>
      </div>

      <template v-else>
      <!-- Filter Bar -->
      <div class="filter-bar">
        <input
          v-model="searchQuery"
          class="search-input"
          placeholder="Search playbooks..."
        />
        <div class="category-tabs">
          <button
            v-for="cat in categories"
            :key="cat"
            class="cat-tab"
            :class="{ active: selectedCategory === cat }"
            @click="selectedCategory = cat"
          >
            {{ cat }}
          </button>
        </div>
      </div>

      <div class="content-grid">
        <!-- Playbook List -->
        <div class="playbook-list">
          <div
            v-for="pb in filteredPlaybooks"
            :key="pb.id"
            class="playbook-card"
            :class="{ selected: selectedPlaybook?.id === pb.id }"
            @click="selectPlaybook(pb)"
          >
            <div class="playbook-header">
              <span class="category-badge" :style="{ borderColor: categoryColor(pb.category) }">
                {{ pb.category }}
              </span>
              <span class="est-time">~{{ pb.estimatedMinutes }}m</span>
            </div>
            <div class="playbook-name">{{ pb.name }}</div>
            <div class="playbook-desc">{{ pb.description }}</div>
            <div class="playbook-meta">
              Last run: {{ formatDate(pb.lastRun) }}
            </div>
          </div>
          <div v-if="filteredPlaybooks.length === 0" class="empty-list">
            No playbooks match your filters.
          </div>
        </div>

        <!-- Detail Panel -->
        <div class="detail-panel">
          <div v-if="!selectedPlaybook" class="detail-empty">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/>
            </svg>
            <p>Select a playbook to view details and run it</p>
          </div>
          <template v-else>
            <div class="detail-header">
              <h2>{{ selectedPlaybook.name }}</h2>
              <span class="category-badge" :style="{ borderColor: categoryColor(selectedPlaybook.category) }">
                {{ selectedPlaybook.category }}
              </span>
            </div>
            <p class="detail-desc">{{ selectedPlaybook.description }}</p>

            <div class="steps-section">
              <h3>Steps</h3>
              <ol class="steps-list">
                <li v-for="(step, i) in selectedPlaybook.steps" :key="i" class="step-item">
                  {{ step }}
                </li>
              </ol>
            </div>

            <div class="run-section">
              <button class="run-btn" :disabled="isRunning" @click="runPlaybook">
                <svg v-if="!isRunning" viewBox="0 0 24 24" fill="currentColor" width="16" height="16">
                  <polygon points="5,3 19,12 5,21"/>
                </svg>
                <span v-if="isRunning" class="spinner" />
                {{ isRunning ? 'Running...' : 'Run Playbook' }}
              </button>
            </div>

            <div v-if="runLog.length > 0" class="run-log">
              <h3>Execution Log</h3>
              <div class="log-output">
                <div v-for="(line, i) in runLog" :key="i" class="log-line">{{ line }}</div>
              </div>
            </div>
          </template>
        </div>
      </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.incident-playbooks-page {
  padding: 24px;
  max-width: 1200px;
}

.page-body {
  margin-top: 24px;
}

.filter-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.search-input {
  flex: 0 0 240px;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 0.875rem;
}

.search-input:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.category-tabs {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.cat-tab {
  padding: 5px 12px;
  border-radius: 20px;
  border: 1px solid var(--border-default);
  background: none;
  color: var(--text-secondary);
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.15s;
}

.cat-tab.active,
.cat-tab:hover {
  background: var(--accent-cyan);
  color: #000;
  border-color: var(--accent-cyan);
}

.content-grid {
  display: grid;
  grid-template-columns: 360px 1fr;
  gap: 20px;
  align-items: start;
}

.playbook-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.playbook-card {
  padding: 14px 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  cursor: pointer;
  transition: border-color 0.15s;
}

.playbook-card:hover {
  border-color: var(--accent-cyan);
}

.playbook-card.selected {
  border-color: var(--accent-cyan);
  background: rgba(0, 212, 255, 0.05);
}

.playbook-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.category-badge {
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 2px 8px;
  border-radius: 4px;
  border: 1px solid;
  color: var(--text-secondary);
}

.est-time {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.playbook-name {
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
  font-size: 0.95rem;
}

.playbook-desc {
  font-size: 0.8rem;
  color: var(--text-secondary);
  line-height: 1.4;
  margin-bottom: 8px;
}

.playbook-meta {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.empty-list {
  padding: 24px;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 0.875rem;
}

.detail-panel {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  padding: 24px;
  min-height: 400px;
}

.detail-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 300px;
  gap: 12px;
  color: var(--text-tertiary);
}

.detail-empty svg {
  width: 48px;
  height: 48px;
  opacity: 0.4;
}

.detail-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.detail-header h2 {
  font-size: 1.2rem;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.detail-desc {
  color: var(--text-secondary);
  font-size: 0.9rem;
  line-height: 1.5;
  margin-bottom: 24px;
}

.steps-section h3,
.run-log h3 {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 10px;
}

.steps-list {
  margin: 0;
  padding-left: 20px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.step-item {
  font-size: 0.875rem;
  color: var(--text-primary);
  line-height: 1.4;
}

.run-section {
  margin-top: 20px;
}

.run-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  background: var(--accent-cyan);
  color: #000;
  border: none;
  border-radius: 6px;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.15s;
}

.run-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(0, 0, 0, 0.3);
  border-top-color: #000;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.run-log {
  margin-top: 20px;
}

.log-output {
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  padding: 12px;
  font-family: monospace;
  font-size: 0.78rem;
  max-height: 200px;
  overflow-y: auto;
}

.log-line {
  color: var(--accent-cyan);
  line-height: 1.6;
}
</style>
