<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import type { AuditRecord, AuditStats, ProjectInfo, Trigger } from '../services/api';
import { auditApi, triggerApi, ApiError } from '../services/api';
import FindingsChart from '../components/security/FindingsChart.vue';
import RunScanModal from '../components/security/RunScanModal.vue';
import ResolveIssuesModal from '../components/security/ResolveIssuesModal.vue';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import DataTable from '../components/base/DataTable.vue';
import type { DataTableColumn } from '../components/base/DataTable.vue';
import StatusBadge from '../components/base/StatusBadge.vue';
import EmptyState from '../components/base/EmptyState.vue';
import LoadingState from '../components/base/LoadingState.vue';
import StatCard from '../components/base/StatCard.vue';
import { useToast } from '../composables/useToast';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const router = useRouter();
const showToast = useToast();

const stats = ref<AuditStats | null>(null);
const projects = ref<ProjectInfo[]>([]);
const auditHistory = ref<AuditRecord[]>([]);
const triggers = ref<Trigger[]>([]);
const isLoading = ref(true);
const showRunScanModal = ref(false);
const showResolveModal = ref(false);

const hasFindings = ref(false);
const securityTrigger = ref<Trigger | null>(null);
const securityTriggerStatus = ref<{ pr_urls?: string[]; status?: string }>({});

useWebMcpTool({
  name: 'hive_security_dashboard_get_state',
  description: 'Returns the current state of the SecurityDashboard',
  page: 'SecurityDashboard',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'SecurityDashboard',
        isLoading: isLoading.value,
        totalFindings: stats.value?.current?.total_findings ?? 0,
        projectCount: projects.value.length,
        auditHistoryCount: auditHistory.value.length,
        hasFindings: hasFindings.value,
        showRunScanModal: showRunScanModal.value,
        showResolveModal: showResolveModal.value,
        autoResolve: securityTrigger.value?.auto_resolve === 1,
      }),
    }],
  }),
  deps: [isLoading, stats, projects, auditHistory, hasFindings, showRunScanModal, showResolveModal, securityTrigger],
});

async function loadData() {
  isLoading.value = true;
  try {
    const [statsRes, projectsRes, historyRes, triggersRes] = await Promise.all([
      auditApi.getStats(),
      auditApi.getProjects(),
      auditApi.getHistory(),
      triggerApi.list(),
    ]);
    stats.value = statsRes;
    projects.value = projectsRes.projects || [];
    auditHistory.value = historyRes.audits || [];
    triggers.value = triggersRes.triggers || [];
    hasFindings.value = (statsRes.current?.total_findings || 0) > 0;

    // Find the security trigger for auto-resolve feature
    const secTrigger = triggersRes.triggers.find((t: Trigger) => t.id === 'bot-security');
    securityTrigger.value = secTrigger || null;
    if (secTrigger?.execution_status) {
      securityTriggerStatus.value = secTrigger.execution_status;
    }
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to load dashboard data';
    showToast(message, 'error');
  } finally {
    isLoading.value = false;
  }
}

async function toggleAutoResolve() {
  if (!securityTrigger.value) return;
  const newValue = securityTrigger.value.auto_resolve !== 1;
  try {
    await triggerApi.setAutoResolve('bot-security', newValue);
    securityTrigger.value.auto_resolve = newValue ? 1 : 0;
    showToast(newValue ? 'Auto-resolve enabled' : 'Auto-resolve disabled', 'success');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to update auto-resolve';
    showToast(message, 'error');
  }
}

