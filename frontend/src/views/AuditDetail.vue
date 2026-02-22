<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import type { AuditRecord } from '../services/api';
import { auditApi } from '../services/api';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import EntityLayout from '../layouts/EntityLayout.vue';
import { useToast } from '../composables/useToast';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const props = defineProps<{
  auditId?: string;
}>();

const route = useRoute();
const router = useRouter();
const auditId = computed(() => (route.params.auditId as string) || props.auditId || '');

const showToast = useToast();

const audit = ref<AuditRecord | null>(null);

useWebMcpTool({
  name: 'hive_audit_detail_get_state',
  description: 'Returns the current state of the Audit Detail page',
  page: 'AuditDetail',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'AuditDetail',
        auditId: audit.value?.audit_id ?? null,
      }),
    }],
  }),
  deps: [audit],
});

async function loadAudit() {
  const data = await auditApi.getDetail(auditId.value);
  audit.value = data;
  return data;
}

function formatDateShort(dateStr: string): string {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

const triggerContentText = computed(() => {
  if (!audit.value?.trigger_content) return '';
  if (typeof audit.value.trigger_content === 'object') {
    return JSON.stringify(audit.value.trigger_content, null, 2);
  }
  return String(audit.value.trigger_content);
});

async function copyCommand(command: string) {
  try {
    await navigator.clipboard.writeText(command);
    showToast('Command copied to clipboard', 'success');
  } catch {
    showToast('Failed to copy command', 'error');
  }
}


</script>

<template>
  <EntityLayout :load-entity="loadAudit" entity-label="audit">
    <template #default="{ reload: _reload }">
    <div class="audit-detail">
    <AppBreadcrumb :items="[{ label: 'Audit History', action: () => router.back() }, { label: 'Audit Detail' }]" />

    <template v-if="audit">
      <PageHeader :title="'Audit: ' + (audit.audit_id || '')" :subtitle="audit.trigger_name ? 'Trigger: ' + audit.trigger_name : undefined">
        <template #actions>
          <button class="btn btn-secondary" @click="router.back()">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
              <path d="M19 12H5M12 19l-7-7 7-7"/>
            </svg>
            Back
          </button>
        </template>
      </PageHeader>

      <!-- Audit Summary Stats -->
      <div class="summary-grid">
        <div class="summary-card">
          <div class="summary-icon date">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <rect x="3" y="4" width="18" height="18" rx="2"/>
              <path d="M16 2v4M8 2v4M3 10h18"/>
            </svg>
          </div>
          <div class="summary-content">
            <div class="summary-value">{{ formatDateShort(audit.audit_date) }}</div>
            <div class="summary-label">Audit Date</div>
          </div>
        </div>
        <div class="summary-card">
          <div class="summary-icon group">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
              <circle cx="9" cy="7" r="4"/>
              <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>
            </svg>
          </div>
          <div class="summary-content">
            <div class="summary-value mono">{{ audit.group_id || '-' }}</div>
            <div class="summary-label">Group ID</div>
          </div>
        </div>
        <div class="summary-card">
          <div class="summary-icon bot">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <rect x="3" y="11" width="18" height="10" rx="2"/>
              <circle cx="12" cy="5" r="2"/>
              <path d="M12 7v4M7 15h.01M17 15h.01"/>
            </svg>
          </div>
          <div class="summary-content">
            <div class="summary-value">{{ audit.trigger_name || '-' }}</div>
            <div class="summary-label">Trigger</div>
          </div>
        </div>
        <div class="summary-card severity critical">
          <div class="severity-count">{{ audit.critical || 0 }}</div>
          <div class="severity-label">Critical</div>
        </div>
        <div class="summary-card severity high">
          <div class="severity-count">{{ audit.high || 0 }}</div>
          <div class="severity-label">High</div>
        </div>
        <div class="summary-card severity medium">
          <div class="severity-count">{{ audit.medium || 0 }}</div>
          <div class="severity-label">Medium</div>
        </div>
        <div class="summary-card severity low">
          <div class="severity-count">{{ audit.low || 0 }}</div>
          <div class="severity-label">Low</div>
        </div>
      </div>

      <!-- Trigger Content -->
      <div v-if="audit.trigger_content" class="card">
        <div class="card-header">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
          </svg>
          <h3>Trigger Event</h3>
        </div>
        <pre class="trigger-content">{{ triggerContentText }}</pre>
      </div>

      <!-- Findings & Resolution Guide -->
      <div class="card">
        <div class="card-header">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
          </svg>
          <h3>Findings & Resolution Guide</h3>
        </div>

        <div v-if="!audit.findings || audit.findings.length === 0" class="all-clear">
          <div class="all-clear-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
              <polyline points="22 4 12 14.01 9 11.01"/>
            </svg>
          </div>
          <div class="all-clear-title">All Clear!</div>
          <div class="all-clear-text">No vulnerabilities found in this audit.</div>
        </div>

        <div v-else class="findings-list">
          <div
            v-for="(finding, index) in audit.findings"
            :key="index"
            class="finding-card"
            :class="finding.severity"
            :style="{ '--delay': `${index * 50}ms` }"
          >
            <div class="finding-header">
              <div class="finding-title">
                <span class="package-name">{{ finding.package }}</span>
                <span class="severity-badge" :class="finding.severity">
                  {{ finding.severity.toUpperCase() }}
                </span>
              </div>
            </div>

            <div class="finding-meta">
              <div class="meta-item">
                <span class="meta-label">Installed</span>
                <span class="meta-value">{{ finding.installed_version || finding.current_version }}</span>
              </div>
              <div class="meta-item">
                <span class="meta-label">Vulnerable</span>
                <span class="meta-value">{{ finding.vulnerable_version }}</span>
              </div>
              <div class="meta-item">
                <span class="meta-label">CVE</span>
                <span class="meta-value">
                  <a v-if="finding.cve_link" :href="finding.cve_link" target="_blank" rel="noopener noreferrer" class="cve-link">
                    {{ finding.cve }}
                  </a>
                  <template v-else>{{ finding.cve || 'N/A' }}</template>
                </span>
              </div>
              <div class="meta-item">
                <span class="meta-label">Ecosystem</span>
                <span class="meta-value">{{ finding.ecosystem || 'Unknown' }}</span>
              </div>
            </div>

            <div v-if="finding.description" class="finding-description">
              {{ finding.description }}
            </div>

            <div class="resolution-box">
              <div class="resolution-header">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
                </svg>
                <h4>Resolution Guide</h4>
              </div>
              <div v-if="finding.fix_command" class="command-box">
                <code>{{ finding.fix_command }}</code>
                <button class="copy-btn" @click="copyCommand(finding.fix_command!)">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="9" y="9" width="13" height="13" rx="2"/>
                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                  </svg>
                  Copy
                </button>
              </div>
              <div v-if="finding.recommended_version" class="resolution-note highlight">
                Recommended version: <strong>{{ finding.recommended_version }}</strong>
              </div>
              <div class="resolution-note">
                After updating, run your tests to ensure compatibility. Then re-run the security audit to verify the fix.
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
    </template>
  </EntityLayout>
</template>

<style scoped>
.audit-detail {
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

/* Summary Grid */
.summary-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 12px;
}

.summary-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  padding: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  transition: border-color var(--transition-fast);
}

