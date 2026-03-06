<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';

const router = useRouter();
const showToast = useToast();

type Severity = 'critical' | 'high' | 'medium' | 'low' | 'any';
type Channel = 'email' | 'slack' | 'webhook' | 'pagerduty';
type Condition = 'severity_gte' | 'keyword_match' | 'count_gte' | 'bot_id';

interface AlertRule {
  id: string;
  name: string;
  enabled: boolean;
  conditions: RuleCondition[];
  channels: NotificationChannel[];
  createdAt: string;
  lastFired: string | null;
  fireCount: number;
}

interface RuleCondition {
  type: Condition;
  value: string;
}

interface NotificationChannel {
  type: Channel;
  target: string;
}

const rules = ref<AlertRule[]>([
  {
    id: 'ar-001',
    name: 'Critical Security Findings',
    enabled: true,
    conditions: [{ type: 'severity_gte', value: 'critical' }],
    channels: [
      { type: 'slack', target: '#security-alerts' },
      { type: 'email', target: 'security@example.com' },
    ],
    createdAt: '2026-02-10T09:00:00Z',
    lastFired: '2026-03-05T14:32:00Z',
    fireCount: 3,
  },
  {
    id: 'ar-002',
    name: 'Injection Pattern Detection',
    enabled: true,
    conditions: [
      { type: 'keyword_match', value: 'SQL injection' },
      { type: 'keyword_match', value: 'XSS' },
    ],
    channels: [{ type: 'slack', target: '#dev-alerts' }],
    createdAt: '2026-02-15T11:30:00Z',
    lastFired: '2026-03-01T08:15:00Z',
    fireCount: 7,
  },
  {
    id: 'ar-003',
    name: 'High Finding Burst',
    enabled: false,
    conditions: [
      { type: 'severity_gte', value: 'high' },
      { type: 'count_gte', value: '5' },
    ],
    channels: [
      { type: 'pagerduty', target: 'service-key-abc123' },
      { type: 'email', target: 'oncall@example.com' },
    ],
    createdAt: '2026-02-20T14:00:00Z',
    lastFired: null,
    fireCount: 0,
  },
]);

const showEditor = ref(false);
const editingRule = ref<AlertRule | null>(null);
const isSaving = ref(false);

// New/edit form state
const formName = ref('');
const formConditions = ref<RuleCondition[]>([{ type: 'severity_gte', value: 'high' }]);
const formChannels = ref<NotificationChannel[]>([{ type: 'slack', target: '' }]);

const conditionTypeOptions: { value: Condition; label: string }[] = [
  { value: 'severity_gte', label: 'Severity is at least' },
  { value: 'keyword_match', label: 'Output contains keyword' },
  { value: 'count_gte', label: 'Finding count at least' },
  { value: 'bot_id', label: 'From specific bot' },
];

const severityOptions: { value: Severity; label: string }[] = [
  { value: 'critical', label: 'Critical' },
  { value: 'high', label: 'High' },
  { value: 'medium', label: 'Medium' },
  { value: 'low', label: 'Low' },
];

const channelTypeOptions: { value: Channel; label: string; icon: string }[] = [
  { value: 'slack', label: 'Slack', icon: '💬' },
  { value: 'email', label: 'Email', icon: '📧' },
  { value: 'webhook', label: 'Webhook', icon: '🔗' },
  { value: 'pagerduty', label: 'PagerDuty', icon: '🚨' },
];

function channelPlaceholder(type: Channel): string {
  if (type === 'slack') return '#channel-name';
  if (type === 'email') return 'user@example.com';
  if (type === 'webhook') return 'https://hooks.example.com/notify';
  return 'service-key';
}

function openNew() {
  formName.value = '';
  formConditions.value = [{ type: 'severity_gte', value: 'high' }];
  formChannels.value = [{ type: 'slack', target: '' }];
  editingRule.value = null;
  showEditor.value = true;
}

function openEdit(rule: AlertRule) {
  formName.value = rule.name;
  formConditions.value = rule.conditions.map(c => ({ ...c }));
  formChannels.value = rule.channels.map(c => ({ ...c }));
  editingRule.value = rule;
  showEditor.value = true;
}

function addCondition() {
  formConditions.value.push({ type: 'keyword_match', value: '' });
}

