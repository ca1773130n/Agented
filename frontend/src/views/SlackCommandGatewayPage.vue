<script setup lang="ts">
import { ref } from 'vue';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';

const showToast = useToast();

interface SlashCommand {
  id: string;
  command: string;
  description: string;
  botId: string;
  botName: string;
  enabled: boolean;
  usageCount: number;
}

interface CommandLog {
  id: string;
  user: string;
  channel: string;
  command: string;
  args: string;
  status: 'success' | 'running' | 'failed';
  timestamp: string;
  executionId?: string;
}

const slackConnected = ref(true);
const workspace = ref('engineering-team.slack.com');

const commands = ref<SlashCommand[]>([
  {
    id: 'cmd-1',
    command: '/agented run pr-review',
    description: 'Trigger PR review bot on a pull request number',
    botId: 'bot-pr-review',
    botName: 'PR Review Bot',
    enabled: true,
    usageCount: 142,
  },
  {
    id: 'cmd-2',
    command: '/agented run security-scan',
    description: 'Run the weekly security audit bot immediately',
    botId: 'bot-security',
    botName: 'Security Audit Bot',
    enabled: true,
    usageCount: 37,
  },
  {
    id: 'cmd-3',
    command: '/agented status',
    description: 'Show running executions and recent results',
    botId: 'bot-internal',
    botName: 'Status Reporter',
    enabled: true,
    usageCount: 289,
  },
  {
    id: 'cmd-4',
    command: '/agented run changelog',
    description: 'Generate changelog from recent merged PRs',
    botId: 'bot-changelog',
    botName: 'Changelog Generator',
    enabled: false,
    usageCount: 8,
  },
]);

const logs = ref<CommandLog[]>([
  {
    id: 'log-1',
    user: 'alice',
    channel: '#backend',
    command: '/agented run pr-review',
    args: '#312',
    status: 'success',
    timestamp: '2026-03-06T14:31:00Z',
    executionId: 'exec-abc123',
  },
  {
    id: 'log-2',
    user: 'bob',
    channel: '#security',
    command: '/agented run security-scan',
    args: '',
    status: 'running',
    timestamp: '2026-03-06T14:28:00Z',
    executionId: 'exec-def456',
  },
  {
    id: 'log-3',
    user: 'carol',
    channel: '#releases',
    command: '/agented run changelog',
    args: '--since=2026-03-01',
    status: 'failed',
    timestamp: '2026-03-06T13:10:00Z',
  },
]);

const showAddCommand = ref(false);
const newCommand = ref('');
const newDescription = ref('');

function toggleCommand(id: string) {
  const cmd = commands.value.find((c) => c.id === id);
  if (cmd) {
    cmd.enabled = !cmd.enabled;
    showToast(`Command ${cmd.enabled ? 'enabled' : 'disabled'}`, 'success');
  }
}

function addCommand() {
  if (!newCommand.value || !newDescription.value) return;
  commands.value.push({
    id: `cmd-${Date.now()}`,
    command: newCommand.value,
    description: newDescription.value,
    botId: '',
    botName: 'Unassigned',
    enabled: false,
    usageCount: 0,
  });
  newCommand.value = '';
  newDescription.value = '';
  showAddCommand.value = false;
  showToast('Command registered', 'success');
}

function statusColor(status: string) {
  if (status === 'success') return 'var(--color-success)';
  if (status === 'running') return 'var(--color-warning)';
  return 'var(--color-error)';
}

function formatTime(ts: string) {
  return new Date(ts).toLocaleString();
}
</script>

