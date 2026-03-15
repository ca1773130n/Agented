<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import PageHeader from '../components/base/PageHeader.vue';
import { pluginApi, ApiError } from '../services/api';
import type { Plugin } from '../services/api';

const router = useRouter();

type TabId = 'init' | 'develop' | 'test' | 'publish';

interface Tab {
  id: TabId;
  label: string;
  command: string;
  description: string;
}

interface DisplayPlugin {
  id: string;
  name: string;
  version: string;
  description: string;
  triggers: string[];
  status: 'idle' | 'running' | 'done' | 'error';
}

interface LogLine {
  time: string;
  level: 'info' | 'warn' | 'error' | 'success';
  message: string;
}

const isLoading = ref(true);
const loadError = ref<string | null>(null);

const tabs = ref<Tab[]>([
  {
    id: 'init',
    label: 'Init',
    command: 'agented-sdk init my-plugin\ncd my-plugin',
    description: 'Scaffold a new plugin project with the recommended directory structure and a sample manifest.',
  },
  {
    id: 'develop',
    label: 'Develop',
    command: 'agented-sdk dev\n# Hot-reloads on file changes — plugin is live at http://localhost:4200',
    description: 'Start the local dev server. Your plugin hooks are served and invoked just like in production.',
  },
  {
    id: 'test',
    label: 'Test',
    command: 'agented-sdk test\nagented-sdk test --hook on_execution_complete\nagented-sdk test --coverage',
    description: 'Run your plugin\'s test suite. Use --hook to target a specific lifecycle hook, or --coverage for a full report.',
  },
  {
    id: 'publish',
    label: 'Publish',
    command: 'agented-sdk build\nagented-sdk publish --org my-org',
    description: 'Bundle the plugin and publish it to your Agented organisation. Requires an API key set in AGENTED_API_KEY.',
  },
]);

const activeTab = ref<TabId>('init');

const displayPlugins = ref<DisplayPlugin[]>([]);

function pluginToDisplay(p: Plugin): DisplayPlugin {
  return {
    id: p.id,
    name: p.name,
    version: p.version || '0.0.0',
    description: p.description || 'No description',
    triggers: ['on_execution_complete'],
    status: 'idle',
  };
}

async function loadPlugins() {
  isLoading.value = true;
  loadError.value = null;
  try {
    const { plugins } = await pluginApi.list();
    if (plugins.length > 0) {
      displayPlugins.value = plugins.map(pluginToDisplay);
    } else {
      // Provide SDK example plugins when none exist
      displayPlugins.value = [
        { id: 'example-1', name: 'slack-notifier', version: '0.3.1', description: 'Example: Posts a Slack message whenever a bot execution completes or fails.', triggers: ['on_execution_complete', 'on_execution_error'], status: 'idle' },
        { id: 'example-2', name: 'jira-linker', version: '1.0.0', description: 'Example: Automatically creates or updates a Jira ticket from security findings.', triggers: ['on_finding_created'], status: 'idle' },
      ];
    }
  } catch (err) {
    const msg = err instanceof ApiError ? err.message : 'Failed to load plugins';
    loadError.value = msg;
    // Fall back to examples on error
    displayPlugins.value = [
      { id: 'example-1', name: 'slack-notifier', version: '0.3.1', description: 'Example: Posts a Slack message whenever a bot execution completes or fails.', triggers: ['on_execution_complete', 'on_execution_error'], status: 'idle' },
    ];
  } finally {
    isLoading.value = false;
  }
}

onMounted(loadPlugins);

const logLines = ref<LogLine[]>([]);
const runningPlugin = ref<string | null>(null);
const copied = ref(false);

