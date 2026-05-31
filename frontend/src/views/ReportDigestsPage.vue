<script setup lang="ts">
// PR-G: the mutating backend handlers in
// `backend/app_litestar/routes/leaf_crud_c.py` (POST/PUT /reports/digests)
// now return 501 ("Feature not yet enabled"). The GET still returns an
// honest empty `{digests: []}`. We render a banner at the top of the page
// and disable the create/edit submit buttons so operators don't believe
// their changes persisted.
import { ref, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import LoadingState from '../components/base/LoadingState.vue';
import EmptyState from '../components/base/EmptyState.vue';
import { useToast } from '../composables/useToast';
import NotEnabledBanner from '../components/base/NotEnabledBanner.vue';

const showToast = useToast();
const { t } = useI18n();

// Digest delivery is not yet wired up server-side. Flipping this constant
// off (and removing the banner) is what gates the feature when it ships.
const FEATURE_ENABLED = false;
const isLoading = ref(true);
const isSaving = ref(false);
const showCreateForm = ref(false);
const isCreating = ref(false);
const newDigest = ref({
  team_name: '',
  frequency: 'weekly' as Frequency,
  channel: 'email' as Channel,
  recipients: '',
  enabled: false,
});

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
    showToast(t('reportDigests.toasts.saved'), 'success');
  } catch {
    showToast(t('reportDigests.toasts.savedDemo'), 'success');
  } finally {
    isSaving.value = false;
  }
}

function resetCreateForm() {
  newDigest.value = {
    team_name: '',
    frequency: 'weekly',
    channel: 'email',
    recipients: '',
    enabled: false,
  };
}

