<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';

const router = useRouter();
const showToast = useToast();

const prUrl = ref('');
const isAnalyzing = ref(false);

interface ImpactedService {
  name: string;
  repo: string;
  impact: 'breaking' | 'potential' | 'safe';
  reason: string;
  interfaces: string[];
}

interface AnalysisResult {
  prTitle: string;
  prNumber: number;
  changedInterfaces: string[];
  impactScore: number;
  services: ImpactedService[];
}

const result = ref<AnalysisResult | null>(null);

async function handleAnalyze() {
  if (!prUrl.value.trim()) {
    showToast('Enter a PR URL', 'info');
    return;
  }
  isAnalyzing.value = true;
  result.value = null;
  try {
    await new Promise(resolve => setTimeout(resolve, 2200));
    const prNum = parseInt(prUrl.value.match(/\/(\d+)/)?.[1] ?? '42');
    result.value = {
      prTitle: 'Refactor authentication middleware',
      prNumber: prNum,
      changedInterfaces: ['/api/auth/token', '/api/auth/refresh', 'AuthMiddleware.verify()'],
      impactScore: 72,
      services: [
        { name: 'API Gateway', repo: 'org/gateway', impact: 'breaking', reason: 'Calls /api/auth/token with deprecated parameter format', interfaces: ['/api/auth/token'] },
        { name: 'Mobile Backend', repo: 'org/mobile-api', impact: 'breaking', reason: 'Uses /api/auth/refresh endpoint with removed field', interfaces: ['/api/auth/refresh'] },
        { name: 'Admin Dashboard', repo: 'org/admin', impact: 'potential', reason: 'Imports AuthMiddleware.verify() — signature changed', interfaces: ['AuthMiddleware.verify()'] },
        { name: 'Analytics Service', repo: 'org/analytics', impact: 'safe', reason: 'Only uses /api/auth/token with compliant parameters', interfaces: ['/api/auth/token'] },
        { name: 'Notification Service', repo: 'org/notifications', impact: 'safe', reason: 'No authentication interface dependency detected', interfaces: [] },
      ],
    };
  } catch {
    showToast('Analysis failed', 'error');
  } finally {
    isAnalyzing.value = false;
  }
}

function impactColor(imp: string): string {
  const map: Record<string, string> = { breaking: '#ef4444', potential: '#f59e0b', safe: '#34d399' };
  return map[imp] ?? '#6b7280';
}

function impactIcon(imp: string): string {
  if (imp === 'breaking') return 'M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0zM12 9v4M12 17h.01';
  if (imp === 'potential') return 'M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0zM12 9v4M12 17h.01';
  return 'M20 6L9 17 4 12';
}

function scoreColor(score: number): string {
  if (score >= 70) return '#ef4444';
  if (score >= 40) return '#f59e0b';
  return '#34d399';
}
</script>

