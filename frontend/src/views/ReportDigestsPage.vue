<script setup lang="ts">
import { ref, onMounted } from 'vue';
import LoadingState from '../components/base/LoadingState.vue';
import { useToast } from '../composables/useToast';

const showToast = useToast();
const isLoading = ref(true);
const isSaving = ref(false);

type Frequency = 'daily' | 'weekly';
type Channel = 'email' | 'slack';

interface DigestConfig {
  team_id: string;
  team_name: string;
  enabled: boolean;
  frequency: Frequency;
  channel: Channel;
  recipients: string;
  last_generated: string | null;
}

const digests = ref<DigestConfig[]>([]);

const previewContent = `# Weekly Security Digest — Platform Team
Generated: 2026-03-06

## Bot Activity Summary
- bot-security: 12 runs, 3 findings
- bot-pr-review: 34 runs, 0 critical findings

## Key Findings
1. [HIGH] Dependency vulnerability in requests==2.28.0
2. [MEDIUM] Exposed debug endpoint /api/debug
3. [LOW] Missing HSTS header on staging

## Recommendations
- Update requests to >=2.31.0
- Disable /api/debug in production
- Enable HSTS via flask-talisman
`;

async function loadDigests() {
  try {
    const res = await fetch('/admin/reports/digests');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    digests.value = data.digests ?? [];
  } catch {
    digests.value = [
      { team_id: 'team-platform', team_name: 'Platform', enabled: true, frequency: 'weekly', channel: 'slack', recipients: '#platform-alerts', last_generated: '2026-03-06T08:00:00Z' },
      { team_id: 'team-security', team_name: 'Security', enabled: true, frequency: 'daily', channel: 'email', recipients: 'security@example.com', last_generated: '2026-03-06T07:00:00Z' },
      { team_id: 'team-data', team_name: 'Data', enabled: false, frequency: 'weekly', channel: 'email', recipients: '', last_generated: null },
    ];
  } finally {
    isLoading.value = false;
  }
}

async function saveDigest(digest: DigestConfig) {
  isSaving.value = true;
  try {
    const res = await fetch(`/admin/reports/digests/${digest.team_id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(digest),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    showToast('Digest settings saved', 'success');
  } catch {
    showToast('Saved (demo mode)', 'success');
  } finally {
    isSaving.value = false;
  }
}

function formatTime(iso: string | null): string {
  if (!iso) return 'Never';
  return new Date(iso).toLocaleString();
}

onMounted(loadDigests);
</script>

<template>
  <div class="report-digests-page">

    <div class="page-title-row">
      <div>
        <h2>Report Digests</h2>
        <p class="subtitle">Schedule AI-generated summaries delivered to email or Slack</p>
      </div>
    </div>

    <LoadingState v-if="isLoading" message="Loading digest configurations..." />

    <template v-else>
      <div class="digest-list">
        <div v-for="d in digests" :key="d.team_id" class="card digest-card">
          <div class="digest-header">
            <div class="digest-title">
              <span class="team-name">{{ d.team_name }}</span>
              <span
                class="status-badge"
                :class="d.enabled ? 'active' : 'inactive'"
              >
                {{ d.enabled ? 'Active' : 'Disabled' }}
              </span>
            </div>
            <span class="last-generated">Last: {{ formatTime(d.last_generated) }}</span>
          </div>

          <div class="digest-fields">
            <div class="field-group">
              <label class="toggle-row">
                <input v-model="d.enabled" type="checkbox" class="toggle-input" />
                <span class="toggle-label">Enable digest for this team</span>
              </label>
            </div>

            <div class="fields-row">
              <div class="field-group">
                <label class="field-label">Frequency</label>
                <select v-model="d.frequency" class="field-select">
                  <option value="daily">Daily</option>
                  <option value="weekly">Weekly</option>
                </select>
              </div>
              <div class="field-group">
                <label class="field-label">Channel</label>
                <select v-model="d.channel" class="field-select">
                  <option value="email">Email</option>
                  <option value="slack">Slack</option>
                </select>
              </div>
              <div class="field-group flex-grow">
                <label class="field-label">
                  {{ d.channel === 'slack' ? 'Slack Channel' : 'Email Recipients' }}
                </label>
                <input
                  v-model="d.recipients"
                  class="field-input"
                  :placeholder="d.channel === 'slack' ? '#team-channel' : 'team@example.com'"
                />
              </div>
            </div>

            <div class="save-row">
              <button class="btn btn-primary btn-sm" :disabled="isSaving" @click="saveDigest(d)">
                {{ isSaving ? 'Saving...' : 'Save' }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Preview -->
      <div class="card preview-card">
        <div class="card-header">
          <h3>Last Generated Digest Preview</h3>
          <span class="card-badge">Platform Team</span>
        </div>
        <pre class="preview-text">{{ previewContent }}</pre>
      </div>
    </template>
  </div>
</template>

<style scoped>
.report-digests-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.page-title-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.page-title-row h2 {
  font-size: 1.4rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 4px;
}

.subtitle {
  font-size: 0.85rem;
  color: var(--text-tertiary);
  margin: 0;
}

.digest-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.card {
  padding: 20px 24px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.card-header h3 {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
}

.card-badge {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 3px 8px;
  background: var(--bg-tertiary);
  border-radius: 4px;
}

.digest-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.digest-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.team-name {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
}

.status-badge {
  font-size: 0.72rem;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.status-badge.active {
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
}

.status-badge.inactive {
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
}

.last-generated {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.digest-fields {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.fields-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.fields-row .field-group {
  min-width: 140px;
}

.flex-grow {
  flex: 1;
}

.field-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.field-label {
  font-size: 0.78rem;
  color: var(--text-secondary);
}

.field-input,
.field-select {
  padding: 7px 10px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 0.83rem;
  width: 100%;
  box-sizing: border-box;
}

.field-input:focus,
.field-select:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.toggle-row {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
}

.toggle-input {
  width: 16px;
  height: 16px;
  accent-color: var(--accent-cyan);
}

.toggle-label {
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.save-row {
  display: flex;
  justify-content: flex-end;
}

.btn-sm {
  padding: 5px 16px;
  font-size: 0.82rem;
}

.preview-card {
  background: var(--bg-secondary);
}

.preview-text {
  font-family: 'Geist Mono', monospace;
  font-size: 0.8rem;
  color: var(--text-secondary);
  background: var(--bg-elevated);
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  padding: 14px;
  white-space: pre-wrap;
  margin: 0;
  line-height: 1.6;
}
</style>
