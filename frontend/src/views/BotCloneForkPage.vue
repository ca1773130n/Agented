<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';

const router = useRouter();
const showToast = useToast();

interface Bot {
  id: string;
  name: string;
  trigger: string;
  team: string;
  description: string;
  promptPreview: string;
  runCount: number;
  successRate: number;
  tags: string[];
}

interface Team {
  id: string;
  name: string;
}

const bots = ref<Bot[]>([
  {
    id: 'bot-security',
    name: 'Weekly Security Audit',
    trigger: 'schedule (Mon 9am)',
    team: 'Platform',
    description: 'Scans repositories for security vulnerabilities, exposed secrets, and OWASP issues.',
    promptPreview: 'You are a security expert. Analyze the following code changes for vulnerabilities...',
    runCount: 148,
    successRate: 97,
    tags: ['security', 'scheduled'],
  },
  {
    id: 'bot-pr-review',
    name: 'PR Review',
    trigger: 'github: pull_request',
    team: 'Platform',
    description: 'Reviews pull requests for code quality, test coverage, and adherence to conventions.',
    promptPreview: 'You are a senior engineer. Review this PR for code quality issues...',
    runCount: 342,
    successRate: 99,
    tags: ['review', 'github'],
  },
  {
    id: 'bot-dep-update',
    name: 'Dependency Updater',
    trigger: 'schedule (daily)',
    team: 'Security',
    description: 'Monitors package manifests for vulnerable or outdated dependencies and creates update PRs.',
    promptPreview: 'Analyze the following package manifest for outdated dependencies...',
    runCount: 61,
    successRate: 95,
    tags: ['dependencies', 'scheduled'],
  },
  {
    id: 'bot-changelog',
    name: 'Changelog Generator',
    trigger: 'github: push (main)',
    team: 'Data',
    description: 'Generates human-readable CHANGELOG entries from git commit history after every merge.',
    promptPreview: 'Generate a CHANGELOG entry from the following commit messages...',
    runCount: 89,
    successRate: 100,
    tags: ['docs', 'github'],
  },
]);

const teams = ref<Team[]>([
  { id: 'team-platform', name: 'Platform' },
  { id: 'team-security', name: 'Security' },
  { id: 'team-data', name: 'Data' },
  { id: 'team-frontend', name: 'Frontend' },
]);

const searchQuery = ref('');
const selectedBotId = ref<string | null>(null);
const cloningId = ref<string | null>(null);

const cloneConfig = ref({
  name: '',
  team: '',
  includeTrigger: true,
  includeSchedule: true,
  includePrompt: true,
});

const filteredBots = computed(() => {
  const q = searchQuery.value.toLowerCase();
  if (!q) return bots.value;
  return bots.value.filter(b =>
    b.name.toLowerCase().includes(q) ||
    b.description.toLowerCase().includes(q) ||
    b.tags.some(t => t.includes(q))
  );
});

const selectedBot = computed(() => bots.value.find(b => b.id === selectedBotId.value) ?? null);

function selectBot(bot: Bot) {
  selectedBotId.value = bot.id;
  cloneConfig.value.name = `${bot.name} (Copy)`;
  cloneConfig.value.team = bot.team;
}

async function handleClone() {
  if (!selectedBot.value || !cloneConfig.value.name.trim()) {
    showToast('Bot name is required', 'info');
    return;
  }
  cloningId.value = selectedBotId.value;
  try {
    await new Promise(resolve => setTimeout(resolve, 900));
    const newId = 'bot-' + Math.random().toString(36).slice(2, 8);
    bots.value.push({
      ...selectedBot.value,
      id: newId,
      name: cloneConfig.value.name,
      team: cloneConfig.value.team,
      runCount: 0,
      successRate: 100,
    });
    showToast(`"${cloneConfig.value.name}" created successfully`, 'success');
    selectedBotId.value = null;
    cloneConfig.value = { name: '', team: '', includeTrigger: true, includeSchedule: true, includePrompt: true };
  } catch {
    showToast('Clone failed', 'error');
  } finally {
    cloningId.value = null;
  }
}
</script>

