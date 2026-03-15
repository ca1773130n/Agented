<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { integrationApi, ApiError } from '../services/api';
import type { Integration } from '../services/api';

const router = useRouter();
const showToast = useToast();

interface NotificationChannel {
  id: string;
  name: string;
  slackChannel: string;
  webhookUrl: string;
  enabled: boolean;
  events: string[];
  template: string;
  bots: string[];
}

interface NotificationLog {
  id: string;
  channel: string;
  event: string;
  botId: string;
  status: 'sent' | 'failed' | 'pending';
  sentAt: string;
  message: string;
}

const eventTypes = [
  { value: 'execution_started', label: 'Execution Started' },
  { value: 'execution_success', label: 'Execution Succeeded' },
  { value: 'execution_failed', label: 'Execution Failed' },
  { value: 'execution_timeout', label: 'Execution Timed Out' },
  { value: 'daily_digest', label: 'Daily Digest' },
  { value: 'weekly_digest', label: 'Weekly Digest' },
];

const loading = ref(true);
const error = ref('');
const channels = ref<NotificationChannel[]>([]);
const logs = ref<NotificationLog[]>([]);
const selectedChannel = ref<NotificationChannel | null>(null);
const isTestingSend = ref(false);
const isSaving = ref(false);
const activeTab = ref<'config' | 'logs'>('config');

function integrationToChannel(int: Integration): NotificationChannel {
  const config = int.config || {};
  return {
    id: int.id,
    name: int.name,
    slackChannel: (config.slack_channel as string) || '',
    webhookUrl: (config.webhook_url as string) || '',
    enabled: int.enabled,
    events: (config.events as string[]) || [],
    template: (config.template as string) || '{{bot_name}} — {{status}}',
    bots: (config.bots as string[]) || [],
  };
}

function channelToIntegration(ch: NotificationChannel): Partial<Integration> {
  return {
    name: ch.name,
    type: 'slack',
    enabled: ch.enabled,
    config: {
      slack_channel: ch.slackChannel,
      webhook_url: ch.webhookUrl,
      events: ch.events,
      template: ch.template,
      bots: ch.bots,
    },
  };
}

async function fetchChannels() {
  loading.value = true;
  error.value = '';
  try {
    const allIntegrations = await integrationApi.list();
    const slackIntegrations = (allIntegrations || []).filter(
      (i) => i.type && i.type.toLowerCase().includes('slack')
    );
    channels.value = slackIntegrations.map(integrationToChannel);
    if (channels.value.length > 0 && !selectedChannel.value) {
      selectedChannel.value = channels.value[0];
    }
  } catch (err) {
    if (err instanceof ApiError) {
      error.value = `Failed to load Slack integrations: ${err.message}`;
    } else {
      error.value = 'Failed to load Slack integrations';
    }
  } finally {
    loading.value = false;
  }
}

onMounted(fetchChannels);

function toggleEvent(val: string) {
  if (!selectedChannel.value) return;
  const evts = selectedChannel.value.events;
  const i = evts.indexOf(val);
  if (i === -1) evts.push(val);
  else evts.splice(i, 1);
}

async function handleTestSend() {
  if (!selectedChannel.value) return;
  isTestingSend.value = true;
  try {
    const result = await integrationApi.test(selectedChannel.value.id);
    if (result.success) {
      showToast(`Test message sent to ${selectedChannel.value.slackChannel}`, 'success');
    } else {
      showToast(result.message || 'Test send failed', 'error');
    }
  } catch (err) {
    showToast(err instanceof ApiError ? err.message : 'Test send failed', 'error');
  } finally {
    isTestingSend.value = false;
  }
}

async function handleSave() {
  if (!selectedChannel.value) return;
  isSaving.value = true;
  try {
    const data = channelToIntegration(selectedChannel.value);
    await integrationApi.update(selectedChannel.value.id, data);
    showToast('Notification channel saved', 'success');
  } catch (err) {
    showToast(err instanceof ApiError ? err.message : 'Failed to save channel', 'error');
  } finally {
    isSaving.value = false;
  }
}