<template>
  <div class="slack-gateway">
    <AppBreadcrumb :items="[{ label: 'Integrations' }, { label: 'Slack Command Gateway' }]" />
    <PageHeader
      title="Slack Command Gateway"
      subtitle="Trigger bots directly from Slack with slash commands — results stream back as threaded replies"
    />

    <div class="page-content">
      <section class="section connection-card">
        <div class="connection-header">
          <div class="conn-status" :class="{ connected: slackConnected }">
            <span class="status-dot" />
            {{ slackConnected ? 'Connected' : 'Disconnected' }}
          </div>
          <span class="workspace-label">{{ workspace }}</span>
          <button class="btn-secondary" @click="showToast('Reconnecting...', 'info')">
            Reconnect
          </button>
        </div>
        <p class="help-text">
          Add the Agented Slack app to your workspace, then configure a slash command pointing to
          <code>/api/slack/command</code>.
        </p>
      </section>

      <section class="section">
        <div class="section-header">
          <h2 class="section-title">Registered Commands</h2>
          <button class="btn-primary" @click="showAddCommand = !showAddCommand">
            + Add Command
          </button>
        </div>

        <div v-if="showAddCommand" class="add-form">
          <input v-model="newCommand" placeholder="/agented run my-bot" class="input" />
          <input v-model="newDescription" placeholder="What does this command do?" class="input" />
          <div class="form-actions">
            <button class="btn-primary" @click="addCommand">Save</button>
            <button class="btn-ghost" @click="showAddCommand = false">Cancel</button>
          </div>
        </div>

        <div class="commands-list">
          <div v-for="cmd in commands" :key="cmd.id" class="command-card">
            <div class="command-main">
              <code class="command-text">{{ cmd.command }}</code>
              <p class="command-desc">{{ cmd.description }}</p>
              <span class="bot-badge">{{ cmd.botName }}</span>
            </div>
            <div class="command-meta">
              <span class="usage-count">{{ cmd.usageCount }} uses</span>
              <button
                class="toggle-btn"
                :class="{ active: cmd.enabled }"
                @click="toggleCommand(cmd.id)"
              >
                {{ cmd.enabled ? 'Enabled' : 'Disabled' }}
              </button>
            </div>
          </div>
        </div>
      </section>

      <section class="section">
        <h2 class="section-title">Command Logs</h2>
        <table class="log-table">
          <thead>
            <tr>
              <th>User</th>
              <th>Channel</th>
              <th>Command</th>
              <th>Args</th>
              <th>Status</th>
              <th>Time</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="log in logs" :key="log.id">
              <td>@{{ log.user }}</td>
              <td>{{ log.channel }}</td>
              <td><code>{{ log.command }}</code></td>
              <td><code>{{ log.args || '—' }}</code></td>
              <td>
                <span class="status-pill" :style="{ color: statusColor(log.status) }">
                  {{ log.status }}
                </span>
              </td>
              <td class="ts">{{ formatTime(log.timestamp) }}</td>
            </tr>
          </tbody>
        </table>
      </section>
    </div>
  </div>
</template>

<style scoped>
.slack-gateway {
  max-width: 960px;
  margin: 0 auto;
  padding: 0 1.5rem 3rem;
}

.page-content {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.section {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 1.25rem;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
}

.section-title {
  font-size: 1rem;
  font-weight: 600;
  margin: 0 0 1rem;
}

.connection-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 0.75rem;
  flex-wrap: wrap;
}

.conn-status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 600;
  font-size: 0.875rem;
  color: var(--color-error);
}

.conn-status.connected {
  color: var(--color-success);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
}

.workspace-label {
  font-size: 0.85rem;
  color: var(--color-text-muted);
  flex: 1;
}

.help-text {
  font-size: 0.8rem;
  color: var(--color-text-muted);
  margin: 0;
}

.help-text code {
  background: var(--color-bg);
  padding: 0.1rem 0.4rem;
  border-radius: 3px;
}

.add-form {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin-bottom: 1rem;
  padding: 1rem;
  background: var(--color-bg);
  border-radius: 6px;
}

.form-actions {
  display: flex;
  gap: 0.5rem;
}

.commands-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.command-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.875rem;
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  gap: 1rem;
  flex-wrap: wrap;
}

.command-main {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  flex: 1;
}

.command-text {
  font-size: 0.9rem;
  font-family: monospace;
  color: var(--color-primary);
}

.command-desc {
  font-size: 0.8rem;
  color: var(--color-text-muted);
  margin: 0;
}

.bot-badge {
  display: inline-block;
  font-size: 0.75rem;
  background: color-mix(in srgb, var(--color-primary) 12%, transparent);
  color: var(--color-primary);
  padding: 0.15rem 0.5rem;
  border-radius: 10px;
  width: fit-content;
}

.command-meta {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.usage-count {
  font-size: 0.8rem;
  color: var(--color-text-muted);
}

.toggle-btn {
  padding: 0.3rem 0.75rem;
  border-radius: 4px;
  border: 1px solid var(--color-border);
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  font-size: 0.8rem;
}

.toggle-btn.active {
  background: var(--color-primary);
  color: white;
  border-color: var(--color-primary);
}

.log-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8rem;
}

.log-table th,
.log-table td {
  padding: 0.55rem 0.75rem;
  text-align: left;
  border-bottom: 1px solid var(--color-border);
}

.log-table th {
  color: var(--color-text-muted);
  font-weight: 500;
}

.log-table code {
  font-family: monospace;
  font-size: 0.8rem;
}

.status-pill {
  font-weight: 600;
  font-size: 0.75rem;
}

.ts {
  color: var(--color-text-muted);
}

.input {
  padding: 0.5rem 0.75rem;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  color: var(--color-text);
  font-size: 0.875rem;
}

.btn-primary {
  padding: 0.5rem 1rem;
  background: var(--color-primary);
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.875rem;
}

.btn-primary:hover { opacity: 0.9; }

.btn-secondary {
  padding: 0.4rem 0.875rem;
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  color: var(--color-text);
  cursor: pointer;
  font-size: 0.8rem;
}

.btn-ghost {
  padding: 0.5rem 1rem;
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  color: var(--color-text);
  cursor: pointer;
  font-size: 0.875rem;
}
</style>