async function runPlugin(plugin: DisplayPlugin) {
  if (runningPlugin.value) return;
  runningPlugin.value = plugin.id;
  plugin.status = 'running';
  logLines.value = [];

  try {
    // Load plugin details from API to show real data
    logLines.value.push({ time: '00:00.001', level: 'info', message: `Booting local runner for ${plugin.name}@${plugin.version}` });

    let pluginDetails: Plugin | null = null;
    if (!plugin.id.startsWith('example-')) {
      try {
        pluginDetails = await pluginApi.get(plugin.id);
        logLines.value.push({ time: '00:00.030', level: 'info', message: `Loaded plugin: ${pluginDetails.name} (${pluginDetails.status || 'active'})` });
      } catch {
        logLines.value.push({ time: '00:00.030', level: 'warn', message: 'Could not fetch plugin details from API' });
      }

      // Load components
      try {
        const { components } = await pluginApi.listComponents(plugin.id);
        logLines.value.push({ time: '00:00.060', level: 'info', message: `Found ${components.length} component(s)` });
        for (const comp of components) {
          logLines.value.push({ time: '00:00.065', level: 'info', message: `  - ${comp.type}: ${comp.name}` });
        }
      } catch {
        logLines.value.push({ time: '00:00.060', level: 'warn', message: 'No components found' });
      }
    } else {
      logLines.value.push({ time: '00:00.030', level: 'info', message: 'Loading manifest: agented.plugin.json' });
    }

    for (const trigger of plugin.triggers) {
      logLines.value.push({ time: '00:00.080', level: 'info', message: `Registered hook: ${trigger}` });
    }

    logLines.value.push({ time: '00:00.100', level: 'info', message: `Simulating trigger: ${plugin.triggers[0]}` });
    logLines.value.push({ time: '00:00.120', level: 'info', message: 'Hook invoked with mock payload' });
    logLines.value.push({ time: '00:00.250', level: 'success', message: `Plugin run complete for ${plugin.name}` });

    plugin.status = 'done';
  } catch {
    logLines.value.push({ time: '00:00.500', level: 'error', message: 'Plugin run finished with errors' });
    plugin.status = 'error';
  } finally {
    runningPlugin.value = null;
  }
}

function getActiveTab(): Tab {
  return tabs.value.find(t => t.id === activeTab.value) ?? tabs.value[0];
}

async function copyInstall() {
  try {
    await navigator.clipboard.writeText('npm install -g @agented/plugin-sdk');
    copied.value = true;
    setTimeout(() => { copied.value = false; }, 2000);
  } catch {
    // clipboard not available in all environments
  }
}

const manifestFields = [
  { field: 'name', type: 'string', required: true, description: 'Unique plugin identifier (kebab-case)' },
  { field: 'version', type: 'string', required: true, description: 'Semantic version, e.g. "1.0.0"' },
  { field: 'description', type: 'string', required: true, description: 'Short human-readable description' },
  { field: 'triggers', type: 'string[]', required: true, description: 'Lifecycle hooks the plugin subscribes to' },
  { field: 'hooks', type: 'object', required: true, description: 'Map of hook names to handler file paths' },
  { field: 'permissions', type: 'string[]', required: false, description: 'Scopes required: executions:read, bots:write, …' },
  { field: 'config', type: 'object', required: false, description: 'User-configurable settings schema (JSON Schema)' },
];
</script>

<template>
  <div class="plugin-sdk">

    <PageHeader
      title="Plugin SDK & CLI"
      subtitle="Build, test, and publish custom plugins for Agented — locally before going live."
    />

    <!-- Installation -->
    <div class="card">
      <div class="card-header">
        <h3>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="7 10 12 15 17 10"/>
            <line x1="12" y1="15" x2="12" y2="3"/>
          </svg>
          Installation
        </h3>
        <span class="badge-info">npm · yarn · pnpm</span>
      </div>
      <div class="install-body">
        <p class="install-desc">Install the Agented Plugin SDK globally to get the <code>agented-sdk</code> CLI.</p>
        <div class="code-block">
          <pre class="code-pre"><span class="code-prompt">$</span> npm install -g @agented/plugin-sdk</pre>
          <button class="btn btn-ghost-sm copy-btn" @click="copyInstall">
            <svg v-if="!copied" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
            </svg>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14" style="color: #34d399">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
            {{ copied ? 'Copied!' : 'Copy' }}
          </button>
        </div>
        <p class="install-note">Requires Node.js 18+. Use <code>agented-sdk --version</code> to confirm the install.</p>
      </div>
    </div>

    <!-- Quick Start -->
    <div class="card">
      <div class="card-header">
        <h3>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
            <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
          </svg>
          Quick Start
        </h3>
      </div>
      <div class="tabs-nav">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          class="tab-btn"
          :class="{ active: activeTab === tab.id }"
          @click="activeTab = tab.id"
        >
          {{ tab.label }}
        </button>
      </div>
      <div class="tab-body">
        <p class="tab-desc">{{ getActiveTab().description }}</p>
        <div class="code-block">
          <pre class="code-pre"><template v-for="(line, i) in getActiveTab().command.split('\n')" :key="i"><span v-if="!line.startsWith('#')" class="code-prompt">$</span><span v-else class="code-comment">&nbsp;</span>{{ line }}