function formatDate(dateStr: string): string {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleDateString('en-US', {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

function getProjectStatusClass(status: string): string {
  if (status === 'pass') return 'pass';
  if (status === 'fail') return 'fail';
  return 'pending';
}

function getProjectIcon(status: string): string {
  if (status === 'pass') return '✓';
  if (status === 'fail') return '!';
  return '?';
}

function getStatusBadgeClass(): string {
  if (!stats.value) return '';
  if (stats.value.current.status === 'pass') return 'pass';
  if (stats.value.current.total_findings > 0) return 'fail';
  return '';
}

function getStatusBadgeText(): string {
  if (!stats.value) return '-';
  if (stats.value.current.status === 'pass') return 'All Clear';
  if (stats.value.current.total_findings > 0) return `${stats.value.current.total_findings} Issues`;
  return 'No Data';
}

function onScanComplete() {
  showRunScanModal.value = false;
  setTimeout(loadData, 5000);
}

function onResolveComplete() {
  showResolveModal.value = false;
}

const auditTableColumns: DataTableColumn[] = [
  { key: 'project', label: 'Project' },
  { key: 'audit_date', label: 'Date' },
  { key: 'total_findings', label: 'Findings' },
  { key: 'critical', label: 'Critical' },
  { key: 'high', label: 'High' },
  { key: 'medium', label: 'Medium' },
  { key: 'low', label: 'Low' },
  { key: 'status', label: 'Status' },
];

function getAuditStatusVariant(status: string): 'success' | 'danger' | 'neutral' {
  if (status === 'pass') return 'success';
  if (status === 'fail') return 'danger';
  return 'neutral';
}

function getSeverityVariant(severity: string): 'danger' | 'warning' | 'info' | 'success' {
  if (severity === 'critical') return 'danger';
  if (severity === 'high') return 'warning';
  if (severity === 'medium') return 'info';
  return 'success';
}

const latestAuditByProject = computed(() => {
  const map: Record<string, AuditRecord> = {};
  for (const audit of auditHistory.value) {
    const existing = map[audit.project_path];
    if (!existing || new Date(audit.audit_date) > new Date(existing.audit_date)) {
      map[audit.project_path] = audit;
    }
  }
  return map;
});

onMounted(loadData);
</script>

<template>
  <div class="security-dashboard">
    <AppBreadcrumb :items="[{ label: 'Dashboards', action: () => router.push({ name: 'dashboards' }) }, { label: 'Security Scan' }]" />

    <LoadingState v-if="isLoading" message="Loading security data..." />

    <template v-else>
      <!-- Current Security Status Card -->
      <div class="card status-card">
        <div class="status-card-inner">
          <div class="status-header">
            <div class="status-title-area">
              <div class="status-icon" :class="getStatusBadgeClass()">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                </svg>
              </div>
              <div>
                <h3>Security Status</h3>
                <p class="status-subtitle">Based on the latest scan for each tracked project</p>
              </div>
            </div>
            <div class="status-actions">
              <span class="status-badge" :class="getStatusBadgeClass()">{{ getStatusBadgeText() }}</span>
              <label v-if="securityTrigger" class="auto-resolve-toggle" title="Automatically resolve issues and create a PR for GitHub repos">
                <input
                  type="checkbox"
                  :checked="securityTrigger.auto_resolve === 1"
                  @change="toggleAutoResolve"
                />
                <span class="toggle-label">Auto-resolve &amp; PR</span>
              </label>
              <button class="btn btn-warning" @click="showRunScanModal = true">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M21 12a9 9 0 11-9-9c2.52 0 4.93 1 6.74 2.74"/>
                  <path d="M21 3v6h-6"/>
                </svg>
                Run Scan
              </button>
              <button class="btn btn-primary" :disabled="!hasFindings" @click="showResolveModal = true">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M12 20h9M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/>
                </svg>
                Resolve Issues
              </button>
            </div>
          </div>

          <div class="stats-grid">
            <StatCard title="Open Findings" :value="stats?.current?.total_findings ?? '-'" />
            <StatCard title="Critical" :value="stats?.current?.severity_totals?.critical ?? '-'" color="var(--accent-crimson)" />
            <StatCard title="High" :value="stats?.current?.severity_totals?.high ?? '-'" color="var(--accent-amber)" />
            <StatCard title="Medium + Low" :value="((stats?.current?.severity_totals?.medium ?? 0) + (stats?.current?.severity_totals?.low ?? 0)) || '-'" />
          </div>

          <!-- Resolving status indicator -->
          <div v-if="securityTriggerStatus.status === 'resolving'" class="resolving-banner">
            <div class="resolving-spinner"></div>
            <span>Auto-resolving issues and creating pull requests...</span>
          </div>

          <!-- PR URLs from auto-resolve -->
          <div v-if="securityTriggerStatus.pr_urls && securityTriggerStatus.pr_urls.length > 0" class="pr-urls-section">
            <h4 class="pr-urls-title">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M15 22v-4a4.8 4.8 0 00-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 004 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4"/>
                <path d="M9 18c-4.51 2-5-2-7-2"/>
              </svg>
              Pull Requests Created
            </h4>
            <div class="pr-urls-list">
              <a
                v-for="(prUrl, idx) in securityTriggerStatus.pr_urls"
                :key="idx"
                :href="prUrl"
                target="_blank"
                rel="noopener noreferrer"
                class="pr-url-link"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/>
                  <path d="M15 3h6v6"/>
                  <path d="M10 14L21 3"/>
                </svg>
                {{ prUrl }}
              </a>
            </div>
          </div>
        </div>
      </div>

      <!-- Historical Statistics -->
      <div class="card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <circle cx="12" cy="12" r="10"/>
              <path d="M12 6v6l4 2"/>
            </svg>
            Historical Statistics
          </h3>
          <span class="card-badge">Cumulative</span>
        </div>
        <div class="stats-grid compact">
          <StatCard title="Total Scans" :value="stats?.historical?.total_audits ?? '-'" />
          <StatCard title="Projects Tracked" :value="(stats?.projects || []).length || '-'" />
          <StatCard title="Total Findings" :value="stats?.historical?.total_findings ?? '-'" color="var(--accent-amber)" />
          <StatCard title="High+ Severity" :value="((stats?.historical?.severity_totals?.critical ?? 0) + (stats?.historical?.severity_totals?.high ?? 0)) || '-'" color="var(--accent-crimson)" />
        </div>
      </div>

      <!-- Findings Over Time Chart -->
      <div class="card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M3 3v18h18"/>
              <path d="M18 17l-5-5-4 4-4-4"/>
            </svg>
            Findings Over Time
          </h3>
        </div>
        <FindingsChart :audits="auditHistory" />
      </div>

      <!-- Tracked Projects -->
      <div class="card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>
            </svg>
            Tracked Projects
          </h3>
          <span class="card-badge">{{ projects.length }} total</span>
        </div>

        <div v-if="projects.length === 0" class="empty-state">
          <div class="empty-icon">◇</div>
          <p>No projects tracked yet</p>
          <span>Add project paths to a bot to start tracking</span>
        </div>

        <div v-else class="projects-grid">
          <div
            v-for="(project, index) in projects"
            :key="project.project_path"
            class="project-card"
            :style="{ '--delay': `${index * 30}ms` }"
            @click="router.push({ name: 'security-history', query: { project: project.project_path } })"
          >
            <div class="project-status-icon" :class="getProjectStatusClass(project.last_status)">
              {{ getProjectIcon(project.last_status) }}
            </div>
            <div class="project-info">
              <div class="project-name" :title="project.project_path">
                {{ project.project_name || project.project_path }}
                <span class="project-type-badge" :class="project.project_type || 'local'">
                  {{ project.project_type === 'github' ? 'GitHub' : 'Local' }}
                </span>
              </div>
              <div class="project-meta">
                <template v-if="project.last_status === 'not_scanned' || !project.last_audit">
                  Not scanned yet<template v-if="project.registered_by_triggers?.length"> · Trigger: {{ project.registered_by_triggers[0] }}</template>
                </template>
                <template v-else>
                  {{ project.audit_count }} scan{{ project.audit_count !== 1 ? 's' : '' }} · Last: {{ formatDate(project.last_audit) }}
                </template>
              </div>
            </div>
            <div class="project-findings">
              <div class="findings-count" :class="getProjectStatusClass(project.last_status)">
                {{ project.last_status === 'not_scanned' || !project.last_audit ? '-' : (latestAuditByProject[project.project_path]?.total_findings ?? '-') }}
              </div>
              <div class="findings-label">
                {{ project.last_status === 'not_scanned' || !project.last_audit ? 'pending' : 'findings' }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Recent Audit Results -->
      <div class="card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
              <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/>
            </svg>
            Recent Audit Results
          </h3>
        </div>
        <DataTable
          :columns="auditTableColumns"
          :items="auditHistory.slice(0, 5)"
          row-clickable
          @row-click="(item: AuditRecord) => router.push({ name: 'audit-detail', params: { auditId: item.audit_id } })"
        >
          <template #empty>
            <EmptyState title="No audit data available" />
          </template>
          <template #cell-project="{ item }">
            <span class="cell-project">{{ item.project_name || item.project_path }}</span>
          </template>
          <template #cell-audit_date="{ item }">
            <span class="cell-date">{{ formatDate(item.audit_date) }}</span>
          </template>
          <template #cell-total_findings="{ item }">
            <span class="cell-number">{{ item.total_findings }}</span>
          </template>
          <template #cell-critical="{ item }">
            <StatusBadge :label="String(item.critical)" :variant="getSeverityVariant('critical')" />
          </template>
          <template #cell-high="{ item }">
            <StatusBadge :label="String(item.high)" :variant="getSeverityVariant('high')" />
          </template>
          <template #cell-medium="{ item }">
            <StatusBadge :label="String(item.medium)" :variant="getSeverityVariant('medium')" />
          </template>
          <template #cell-low="{ item }">
            <StatusBadge :label="String(item.low)" :variant="getSeverityVariant('low')" />
          </template>
          <template #cell-status="{ item }">
            <StatusBadge :label="item.status" :variant="getAuditStatusVariant(item.status)" />
          </template>
        </DataTable>
      </div>
    </template>

    <!-- Modals -->
    <RunScanModal
      v-if="showRunScanModal"
      :triggers="triggers"
      @close="showRunScanModal = false"
      @scanStarted="onScanComplete"
    />
    <ResolveIssuesModal
      v-if="showResolveModal"
      :audit-history="auditHistory"
      @close="showResolveModal = false"
      @resolved="onResolveComplete"
    />
  </div>
</template>

<style scoped>
.security-dashboard {
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

/* Cards */
.card {
  padding: 24px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.card-header h3 {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
}

.card-header h3 svg {
  width: 18px;
  height: 18px;
  color: var(--accent-cyan);
}

.card-badge {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 4px 10px;
  background: var(--bg-tertiary);
  border-radius: 4px;
}

/* Status Card */
.status-card {
  background: linear-gradient(135deg, var(--bg-secondary) 0%, var(--bg-tertiary) 100%);
  border-color: var(--border-default);
  padding: 0;
  overflow: hidden;
}

.status-card-inner {
  padding: 28px;
}

.status-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 28px;
  flex-wrap: wrap;
  gap: 16px;
}

.status-title-area {
  display: flex;
  align-items: flex-start;
  gap: 16px;
}

.status-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-elevated);
  border: 1px solid var(--border-default);
}

.status-icon svg {
  width: 24px;
  height: 24px;
  color: var(--text-secondary);
}

.status-icon.pass {
  background: var(--accent-emerald-dim);
  border-color: var(--accent-emerald);
}

.status-icon.pass svg {
  color: var(--accent-emerald);
}

.status-icon.fail {
  background: var(--accent-crimson-dim);
  border-color: var(--accent-crimson);
}

.status-icon.fail svg {
  color: var(--accent-crimson);
}

.status-title-area h3 {
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.status-subtitle {
  font-size: 0.85rem;
  color: var(--text-tertiary);
}

.status-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.status-badge {
  padding: 6px 16px;
  border-radius: 20px;
  font-weight: 600;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  background: var(--bg-elevated);
  color: var(--text-secondary);
}

.status-badge.pass {
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
}

.status-badge.fail {
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
}

/* Buttons */

.btn-primary:hover:not(:disabled) {
  box-shadow: var(--shadow-glow-cyan);
  transform: translateY(-1px);
}

.btn-warning {
  background: var(--accent-amber);
  color: var(--bg-primary);
}

.btn-warning:hover:not(:disabled) {
  filter: brightness(1.1);
  transform: translateY(-1px);
}

/* Stats Grid */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.stats-grid.compact {
  gap: 12px;
}

/* Projects Grid */
.projects-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}

.project-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  background: var(--bg-primary);
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  cursor: pointer;
  transition: all var(--transition-fast);
  animation: cardSlideIn 0.4s ease backwards;
  animation-delay: var(--delay, 0ms);
}

@keyframes cardSlideIn {
  from { opacity: 0; transform: translateX(-10px); }
  to { opacity: 1; transform: translateX(0); }
}

.project-card:hover {
  border-color: var(--accent-cyan);
  background: var(--bg-tertiary);
}

.project-status-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 1rem;
  flex-shrink: 0;
  background: var(--bg-elevated);
  color: var(--text-tertiary);
}

.project-status-icon.pass {
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
}

.project-status-icon.fail {
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
}

.project-status-icon.pending {
  background: var(--bg-elevated);
  color: var(--text-muted);
}

.project-info {
  flex: 1;
  min-width: 0;
}

.project-name {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--text-primary);
  font-size: 0.9rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.project-type-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.6rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  flex-shrink: 0;
}

