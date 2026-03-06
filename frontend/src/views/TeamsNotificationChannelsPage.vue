<script setup lang="ts">
import { ref, computed } from 'vue';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';

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

const showAddModal = ref(false);
const testingChannelId = ref<string | null>(null);
const testResults = ref<TestResult[]>([]);

const newChannel = ref<Partial<NotificationChannel> & { type: ChannelType }>({
  type: 'slack',
  name: '',
  destination: '',
  events: ['execution_failed', 'critical_finding'],
  botIds: [],
  enabled: true,
});

const channels = ref<NotificationChannel[]>([
  {
    id: 'ch-001',
    name: '#platform-alerts',
    type: 'slack',
    destination: 'https://hooks.slack.com/services/T000/B000/xxx',
    enabled: true,
    events: ['execution_failed', 'critical_finding', 'bot_disabled'],
    botIds: ['bot-security', 'bot-pr-review'],
    lastDeliveredAt: '2026-03-06T11:42:00Z',
    deliveryCount: 187,
    failureCount: 2,
  },
  {
    id: 'ch-002',
    name: 'Engineering Team Channel',
    type: 'teams',
    destination: 'https://outlook.office.com/webhook/abc123/IncomingWebhook/xxx',
    enabled: true,
    events: ['execution_complete', 'critical_finding'],
    botIds: ['bot-pr-review'],
    lastDeliveredAt: '2026-03-06T09:15:00Z',
    deliveryCount: 94,
    failureCount: 0,
  },
  {
    id: 'ch-003',
    name: 'Security Team Email',
    type: 'email',
    destination: 'security-team@company.com',
    enabled: true,
    events: ['critical_finding', 'execution_failed'],
    botIds: ['bot-security'],
    lastDeliveredAt: '2026-03-05T08:00:00Z',
    deliveryCount: 31,
    failureCount: 1,
  },
  {
    id: 'ch-004',
    name: '#dev-digest',
    type: 'slack',
    destination: 'https://hooks.slack.com/services/T000/B001/yyy',
    enabled: false,
    events: ['execution_complete'],
    botIds: [],
    lastDeliveredAt: null,
    deliveryCount: 0,
    failureCount: 0,
  },
]);

const allEvents: { key: EventType; label: string }[] = [
  { key: 'execution_complete', label: 'Execution Complete' },
  { key: 'execution_failed', label: 'Execution Failed' },
  { key: 'critical_finding', label: 'Critical Finding' },
  { key: 'bot_disabled', label: 'Bot Auto-Disabled' },
  { key: 'quota_exceeded', label: 'Quota Exceeded' },
];

const allBots = [
  { id: 'bot-security', name: 'Security Audit Bot' },
  { id: 'bot-pr-review', name: 'PR Review Bot' },
  { id: 'bot-dep-audit', name: 'Dependency Audit Bot' },
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

function toggleChannel(ch: NotificationChannel) {
  ch.enabled = !ch.enabled;
  showToast(`Channel ${ch.enabled ? 'enabled' : 'disabled'}`, 'info');
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

function deleteChannel(id: string) {
  channels.value = channels.value.filter((ch) => ch.id !== id);
  showToast('Channel removed', 'info');
}

async function testChannel(ch: NotificationChannel) {
  testingChannelId.value = ch.id;
  await new Promise((r) => setTimeout(r, 1000));
  testingChannelId.value = null;
  const success = Math.random() > 0.2;
  testResults.value.unshift({
    channelId: ch.id,
    success,
    message: success ? 'Test message delivered successfully' : 'Delivery failed: webhook returned 404',
    testedAt: new Date().toISOString(),
  });
  showToast(success ? 'Test notification delivered!' : 'Delivery failed — check webhook URL', success ? 'success' : 'error');
}

function saveNewChannel() {
  if (!newChannel.value.name?.trim() || !newChannel.value.destination?.trim()) {
    showToast('Name and destination are required', 'error');
    return;
  }
  channels.value.push({
    id: `ch-${Date.now()}`,
    name: newChannel.value.name,
    type: newChannel.value.type,
    destination: newChannel.value.destination,
    enabled: true,
    events: newChannel.value.events ?? [],
    botIds: newChannel.value.botIds ?? [],
    lastDeliveredAt: null,
    deliveryCount: 0,
    failureCount: 0,
  });
  showAddModal.value = false;
  newChannel.value = { type: 'slack', name: '', destination: '', events: ['execution_failed', 'critical_finding'], botIds: [], enabled: true };
  showToast('Notification channel added', 'success');
}

const totalDeliveries = computed(() => channels.value.reduce((s, c) => s + c.deliveryCount, 0));
const enabledCount = computed(() => channels.value.filter((c) => c.enabled).length);
const lastTestForChannel = (id: string) => testResults.value.find((r) => r.channelId === id);
</script>

<template>
  <div class="page-container">
    <AppBreadcrumb :items="[{ label: 'Integrations' }, { label: 'Notification Channels' }]" />
    <PageHeader
      title="Notification Channels"
      subtitle="Configure Slack, Microsoft Teams, and email channels to receive bot execution results and critical alerts"
    />

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

    <div class="section-card">
      <div class="section-header">
        <h3 class="section-title">Configured Channels</h3>
        <button class="btn-primary" @click="showAddModal = true">+ Add Channel</button>
      </div>

      <div class="channels-list">
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
                {{ allBots.find((b) => b.id === id)?.name ?? id }}
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
