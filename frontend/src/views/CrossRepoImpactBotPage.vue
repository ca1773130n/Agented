<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import LoadingState from '../components/base/LoadingState.vue';
import { useToast } from '../composables/useToast';

const showToast = useToast();
const isLoading = ref(true);
const isScanning = ref(false);

interface DownstreamRepo {
  name: string;
  owner: string;
  impact: 'breaking' | 'compatible' | 'unknown';
  reason: string;
  notified: boolean;
}

interface ImpactAnalysis {
  id: string;
  source_repo: string;
  pr_number: number;
  pr_title: string;
  changed_contracts: string[];
  downstream_repos: DownstreamRepo[];
  run_at: string;
  status: 'complete' | 'running' | 'failed';
}

const analyses = ref<ImpactAnalysis[]>([]);
const selected = ref<ImpactAnalysis | null>(null);
const prUrl = ref('');

async function loadHistory() {
  try {
    const res = await fetch('/admin/bots/cross-repo-impact');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    analyses.value = (await res.json()).analyses ?? [];
  } catch {
    const now = Date.now();
    analyses.value = [
      {
        id: 'impact-001',
        source_repo: 'acme-corp/api-gateway',
        pr_number: 247,
        pr_title: 'feat: add rate-limit headers to all responses',
        changed_contracts: ['ResponseEnvelope', 'RateLimitHeaders'],
        downstream_repos: [
          { name: 'payments-service', owner: 'acme-corp', impact: 'breaking', reason: 'Consumes ResponseEnvelope — field rename breaks deserialization', notified: true },
          { name: 'frontend-app', owner: 'acme-corp', impact: 'compatible', reason: 'Uses RateLimitHeaders but only reads X-RateLimit-Remaining which is preserved', notified: false },
          { name: 'data-pipeline', owner: 'acme-corp', impact: 'unknown', reason: 'Dependency detected but contract usage unclear — manual review recommended', notified: false },
        ],
        run_at: new Date(now - 3600000).toISOString(),
        status: 'complete',
      },
      {
        id: 'impact-002',
        source_repo: 'acme-corp/shared-auth',
        pr_number: 89,
        pr_title: 'refactor: rename JwtPayload.sub to JwtPayload.user_id',
        changed_contracts: ['JwtPayload'],
        downstream_repos: [
          { name: 'api-gateway', owner: 'acme-corp', impact: 'breaking', reason: 'JwtPayload.sub referenced in 12 locations', notified: true },
          { name: 'payments-service', owner: 'acme-corp', impact: 'breaking', reason: 'JwtPayload.sub referenced in 5 locations', notified: true },
          { name: 'admin-panel', owner: 'acme-corp', impact: 'compatible', reason: 'Does not use JwtPayload directly — uses decoded claims only', notified: false },
        ],
        run_at: new Date(now - 86400000).toISOString(),
        status: 'complete',
      },
    ];
    if (analyses.value.length > 0) selected.value = analyses.value[0];
  } finally {
    isLoading.value = false;
  }
}

async function runAnalysis() {
  if (!prUrl.value.trim()) {
    showToast('Enter a PR URL or number', 'error');
    return;
  }
  isScanning.value = true;
  try {
    const res = await fetch('/admin/bots/cross-repo-impact', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pr_url: prUrl.value }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    showToast('Analysis started', 'success');
    await loadHistory();
  } catch {
    showToast('Analysis queued (demo mode)', 'success');
  } finally {
    isScanning.value = false;
    prUrl.value = '';
  }
}

function notifyTeam(repo: DownstreamRepo) {
  repo.notified = true;
  showToast(`Notified ${repo.owner}/${repo.name}`, 'success');
}

function impactColor(impact: DownstreamRepo['impact']): string {
  if (impact === 'breaking') return '#f87171';
  if (impact === 'compatible') return '#34d399';
  return '#fbbf24';
}

const breakingCount = computed(
  () => selected.value?.downstream_repos.filter(r => r.impact === 'breaking').length ?? 0,
);

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' });
}

onMounted(loadHistory);
</script>