.summary-card:hover {
  border-color: var(--border-default);
}

.summary-icon {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.summary-icon svg {
  width: 20px;
  height: 20px;
}

.summary-icon.date {
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
}

.summary-icon.group {
  background: var(--accent-violet-dim);
  color: var(--accent-violet);
}

.summary-icon.bot {
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
}

.summary-content {
  min-width: 0;
}

.summary-value {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.summary-value.mono {
  font-family: var(--font-mono);
  font-size: 0.9rem;
}

.summary-label {
  font-size: 0.7rem;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-top: 2px;
}

/* Severity Cards */
.summary-card.severity {
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 20px 16px;
}

.severity-count {
  font-family: var(--font-mono);
  font-size: 1.75rem;
  font-weight: 700;
  line-height: 1;
}

.severity-label {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-top: 6px;
}

.summary-card.severity.critical {
  border-color: var(--accent-crimson-dim);
}
.summary-card.severity.critical .severity-count { color: var(--accent-crimson); }
.summary-card.severity.critical .severity-label { color: var(--accent-crimson); }

.summary-card.severity.high {
  border-color: var(--accent-amber-dim);
}
.summary-card.severity.high .severity-count { color: var(--accent-amber); }
.summary-card.severity.high .severity-label { color: var(--accent-amber); }

.summary-card.severity.medium {
  border-color: var(--accent-cyan-dim);
}
.summary-card.severity.medium .severity-count { color: var(--accent-cyan); }
.summary-card.severity.medium .severity-label { color: var(--accent-cyan); }

.summary-card.severity.low {
  border-color: var(--accent-emerald-dim);
}
.summary-card.severity.low .severity-count { color: var(--accent-emerald); }
.summary-card.severity.low .severity-label { color: var(--accent-emerald); }

/* Card */
.card {
  padding: 24px;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
}

.card-header svg {
  width: 20px;
  height: 20px;
  color: var(--accent-cyan);
}

.card-header h3 {
  font-family: var(--font-mono);
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}

/* Trigger Content */
.trigger-content {
  background: var(--bg-primary);
  padding: 16px;
  border-radius: 8px;
  border: 1px solid var(--border-subtle);
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: var(--text-tertiary);
  overflow-x: auto;
  white-space: pre-wrap;
  max-height: 300px;
  overflow-y: auto;
}

/* All Clear */
.all-clear {
  text-align: center;
  padding: 60px 40px;
}

.all-clear-icon {
  width: 64px;
  height: 64px;
  background: var(--accent-emerald-dim);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 16px;
}

.all-clear-icon svg {
  width: 32px;
  height: 32px;
  color: var(--accent-emerald);
}

.all-clear-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--accent-emerald);
  margin-bottom: 8px;
}