async function addChannel() {
  const nc: NotificationChannel = {
    id: '',
    name: 'New Channel',
    slackChannel: '#channel-name',
    webhookUrl: '',
    enabled: false,
    events: [],
    template: '{{bot_name}} — {{status}}',
    bots: [],
  };
  try {
    const created = await integrationApi.create(channelToIntegration(nc));
    const createdChannel = integrationToChannel(created);
    channels.value.push(createdChannel);
    selectedChannel.value = createdChannel;
    showToast('New Slack channel created', 'success');
  } catch (err) {
    showToast(err instanceof ApiError ? err.message : 'Failed to create channel', 'error');
  }
}

function statusColor(s: NotificationLog['status']): string {
  return { sent: '#34d399', failed: '#ef4444', pending: '#fbbf24' }[s];
}

function formatDate(ts: string): string {
  return new Date(ts).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}
</script>

<template>
  <div class="slack-notifications">

    <PageHeader
      title="Slack Execution Notifications"
      subtitle="Route bot execution results, failures, and summaries to configurable Slack channels."
    />

    <!-- Loading state -->
    <div v-if="loading" class="card" style="padding: 48px; text-align: center;">
      <div style="color: var(--text-tertiary); font-size: 0.875rem;">Loading Slack integrations...</div>
    </div>

    <!-- Error state -->
    <div v-else-if="error" class="card" style="padding: 48px; text-align: center;">
      <div style="color: #ef4444; font-size: 0.875rem; margin-bottom: 12px;">{{ error }}</div>
      <button class="btn btn-ghost" @click="fetchChannels">Retry</button>
    </div>

    <!-- Empty state -->
    <div v-else-if="channels.length === 0 && !loading" class="card" style="padding: 48px; text-align: center;">
      <div style="color: var(--text-tertiary); font-size: 0.875rem; margin-bottom: 12px;">No Slack notification channels configured yet.</div>
      <button class="btn btn-primary" @click="addChannel">+ Add Channel</button>
    </div>

    <div v-else class="layout">
      <!-- Channel list -->
      <aside class="sidebar card">
        <div class="sidebar-header">
          <span>Channels</span>
          <button class="btn-add" @click="addChannel">+</button>
        </div>
        <div
          v-for="ch in channels"
          :key="ch.id"
          class="channel-item"
          :class="{ active: selectedChannel?.id === ch.id }"
          @click="selectedChannel = ch"
        >
          <div class="channel-row">
            <span class="channel-name">{{ ch.name }}</span>
            <span class="status-pill" :class="ch.enabled ? 'pill-on' : 'pill-off'">
              {{ ch.enabled ? 'ON' : 'OFF' }}
            </span>
          </div>
          <div class="channel-slack">{{ ch.slackChannel }}</div>
        </div>
      </aside>

      <!-- Editor -->
      <div v-if="selectedChannel" class="editor">
        <!-- Tabs -->
        <div class="tabs">
          <button :class="['tab', { active: activeTab === 'config' }]" @click="activeTab = 'config'">Configuration</button>
          <button :class="['tab', { active: activeTab === 'logs' }]" @click="activeTab = 'logs'">Delivery Logs</button>
        </div>

        <template v-if="activeTab === 'config'">
          <div class="card">
            <div class="card-header">Channel Settings</div>
            <div class="card-body">
              <div class="field-row">
                <div class="field">
                  <label class="field-label">Channel Name</label>
                  <input v-model="selectedChannel.name" class="input" placeholder="Engineering Alerts" />
                </div>
                <div class="field">
                  <label class="field-label">Slack Channel</label>
                  <input v-model="selectedChannel.slackChannel" class="input" placeholder="#channel-name" />
                </div>
              </div>
              <div class="field">
                <label class="field-label">Webhook URL</label>
                <input v-model="selectedChannel.webhookUrl" class="input" placeholder="https://hooks.slack.com/services/..." type="password" />
              </div>
              <div class="field">
                <label class="field-label">Enable Channel</label>
                <label class="toggle-label">
                  <input type="checkbox" v-model="selectedChannel.enabled" />
                  <span>{{ selectedChannel.enabled ? 'Active' : 'Disabled' }}</span>
                </label>
              </div>
            </div>
          </div>

          <div class="card">
            <div class="card-header">Notification Events</div>
            <div class="card-body">
              <div class="event-grid">
                <label v-for="evt in eventTypes" :key="evt.value" class="event-check">
                  <input
                    type="checkbox"
                    :checked="selectedChannel.events.includes(evt.value)"
                    @change="toggleEvent(evt.value)"
                  />
                  {{ evt.label }}
                </label>
              </div>
            </div>
          </div>

          <div class="card">
            <div class="card-header">Message Template</div>
            <div class="card-body">
              <div class="template-hint">
                Available variables: <code>{{'{'}}{{'bot_name'}}{{'}'}}</code>, <code>{{'{'}}{{'status'}}{{'}'}}</code>,
                <code>{{'{'}}{{'error_summary'}}{{'}'}}</code>, <code>{{'{'}}{{'execution_url'}}{{'}'}}</code>,
                <code>{{'{'}}{{'summary_table'}}{{'}'}}</code>
              </div>
              <textarea v-model="selectedChannel.template" class="textarea" rows="5" />
            </div>
          </div>

          <div class="actions">
            <button class="btn btn-ghost" :disabled="isTestingSend" @click="handleTestSend">
              {{ isTestingSend ? 'Sending...' : 'Send Test Message' }}
            </button>
            <button class="btn btn-primary" :disabled="isSaving" @click="handleSave">
              {{ isSaving ? 'Saving...' : 'Save Channel' }}
            </button>
          </div>
        </template>

        <template v-else>
          <div class="card">
            <div class="card-header">
              <span>Recent Deliveries</span>
              <span class="badge-count">{{ logs.length }}</span>
            </div>
            <div v-if="logs.length === 0" style="padding: 32px; text-align: center; color: var(--text-tertiary); font-size: 0.82rem;">
              No delivery logs available yet.
            </div>
            <div v-else class="log-list">
              <div v-for="log in logs" :key="log.id" class="log-row">
                <span class="log-status-dot" :style="{ background: statusColor(log.status) }"></span>
                <div class="log-info">
                  <div class="log-message">{{ log.message }}</div>
                  <div class="log-meta">
                    <span>{{ log.channel }}</span>
                    <span class="sep">·</span>
                    <span>{{ log.botId }}</span>
                    <span class="sep">·</span>
                    <span>{{ formatDate(log.sentAt) }}</span>
                  </div>
                </div>
                <span class="log-status-text" :style="{ color: statusColor(log.status) }">{{ log.status }}</span>
              </div>
            </div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.slack-notifications { display: flex; flex-direction: column; gap: 24px; animation: fadeIn 0.4s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

.layout { display: grid; grid-template-columns: 220px 1fr; gap: 20px; align-items: start; }

.card { background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 12px; overflow: hidden; }

.sidebar-header {
  display: flex; align-items: center; justify-content: space-between; padding: 14px 16px;
  border-bottom: 1px solid var(--border-default); font-size: 0.8rem; font-weight: 600; color: var(--text-secondary);
}
.btn-add { background: var(--accent-cyan); color: #000; border: none; width: 22px; height: 22px; border-radius: 4px; cursor: pointer; font-weight: 700; font-size: 1rem; display: flex; align-items: center; justify-content: center; }

.channel-item { padding: 12px 16px; cursor: pointer; border-bottom: 1px solid var(--border-subtle); transition: background 0.1s; }
.channel-item:hover { background: var(--bg-tertiary); }
.channel-item.active { background: rgba(6,182,212,0.08); border-left: 2px solid var(--accent-cyan); }
.channel-item:last-child { border-bottom: none; }
.channel-row { display: flex; align-items: center; justify-content: space-between; }
.channel-name { font-size: 0.82rem; font-weight: 600; color: var(--text-primary); }
.channel-slack { font-size: 0.72rem; color: var(--text-muted); margin-top: 3px; font-family: monospace; }

.status-pill { font-size: 0.6rem; font-weight: 700; padding: 1px 5px; border-radius: 3px; }
.pill-on { background: rgba(52, 211, 153, 0.2); color: #34d399; }
.pill-off { background: var(--bg-tertiary); color: var(--text-muted); }

.editor { display: flex; flex-direction: column; gap: 16px; }

.tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--border-default); }
.tab { padding: 8px 16px; background: none; border: none; color: var(--text-secondary); font-size: 0.85rem; cursor: pointer; border-bottom: 2px solid transparent; margin-bottom: -1px; }
.tab.active { color: var(--text-primary); border-bottom-color: var(--accent-cyan); }

.card-header { padding: 14px 20px; border-bottom: 1px solid var(--border-default); font-size: 0.82rem; font-weight: 600; color: var(--text-secondary); display: flex; align-items: center; justify-content: space-between; }
.badge-count { background: var(--bg-tertiary); border: 1px solid var(--border-default); color: var(--text-tertiary); font-size: 0.7rem; padding: 2px 8px; border-radius: 4px; }

.card-body { padding: 20px; display: flex; flex-direction: column; gap: 16px; }

.field-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.field { display: flex; flex-direction: column; gap: 6px; }
.field-label { font-size: 0.78rem; font-weight: 500; color: var(--text-secondary); }

.input { padding: 8px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 7px; color: var(--text-primary); font-size: 0.875rem; }
.input:focus { outline: none; border-color: var(--accent-cyan); }

.toggle-label { display: flex; align-items: center; gap: 8px; font-size: 0.82rem; color: var(--text-secondary); cursor: pointer; }
.toggle-label input { accent-color: var(--accent-cyan); cursor: pointer; }

.event-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.event-check { display: flex; align-items: center; gap: 8px; font-size: 0.82rem; color: var(--text-secondary); cursor: pointer; }
.event-check input { accent-color: var(--accent-cyan); cursor: pointer; }

.template-hint { font-size: 0.75rem; color: var(--text-tertiary); margin-bottom: 8px; }
.template-hint code { background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 3px; padding: 1px 4px; font-family: monospace; color: var(--accent-cyan); }

.textarea { width: 100%; padding: 10px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 7px; color: var(--text-primary); font-size: 0.82rem; font-family: 'Geist Mono', monospace; resize: vertical; box-sizing: border-box; }
.textarea:focus { outline: none; border-color: var(--accent-cyan); }

.actions { display: flex; justify-content: flex-end; gap: 12px; }
.btn { display: flex; align-items: center; gap: 6px; padding: 8px 16px; border-radius: 7px; font-size: 0.82rem; font-weight: 500; cursor: pointer; border: none; transition: all 0.15s; }
.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-ghost { background: var(--bg-tertiary); border: 1px solid var(--border-default); color: var(--text-secondary); }
.btn-ghost:hover:not(:disabled) { border-color: var(--accent-cyan); color: var(--accent-cyan); }
.btn-ghost:disabled { opacity: 0.4; cursor: not-allowed; }

.log-list { display: flex; flex-direction: column; }
.log-row { display: flex; align-items: center; gap: 12px; padding: 12px 20px; border-bottom: 1px solid var(--border-subtle); }
.log-row:last-child { border-bottom: none; }
.log-status-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.log-info { flex: 1; }
.log-message { font-size: 0.82rem; color: var(--text-primary); font-family: monospace; }
.log-meta { font-size: 0.72rem; color: var(--text-muted); display: flex; gap: 4px; margin-top: 3px; }
.sep { opacity: 0.5; }
.log-status-text { font-size: 0.72rem; font-weight: 600; text-transform: uppercase; }

@media (max-width: 900px) { .layout { grid-template-columns: 1fr; } .event-grid { grid-template-columns: 1fr 1fr; } .field-row { grid-template-columns: 1fr; } }
</style>