function removeCondition(idx: number) {
  formConditions.value.splice(idx, 1);
}

function addChannel() {
  formChannels.value.push({ type: 'email', target: '' });
}

function removeChannel(idx: number) {
  formChannels.value.splice(idx, 1);
}

async function saveRule() {
  if (!formName.value.trim()) {
    showToast('Rule name is required.', 'error');
    return;
  }
  isSaving.value = true;
  try {
    await new Promise(r => setTimeout(r, 600));
    if (editingRule.value) {
      const r = rules.value.find(r => r.id === editingRule.value!.id);
      if (r) {
        r.name = formName.value;
        r.conditions = formConditions.value.map(c => ({ ...c }));
        r.channels = formChannels.value.map(c => ({ ...c }));
      }
      showToast(`Rule "${formName.value}" updated.`, 'success');
    } else {
      rules.value.unshift({
        id: `ar-${Date.now()}`,
        name: formName.value,
        enabled: true,
        conditions: formConditions.value.map(c => ({ ...c })),
        channels: formChannels.value.map(c => ({ ...c })),
        createdAt: new Date().toISOString(),
        lastFired: null,
        fireCount: 0,
      });
      showToast(`Rule "${formName.value}" created.`, 'success');
    }
    showEditor.value = false;
  } finally {
    isSaving.value = false;
  }
}

async function toggleEnabled(rule: AlertRule) {
  rule.enabled = !rule.enabled;
  showToast(`Rule "${rule.name}" ${rule.enabled ? 'enabled' : 'disabled'}.`, 'success');
}

