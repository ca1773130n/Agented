<script setup lang="ts">
import { ref } from 'vue';
import { superAgentSessionApi } from '../../services/api/super-agents';
import type { SuperAgentSession, GitAction } from '../../services/api/types';

const props = defineProps<{
  session: SuperAgentSession;
  superAgentId: string;
}>();

const emit = defineEmits<{
  (e: 'action-complete'): void;
}>();

const loading = ref<GitAction | null>(null);
const lastResult = ref<{ action: string; success: boolean; output?: string; pr_url?: string } | null>(null);
const commitMessage = ref('');
const showCommitInput = ref(false);
const showDiff = ref(false);
const diffContent = ref('');

const hasWorktree = () => !!props.session.worktree_path;

async function runAction(action: GitAction, extra?: Record<string, string>) {
  if (loading.value) return;
  loading.value = action;
  lastResult.value = null;
  try {
    const result = await superAgentSessionApi.gitAction(
      props.superAgentId,
      props.session.id,
      { action, ...extra },
    );
    lastResult.value = result;
    if (action === 'diff' && result.diff) {
      diffContent.value = result.diff;
      showDiff.value = true;
    }
    emit('action-complete');
  } catch (err) {
    lastResult.value = { action, success: false, output: String(err) };
  } finally {
    loading.value = null;
  }
}

function handleCommit() {
  if (!commitMessage.value.trim()) return;
  runAction('commit', { message: commitMessage.value.trim() });
  commitMessage.value = '';
  showCommitInput.value = false;
}
</script>

<template>
  <div v-if="hasWorktree()" class="git-actions-toolbar">
    <div class="toolbar-row">
      <span class="branch-badge" :title="session.branch_name || ''">
        {{ session.branch_name || 'no branch' }}
      </span>
      <div class="actions">
        <button
          class="action-btn"
          :disabled="!!loading"
          @click="showCommitInput = !showCommitInput"
          title="Commit changes"
        >
          {{ loading === 'commit' ? '...' : 'Commit' }}
        </button>
        <button
          class="action-btn"
          :disabled="!!loading"
          @click="runAction('push')"
          title="Push to remote"
        >
          {{ loading === 'push' ? '...' : 'Push' }}
        </button>
        <button
          class="action-btn action-btn--primary"
          :disabled="!!loading || !!session.pr_url"
          @click="runAction('create_pr')"
          title="Create pull request"
        >
          {{ loading === 'create_pr' ? '...' : session.pr_url ? 'PR Created' : 'Create PR' }}
        </button>
        <button
          class="action-btn"
          :disabled="!!loading"
          @click="runAction('rebase')"
          title="Rebase onto main"
        >
          {{ loading === 'rebase' ? '...' : 'Rebase' }}
        </button>
        <button
          class="action-btn"
          :disabled="!!loading"
          @click="runAction('diff')"
          title="Show diff vs main"
        >
          {{ loading === 'diff' ? '...' : 'Diff' }}
        </button>
      </div>
      <a
        v-if="session.pr_url"
        :href="session.pr_url"
        target="_blank"
        rel="noopener"
        class="pr-link"
      >
        View PR
      </a>
    </div>

    <div v-if="showCommitInput" class="commit-input-row">
      <input
        v-model="commitMessage"
        type="text"
        placeholder="Commit message..."
        class="commit-input"
        @keydown.enter="handleCommit"
      />
      <button class="action-btn action-btn--primary" @click="handleCommit">
        Commit
      </button>
    </div>

    <div v-if="lastResult && !lastResult.success" class="result-row result-row--error">
      {{ lastResult.output }}
    </div>
    <div v-if="lastResult && lastResult.success && lastResult.output" class="result-row">
      {{ lastResult.output }}
    </div>

    <div v-if="showDiff" class="diff-panel">
      <div class="diff-header">
        <span>Diff vs main</span>
        <button class="action-btn" @click="showDiff = false">Close</button>
      </div>
      <pre class="diff-content">{{ diffContent }}</pre>
    </div>
  </div>
</template>

<style scoped>
.git-actions-toolbar {
  border: 1px solid var(--color-border, #333);
  border-radius: 6px;
  padding: 8px 12px;
  margin-bottom: 8px;
  background: var(--color-bg-secondary, #1a1a1a);
  font-size: 13px;
}

.toolbar-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.branch-badge {
  font-family: monospace;
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--color-bg-tertiary, #2a2a2a);
  color: var(--color-text-secondary, #999);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 200px;
}

.actions {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.action-btn {
  padding: 4px 10px;
  border: 1px solid var(--color-border, #444);
  border-radius: 4px;
  background: transparent;
  color: var(--color-text, #ccc);
  cursor: pointer;
  font-size: 12px;
  white-space: nowrap;
}

.action-btn:hover:not(:disabled) {
  background: var(--color-bg-tertiary, #333);
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.action-btn--primary {
  border-color: var(--color-primary, #6366f1);
  color: var(--color-primary, #6366f1);
}

.action-btn--primary:hover:not(:disabled) {
  background: rgba(99, 102, 241, 0.1);
}

.pr-link {
  margin-left: auto;
  color: var(--color-primary, #6366f1);
  font-size: 12px;
  text-decoration: none;
}

.pr-link:hover {
  text-decoration: underline;
}

.commit-input-row {
  display: flex;
  gap: 6px;
  margin-top: 6px;
}

.commit-input {
  flex: 1;
  padding: 4px 8px;
  border: 1px solid var(--color-border, #444);
  border-radius: 4px;
  background: var(--color-bg-primary, #111);
  color: var(--color-text, #ccc);
  font-size: 12px;
}

.result-row {
  margin-top: 6px;
  padding: 4px 8px;
  border-radius: 4px;
  font-family: monospace;
  font-size: 11px;
  background: var(--color-bg-tertiary, #2a2a2a);
  color: var(--color-text-secondary, #999);
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 80px;
  overflow-y: auto;
}

.result-row--error {
  color: var(--color-error, #ef4444);
}

.diff-panel {
  margin-top: 8px;
  border: 1px solid var(--color-border, #333);
  border-radius: 4px;
  max-height: 300px;
  overflow-y: auto;
}

.diff-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 10px;
  border-bottom: 1px solid var(--color-border, #333);
  background: var(--color-bg-tertiary, #2a2a2a);
  font-size: 12px;
}

.diff-content {
  padding: 8px 10px;
  margin: 0;
  font-size: 11px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