</template></pre>
        </div>
      </div>
    </div>

    <!-- Local Runner -->
    <div class="card">
      <div class="card-header">
        <h3>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
            <circle cx="12" cy="12" r="10"/>
            <polygon points="10 8 16 12 10 16 10 8"/>
          </svg>
          Local Runner
        </h3>
        <span class="badge-info">Simulated environment</span>
      </div>

      <div v-if="isLoading" style="padding: 32px; text-align: center; color: var(--text-tertiary);">
        Loading plugins...
      </div>
      <div v-else-if="loadError" style="padding: 32px; text-align: center; color: #ef4444;">
        {{ loadError }}
        <button class="btn btn-run" style="margin-top: 12px;" @click="loadPlugins">Retry</button>
      </div>
      <div v-else-if="displayPlugins.length === 0" style="padding: 32px; text-align: center; color: var(--text-tertiary);">
        No plugins found. Create a plugin to see it here.
      </div>
      <div v-else class="runner-layout">
        <div class="plugin-list">
          <div
            v-for="plugin in displayPlugins"
            :key="plugin.id"
            class="plugin-row"
            :class="{ 'is-running': runningPlugin === plugin.id }"
          >
            <div class="plugin-info">
              <div class="plugin-name">
                {{ plugin.name }}
                <span class="plugin-version">v{{ plugin.version }}</span>
              </div>
              <div class="plugin-desc">{{ plugin.description }}</div>
              <div class="plugin-triggers">
                <span v-for="t in plugin.triggers" :key="t" class="trigger-tag">{{ t }}</span>
              </div>
            </div>
            <div class="plugin-controls">
              <span v-if="plugin.status === 'done'" class="run-status status-done">Done</span>
              <span v-else-if="plugin.status === 'error'" class="run-status status-error">Error</span>
              <span v-else-if="plugin.status === 'running'" class="run-status status-running">Running…</span>
              <button
                class="btn btn-run"
                :disabled="!!runningPlugin"
                @click="runPlugin(plugin)"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13">
                  <polygon points="5 3 19 12 5 21 5 3"/>
                </svg>
                Run Locally
              </button>
            </div>
          </div>
        </div>

        <div class="log-panel">
          <div class="log-header">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14" style="color: var(--accent-cyan)">
              <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
            </svg>
            Simulated Output
          </div>
          <div class="log-body">
            <div v-if="logLines.length === 0" class="log-empty">
              Select a plugin and click "Run Locally" to see simulated output here.
            </div>
            <div
              v-for="(line, idx) in logLines"
              :key="idx"
              class="log-line"
              :class="`log-${line.level}`"
            >
              <span class="log-time">{{ line.time }}</span>
              <span class="log-level">{{ line.level.toUpperCase() }}</span>
              <span class="log-msg">{{ line.message }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Manifest Schema Reference -->
    <div class="card">
      <div class="card-header">
        <h3>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
            <line x1="16" y1="13" x2="8" y2="13"/>
            <line x1="16" y1="17" x2="8" y2="17"/>
            <polyline points="10 9 9 9 8 9"/>
          </svg>
          Plugin Manifest Schema
        </h3>
        <code class="badge-code">agented.plugin.json</code>
      </div>
      <div class="schema-body">
        <p class="schema-intro">
          Every plugin must include an <code>agented.plugin.json</code> manifest at the project root.
          Required fields are marked with <span class="req-mark">*</span>.
        </p>
        <div class="schema-table">
          <div class="schema-row schema-heading">
            <span>Field</span>
            <span>Type</span>
            <span>Description</span>
          </div>
          <div
            v-for="f in manifestFields"
            :key="f.field"
            class="schema-row"
          >
            <span class="schema-field">
              <code>{{ f.field }}</code>
              <span v-if="f.required" class="req-mark">*</span>
            </span>
            <span class="schema-type">{{ f.type }}</span>
            <span class="schema-desc">{{ f.description }}</span>
          </div>
        </div>

        <div class="manifest-example">
          <div class="example-label">Example manifest</div>
          <pre class="code-pre code-json">{
  "name": "my-plugin",
  "version": "1.0.0",
  "description": "Does something useful.",
  "triggers": ["on_execution_complete"],
  "hooks": {
    "on_execution_complete": "./hooks/on-complete.js"
  },
  "permissions": ["executions:read"],
  "config": {
    "WEBHOOK_URL": { "type": "string", "required": true }
  }
}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.plugin-sdk {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-default);
}