async function deleteRule(rule: AlertRule) {
  rules.value = rules.value.filter(r => r.id !== rule.id);
  showToast(`Rule "${rule.name}" deleted.`, 'success');
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function severityColor(val: string): string {
  if (val === 'critical') return '#f87171';
  if (val === 'high') return '#fb923c';
  if (val === 'medium') return '#fbbf24';
  return '#94a3b8';
}
</script>

<template>
  <div class="smart-alert-rules">
    <AppBreadcrumb :items="[
      { label: 'Monitoring', action: () => router.push({ name: 'alert-grouping' }) },
      { label: 'Smart Alert Rules' },
    ]" />

    <PageHeader
      title="Smart Alert Rules"
      subtitle="Define conditions that fire notifications when bot findings match specific severity, keywords, or patterns."
    >
      <template #actions>
        <button class="btn btn-primary" @click="openNew">+ New Rule</button>
      </template>
    </PageHeader>

    <div class="rules-list">
      <div v-if="rules.length === 0" class="empty-state">
        <div class="empty-icon">🔔</div>
        <p>No alert rules defined yet. Create your first rule to get proactive notifications.</p>
        <button class="btn btn-primary" @click="openNew">Create Alert Rule</button>
      </div>

      <div v-for="rule in rules" :key="rule.id" class="rule-card card">
        <div class="rule-header">
          <div class="rule-title-row">
            <span class="rule-name">{{ rule.name }}</span>
            <span class="status-dot" :class="{ active: rule.enabled, inactive: !rule.enabled }">
              {{ rule.enabled ? 'Active' : 'Disabled' }}
            </span>
          </div>
          <div class="rule-actions">
            <button class="btn btn-xs btn-ghost" @click="openEdit(rule)">Edit</button>
            <button class="btn btn-xs btn-ghost" @click="toggleEnabled(rule)">
              {{ rule.enabled ? 'Disable' : 'Enable' }}
            </button>
            <button class="btn btn-xs btn-ghost btn-danger" @click="deleteRule(rule)">Delete</button>
          </div>
        </div>

        <div class="rule-body">
          <div class="rule-section">
            <div class="section-label">Conditions (ALL must match)</div>
            <div class="condition-tags">
              <span v-for="(c, i) in rule.conditions" :key="i" class="condition-tag">
                <template v-if="c.type === 'severity_gte'">
                  Severity ≥ <span :style="{ color: severityColor(c.value), fontWeight: '700' }">{{ c.value }}</span>
                </template>
                <template v-else-if="c.type === 'keyword_match'">
                  Contains <span class="keyword">"{{ c.value }}"</span>
                </template>
                <template v-else-if="c.type === 'count_gte'">
                  Finding count ≥ {{ c.value }}
                </template>
                <template v-else>
                  Bot ID = {{ c.value }}
                </template>
              </span>
            </div>
          </div>

          <div class="rule-section">
            <div class="section-label">Notify via</div>
            <div class="channel-tags">
              <span v-for="(ch, i) in rule.channels" :key="i" class="channel-tag">
                {{ channelTypeOptions.find(o => o.value === ch.type)?.icon }}
                {{ ch.target }}
              </span>
            </div>
          </div>
        </div>

        <div class="rule-footer">
          <span class="meta">Created {{ fmtDate(rule.createdAt) }}</span>
          <span class="sep">·</span>
          <span class="meta">Fired {{ rule.fireCount }} time{{ rule.fireCount !== 1 ? 's' : '' }}</span>
          <template v-if="rule.lastFired">
            <span class="sep">·</span>
            <span class="meta">Last fired {{ fmtDate(rule.lastFired) }}</span>
          </template>
          <template v-else>
            <span class="sep">·</span>
            <span class="meta muted">Never fired</span>
          </template>
        </div>
      </div>
    </div>

    <!-- Editor slide-over -->
    <div v-if="showEditor" class="overlay" @click.self="showEditor = false">
      <div class="slide-panel">
        <div class="panel-header">
          <h2 class="panel-title">{{ editingRule ? 'Edit Alert Rule' : 'New Alert Rule' }}</h2>
          <button class="close-btn" @click="showEditor = false">✕</button>
        </div>

        <div class="panel-body">
          <div class="field">
            <label class="field-label">Rule Name</label>
            <input v-model="formName" class="input" placeholder="e.g. Critical Security Findings" />
          </div>

          <div class="field">
            <div class="field-header">
              <label class="field-label">Conditions</label>
              <button class="btn btn-xs btn-ghost" @click="addCondition">+ Add Condition</button>
            </div>
            <div class="conditions-editor">
              <div v-for="(cond, i) in formConditions" :key="i" class="condition-row">
                <select v-model="cond.type" class="select select-sm">
                  <option v-for="opt in conditionTypeOptions" :key="opt.value" :value="opt.value">
                    {{ opt.label }}
                  </option>
                </select>
                <select v-if="cond.type === 'severity_gte'" v-model="cond.value" class="select select-sm">
                  <option v-for="s in severityOptions" :key="s.value" :value="s.value">{{ s.label }}</option>
                </select>
                <input v-else v-model="cond.value" class="input input-sm" :placeholder="cond.type === 'count_gte' ? '5' : 'value'" />
                <button class="btn btn-xs btn-ghost btn-icon" @click="removeCondition(i)" :disabled="formConditions.length <= 1">✕</button>
              </div>
            </div>
          </div>

          <div class="field">
            <div class="field-header">
              <label class="field-label">Notification Channels</label>
              <button class="btn btn-xs btn-ghost" @click="addChannel">+ Add Channel</button>
            </div>
            <div class="channels-editor">
              <div v-for="(ch, i) in formChannels" :key="i" class="channel-row">
                <select v-model="ch.type" class="select select-sm">
                  <option v-for="opt in channelTypeOptions" :key="opt.value" :value="opt.value">
                    {{ opt.icon }} {{ opt.label }}
                  </option>
                </select>
                <input v-model="ch.target" class="input input-sm" :placeholder="channelPlaceholder(ch.type)" />
                <button class="btn btn-xs btn-ghost btn-icon" @click="removeChannel(i)" :disabled="formChannels.length <= 1">✕</button>
              </div>
            </div>
          </div>
        </div>

        <div class="panel-footer">
          <button class="btn btn-ghost" @click="showEditor = false">Cancel</button>
          <button class="btn btn-primary" :disabled="isSaving || !formName.trim()" @click="saveRule">
            {{ isSaving ? 'Saving...' : editingRule ? 'Update Rule' : 'Create Rule' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.smart-alert-rules { display: flex; flex-direction: column; gap: 20px; animation: fadeIn 0.3s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }

.card { background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 10px; overflow: hidden; }

.rules-list { display: flex; flex-direction: column; gap: 12px; }

.rule-card { }
.rule-header { display: flex; align-items: center; justify-content: space-between; padding: 14px 18px; border-bottom: 1px solid var(--border-default); }
.rule-title-row { display: flex; align-items: center; gap: 10px; }
.rule-name { font-size: 0.9rem; font-weight: 600; color: var(--text-primary); }
.status-dot { font-size: 0.72rem; font-weight: 600; padding: 2px 8px; border-radius: 20px; }
.status-dot.active { background: rgba(52,211,153,0.12); color: #34d399; }
.status-dot.inactive { background: var(--bg-tertiary); color: var(--text-tertiary); }
.rule-actions { display: flex; gap: 6px; }

.rule-body { padding: 14px 18px; display: flex; flex-direction: column; gap: 12px; }
.rule-section { display: flex; flex-direction: column; gap: 6px; }
.section-label { font-size: 0.72rem; font-weight: 500; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.04em; }

.condition-tags, .channel-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.condition-tag { font-size: 0.78rem; background: var(--bg-tertiary); border: 1px solid var(--border-default); padding: 3px 10px; border-radius: 6px; color: var(--text-secondary); }
.keyword { color: var(--accent-cyan); font-family: monospace; }
.channel-tag { font-size: 0.78rem; background: rgba(99,102,241,0.1); border: 1px solid rgba(99,102,241,0.2); padding: 3px 10px; border-radius: 6px; color: var(--text-secondary); }

.rule-footer { padding: 10px 18px; background: var(--bg-tertiary); display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.meta { font-size: 0.75rem; color: var(--text-tertiary); }
.muted { opacity: 0.6; }
.sep { color: var(--border-default); font-size: 0.75rem; }

/* Buttons */
.btn { padding: 7px 14px; border-radius: 7px; font-size: 0.82rem; font-weight: 500; cursor: pointer; border: none; transition: all 0.15s; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.9; }
.btn-ghost { background: transparent; border: 1px solid var(--border-default); color: var(--text-secondary); }
.btn-ghost:hover:not(:disabled) { background: var(--bg-tertiary); color: var(--text-primary); }
.btn-danger:hover:not(:disabled) { border-color: #f87171; color: #f87171; }
.btn-xs { padding: 4px 10px; font-size: 0.78rem; }
.btn-icon { padding: 4px 8px; }

/* Editor overlay */
.overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 100; display: flex; justify-content: flex-end; }
.slide-panel { width: 480px; max-width: 100%; background: var(--bg-secondary); display: flex; flex-direction: column; height: 100%; overflow: hidden; }
.panel-header { display: flex; align-items: center; justify-content: space-between; padding: 20px 24px; border-bottom: 1px solid var(--border-default); }
.panel-title { font-size: 1rem; font-weight: 700; color: var(--text-primary); margin: 0; }
.close-btn { background: none; border: none; color: var(--text-secondary); cursor: pointer; font-size: 1rem; }
.close-btn:hover { color: var(--text-primary); }

.panel-body { flex: 1; overflow-y: auto; padding: 24px; display: flex; flex-direction: column; gap: 20px; }
.panel-footer { padding: 16px 24px; border-top: 1px solid var(--border-default); display: flex; justify-content: flex-end; gap: 10px; }

.field { display: flex; flex-direction: column; gap: 8px; }
.field-header { display: flex; align-items: center; justify-content: space-between; }
.field-label { font-size: 0.78rem; font-weight: 500; color: var(--text-secondary); }
.input { padding: 9px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 7px; color: var(--text-primary); font-size: 0.875rem; }
.input:focus { outline: none; border-color: var(--accent-cyan); }
.input-sm { padding: 6px 10px; font-size: 0.82rem; }
.select { padding: 7px 10px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 7px; color: var(--text-primary); font-size: 0.82rem; }
.select-sm { font-size: 0.78rem; padding: 5px 8px; }

.conditions-editor, .channels-editor { display: flex; flex-direction: column; gap: 8px; }
.condition-row, .channel-row { display: flex; align-items: center; gap: 8px; }
.condition-row .select, .channel-row .select { flex-shrink: 0; }
.condition-row .input, .channel-row .input { flex: 1; }

.empty-state { text-align: center; padding: 60px 20px; color: var(--text-secondary); }
.empty-icon { font-size: 2.5rem; margin-bottom: 12px; }
.empty-state p { margin-bottom: 16px; }
</style>