.project-type-badge.local {
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
}

.project-type-badge.github {
  background: var(--accent-violet-dim);
  color: var(--accent-violet);
}

.project-meta {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  margin-top: 4px;
}

.project-findings {
  text-align: center;
  flex-shrink: 0;
}

.findings-count {
  font-family: var(--font-mono);
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--text-secondary);
}

.findings-count.pass {
  color: var(--accent-emerald);
}

.findings-count.fail {
  color: var(--accent-crimson);
}

.findings-label {
  font-size: 0.65rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

/* Cell styles for DataTable */
.cell-project {
  font-weight: 500;
  color: var(--text-primary);
}

.cell-date {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: var(--text-tertiary);
}

.cell-number {
  font-family: var(--font-mono);
  font-weight: 600;
}

/* Empty State */

.empty-icon {
  font-size: 2.5rem;
  color: var(--text-muted);
  margin-bottom: 12px;
}

.empty-state span {
  font-size: 0.85rem;
  color: var(--text-tertiary);
}

/* Auto-resolve toggle */
.auto-resolve-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 8px 14px;
  border-radius: 8px;
  background: var(--bg-elevated);
  border: 1px solid var(--border-default);
  transition: all var(--transition-fast);
}

.auto-resolve-toggle:hover {
  border-color: var(--accent-cyan);
}

