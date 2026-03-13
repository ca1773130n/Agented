<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import LoadingState from '../components/base/LoadingState.vue';
import { useToast } from '../composables/useToast';
import { integrationApi, ApiError } from '../services/api';
import type { Integration } from '../services/api';

const router = useRouter();
const showToast = useToast();

const isLoading = ref(true);
const error = ref('');

interface ForwardingRule {
  id: string;
  botName: string;
  targetUrl: string;
  enabled: boolean;
  events: string[];
  lastFiredAt: string | null;
  deliveryCount: number;
  failureCount: number;
}

const rules = ref<ForwardingRule[]>([]);

const isAdding = ref(false);
const newBotName = ref('');
const newTargetUrl = ref('');
const isTesting = ref<string | null>(null);
const isSaving = ref(false);

const eventOptions = [
  { value: 'execution_complete', label: 'Execution Complete' },
  { value: 'execution_failed', label: 'Execution Failed' },
  { value: 'execution_started', label: 'Execution Started' },
  { value: 'approval_required', label: 'Approval Required' },
];

function integrationToRule(i: Integration): ForwardingRule {
  const config = i.config ?? {};
  return {
    id: i.id,
    botName: i.name || i.trigger_id || 'Unknown',
    targetUrl: (config.target_url as string) ?? (config.url as string) ?? '',
    enabled: i.enabled,
    events: (config.events as string[]) ?? ['execution_complete'],
    lastFiredAt: (config.last_fired_at as string) ?? null,
    deliveryCount: (config.delivery_count as number) ?? 0,
    failureCount: (config.failure_count as number) ?? 0,
  };
}

async function loadRules() {
  isLoading.value = true;
  error.value = '';
  try {
    const integrations = await integrationApi.list();
    const list = Array.isArray(integrations) ? integrations : [];
    // Filter to webhook forwarding type
    rules.value = list
      .filter((i: Integration) => i.type === 'webhook_forward' || i.type === 'webhook')
      .map(integrationToRule);
  } catch (e) {
    if (e instanceof ApiError) {
      error.value = e.message;
    } else {
      error.value = 'Failed to load forwarding rules';
    }
    showToast(error.value, 'error');
  } finally {
    isLoading.value = false;
  }
}

function toggleEvent(rule: ForwardingRule, event: string) {
  const i = rule.events.indexOf(event);
  if (i === -1) rule.events.push(event);
  else rule.events.splice(i, 1);
}

async function testDelivery(rule: ForwardingRule) {
  isTesting.value = rule.id;
  try {
    const result = await integrationApi.test(rule.id);
    if (result.success) {
      showToast(`Test payload delivered to ${rule.targetUrl}`, 'success');
    } else {
      showToast(`Test failed: ${result.message}`, 'error');
    }
  } catch {
    showToast('Test delivery failed', 'error');
  } finally {
    isTesting.value = null;
  }
}

async function addRule() {
  if (!newBotName.value || !newTargetUrl.value) {
    showToast('Bot name and target URL are required', 'error');
    return;
  }
  isSaving.value = true;
  try {
    await integrationApi.create({
      name: newBotName.value,
      type: 'webhook_forward',
      enabled: true,
      config: {
        target_url: newTargetUrl.value,
        events: ['execution_complete'],
      },
    });
    newBotName.value = '';
    newTargetUrl.value = '';
    isAdding.value = false;
    showToast('Forwarding rule added', 'success');
    await loadRules();
  } catch {
    showToast('Failed to add forwarding rule', 'error');
  } finally {
    isSaving.value = false;
  }
}

async function removeRule(rule: ForwardingRule) {
  try {
    await integrationApi.delete(rule.id);
    rules.value = rules.value.filter(r => r.id !== rule.id);
    showToast('Forwarding rule removed', 'success');
  } catch {
    showToast('Failed to remove forwarding rule', 'error');
  }
}

