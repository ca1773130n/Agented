<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';

const router = useRouter();
const showToast = useToast();

interface BotSummary {
  id: string;
  name: string;
  trigger: string;
  lastRun: string;
  hasDoc: boolean;
}

const bots = ref<BotSummary[]>([
  { id: 'bot-security', name: 'Weekly Security Audit', trigger: 'schedule (Mon 9am)', lastRun: '3 hours ago', hasDoc: true },
  { id: 'bot-pr-review', name: 'PR Review', trigger: 'github: pull_request', lastRun: '12 minutes ago', hasDoc: false },
  { id: 'bot-dep-update', name: 'Dependency Updater', trigger: 'schedule (daily)', lastRun: '1 day ago', hasDoc: false },
  { id: 'bot-changelog', name: 'Changelog Generator', trigger: 'github: push (main)', lastRun: '2 days ago', hasDoc: true },
]);

const selectedBotId = ref<string | null>(null);
const isGenerating = ref(false);
const generatedDoc = ref<string | null>(null);
const isCopying = ref(false);

const sampleDocs: Record<string, string> = {
  'bot-security': `# Weekly Security Audit Bot

## What It Does
Runs a comprehensive security scan across connected repositories every Monday at 9am. Checks for dependency vulnerabilities, exposed secrets, SQL injection patterns, and OWASP Top 10 issues.

## Trigger
- **Type:** Scheduled
- **Cron:** \`0 9 * * 1\` (Every Monday at 9:00 AM UTC)

## Permissions Required
- Read access to all connected repositories
- GitHub API token for creating issues
- Jira API key for ticket creation (optional)

## Prompt Template Overview
The bot receives the full diff of changes since the last scan and analyzes them for security issues using a structured checklist approach.

## Example Output
\`\`\`
Found 2 issues in PR #142:
  [HIGH] SQL injection risk in /api/users?search= (line 45)
  [MEDIUM] Dependency lodash@4.17.19 has known CVE-2021-23337
\`\`\`

## Known Limitations
- Does not perform dynamic/runtime analysis
- False positive rate ~8% on minified/generated code
- Requires repos to be connected before first run`,

  'bot-changelog': `# Changelog Generator Bot

## What It Does
Automatically generates a human-readable CHANGELOG entry from git commit messages whenever code is pushed to the main branch. Groups commits by type (feat, fix, chore) and formats them as Markdown.

## Trigger
- **Type:** GitHub Event
- **Event:** \`push\` to \`main\` branch

## Permissions Required
- Read access to commit history
- Write access to update CHANGELOG.md via PR

## Example Output
\`\`\`
## v2.4.1 (2026-03-06)
### Features
- Add semantic search for repository context
### Bug Fixes
- Fix token counting off-by-one in estimator
### Chores
- Update dependencies
\`\`\``,
};

function selectBot(id: string) {
  selectedBotId.value = id;
  generatedDoc.value = null;
}

async function generateDoc() {
  if (!selectedBotId.value) return;
  isGenerating.value = true;
  try {
    await new Promise(resolve => setTimeout(resolve, 1400));
    const bot = bots.value.find(b => b.id === selectedBotId.value);
    generatedDoc.value = sampleDocs[selectedBotId.value] ?? `# ${bot?.name ?? 'Bot'} Documentation

## What It Does
This bot automates key development workflows triggered by ${bot?.trigger ?? 'configured events'}. It analyzes the incoming context and produces actionable output tailored to your team's conventions.

## Trigger
- **Type:** ${bot?.trigger ?? 'Configured trigger'}

## Permissions Required
- Read access to connected repositories
- Write access for creating comments or PRs

## Example Output
The bot produces structured Markdown output summarizing findings and recommended actions.

## Known Limitations
- Best results when prompt templates are kept under 2,000 tokens
- Requires at least 3 prior executions for optimal context calibration`;

    const b = bots.value.find(b => b.id === selectedBotId.value);
    if (b) b.hasDoc = true;
    showToast('Documentation generated', 'success');
  } catch {
    showToast('Failed to generate documentation', 'error');
  } finally {
    isGenerating.value = false;
  }
}

async function copyDoc() {
  if (!generatedDoc.value) return;
  isCopying.value = true;
  try {
    await navigator.clipboard.writeText(generatedDoc.value);
    showToast('Copied to clipboard', 'success');
  } catch {
    showToast('Copy failed', 'error');
  } finally {
    setTimeout(() => { isCopying.value = false; }, 1000);
  }
}

async function saveDoc() {
  if (!generatedDoc.value) return;
  await new Promise(resolve => setTimeout(resolve, 500));
  showToast('Documentation saved to bot config', 'success');
}
</script>