.auto-resolve-toggle input[type="checkbox"] {
  width: 16px;
  height: 16px;
  accent-color: var(--accent-cyan);
  cursor: pointer;
}

.toggle-label {
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--text-secondary);
  white-space: nowrap;
}

/* Resolving banner */
.resolving-banner {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 20px;
  padding: 14px 20px;
  background: var(--accent-cyan-dim);
  border: 1px solid var(--accent-cyan);
  border-radius: 10px;
  color: var(--accent-cyan);
  font-size: 0.85rem;
  font-weight: 500;
}

.resolving-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid var(--accent-cyan);
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  flex-shrink: 0;
}

/* PR URLs section */
.pr-urls-section {
  margin-top: 20px;
  padding: 16px 20px;
  background: var(--bg-primary);
  border: 1px solid var(--accent-emerald);
  border-radius: 10px;
}

.pr-urls-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--accent-emerald);
  margin-bottom: 12px;
}

.pr-urls-title svg {
  width: 16px;
  height: 16px;
}

.pr-urls-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.pr-url-link {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--accent-cyan);
  font-size: 0.8rem;
  font-family: var(--font-mono);
  text-decoration: none;
  padding: 8px 12px;
  border-radius: 6px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  transition: all var(--transition-fast);
  word-break: break-all;
}

.pr-url-link:hover {
  border-color: var(--accent-cyan);
  background: var(--bg-tertiary);
}

.pr-url-link svg {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}

@media (max-width: 900px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .status-header {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