function formatDate(ts: string | null) {
  if (!ts) return 'Never';
  return new Date(ts).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

onMounted(loadRules);
</script>

<template>
  <div class="webhook-fwd">
    <AppBreadcrumb :items="[
      { label: 'Integrations', action: () => router.push({ name: 'triggers' }) },
      { label: 'Webhook Output Forwarding' },
    ]" />

    <PageHeader
      title="Bot Output Webhook Forwarding"
      subtitle="POST structured bot execution output to external URLs when runs complete — integrate with any system."
    />

    <LoadingState v-if="isLoading" message="Loading forwarding rules..." />

    <div v-else-if="error" class="card error-state">
      <p class="error-text">{{ error }}</p>
      <button class="btn btn-primary" @click="loadRules">Retry</button>
    </div>

    <template v-else>
      <div class="page-actions">
        <button class="btn btn-primary" @click="isAdding = !isAdding">
          {{ isAdding ? 'Cancel' : '+ Add Forwarding Rule' }}
        </button>
      </div>

      <div v-if="isAdding" class="card add-card">
        <div class="add-header">New Forwarding Rule</div>
        <div class="add-body">
          <div class="field-group">
            <label class="field-label">Bot Name</label>
            <input v-model="newBotName" class="text-input" placeholder="bot-security" />
          </div>
          <div class="field-group">
            <label class="field-label">Target URL</label>
            <input v-model="newTargetUrl" class="text-input" placeholder="https://hooks.example.com/endpoint" />
          </div>
          <div class="add-actions">
            <button class="btn btn-primary" :disabled="isSaving" @click="addRule">
              {{ isSaving ? 'Adding...' : 'Add Rule' }}
            </button>
          </div>
        </div>
      </div>

      <div class="rules-list">
        <div v-for="rule in rules" :key="rule.id" class="rule-card card">
          <div class="rule-header">
            <div class="rule-left">
              <button :class="['toggle-btn', { active: rule.enabled }]" @click="rule.enabled = !rule.enabled">
                <span class="toggle-knob"></span>
              </button>
              <div>
                <div class="rule-bot">{{ rule.botName }}</div>
                <div class="rule-url">{{ rule.targetUrl }}</div>
              </div>
            </div>
            <div class="rule-stats">
              <span class="stat"><span class="stat-num">{{ rule.deliveryCount }}</span> delivered</span>
              <span v-if="rule.failureCount > 0" class="stat stat-fail"><span class="stat-num">{{ rule.failureCount }}</span> failed</span>
              <span class="stat last-fired">Last: {{ formatDate(rule.lastFiredAt) }}</span>
            </div>
          </div>

          <div class="rule-events">
            <span class="events-label">Events:</span>
            <label v-for="opt in eventOptions" :key="opt.value" class="event-check">
              <input
                type="checkbox"
                :checked="rule.events.includes(opt.value)"
                @change="toggleEvent(rule, opt.value)"
              />
              {{ opt.label }}
            </label>
          </div>

          <div class="rule-footer">
            <button
              class="btn btn-ghost btn-sm"
              :disabled="isTesting === rule.id"
              @click="testDelivery(rule)"
            >
              {{ isTesting === rule.id ? 'Sending...' : 'Test Delivery' }}
            </button>
            <button class="btn btn-danger btn-sm" @click="removeRule(rule)">Remove</button>
          </div>
        </div>

        <div v-if="rules.length === 0" class="empty-state card">
          <p>No forwarding rules configured. Add one to start forwarding bot output.</p>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.webhook-fwd { display: flex; flex-direction: column; gap: 24px; animation: fadeIn 0.4s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

.error-state { padding: 32px 24px; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 12px; }
.error-text { font-size: 0.875rem; color: #ef4444; margin: 0; }

.page-actions { display: flex; justify-content: flex-end; }

.card { background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 12px; overflow: hidden; }

.add-header { padding: 14px 20px; border-bottom: 1px solid var(--border-default); font-size: 0.82rem; font-weight: 600; color: var(--text-secondary); }
.add-body { padding: 20px; display: flex; flex-direction: column; gap: 14px; }
.field-group { display: flex; flex-direction: column; gap: 6px; }
.field-label { font-size: 0.75rem; color: var(--text-tertiary); font-weight: 500; }
.text-input { padding: 8px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 7px; color: var(--text-primary); font-size: 0.85rem; }
.text-input:focus { outline: none; border-color: var(--accent-cyan); }
.add-actions { display: flex; justify-content: flex-end; }

.rules-list { display: flex; flex-direction: column; gap: 12px; }

.rule-card { }
.rule-header { display: flex; align-items: flex-start; justify-content: space-between; padding: 16px 20px; border-bottom: 1px solid var(--border-subtle); }
.rule-left { display: flex; align-items: flex-start; gap: 12px; }

.toggle-btn { width: 36px; height: 20px; border-radius: 10px; background: var(--bg-tertiary); border: 1px solid var(--border-default); cursor: pointer; position: relative; flex-shrink: 0; padding: 0; margin-top: 2px; transition: background 0.2s; }
.toggle-btn.active { background: var(--accent-cyan); border-color: var(--accent-cyan); }
.toggle-knob { position: absolute; top: 2px; left: 2px; width: 14px; height: 14px; border-radius: 50%; background: #fff; transition: left 0.2s; }
.toggle-btn.active .toggle-knob { left: 18px; }

.rule-bot { font-size: 0.88rem; font-weight: 600; color: var(--text-primary); margin-bottom: 3px; }
.rule-url { font-size: 0.75rem; color: var(--text-muted); font-family: monospace; word-break: break-all; }

.rule-stats { display: flex; align-items: center; gap: 14px; flex-shrink: 0; }
.stat { font-size: 0.75rem; color: var(--text-tertiary); }
.stat-num { font-weight: 600; color: var(--text-primary); }
.stat-fail .stat-num { color: #ef4444; }
.last-fired { font-size: 0.7rem; }

.rule-events { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; padding: 12px 20px; border-bottom: 1px solid var(--border-subtle); }
.events-label { font-size: 0.72rem; color: var(--text-tertiary); font-weight: 500; }
.event-check { display: flex; align-items: center; gap: 6px; font-size: 0.78rem; color: var(--text-secondary); cursor: pointer; }
.event-check input { accent-color: var(--accent-cyan); cursor: pointer; }

.rule-footer { display: flex; gap: 10px; padding: 12px 20px; }

.empty-state { padding: 48px 24px; text-align: center; }
.empty-state p { font-size: 0.875rem; color: var(--text-tertiary); margin: 0; }

.btn { display: flex; align-items: center; padding: 8px 16px; border-radius: 7px; font-size: 0.82rem; font-weight: 500; cursor: pointer; border: none; transition: all 0.15s; }
.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-ghost { background: var(--bg-tertiary); border: 1px solid var(--border-default); color: var(--text-secondary); }
.btn-ghost:hover:not(:disabled) { border-color: var(--accent-cyan); color: var(--accent-cyan); }
.btn-ghost:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-danger { background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3); color: #ef4444; }
.btn-danger:hover { background: rgba(239,68,68,0.2); }
.btn-sm { padding: 5px 12px; font-size: 0.75rem; }
</style>