<template>
  <div class="bot-clone-fork-page">
    <AppBreadcrumb :items="[
      { label: 'Bots', action: () => router.push({ name: 'bots' }) },
      { label: 'Clone & Fork' },
    ]" />

    <PageHeader
      title="Bot Clone & Fork"
      subtitle="Duplicate any bot as a starting point for a new one — optionally into a different team's workspace."
    />

    <div class="layout">
      <!-- Source bot selector -->
      <div class="source-panel card">
        <div class="card-header">
          <h3>Choose Source Bot</h3>
        </div>
        <div class="search-wrap">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14">
            <circle cx="11" cy="11" r="8"/>
            <line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <input v-model="searchQuery" type="text" class="search-input" placeholder="Search bots..." />
        </div>
        <div class="bots-list">
          <button
            v-for="b in filteredBots"
            :key="b.id"
            class="bot-row"
            :class="{ selected: selectedBotId === b.id }"
            @click="selectBot(b)"
          >
            <div class="bot-info">
              <span class="bot-name">{{ b.name }}</span>
              <span class="bot-team">{{ b.team }}</span>
              <div class="bot-tags">
                <span v-for="t in b.tags" :key="t" class="tag">{{ t }}</span>
              </div>
              <span class="bot-stats">{{ b.runCount }} runs · {{ b.successRate }}% success</span>
            </div>
            <div class="bot-trigger">{{ b.trigger }}</div>
          </button>
          <div v-if="filteredBots.length === 0" class="list-empty">No bots match your search</div>
        </div>
      </div>

      <!-- Clone configuration -->
      <div class="clone-panel card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
            </svg>
            Clone Configuration
          </h3>
        </div>

        <div v-if="!selectedBot" class="clone-empty">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" width="48" height="48">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
          </svg>
          <p>Select a source bot to configure the clone</p>
        </div>

        <div v-else class="clone-form">
          <!-- Source preview -->
          <div class="source-preview">
            <div class="preview-label">Cloning from</div>
            <div class="preview-bot">
              <span class="preview-name">{{ selectedBot.name }}</span>
              <span class="preview-team">{{ selectedBot.team }}</span>
            </div>
            <p class="preview-desc">{{ selectedBot.description }}</p>
            <div class="preview-prompt">
              <code>{{ selectedBot.promptPreview }}</code>
            </div>
          </div>

          <!-- Clone options -->
          <div class="options-section">
            <div class="form-field">
              <label>New Bot Name</label>
              <input v-model="cloneConfig.name" type="text" class="text-input" placeholder="My Forked Bot" />
            </div>
            <div class="form-field">
              <label>Target Team</label>
              <select v-model="cloneConfig.team" class="select-input">
                <option v-for="t in teams" :key="t.id" :value="t.name">{{ t.name }}</option>
              </select>
            </div>

            <div class="checkbox-group">
              <label class="checkbox-label">
                <input v-model="cloneConfig.includePrompt" type="checkbox" />
                <span>Copy prompt template</span>
              </label>
              <label class="checkbox-label">
                <input v-model="cloneConfig.includeTrigger" type="checkbox" />
                <span>Copy trigger configuration</span>
              </label>
              <label class="checkbox-label">
                <input v-model="cloneConfig.includeSchedule" type="checkbox" />
                <span>Copy schedule settings</span>
              </label>
            </div>

            <div class="clone-summary">
              <div class="summary-row">
                <span class="summary-key">New name</span>
                <span class="summary-val">{{ cloneConfig.name || '—' }}</span>
              </div>
              <div class="summary-row">
                <span class="summary-key">Target team</span>
                <span class="summary-val">{{ cloneConfig.team || '—' }}</span>
              </div>
              <div class="summary-row">
                <span class="summary-key">Copying</span>
                <span class="summary-val">
                  {{
                    [
                      cloneConfig.includePrompt && 'Prompt',
                      cloneConfig.includeTrigger && 'Trigger',
                      cloneConfig.includeSchedule && 'Schedule',
                    ].filter(Boolean).join(' · ') || 'Config only'
                  }}
                </span>
              </div>
            </div>

            <button
              class="btn btn-primary btn-full"
              :disabled="!!cloningId || !cloneConfig.name.trim()"
              @click="handleClone"
            >
              <svg v-if="!cloningId" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
              </svg>
              {{ cloningId ? 'Cloning...' : 'Clone Bot' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.bot-clone-fork-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.layout {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 20px;
  align-items: start;
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
  padding: 18px 20px;
  border-bottom: 1px solid var(--border-default);
}

.card-header h3 {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.card-header h3 svg { color: var(--accent-cyan); }

.search-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-tertiary);
}

.search-input {
  flex: 1;
  background: transparent;
  border: none;
  color: var(--text-primary);
  font-size: 0.875rem;
  outline: none;
}

.search-input::placeholder { color: var(--text-tertiary); }

.bots-list {
  display: flex;
  flex-direction: column;
  max-height: 480px;
  overflow-y: auto;
}

.bot-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 20px;
  border: none;
  background: transparent;
  text-align: left;
  cursor: pointer;
  border-bottom: 1px solid var(--border-subtle);
  transition: background 0.15s;
}