<template>
  <div class="dep-impact">
    <AppBreadcrumb :items="[
      { label: 'Tools', action: () => router.push({ name: 'tools' }) },
      { label: 'Dependency Impact' },
    ]" />

    <PageHeader
      title="Dependency Impact Bot"
      subtitle="Analyze which downstream services are affected by interface changes in a PR."
    />

    <div class="card input-card">
      <div class="card-header">
        <h3>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
            <circle cx="12" cy="12" r="3"/><path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83"/>
          </svg>
          Analyze PR
        </h3>
      </div>
      <div class="input-body">
        <div class="input-row">
          <input
            v-model="prUrl"
            type="text"
            class="text-input"
            placeholder="https://github.com/org/repo/pull/42"
            @keydown.enter="handleAnalyze"
          />
          <button class="btn btn-primary" :disabled="isAnalyzing || !prUrl.trim()" @click="handleAnalyze">
            <svg v-if="isAnalyzing" class="spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
              <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
            </svg>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
              <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </svg>
            {{ isAnalyzing ? 'Analyzing...' : 'Analyze Impact' }}
          </button>
        </div>
      </div>
    </div>

    <template v-if="result">
      <div class="summary-row">
        <div class="summary-card card">
          <div class="summary-label">PR</div>
          <div class="summary-val">#{{ result.prNumber }} {{ result.prTitle }}</div>
        </div>
        <div class="summary-card card score-card" :style="{ borderColor: scoreColor(result.impactScore) + '60' }">
          <div class="summary-label">Impact Score</div>
          <div class="score-display" :style="{ color: scoreColor(result.impactScore) }">
            {{ result.impactScore }}
            <span class="score-max">/100</span>
          </div>
          <div class="score-bar">
            <div class="score-fill" :style="{ width: result.impactScore + '%', background: scoreColor(result.impactScore) }"></div>
          </div>
        </div>
        <div class="summary-card card">
          <div class="summary-label">Changed Interfaces</div>
          <div class="interfaces-list">
            <code v-for="i in result.changedInterfaces" :key="i" class="iface-tag">{{ i }}</code>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
              <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>
              <line x1="8" y1="21" x2="16" y2="21"/>
              <line x1="12" y1="17" x2="12" y2="21"/>
            </svg>
            Impacted Services
          </h3>
          <div class="impact-legend">
            <span class="legend-item" style="color: #ef4444">Breaking</span>
            <span class="legend-item" style="color: #f59e0b">Potential</span>
            <span class="legend-item" style="color: #34d399">Safe</span>
          </div>
        </div>
        <div class="services-list">
          <div v-for="svc in result.services" :key="svc.name" class="service-row">
            <div class="service-impact-bar" :style="{ background: impactColor(svc.impact) }"></div>
            <div class="service-icon" :style="{ color: impactColor(svc.impact), background: impactColor(svc.impact) + '15' }">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                <path :d="impactIcon(svc.impact)"/>
              </svg>
            </div>
            <div class="service-info">
              <div class="service-name-row">
                <span class="service-name">{{ svc.name }}</span>
                <a :href="`https://github.com/${svc.repo}`" class="service-repo" target="_blank">{{ svc.repo }}</a>
              </div>
              <div class="service-reason">{{ svc.reason }}</div>
              <div v-if="svc.interfaces.length > 0" class="service-ifaces">
                <code v-for="i in svc.interfaces" :key="i" class="iface-badge">{{ i }}</code>
              </div>
            </div>
            <div class="service-badge" :style="{ color: impactColor(svc.impact), background: impactColor(svc.impact) + '15', borderColor: impactColor(svc.impact) + '40' }">
              {{ svc.impact }}
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.dep-impact {
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

.input-body { padding: 20px 24px; }

.input-row {
  display: flex;
  gap: 12px;
}

.text-input {
  flex: 1;
  padding: 9px 14px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.875rem;
}

.text-input:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.summary-row {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 16px;
}

.summary-card {
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.summary-label {
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.summary-val {
  font-size: 0.9rem;
  font-weight: 500;
  color: var(--text-primary);
}

.score-display {
  font-size: 2.5rem;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  line-height: 1;
}

.score-max {
  font-size: 1rem;
  font-weight: 400;
  color: var(--text-tertiary);
}

.score-bar {
  height: 6px;
  background: var(--bg-tertiary);
  border-radius: 3px;
  overflow: hidden;
}

.score-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.5s ease;
}

.interfaces-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.iface-tag {
  font-family: 'Geist Mono', monospace;
  font-size: 0.72rem;
  padding: 3px 8px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 4px;
  color: var(--text-secondary);
}

.impact-legend {
  display: flex;
  gap: 14px;
}

.legend-item {
  font-size: 0.78rem;
  font-weight: 600;
}

.services-list {
  display: flex;
  flex-direction: column;
}

.service-row {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 16px 24px;
  border-bottom: 1px solid var(--border-subtle);
  position: relative;
}

.service-row:last-child { border-bottom: none; }

.service-impact-bar {
  width: 3px;
  height: 100%;
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
}

.service-icon {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-left: 12px;
}

.service-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.service-name-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.service-name {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-primary);
}

.service-repo {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  font-family: monospace;
  text-decoration: none;
}

.service-repo:hover { color: var(--accent-cyan); }

.service-reason {
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.service-ifaces {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.iface-badge {
  font-family: 'Geist Mono', monospace;
  font-size: 0.7rem;
  padding: 2px 6px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 3px;
  color: var(--text-tertiary);
}

.service-badge {
  font-size: 0.72rem;
  font-weight: 700;
  padding: 3px 10px;
  border-radius: 4px;
  border: 1px solid;
  text-transform: capitalize;
  white-space: nowrap;
  align-self: flex-start;
}

.btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 16px;
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}

.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }

.spinner { animation: spin 1s linear infinite; }

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@media (max-width: 900px) {
  .summary-row { grid-template-columns: 1fr; }
}
</style>
