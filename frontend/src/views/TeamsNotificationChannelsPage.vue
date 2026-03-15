<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { integrationApi, teamApi, ApiError } from '../services/api';
import type { Integration } from '../services/api';
import type { Team } from '../services/api';

const showToast = useToast();

type ChannelType = 'slack' | 'teams' | 'email';
type EventType = 'execution_complete' | 'execution_failed' | 'critical_finding' | 'bot_disabled' | 'quota_exceeded';

interface NotificationChannel {
  id: string;
  name: string;
  type: ChannelType;
  destination: string;
  enabled: boolean;
  events: EventType[];
  botIds: string[];
  lastDeliveredAt: string | null;
  deliveryCount: number;
  failureCount: number;
}

interface TestResult {
  channelId: string;
  success: boolean;
  message: string;
  testedAt: string;
}

const loading = ref(true);
const error = ref('');
const showAddModal = ref(false);
const testingChannelId = ref<string | null>(null);
const testResults = ref<TestResult[]>([]);
const teams = ref<Team[]>([]);

const newChannel = ref<Partial<NotificationChannel> & { type: ChannelType }>({
  type: 'slack',
  name: '',
  destination: '',
  events: ['execution_failed', 'critical_finding'],
  botIds: [],
  enabled: true,
});

const channels = ref<NotificationChannel[]>([]);

function integrationToChannel(int: Integration): NotificationChannel {
  const config = int.config || {};
  const channelType = (int.type || 'slack').toLowerCase();
  let mappedType: ChannelType = 'slack';
  if (channelType.includes('teams') || channelType.includes('microsoft')) mappedType = 'teams';
  else if (channelType.includes('email')) mappedType = 'email';

  return {
    id: int.id,
    name: int.name,
    type: mappedType,
    destination: (config.destination as string) || (config.webhook_url as string) || '',
    enabled: int.enabled,
    events: (config.events as EventType[]) || [],
    botIds: (config.bot_ids as string[]) || [],
    lastDeliveredAt: (config.last_delivered_at as string) || null,
    deliveryCount: (config.delivery_count as number) || 0,
    failureCount: (config.failure_count as number) || 0,
  };
}

function channelToIntegrationData(ch: Partial<NotificationChannel> & { type: ChannelType }): Partial<Integration> {
  return {
    name: ch.name || '',
    type: ch.type,
    enabled: ch.enabled ?? true,
    config: {
      destination: ch.destination || '',
      events: ch.events || [],
      bot_ids: ch.botIds || [],
    },
  };
}

async function fetchData() {
  loading.value = true;
  error.value = '';
  try {
    const [integrationsResult, teamsResult] = await Promise.all([
      integrationApi.list(),
      teamApi.list(),
    ]);
    const allIntegrations = integrationsResult || [];
    channels.value = allIntegrations
      .filter((i) => {
        const t = (i.type || '').toLowerCase();
        return t.includes('slack') || t.includes('teams') || t.includes('email') || t.includes('notification');
      })
      .map(integrationToChannel);
    teams.value = teamsResult?.teams || [];
  } catch (err) {
    if (err instanceof ApiError) {
      error.value = `Failed to load notification channels: ${err.message}`;
    } else {
      error.value = 'Failed to load notification channels';
    }
  } finally {
    loading.value = false;
  }
}

onMounted(fetchData);

const allEvents: { key: EventType; label: string }[] = [
  { key: 'execution_complete', label: 'Execution Complete' },
  { key: 'execution_failed', label: 'Execution Failed' },
  { key: 'critical_finding', label: 'Critical Finding' },
  { key: 'bot_disabled', label: 'Bot Auto-Disabled' },
  { key: 'quota_exceeded', label: 'Quota Exceeded' },
];

function channelIcon(type: ChannelType): string {
  return type === 'slack' ? '💬' : type === 'teams' ? '🟦' : '📧';
}

function channelColor(type: ChannelType): string {
  return type === 'slack' ? 'var(--accent-green)' : type === 'teams' ? 'var(--accent-blue)' : 'var(--accent-amber)';
}