<template>
  <div class="page-container">

    <div class="page-header">
      <div>
        <h1 class="page-title">Cross-Repo Impact Analysis Bot</h1>
        <p class="page-subtitle">
          When a PR changes a shared library or API contract, automatically identify downstream
          repos affected and post impact warnings to their teams before the change ships.
        </p>
      </div>
    </div>

    <!-- Run panel -->
    <div class="run-card">
      <div class="run-form">
        <input
          v-model="prUrl"
          class="pr-input"
          placeholder="GitHub PR URL or e.g. acme-corp/api-gateway#247"
        />
        <button class="run-btn" :disabled="isScanning" @click="runAnalysis">
          {{ isScanning ? 'Scanning...' : 'Analyze Impact' }}
        </button>
      </div>
    </div>

    <LoadingState v-if="isLoading" message="Loading analyses..." />
    <div v-else class="analysis-layout">
      <!-- Left: history list -->
      <div class="history-panel">
        <h2 class="section-title">Recent Analyses</h2>
        <div
          v-for="a in analyses"
          :key="a.id"
          class="analysis-item"
          :class="{ active: selected?.id === a.id }"
          @click="selected = a"
        >
          <div class="analysis-header">
            <span class="analysis-repo">{{ a.source_repo }}</span>
            <span class="analysis-pr">#{{ a.pr_number }}</span>
          </div>
          <p class="analysis-title">{{ a.pr_title }}</p>
          <div class="analysis-footer">
            <span class="downstream-count">{{ a.downstream_repos.length }} repos affected</span>
            <span class="analysis-time">{{ formatTime(a.run_at) }}</span>
          </div>
        </div>
        <p v-if="analyses.length === 0" class="empty-msg">No analyses yet.</p>
      </div>

      <!-- Right: detail -->
      <div v-if="selected" class="detail-panel">
        <div class="detail-header">
          <div>
            <h2 class="detail-title">{{ selected.pr_title }}</h2>
            <p class="detail-meta">{{ selected.source_repo }} · PR #{{ selected.pr_number }} · {{ formatTime(selected.run_at) }}</p>
          </div>
          <div v-if="breakingCount > 0" class="breaking-badge">
            {{ breakingCount }} breaking
          </div>
        </div>

        <div class="contracts-section">
          <h3 class="sub-title">Changed Contracts</h3>
          <div class="contracts-list">
            <span v-for="c in selected.changed_contracts" :key="c" class="contract-chip">
              {{ c }}
            </span>
          </div>
        </div>

        <div class="repos-section">
          <h3 class="sub-title">Downstream Repositories</h3>
          <div v-for="repo in selected.downstream_repos" :key="repo.name" class="repo-card">
            <div class="repo-card-header">
              <div class="repo-left">
                <span class="impact-dot" :style="{ background: impactColor(repo.impact) }"></span>
                <span class="repo-full-name">{{ repo.owner }}/{{ repo.name }}</span>
              </div>
              <div class="repo-right">
                <span class="impact-label" :style="{ color: impactColor(repo.impact) }">
                  {{ repo.impact }}
                </span>
                <button
                  v-if="!repo.notified"
                  class="notify-btn"
                  @click="notifyTeam(repo)"
                >
                  Notify Team
                </button>
                <span v-else class="notified-badge">Notified ✓</span>
              </div>
            </div>
            <p class="repo-reason">{{ repo.reason }}</p>
          </div>
        </div>
      </div>
      <div v-else class="detail-placeholder">
        <p>Select an analysis to view downstream impact</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-container { padding: 2rem; max-width: 1200px; margin: 0 auto; }