.card-header h3 {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.card-header h3 svg { color: var(--accent-cyan); }

.badge-info {
  font-size: 0.7rem;
  font-weight: 600;
  padding: 3px 10px;
  background: rgba(6, 182, 212, 0.12);
  color: var(--accent-cyan);
  border-radius: 4px;
}

.badge-code {
  font-size: 0.72rem;
  padding: 3px 10px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 4px;
  color: var(--text-secondary);
  font-family: 'Geist Mono', monospace;
}

/* Installation */
.install-body {
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.install-desc {
  font-size: 0.875rem;
  color: var(--text-secondary);
  margin: 0;
}

.install-note {
  font-size: 0.8rem;
  color: var(--text-tertiary);
  margin: 0;
}

/* Code blocks */
.code-block {
  position: relative;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  overflow: hidden;
}

.code-pre {
  margin: 0;
  padding: 14px 48px 14px 16px;
  font-size: 0.82rem;
  font-family: 'Geist Mono', monospace;
  color: var(--text-primary);
  white-space: pre;
  overflow-x: auto;
  line-height: 1.7;
}

.code-prompt {
  color: var(--accent-cyan);
  margin-right: 8px;
  user-select: none;
}

.code-comment {
  display: inline-block;
  width: 16px;
}

.code-pre .code-comment + * {
  color: var(--text-tertiary);
}

.copy-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  padding: 4px 10px;
  font-size: 0.75rem;
}

/* Tabs */
.tabs-nav {
  display: flex;
  border-bottom: 1px solid var(--border-default);
  padding: 0 24px;
  gap: 2px;
}

.tab-btn {
  padding: 10px 16px;
  font-size: 0.82rem;
  font-weight: 500;
  color: var(--text-tertiary);
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s;
  margin-bottom: -1px;
}

.tab-btn:hover { color: var(--text-primary); }

.tab-btn.active {
  color: var(--accent-cyan);
  border-bottom-color: var(--accent-cyan);
}

.tab-body {
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.tab-desc {
  font-size: 0.875rem;
  color: var(--text-secondary);
  margin: 0;
}

/* Local Runner */
.runner-layout {
  display: grid;
  grid-template-columns: 1fr 1fr;
  min-height: 280px;
}

@media (max-width: 800px) {
  .runner-layout { grid-template-columns: 1fr; }
}

.plugin-list {
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--border-default);
}

.plugin-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-subtle);
  transition: background 0.1s;
}

.plugin-row:last-child { border-bottom: none; }
.plugin-row:hover { background: var(--bg-tertiary); }
.plugin-row.is-running { background: rgba(6, 182, 212, 0.04); }

.plugin-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  min-width: 0;
}

.plugin-name {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 6px;
}

.plugin-version {
  font-size: 0.7rem;
  color: var(--text-tertiary);
  font-family: 'Geist Mono', monospace;
  font-weight: 400;
}

.plugin-desc {
  font-size: 0.8rem;
  color: var(--text-secondary);
  line-height: 1.4;
}

.plugin-triggers {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 2px;
}

.trigger-tag {
  font-size: 0.68rem;
  padding: 2px 7px;
  background: rgba(6, 182, 212, 0.1);
  color: var(--accent-cyan);
  border-radius: 3px;
  font-family: 'Geist Mono', monospace;
}

.plugin-controls {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
  flex-shrink: 0;
}