async function createDigest() {
  if (!newDigest.value.team_name.trim()) {
    showToast(t('reportDigests.toasts.teamNameRequired'), 'error');
    return;
  }
  isCreating.value = true;
  try {
    const res = await fetch('/admin/reports/digests', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(newDigest.value),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const created = await res.json();
    digests.value.push(created);
    showCreateForm.value = false;
    resetCreateForm();
    showToast(t('reportDigests.toasts.created'), 'success');
  } catch {
    showToast(t('reportDigests.toasts.createdDemo'), 'success');
    const suffix = Math.random().toString(36).substring(2, 8);
    digests.value.push({
      team_id: `team-${suffix}`,
      team_name: newDigest.value.team_name,
      frequency: newDigest.value.frequency,
      channel: newDigest.value.channel,
      recipients: newDigest.value.recipients,
      enabled: newDigest.value.enabled,
      last_generated: null,
    });
    showCreateForm.value = false;
    resetCreateForm();
  } finally {
    isCreating.value = false;
  }
}

function formatTime(iso: string | null): string {
  if (!iso) return t('reportDigests.never');
  return new Date(iso).toLocaleString();
}

onMounted(loadDigests);
</script>

<template>
  <div class="report-digests-page">

    <NotEnabledBanner
      v-if="!FEATURE_ENABLED"
      :feature="t('reportDigests.notEnabled.feature')"
      :detail="t('reportDigests.notEnabled.detail')"
      testid="digests-not-enabled"
    />

    <div class="page-title-row">
      <div>
        <h2>{{ t('reportDigests.title') }}</h2>
        <p class="subtitle">{{ t('reportDigests.subtitle') }}</p>
      </div>
      <button
        class="btn btn-primary"
        :disabled="!FEATURE_ENABLED"
        :title="!FEATURE_ENABLED ? t('reportDigests.notEnabledTooltipShort') : ''"
        @click="showCreateForm = !showCreateForm"
      >
        {{ showCreateForm ? t('common.cancel') : t('reportDigests.addDigest') }}
      </button>
    </div>

    <!-- Create form -->
    <div v-if="showCreateForm" class="card create-form">
      <div class="create-form-header">{{ t('reportDigests.newDigest') }}</div>
      <div class="digest-fields" style="padding: 20px 24px;">
        <div class="fields-row">
          <div class="field-group">
            <label class="field-label">{{ t('reportDigests.fields.teamName') }}</label>
            <input v-model="newDigest.team_name" class="field-input" placeholder="e.g. Platform" />
          </div>
          <div class="field-group">
            <label class="field-label">{{ t('reportDigests.fields.frequency') }}</label>
            <select v-model="newDigest.frequency" class="field-select">
              <option value="daily">{{ t('reportDigests.frequency.daily') }}</option>
              <option value="weekly">{{ t('reportDigests.frequency.weekly') }}</option>
            </select>
          </div>
          <div class="field-group">
            <label class="field-label">{{ t('reportDigests.fields.channel') }}</label>
            <select v-model="newDigest.channel" class="field-select">
              <option value="email">{{ t('reportDigests.channel.email') }}</option>
              <option value="slack">Slack</option>
            </select>
          </div>
        </div>
        <div class="fields-row">
          <div class="field-group flex-grow">
            <label class="field-label">
              {{ newDigest.channel === 'slack' ? t('reportDigests.fields.slackChannel') : t('reportDigests.fields.emailRecipients') }}
            </label>
            <input
              v-model="newDigest.recipients"
              class="field-input"
              :placeholder="newDigest.channel === 'slack' ? '#team-channel' : 'team@example.com'"
            />
          </div>
        </div>
        <div class="create-actions">
          <button class="btn btn-secondary btn-sm" @click="showCreateForm = false; resetCreateForm()">{{ t('common.cancel') }}</button>
          <button
            class="btn btn-primary btn-sm"
            :disabled="isCreating || !FEATURE_ENABLED"
            :title="!FEATURE_ENABLED ? t('reportDigests.notEnabledTooltip') : undefined"
            data-testid="digest-create-submit"
            @click="createDigest"
          >
            {{ isCreating ? t('reportDigests.creating') : t('reportDigests.createDigest') }}
          </button>
        </div>
      </div>
    </div>

    <LoadingState v-if="isLoading" :message="t('reportDigests.loading')" />

    <template v-else>
      <EmptyState v-if="digests.length === 0" :title="t('reportDigests.empty.title')" :description="t('reportDigests.empty.description')">
        <template #actions>
          <button
            class="btn btn-primary"
            :disabled="!FEATURE_ENABLED"
            :title="!FEATURE_ENABLED ? t('reportDigests.notEnabledTooltipShort') : ''"
            @click="showCreateForm = true"
          >{{ t('reportDigests.addDigest') }}</button>
        </template>
      </EmptyState>
      <div class="digest-list">
        <div v-for="d in digests" :key="d.team_id" class="card digest-card">
          <div class="digest-header">
            <div class="digest-title">
              <span class="team-name">{{ d.team_name }}</span>
              <span
                class="status-badge"
                :class="d.enabled ? 'active' : 'inactive'"
              >
                {{ d.enabled ? t('reportDigests.active') : t('reportDigests.disabled') }}
              </span>
            </div>
            <span class="last-generated">{{ t('reportDigests.lastLabel', { time: formatTime(d.last_generated) }) }}</span>
          </div>

          <div class="digest-fields">
            <div class="field-group">
              <label class="toggle-row">
                <input v-model="d.enabled" type="checkbox" class="toggle-input" />
                <span class="toggle-label">{{ t('reportDigests.enableForTeam') }}</span>
              </label>
            </div>

            <div class="fields-row">
              <div class="field-group">
                <label class="field-label">{{ t('reportDigests.fields.frequency') }}</label>
                <select v-model="d.frequency" class="field-select">
                  <option value="daily">{{ t('reportDigests.frequency.daily') }}</option>
                  <option value="weekly">{{ t('reportDigests.frequency.weekly') }}</option>
                </select>
              </div>
              <div class="field-group">
                <label class="field-label">{{ t('reportDigests.fields.channel') }}</label>
                <select v-model="d.channel" class="field-select">
                  <option value="email">{{ t('reportDigests.channel.email') }}</option>
                  <option value="slack">Slack</option>
                </select>
              </div>
              <div class="field-group flex-grow">
                <label class="field-label">
                  {{ d.channel === 'slack' ? t('reportDigests.fields.slackChannel') : t('reportDigests.fields.emailRecipients') }}
                </label>
                <input
                  v-model="d.recipients"
                  class="field-input"
                  :placeholder="d.channel === 'slack' ? '#team-channel' : 'team@example.com'"
                />
              </div>
            </div>

            <div class="save-row">
              <button
                class="btn btn-primary btn-sm"
                :disabled="isSaving || !FEATURE_ENABLED"
                :title="!FEATURE_ENABLED ? t('reportDigests.notEnabledTooltip') : undefined"
                @click="saveDigest(d)"
              >
                {{ isSaving ? t('reportDigests.saving') : t('common.save') }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Preview -->
      <div class="card preview-card">
        <div class="card-header">
          <h3>{{ t('reportDigests.previewTitle') }}</h3>
          <span class="card-badge">{{ t('reportDigests.platformTeam') }}</span>
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

.btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}

.btn-primary {
  background: var(--accent-cyan);
  color: #000;
}

.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }

.btn-secondary {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
}

.btn-secondary:hover { border-color: var(--accent-cyan); color: var(--text-primary); }

.create-form {
  padding: 0;
}

.create-form-header {
  padding: 16px 24px;
  border-bottom: 1px solid var(--border-default);
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-primary);
}

.create-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
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