.bot-row:last-child { border-bottom: none; }
.bot-row:hover { background: var(--bg-tertiary); }
.bot-row.selected {
  background: rgba(6, 182, 212, 0.08);
  border-left: 3px solid var(--accent-cyan);
  padding-left: 17px;
}

.bot-info {
  display: flex;
  flex-direction: column;
  gap: 3px;
  flex: 1;
}

.bot-name {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-primary);
}

.bot-team {
  font-size: 0.72rem;
  color: var(--text-tertiary);
}

.bot-tags {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  margin-top: 2px;
}

.tag {
  font-size: 0.65rem;
  padding: 1px 6px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 3px;
  color: var(--text-tertiary);
}

.bot-stats {
  font-size: 0.7rem;
  color: var(--text-tertiary);
  margin-top: 2px;
}

.bot-trigger {
  font-size: 0.7rem;
  color: var(--text-tertiary);
  font-family: monospace;
  white-space: nowrap;
}

.list-empty {
  padding: 32px 20px;
  text-align: center;
  font-size: 0.875rem;
  color: var(--text-tertiary);
}

.clone-empty {
  padding: 64px 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  color: var(--text-tertiary);
}

.clone-empty p { font-size: 0.875rem; margin: 0; }
.clone-empty svg { opacity: 0.3; }

.clone-form {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.source-preview {
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-default);
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: var(--bg-tertiary);
}

.preview-label {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.preview-bot {
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.preview-name {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
}

.preview-team {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.preview-desc {
  font-size: 0.82rem;
  color: var(--text-secondary);
  margin: 0;
}

.preview-prompt code {
  font-family: 'Geist Mono', monospace;
  font-size: 0.75rem;
  color: var(--text-tertiary);
  background: var(--bg-secondary);
  padding: 6px 10px;
  border-radius: 6px;
  border: 1px solid var(--border-default);
  display: block;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.options-section {
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-field label {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.text-input,
.select-input {
  padding: 8px 10px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 7px;
  color: var(--text-primary);
  font-size: 0.875rem;
  width: 100%;
}

.text-input:focus,
.select-input:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.checkbox-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.85rem;
  color: var(--text-secondary);
  cursor: pointer;
}

.checkbox-label input[type="checkbox"] {
  width: 16px;
  height: 16px;
  accent-color: var(--accent-cyan);
}

.clone-summary {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.summary-row {
  display: flex;
  justify-content: space-between;
  font-size: 0.82rem;
}

.summary-key { color: var(--text-tertiary); }
.summary-val { color: var(--text-primary); font-weight: 500; }

.btn-full { width: 100%; justify-content: center; }

.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 9px 16px;
  border-radius: 7px;
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}

.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