<template>
  <div class="bot-doc-generator-page">
    <AppBreadcrumb :items="[
      { label: 'Bots', action: () => router.push({ name: 'bots' }) },
      { label: 'Doc Generator' },
    ]" />

    <PageHeader
      title="Auto-Generated Bot Documentation"
      subtitle="Generate human-readable README documentation for any bot — trigger type, permissions, example output, and limitations."
    />

    <div class="layout">
      <!-- Bot picker -->
      <div class="bot-picker card">
        <div class="card-header">
          <h3>Select a Bot</h3>
        </div>
        <div class="bot-list">
          <button
            v-for="b in bots"
            :key="b.id"
            class="bot-item"
            :class="{ selected: selectedBotId === b.id }"
            @click="selectBot(b.id)"
          >
            <div class="bot-item-info">
              <span class="bot-item-name">{{ b.name }}</span>
              <span class="bot-item-trigger">{{ b.trigger }}</span>
              <span class="bot-item-meta">Last run {{ b.lastRun }}</span>
            </div>
            <span v-if="b.hasDoc" class="doc-badge">Documented</span>
          </button>
        </div>
      </div>

      <!-- Doc preview -->
      <div class="doc-panel card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
              <line x1="16" y1="13" x2="8" y2="13"/>
              <line x1="16" y1="17" x2="8" y2="17"/>
              <polyline points="10 9 9 9 8 9"/>
            </svg>
            Generated Documentation
          </h3>
          <div class="header-actions" v-if="generatedDoc">
            <button class="btn btn-ghost" @click="copyDoc">
              {{ isCopying ? 'Copied!' : 'Copy' }}
            </button>
            <button class="btn btn-primary" @click="saveDoc">Save to Bot</button>
          </div>
        </div>

        <div v-if="!selectedBotId" class="doc-empty">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" width="48" height="48">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
          </svg>
          <p>Select a bot to generate its documentation</p>
        </div>

        <div v-else-if="!generatedDoc" class="generate-prompt">
          <p class="generate-hint">
            Click Generate to create a one-click README for
            <strong>{{ bots.find(b => b.id === selectedBotId)?.name }}</strong>
            — including trigger config, permissions, example outputs, and limitations.
          </p>
          <button class="btn btn-primary btn-lg" :disabled="isGenerating" @click="generateDoc">
            <svg v-if="!isGenerating" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16">
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
            </svg>
            {{ isGenerating ? 'Generating...' : 'Generate Documentation' }}
          </button>
          <div v-if="isGenerating" class="generating-indicator">
            <div class="spinner" />
            <span>Analyzing bot config and past executions...</span>
          </div>
        </div>

        <div v-else class="doc-content">
          <pre class="doc-text">{{ generatedDoc }}</pre>
          <button class="btn btn-secondary regenerate-btn" :disabled="isGenerating" @click="generateDoc">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14">
              <polyline points="1 4 1 10 7 10"/>
              <path d="M3.51 15a9 9 0 1 0 .49-3.75"/>
            </svg>
            Regenerate
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.bot-doc-generator-page {
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
  grid-template-columns: 280px 1fr;
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

.header-actions {
  display: flex;
  gap: 8px;
}

.bot-list {
  display: flex;
  flex-direction: column;
}

.bot-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  border: none;
  background: transparent;
  text-align: left;
  cursor: pointer;
  border-bottom: 1px solid var(--border-subtle);
  transition: background 0.15s;
}

.bot-item:last-child { border-bottom: none; }
.bot-item:hover { background: var(--bg-tertiary); }
.bot-item.selected { background: rgba(6, 182, 212, 0.08); border-left: 3px solid var(--accent-cyan); }

.bot-item-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.bot-item-name {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-primary);
}

.bot-item-trigger {
  font-size: 0.72rem;
  color: var(--text-tertiary);
  font-family: monospace;
}

.bot-item-meta {
  font-size: 0.7rem;
  color: var(--text-tertiary);
}

.doc-badge {
  font-size: 0.65rem;
  font-weight: 700;
  padding: 2px 7px;
  background: rgba(52, 211, 153, 0.15);
  color: #34d399;
  border-radius: 4px;
  white-space: nowrap;
}

.doc-empty {
  padding: 64px 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  color: var(--text-tertiary);
}

.doc-empty p { font-size: 0.875rem; margin: 0; }
.doc-empty svg { opacity: 0.3; }

.generate-prompt {
  padding: 40px 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
}

.generate-hint {
  font-size: 0.875rem;
  color: var(--text-secondary);
  text-align: center;
  max-width: 400px;
  margin: 0;
}

.generate-hint strong { color: var(--text-primary); }

.btn-lg { padding: 10px 24px; font-size: 0.9rem; }

.generating-indicator {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.8rem;
  color: var(--text-tertiary);
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid var(--bg-tertiary);
  border-top-color: var(--accent-cyan);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.doc-content {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.doc-text {
  font-family: 'Geist Mono', monospace;
  font-size: 0.8rem;
  color: var(--text-secondary);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  padding: 20px;
  white-space: pre-wrap;
  margin: 0;
  line-height: 1.6;
}

.regenerate-btn { align-self: flex-end; }

.btn {
  display: inline-flex;
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

.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-secondary { background: var(--bg-tertiary); border: 1px solid var(--border-default); color: var(--text-secondary); }
.btn-secondary:hover:not(:disabled) { border-color: var(--accent-cyan); color: var(--accent-cyan); }
.btn-secondary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-ghost { background: transparent; border: 1px solid var(--border-default); color: var(--text-secondary); }
.btn-ghost:hover { border-color: var(--text-secondary); color: var(--text-primary); }
</style>