function formatDate(iso: string | null): string {
  if (!iso) return 'Never';
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

async function toggleChannel(ch: NotificationChannel) {
  const prev = ch.enabled;
  ch.enabled = !ch.enabled;
  try {
    await integrationApi.update(ch.id, { enabled: ch.enabled });
    showToast(`Channel ${ch.enabled ? 'enabled' : 'disabled'}`, 'info');
  } catch (err) {
    ch.enabled = prev;
    showToast(err instanceof ApiError ? err.message : 'Failed to toggle channel', 'error');
  }
}

function toggleEvent(ch: NotificationChannel, event: EventType) {
  if (ch.events.includes(event)) {
    ch.events = ch.events.filter((e) => e !== event);
  } else {
    ch.events = [...ch.events, event];
  }
}

function toggleNewEvent(event: EventType) {
  const events = newChannel.value.events ?? [];
  if (events.includes(event)) {
    newChannel.value.events = events.filter((e) => e !== event);
  } else {
    newChannel.value.events = [...events, event];
  }
}

async function deleteChannel(id: string) {
  try {
    await integrationApi.delete(id);
    channels.value = channels.value.filter((ch) => ch.id !== id);
    showToast('Channel removed', 'info');
  } catch (err) {
    showToast(err instanceof ApiError ? err.message : 'Failed to delete channel', 'error');
  }
}

async function testChannel(ch: NotificationChannel) {
  testingChannelId.value = ch.id;
  try {
    const result = await integrationApi.test(ch.id);
    testResults.value.unshift({
      channelId: ch.id,
      success: result.success,
      message: result.message,
      testedAt: new Date().toISOString(),
    });
    showToast(result.success ? 'Test notification delivered!' : `Delivery failed: ${result.message}`, result.success ? 'success' : 'error');
  } catch (err) {
    testResults.value.unshift({
      channelId: ch.id,
      success: false,
      message: err instanceof ApiError ? err.message : 'Test failed',
      testedAt: new Date().toISOString(),
    });
    showToast(err instanceof ApiError ? err.message : 'Test failed', 'error');
  } finally {
    testingChannelId.value = null;
  }
}

async function saveNewChannel() {
  if (!newChannel.value.name?.trim() || !newChannel.value.destination?.trim()) {
    showToast('Name and destination are required', 'error');
    return;
  }
  try {
    const data = channelToIntegrationData(newChannel.value);
    const created = await integrationApi.create(data);
    channels.value.push(integrationToChannel(created));
    showAddModal.value = false;
    newChannel.value = { type: 'slack', name: '', destination: '', events: ['execution_failed', 'critical_finding'], botIds: [], enabled: true };
    showToast('Notification channel added', 'success');
  } catch (err) {
    showToast(err instanceof ApiError ? err.message : 'Failed to create channel', 'error');
  }
}

const totalDeliveries = computed(() => channels.value.reduce((s, c) => s + c.deliveryCount, 0));
const enabledCount = computed(() => channels.value.filter((c) => c.enabled).length);
const lastTestForChannel = (id: string) => testResults.value.find((r) => r.channelId === id);
</script>

<template>
  <div class="page-container">
    <PageHeader
      title="Notification Channels"
      subtitle="Configure Slack, Microsoft Teams, and email channels to receive bot execution results and critical alerts"
    />

    <!-- Loading state -->
    <div v-if="loading" class="section-card" style="padding: 48px; text-align: center;">
      <div style="color: var(--text-tertiary); font-size: 0.875rem;">Loading notification channels...</div>
    </div>

    <!-- Error state -->
    <div v-else-if="error" class="section-card" style="padding: 48px; text-align: center;">
      <div style="color: #ef4444; font-size: 0.875rem; margin-bottom: 12px;">{{ error }}</div>
      <button class="btn-primary" @click="fetchData">Retry</button>
    </div>

    <template v-else>
      <div class="stats-row">
        <div class="stat-card">
          <div class="stat-label">Channels Configured</div>
          <div class="stat-value">{{ channels.length }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Active Channels</div>
          <div class="stat-value" :style="{ color: 'var(--accent-green)' }">{{ enabledCount }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Total Deliveries</div>
          <div class="stat-value">{{ totalDeliveries }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Total Failures</div>
          <div class="stat-value" :style="{ color: channels.reduce((s,c)=>s+c.failureCount,0) > 0 ? 'var(--accent-amber)' : 'var(--text-primary)' }">
            {{ channels.reduce((s, c) => s + c.failureCount, 0) }}
          </div>
        </div>
      </div>

      <div v-if="teams.length > 0" class="section-card" style="margin-bottom: 20px;">
        <div class="section-header">
          <h3 class="section-title">Teams</h3>
        </div>
        <div style="padding: 12px 20px; font-size: 0.82rem; color: var(--text-secondary);">
          {{ teams.length }} team{{ teams.length !== 1 ? 's' : '' }} available:
          <span v-for="(t, i) in teams" :key="t.id">{{ t.name }}<span v-if="i < teams.length - 1">, </span></span>
        </div>
      </div>

      <div class="section-card">
        <div class="section-header">
          <h3 class="section-title">Configured Channels</h3>
          <button class="btn-primary" @click="showAddModal = true">+ Add Channel</button>
        </div>

        <div v-if="channels.length === 0" style="padding: 32px 20px; text-align: center; color: var(--text-tertiary); font-size: 0.82rem;">
          No notification channels configured yet. Click "Add Channel" to get started.
        </div>

        <div v-else class="channels-list">
          <div v-for="ch in channels" :key="ch.id" class="channel-card" :class="{ disabled: !ch.enabled }">
            <div class="channel-main">
              <div class="channel-icon" :style="{ color: channelColor(ch.type) }">{{ channelIcon(ch.type) }}</div>
              <div class="channel-info">
                <div class="channel-name">{{ ch.name }}</div>
                <div class="channel-dest">{{ ch.destination }}</div>
                <div class="channel-meta">
                  {{ ch.deliveryCount }} delivered · {{ ch.failureCount }} failed ·
                  Last: {{ formatDate(ch.lastDeliveredAt) }}
                </div>
                <!-- Test result -->
                <div v-if="lastTestForChannel(ch.id)" class="test-result" :class="lastTestForChannel(ch.id)!.success ? 'ok' : 'err'">
                  {{ lastTestForChannel(ch.id)!.success ? '✓' : '✗' }} {{ lastTestForChannel(ch.id)!.message }}
                </div>
              </div>
              <div class="channel-actions">
                <button
                  class="btn-test"
                  :disabled="testingChannelId === ch.id"
                  @click="testChannel(ch)"
                >
                  {{ testingChannelId === ch.id ? 'Sending…' : 'Test' }}
                </button>
                <label class="toggle">
                  <input type="checkbox" :checked="ch.enabled" @change="toggleChannel(ch)" />
                  <span class="toggle-track"></span>
                </label>
                <button class="btn-delete" @click="deleteChannel(ch.id)">✕</button>
              </div>
            </div>

            <!-- Events -->
            <div class="channel-events">
              <span class="events-label">Notify on:</span>
              <div class="event-tags">
                <span
                  v-for="ev in allEvents"
                  :key="ev.key"
                  class="event-tag"
                  :class="{ active: ch.events.includes(ev.key) }"
                  @click="toggleEvent(ch, ev.key)"
                >
                  {{ ev.label }}
                </span>
              </div>
            </div>

            <!-- Bot scope -->
            <div v-if="ch.botIds.length > 0" class="channel-bots">
              <span class="events-label">Bots:</span>
              <div class="event-tags">
                <span v-for="id in ch.botIds" :key="id" class="bot-tag">
                  {{ id }}
                </span>
              </div>
              <span class="bot-scope-note">All other bots excluded</span>
            </div>
            <div v-else class="channel-bots">
              <span class="events-label">Scope:</span>
              <span class="all-bots-note">All bots</span>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- Add channel modal -->
    <div v-if="showAddModal" class="modal-overlay" @click.self="showAddModal = false">
      <div class="modal">
        <div class="modal-header">
          <h3>Add Notification Channel</h3>
          <button class="btn-close" @click="showAddModal = false">✕</button>
        </div>

        <div class="form-row">
          <label class="form-label">Channel type</label>
          <div class="type-tabs">
            <button
              v-for="t in (['slack', 'teams', 'email'] as ChannelType[])"
              :key="t"
              class="type-tab"
              :class="{ active: newChannel.type === t }"
              @click="newChannel.type = t"
            >
              {{ channelIcon(t) }} {{ t === 'teams' ? 'Microsoft Teams' : t.charAt(0).toUpperCase() + t.slice(1) }}
            </button>
          </div>
        </div>

        <div class="form-row">
          <label class="form-label">Display name</label>
          <input v-model="newChannel.name" class="form-input" placeholder="e.g. #security-alerts" />
        </div>

        <div class="form-row">
          <label class="form-label">
            {{ newChannel.type === 'email' ? 'Email address' : 'Webhook URL' }}
          </label>
          <input
            v-model="newChannel.destination"
            class="form-input"
            :placeholder="newChannel.type === 'email' ? 'team@company.com' : 'https://hooks...'"
          />
        </div>

        <div class="form-row">
          <label class="form-label">Notify on events</label>
          <div class="event-tags">
            <span
              v-for="ev in allEvents"
              :key="ev.key"
              class="event-tag"
              :class="{ active: newChannel.events?.includes(ev.key) }"
              @click="toggleNewEvent(ev.key)"
            >
              {{ ev.label }}
            </span>
          </div>
        </div>

        <div class="modal-footer">
          <button class="btn-secondary" @click="showAddModal = false">Cancel</button>
          <button class="btn-primary" @click="saveNewChannel">Add Channel</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-container { padding: 24px; max-width: 1000px; }
.stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px; }
.stat-card { background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 8px; padding: 16px; text-align: center; }
.stat-label { font-size: 12px; color: var(--text-muted); margin-bottom: 6px; }
.stat-value { font-size: 24px; font-weight: 700; color: var(--text-primary); }
.section-card { background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 8px; padding: 20px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.section-title { font-size: 15px; font-weight: 600; color: var(--text-primary); margin: 0; }
.channels-list { display: flex; flex-direction: column; gap: 12px; }
.channel-card { background: var(--bg-primary); border: 1px solid var(--border-color); border-radius: 8px; padding: 16px; transition: opacity 0.2s; }
.channel-card.disabled { opacity: 0.6; }
.channel-main { display: flex; align-items: flex-start; gap: 12px; margin-bottom: 12px; }
.channel-icon { font-size: 20px; flex-shrink: 0; margin-top: 2px; }
.channel-info { flex: 1; }
.channel-name { font-size: 14px; font-weight: 700; color: var(--text-primary); }
.channel-dest { font-size: 11px; color: var(--text-muted); font-family: monospace; margin: 2px 0; word-break: break-all; }
.channel-meta { font-size: 11px; color: var(--text-muted); }
.test-result { margin-top: 4px; font-size: 11px; padding: 3px 8px; border-radius: 4px; display: inline-block; }
.test-result.ok { background: color-mix(in srgb, var(--accent-green) 15%, transparent); color: var(--accent-green); }
.test-result.err { background: color-mix(in srgb, var(--accent-red) 15%, transparent); color: var(--accent-red); }
.channel-actions { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.btn-test { padding: 5px 12px; border-radius: 5px; border: 1px solid var(--border-color); background: transparent; color: var(--text-primary); cursor: pointer; font-size: 12px; }
.btn-test:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-delete { padding: 5px 8px; border-radius: 5px; border: 1px solid var(--border-color); background: transparent; color: var(--text-muted); cursor: pointer; font-size: 12px; }
.toggle { position: relative; display: inline-block; width: 36px; height: 20px; cursor: pointer; }
.toggle input { opacity: 0; width: 0; height: 0; }
.toggle-track { position: absolute; inset: 0; background: var(--border-color); border-radius: 10px; transition: background 0.2s; }
.toggle input:checked ~ .toggle-track { background: var(--accent-green); }
.toggle-track::after { content: ''; position: absolute; width: 14px; height: 14px; top: 3px; left: 3px; background: white; border-radius: 50%; transition: transform 0.2s; }
.toggle input:checked ~ .toggle-track::after { transform: translateX(16px); }
.channel-events, .channel-bots { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 6px; }
.events-label { font-size: 11px; color: var(--text-muted); white-space: nowrap; }
.event-tags { display: flex; gap: 6px; flex-wrap: wrap; }
.event-tag { padding: 3px 10px; border-radius: 12px; font-size: 11px; border: 1px solid var(--border-color); color: var(--text-muted); cursor: pointer; transition: all 0.15s; }
.event-tag.active { background: color-mix(in srgb, var(--accent-blue) 15%, transparent); color: var(--accent-blue); border-color: var(--accent-blue); }
.bot-tag { padding: 3px 10px; border-radius: 12px; font-size: 11px; background: var(--bg-secondary); color: var(--text-muted); border: 1px solid var(--border-color); }
.bot-scope-note, .all-bots-note { font-size: 11px; color: var(--text-muted); }
.btn-primary { padding: 7px 16px; border-radius: 6px; border: none; background: var(--accent-blue); color: white; cursor: pointer; font-size: 13px; font-weight: 600; }
.btn-secondary { padding: 7px 16px; border-radius: 6px; border: 1px solid var(--border-color); background: transparent; color: var(--text-primary); cursor: pointer; font-size: 13px; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal { background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 12px; padding: 24px; width: 480px; max-width: 95vw; }
.modal-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }
.modal-header h3 { font-size: 16px; font-weight: 700; color: var(--text-primary); margin: 0; }
.btn-close { background: transparent; border: none; color: var(--text-muted); font-size: 16px; cursor: pointer; }
.form-row { margin-bottom: 16px; }
.form-label { display: block; font-size: 12px; color: var(--text-muted); margin-bottom: 6px; font-weight: 500; }
.form-input { width: 100%; padding: 8px 12px; border: 1px solid var(--border-color); border-radius: 6px; background: var(--bg-primary); color: var(--text-primary); font-size: 13px; box-sizing: border-box; }
.type-tabs { display: flex; gap: 8px; }
.type-tab { padding: 6px 14px; border-radius: 6px; border: 1px solid var(--border-color); background: transparent; color: var(--text-muted); cursor: pointer; font-size: 13px; }
.type-tab.active { border-color: var(--accent-blue); color: var(--accent-blue); background: color-mix(in srgb, var(--accent-blue) 10%, transparent); }
.modal-footer { display: flex; justify-content: flex-end; gap: 8px; margin-top: 24px; }
</style>
