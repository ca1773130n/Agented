<script setup lang="ts">
import { ref, onMounted } from 'vue';
import LoadingState from '../components/base/LoadingState.vue';
import { useToast } from '../composables/useToast';
import NotEnabledBanner from '../components/base/NotEnabledBanner.vue';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();
const showToast = useToast();
const isLoading = ref(true);
const isSaving = ref(false);
const isTesting = ref(false);

type EventKey = 'bot_completion' | 'bot_failure' | 'findings';

interface NotificationConfig {
  slack_channel: string;
  teams_webhook: string;
  events: Record<EventKey, boolean>;
  rich_format: boolean;
}

const config = ref<NotificationConfig>({
  slack_channel: '',
  teams_webhook: '',
  events: {
    bot_completion: true,
    bot_failure: true,
    findings: false,
  },
  rich_format: true,
});

const eventLabels: Record<EventKey, string> = {
  bot_completion: t('notificationHub.events.botCompletion'),
  bot_failure: t('notificationHub.events.botFailure'),
  findings: t('notificationHub.events.findings'),
};

const previewMessage = `{
  "text": "Bot *bot-security* completed successfully",
  "attachments": [{
    "color": "#36a64f",
    "fields": [
      { "title": "Status", "value": "completed", "short": true },
      { "title": "Duration", "value": "42s", "short": true }
    ]
  }]
}`;

async function loadConfig() {
  try {
    const res = await fetch('/admin/notifications/config');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    config.value = { ...config.value, ...data };
  } catch {
    // Use defaults
  } finally {
    isLoading.value = false;
  }
}

async function saveConfig() {
  isSaving.value = true;
  try {
    const res = await fetch('/admin/notifications/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config.value),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    showToast(t('notificationHub.toasts.configSaved'), 'success');
  } catch {
    showToast(t('notificationHub.toasts.savedDemo'), 'success');
  } finally {
    isSaving.value = false;
  }
}

async function testNotification() {
  isTesting.value = true;
  try {
    const res = await fetch('/admin/notifications/test', { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    showToast(t('notificationHub.toasts.testSent'), 'success');
  } catch {
    showToast(t('notificationHub.toasts.testSentDemo'), 'success');
  } finally {
    isTesting.value = false;
  }
}

// PR-J3: `/admin/notifications/{config,test}` is not yet wired up server-side.
// Flipping this constant off (and removing the banner) is what gates the
// feature when the backend stub ships in PR-J3b.
const FEATURE_ENABLED = false;

onMounted(loadConfig);
</script>

<template>
  <div class="notification-hub-page">

    <NotEnabledBanner
      v-if="!FEATURE_ENABLED"
      :feature="t('notificationHub.notEnabled.feature')"
      :detail="t('notificationHub.notEnabled.detail')"
      testid="notification-hub-not-enabled"
    />

    <div class="page-title-row">
      <div>
        <h2>{{ t('notificationHub.title') }}</h2>
        <p class="subtitle">{{ t('notificationHub.subtitle') }}</p>
      </div>
      <div class="header-actions">
        <button
          class="btn btn-secondary"
          :disabled="isTesting || !FEATURE_ENABLED"
          :title="!FEATURE_ENABLED ? t('notificationHub.notEnabledTitle') : ''"
          @click="testNotification"
        >
          {{ isTesting ? t('notificationHub.sending') : t('notificationHub.testNotification') }}
        </button>
        <button
          class="btn btn-primary"
          :disabled="isSaving || !FEATURE_ENABLED"
          :title="!FEATURE_ENABLED ? t('notificationHub.notEnabledTitleDeployment') : undefined"
          data-testid="notification-hub-save-submit"
          @click="saveConfig"
        >
          {{ isSaving ? t('notificationHub.saving') : t('notificationHub.saveConfig') }}
        </button>
      </div>
    </div>

    <LoadingState v-if="isLoading" :message="t('notificationHub.loading')" />

    <template v-else>
      <div class="config-grid">
        <!-- Channels -->
        <div class="card">
          <div class="card-header">
            <h3>{{ t('notificationHub.deliveryChannels') }}</h3>
          </div>
          <div class="field-group">
            <label class="field-label">{{ t('notificationHub.slackChannel') }}</label>
            <input
              v-model="config.slack_channel"
              class="field-input"
              type="text"
              :placeholder="t('notificationHub.slackPlaceholder')"
            />
          </div>
          <div class="field-group">
            <label class="field-label">{{ t('notificationHub.teamsWebhook') }}</label>
            <input
              v-model="config.teams_webhook"
              class="field-input"
              type="url"
              placeholder="https://outlook.office.com/webhook/..."
            />
          </div>
          <div class="field-group">
            <label class="toggle-row">
              <input v-model="config.rich_format" type="checkbox" class="toggle-input" />
              <span class="toggle-label">{{ t('notificationHub.richFormat') }}</span>
            </label>
          </div>
        </div>

        <!-- Event routing -->
        <div class="card">
          <div class="card-header">
            <h3>{{ t('notificationHub.eventRouting') }}</h3>
          </div>
          <div
            v-for="(_enabled, key) in config.events"
            :key="key"
            class="event-row"
          >
            <label class="toggle-row">
              <input
                :checked="config.events[key as EventKey]"
                type="checkbox"
                class="toggle-input"
                @change="config.events[key as EventKey] = ($event.target as HTMLInputElement).checked"
              />
              <span class="toggle-label">{{ eventLabels[key as EventKey] }}</span>
            </label>
          </div>
        </div>
      </div>

      <!-- Preview -->
      <div class="card preview-card">
        <div class="card-header">
          <h3>{{ t('notificationHub.messagePreview') }}</h3>
          <span class="card-badge">{{ t('notificationHub.slackFormat') }}</span>
        </div>
        <pre class="preview-code">{{ previewMessage }}</pre>
      </div>
    </template>
  </div>
</template>

<style scoped>
.notification-hub-page {
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
  flex-wrap: wrap;
  gap: 16px;
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

.header-actions {
  display: flex;
  gap: 10px;
}

.config-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

@media (max-width: 800px) {
  .config-grid { grid-template-columns: 1fr; }
}

.card {
  padding: 20px 24px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
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

.field-group {
  margin-bottom: 16px;
}

.field-label {
  display: block;
  font-size: 0.8rem;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.field-input {
  width: 100%;
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 0.85rem;
  box-sizing: border-box;
}

.field-input:focus {
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

.event-row {
  padding: 10px 0;
  border-bottom: 1px solid var(--border-subtle);
}

.event-row:last-child {
  border-bottom: none;
}

.preview-card {
  background: var(--bg-secondary);
}

.preview-code {
  font-family: 'Geist Mono', monospace;
  font-size: 0.8rem;
  color: var(--accent-cyan);
  background: var(--bg-elevated);
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  padding: 14px;
  white-space: pre-wrap;
  margin: 0;
}

</style>