.run-status {
  font-size: 0.68rem;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 3px;
  text-transform: uppercase;
}

.status-done { background: rgba(52, 211, 153, 0.15); color: #34d399; }
.status-error { background: rgba(239, 68, 68, 0.15); color: #ef4444; }
.status-running { background: rgba(6, 182, 212, 0.12); color: var(--accent-cyan); }

.log-panel {
  display: flex;
  flex-direction: column;
  min-height: 280px;
}

.log-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-subtle);
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.log-body {
  flex: 1;
  overflow-y: auto;
  padding: 10px 0;
  font-family: 'Geist Mono', monospace;
  font-size: 0.78rem;
}

.log-empty {
  padding: 32px 20px;
  text-align: center;
  color: var(--text-muted);
  font-family: inherit;
  font-size: 0.82rem;
}

.log-line {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 2px 16px;
  line-height: 1.6;
}

.log-line:hover { background: var(--bg-tertiary); }

.log-time {
  color: var(--text-muted);
  flex-shrink: 0;
  font-size: 0.72rem;
}

.log-level {
  flex-shrink: 0;
  font-size: 0.65rem;
  font-weight: 700;
  width: 52px;
  text-align: center;
  padding: 1px 0;
  border-radius: 2px;
}

.log-info .log-level { color: var(--text-tertiary); }
.log-warn .log-level { color: #f59e0b; }
.log-error .log-level { color: #ef4444; }
.log-success .log-level { color: #34d399; }

.log-msg { color: var(--text-secondary); }
.log-warn .log-msg { color: #fbbf24; }
.log-error .log-msg { color: #fca5a5; }
.log-success .log-msg { color: #6ee7b7; }

/* Manifest Schema */
.schema-body {
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.schema-intro {
  font-size: 0.875rem;
  color: var(--text-secondary);
  margin: 0;
}

.schema-intro code {
  font-size: 0.82rem;
  background: var(--bg-tertiary);
  padding: 1px 6px;
  border-radius: 4px;
  font-family: 'Geist Mono', monospace;
  color: var(--accent-cyan);
}

.req-mark {
  color: #f87171;
  font-weight: 700;
  margin-left: 2px;
}

.schema-table {
  border: 1px solid var(--border-default);
  border-radius: 8px;
  overflow: hidden;
}

.schema-row {
  display: grid;
  grid-template-columns: 180px 110px 1fr;
  gap: 12px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border-subtle);
  font-size: 0.84rem;
  align-items: center;
}

.schema-row:last-child { border-bottom: none; }

.schema-heading {
  background: var(--bg-tertiary);
  font-size: 0.72rem;
  font-weight: 700;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.schema-field {
  display: flex;
  align-items: center;
  gap: 4px;
}

.schema-field code {
  font-family: 'Geist Mono', monospace;
  font-size: 0.8rem;
  color: var(--text-primary);
}

.schema-type {
  font-family: 'Geist Mono', monospace;
  font-size: 0.78rem;
  color: var(--accent-cyan);
}

.schema-desc {
  color: var(--text-secondary);
  font-size: 0.82rem;
}

.manifest-example {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.example-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.code-json {
  padding: 16px;
  color: var(--text-secondary);
  line-height: 1.6;
}

/* Buttons */
.btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border-radius: 7px;
  font-size: 0.82rem;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}

.btn-primary {
  background: var(--accent-cyan);
  color: #000;
}

.btn-primary:hover { opacity: 0.85; }

.btn-run {
  background: rgba(6, 182, 212, 0.12);
  color: var(--accent-cyan);
  border: 1px solid rgba(6, 182, 212, 0.25);
  white-space: nowrap;
}

.btn-run:hover:not(:disabled) { background: rgba(6, 182, 212, 0.22); }

.btn-run:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.btn-ghost-sm {
  background: transparent;
  border: 1px solid var(--border-default);
  color: var(--text-tertiary);
  font-size: 0.78rem;
  cursor: pointer;
  padding: 5px 10px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  gap: 5px;
  transition: color 0.15s, border-color 0.15s;
}

.btn-ghost-sm:hover {
  color: var(--text-primary);
  border-color: var(--border-default);
}
</style>