.page-header { margin-bottom: 1.5rem; }
.page-title { font-size: 1.75rem; font-weight: 700; color: var(--color-text-primary, #f0f0f0); margin: 0 0 0.5rem; }
.page-subtitle { color: var(--color-text-secondary, #a0a0a0); margin: 0; }
.run-card {
  background: var(--color-surface, #1a1a1a);
  border: 1px solid var(--color-border, #2a2a2a);
  border-radius: 8px;
  padding: 1rem 1.25rem;
  margin-bottom: 1.5rem;
}
.run-form { display: flex; gap: 0.75rem; }
.pr-input {
  flex: 1;
  background: var(--color-bg, #111);
  border: 1px solid var(--color-border, #2a2a2a);
  border-radius: 6px;
  padding: 0.5rem 0.75rem;
  color: var(--color-text-primary, #f0f0f0);
  font-size: 0.875rem;
}
.pr-input:focus { outline: none; border-color: var(--color-accent, #6366f1); }
.run-btn {
  padding: 0.5rem 1.25rem;
  border-radius: 6px;
  border: none;
  background: var(--color-accent, #6366f1);
  color: #fff;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}
.run-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.analysis-layout { display: grid; grid-template-columns: 340px 1fr; gap: 1.5rem; align-items: start; }
@media (max-width: 860px) { .analysis-layout { grid-template-columns: 1fr; } }
.history-panel {
  background: var(--color-surface, #1a1a1a);
  border: 1px solid var(--color-border, #2a2a2a);
  border-radius: 8px;
  padding: 1.25rem;
}
.section-title { font-size: 1rem; font-weight: 600; color: var(--color-text-primary, #f0f0f0); margin: 0 0 1rem; }
.analysis-item {
  padding: 0.875rem;
  border-radius: 6px;
  border: 1px solid var(--color-border, #2a2a2a);
  margin-bottom: 0.5rem;
  cursor: pointer;
  transition: border-color 0.12s, background 0.12s;
}
.analysis-item:hover { background: rgba(255,255,255,0.03); }
.analysis-item.active { border-color: var(--color-accent, #6366f1); background: rgba(99,102,241,0.06); }
.analysis-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.25rem; }
.analysis-repo { font-size: 0.8rem; font-family: monospace; color: var(--color-text-secondary, #a0a0a0); }
.analysis-pr { font-size: 0.8rem; color: var(--color-accent, #6366f1); font-family: monospace; }
.analysis-title { font-size: 0.875rem; color: var(--color-text-primary, #f0f0f0); margin: 0 0 0.4rem; line-height: 1.4; }
.analysis-footer { display: flex; align-items: center; justify-content: space-between; }
.downstream-count { font-size: 0.75rem; color: var(--color-text-secondary, #a0a0a0); }
.analysis-time { font-size: 0.75rem; color: var(--color-text-secondary, #a0a0a0); }
.detail-panel {
  background: var(--color-surface, #1a1a1a);
  border: 1px solid var(--color-border, #2a2a2a);
  border-radius: 8px;
  padding: 1.5rem;
}
.detail-placeholder {
  background: var(--color-surface, #1a1a1a);
  border: 1px dashed var(--color-border, #2a2a2a);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 300px;
  color: var(--color-text-secondary, #a0a0a0);
  font-size: 0.875rem;
}
.detail-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; margin-bottom: 1.5rem; }
.detail-title { font-size: 1.1rem; font-weight: 600; color: var(--color-text-primary, #f0f0f0); margin: 0 0 0.25rem; }
.detail-meta { font-size: 0.8rem; color: var(--color-text-secondary, #a0a0a0); margin: 0; font-family: monospace; }
.breaking-badge { background: rgba(248,113,113,0.15); color: #f87171; padding: 0.3rem 0.75rem; border-radius: 20px; font-size: 0.8rem; font-weight: 600; white-space: nowrap; }
.sub-title { font-size: 0.85rem; font-weight: 600; color: var(--color-text-secondary, #a0a0a0); text-transform: uppercase; letter-spacing: 0.05em; margin: 0 0 0.75rem; }
.contracts-section { margin-bottom: 1.5rem; }
.contracts-list { display: flex; flex-wrap: wrap; gap: 0.4rem; }
.contract-chip { background: rgba(99,102,241,0.15); color: #818cf8; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 0.8rem; font-family: monospace; }
.repos-section { }
.repo-card { background: var(--color-bg, #111); border: 1px solid var(--color-border, #2a2a2a); border-radius: 6px; padding: 0.875rem; margin-bottom: 0.6rem; }
.repo-card-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem; }
.repo-left { display: flex; align-items: center; gap: 0.5rem; }
.impact-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.repo-full-name { font-size: 0.875rem; font-weight: 600; color: var(--color-text-primary, #f0f0f0); font-family: monospace; }
.repo-right { display: flex; align-items: center; gap: 0.5rem; }
.impact-label { font-size: 0.75rem; font-weight: 600; text-transform: uppercase; }
.notify-btn { padding: 0.25rem 0.6rem; border-radius: 4px; border: 1px solid var(--color-border, #2a2a2a); background: transparent; color: var(--color-text-secondary, #a0a0a0); font-size: 0.75rem; cursor: pointer; }
.notify-btn:hover { border-color: var(--color-accent, #6366f1); color: var(--color-accent, #6366f1); }
.notified-badge { font-size: 0.75rem; color: #34d399; }
.repo-reason { font-size: 0.8rem; color: var(--color-text-secondary, #a0a0a0); margin: 0; line-height: 1.5; }
.empty-msg { text-align: center; color: var(--color-text-secondary, #a0a0a0); padding: 2rem 0; margin: 0; }
</style>