.all-clear-text {
  color: var(--text-tertiary);
  font-size: 0.9rem;
}

/* Findings List */
.findings-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.finding-card {
  background: var(--bg-primary);
  border-radius: 12px;
  padding: 20px;
  border-left: 4px solid var(--border-default);
  animation: findingSlideIn 0.4s ease backwards;
  animation-delay: var(--delay, 0ms);
}

@keyframes findingSlideIn {
  from { opacity: 0; transform: translateX(-12px); }
  to { opacity: 1; transform: translateX(0); }
}

.finding-card.critical { border-left-color: var(--accent-crimson); }
.finding-card.high { border-left-color: var(--accent-amber); }
.finding-card.medium { border-left-color: var(--accent-cyan); }
.finding-card.low { border-left-color: var(--accent-emerald); }

.finding-header {
  margin-bottom: 16px;
}

.finding-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.package-name {
  font-weight: 600;
  font-size: 1.1rem;
  color: var(--text-primary);
}

.severity-badge {
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 0.7rem;
  font-weight: 700;
  font-family: var(--font-mono);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.severity-badge.critical {
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
}

.severity-badge.high {
  background: var(--accent-amber-dim);
  color: var(--accent-amber);
}

.severity-badge.medium {
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
}

.severity-badge.low {
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
}

/* Finding Meta */
.finding-meta {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.meta-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.meta-label {
  font-size: 0.7rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.meta-value {
  font-size: 0.85rem;
  color: var(--text-secondary);
  font-family: var(--font-mono);
}

.cve-link {
  color: var(--accent-cyan);
  text-decoration: none;
  transition: color var(--transition-fast);
}

.cve-link:hover {
  color: var(--text-primary);
  text-decoration: underline;
}

/* Finding Description */
.finding-description {
  color: var(--text-tertiary);
  font-size: 0.875rem;
  line-height: 1.6;
  margin-bottom: 16px;
  padding: 12px 16px;
  background: var(--bg-secondary);
  border-radius: 8px;
  border: 1px solid var(--border-subtle);
}

/* Resolution Box */
.resolution-box {
  background: var(--bg-secondary);
  border-radius: 8px;
  padding: 16px;
  border: 1px solid var(--border-subtle);
}

.resolution-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.resolution-header svg {
  width: 16px;
  height: 16px;
  color: var(--accent-emerald);
}

.resolution-header h4 {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-primary);
}

.command-box {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  background: var(--bg-primary);
  border-radius: 6px;
  border: 1px solid var(--border-subtle);
  margin-bottom: 12px;
}

.command-box code {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: var(--accent-emerald);
  word-break: break-all;
  flex: 1;
}

.copy-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: var(--accent-cyan);
  color: var(--bg-primary);
  border: none;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
  flex-shrink: 0;
}

.copy-btn svg {
  width: 14px;
  height: 14px;
}

.copy-btn:hover {
  background: var(--text-primary);
}

.resolution-note {
  font-size: 0.8rem;
  color: var(--text-tertiary);
  line-height: 1.5;
}

.resolution-note.highlight {
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.resolution-note strong {
  color: var(--accent-emerald);
}

@media (max-width: 1100px) {
  .summary-grid {
    grid-template-columns: repeat(4, 1fr);
  }
}

@media (max-width: 768px) {
  .summary-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .breadcrumb {
    flex-wrap: wrap;
  }
}
</style>
