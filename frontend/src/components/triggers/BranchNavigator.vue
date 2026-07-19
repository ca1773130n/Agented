<script setup lang="ts">
import { ref, toRef, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import type { BranchTree } from '../../services/api';

const { t } = useI18n();
import { useConversationBranch } from '../../composables/useConversationBranch';
import { safeFormatDateTime } from '../../utils/datetime';
import MarkdownContent from '../base/MarkdownContent.vue';

const props = defineProps<{
  conversationId: string;
  // Phase 25 (25-03) — when BOTH are supplied, each message also offers a
  // "Fork to run" action that spawns a fresh, seeded ``psess-`` run (a separate
  // independent process) via ``sessionForkApi.fork``, in addition to the in-place
  // branch fork. Omitting them (e.g. the bot/trigger ExecutionHistory mount, which
  // has no project scope) hides the run-fork action — branch fork still works.
  projectId?: string;
  sessionId?: string;
}>();

// Surface the new run to the parent so it can navigate to / highlight the
// forked ``psess-`` session.
const emit = defineEmits<{
  (e: 'forked-run', payload: { sessionId: string; branchId: string }): void;
}>();

const conversationIdRef = toRef(props, 'conversationId');
const {
  branches,
  selectedBranch,
  messages,
  branchTree,
  isLoading,
  loadBranches,
  selectBranch,
  createBranch,
  forkRun,
} = useConversationBranch(conversationIdRef);

const forkingAtIndex = ref<number | null>(null);
const newBranchName = ref('');
const hoveredMessageIndex = ref<number | null>(null);

// Run-fork is only offered when the owning project + session are known.
const canForkRun = computed(() => !!props.projectId && !!props.sessionId);
const forkingRunIndex = ref<number | null>(null);
const forkedRunSessionId = ref<string | null>(null);
const branchError = ref<string | null>(null);

async function handleForkRun(messageIndex: number) {
  if (!props.projectId || !props.sessionId || forkingRunIndex.value !== null) return;
  forkingRunIndex.value = messageIndex;
  forkedRunSessionId.value = null;
  branchError.value = null;
  try {
    const result = await forkRun(props.projectId, props.sessionId, messageIndex);
    if (result?.session_id) {
      forkedRunSessionId.value = result.session_id;
      emit('forked-run', { sessionId: result.session_id, branchId: result.branch_id });
    } else {
      // forkRun returns null on failure — surface it instead of failing silently.
      branchError.value = t('branchNavigator.forkRunFailed');
    }
  } finally {
    forkingRunIndex.value = null;
  }
}

function handleFork(messageIndex: number) {
  forkingAtIndex.value = messageIndex;
  newBranchName.value = '';
}

async function submitFork() {
  if (forkingAtIndex.value === null) return;
  branchError.value = null;
  const ok = await createBranch(forkingAtIndex.value, newBranchName.value || undefined);
  if (!ok) {
    // Keep the dialog open and show the error instead of silently closing.
    branchError.value = t('branchNavigator.createFailed');
    return;
  }
  forkingAtIndex.value = null;
  newBranchName.value = '';
}

function cancelFork() {
  forkingAtIndex.value = null;
  newBranchName.value = '';
}

function handleForkKeyDown(e: KeyboardEvent) {
  if (e.key === 'Enter') {
    e.preventDefault();
    submitFork();
  }
  if (e.key === 'Escape') {
    cancelFork();
  }
}

function getBranchDisplayName(node: BranchTree, index: number): string {
  return node.name || t('branchNavigator.branchN', { n: index + 1 });
}

function formatDate(dateStr: string): string {
  return safeFormatDateTime(dateStr, '', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

// Load branches on mount
loadBranches();
</script>

<template>
  <div class="branch-navigator">
    <!-- Branch Tree Sidebar -->
    <div class="branch-sidebar">
      <div class="sidebar-header">
        <h4 class="sidebar-title">{{ t('branchNavigator.branches') }}</h4>
        <span v-if="branches.length > 0" class="branch-count">{{ branches.length }}</span>
      </div>

      <div v-if="isLoading && branches.length === 0" class="sidebar-loading">
        <div class="spinner-small"></div>
        {{ t('branchNavigator.loadingBranches') }}
      </div>

      <div v-else-if="branches.length === 0" class="sidebar-empty">
        {{ t('branchNavigator.noBranches') }}
      </div>

      <!-- Tree rendering -->
      <div v-else class="branch-tree">
        <template v-if="branchTree">
          <div
            class="tree-node"
            :class="{ selected: selectedBranch?.id === branchTree.branch_id }"
            @click="selectBranch(branchTree.branch_id)"
          >
            <span class="node-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                <circle cx="12" cy="12" r="3"/>
              </svg>
            </span>
            <span class="node-name">{{ branchTree.name || t('branchNavigator.main') }}</span>
            <span class="node-count">{{ branchTree.message_count }}msg</span>
          </div>
          <div v-if="branchTree.children.length > 0" class="tree-children">
            <div
              v-for="(child, i) in branchTree.children"
              :key="child.branch_id"
              class="tree-node child"
              :class="{ selected: selectedBranch?.id === child.branch_id }"
              @click="selectBranch(child.branch_id)"
            >
              <span class="tree-connector"></span>
              <span class="node-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
                  <path d="M6 3v12M18 9a3 3 0 100-6 3 3 0 000 6zM6 21a3 3 0 100-6 3 3 0 000 6zM18 9c-3 0-6 3-6 6v3"/>
                </svg>
              </span>
              <span class="node-name">{{ getBranchDisplayName(child, i) }}</span>
              <span class="node-count">{{ child.message_count }}msg</span>
            </div>
          </div>
        </template>

        <!-- Flat list fallback if tree not available -->
        <template v-else>
          <div
            v-for="(branch, i) in branches"
            :key="branch.id"
            class="tree-node"
            :class="{ selected: selectedBranch?.id === branch.id }"
            @click="selectBranch(branch.id)"
          >
            <span class="node-name">{{ branch.name || t('branchNavigator.branchN', { n: i + 1 }) }}</span>
            <span class="node-count">{{ branch.message_count ?? 0 }}msg</span>
          </div>
        </template>
      </div>
    </div>

    <!-- Messages Area -->
    <div class="branch-messages">
      <div v-if="!selectedBranch" class="messages-empty">
        {{ t('branchNavigator.selectBranch') }}
      </div>

      <div v-else>
        <div class="messages-header">
          <h4 class="messages-title">{{ selectedBranch.name || t('branchNavigator.branchMessages') }}</h4>
          <span class="messages-date">{{ formatDate(selectedBranch.created_at) }}</span>
        </div>

        <div v-if="isLoading" class="messages-loading">
          <div class="spinner-small"></div>
          {{ t('branchNavigator.loadingMessages') }}
        </div>

        <div v-else-if="messages.length === 0" class="messages-empty">
          {{ t('branchNavigator.noMessages') }}
        </div>

        <div v-else class="message-thread">
          <div
            v-for="msg in messages"
            :key="msg.id"
            class="message-item"
            :class="msg.role"
            @mouseenter="hoveredMessageIndex = msg.message_index"
            @mouseleave="hoveredMessageIndex = null"
          >
            <div class="message-role">{{ msg.role }}</div>
            <MarkdownContent class="message-content" :content="msg.content" />
            <div class="message-footer">
              <span class="message-time">{{ formatDate(msg.created_at) }}</span>
              <div class="fork-actions">
                <button
                  v-if="hoveredMessageIndex === msg.message_index"
                  class="fork-btn"
                  @click.stop="handleFork(msg.message_index)"
                  :title="t('branchNavigator.forkFromHere')"
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
                    <path d="M6 3v12M18 9a3 3 0 100-6 3 3 0 000 6zM6 21a3 3 0 100-6 3 3 0 000 6zM18 9c-3 0-6 3-6 6v3"/>
                  </svg>
                  {{ t('branchNavigator.fork') }}
                </button>
                <!-- Phase 25 (25-03) — fork onto a SEPARATE independent run -->
                <button
                  v-if="canForkRun && (hoveredMessageIndex === msg.message_index || forkingRunIndex === msg.message_index)"
                  class="fork-run-btn"
                  :disabled="forkingRunIndex !== null"
                  @click.stop="handleForkRun(msg.message_index)"
                  :title="t('branchNavigator.forkToRunHint')"
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
                    <path d="M5 3l14 9-14 9V3z"/>
                  </svg>
                  {{ forkingRunIndex === msg.message_index ? t('branchNavigator.forkingRun') : t('branchNavigator.forkToRun') }}
                </button>
              </div>
            </div>
            <p
              v-if="forkedRunSessionId && forkingRunIndex === null && hoveredMessageIndex === msg.message_index"
              class="fork-run-success"
            >
              {{ t('branchNavigator.forkRunSuccess', { id: forkedRunSessionId }) }}
            </p>

            <!-- Fork input (shown inline below the message) -->
            <div v-if="forkingAtIndex === msg.message_index" class="fork-input-wrapper">
              <input
                v-model="newBranchName"
                type="text"
                class="fork-input"
                :placeholder="t('branchNavigator.branchNamePlaceholder')"
                autofocus
                @keydown="handleForkKeyDown"
              />
              <button class="fork-submit" @click="submitFork">{{ t('common.create') }}</button>
              <button class="fork-cancel" @click="cancelFork">{{ t('common.cancel') }}</button>
            </div>
            <div v-if="branchError" class="branch-error" role="alert">{{ branchError }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.branch-navigator {
  display: flex;
  gap: 1px;
  background: var(--border-subtle);
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  overflow: hidden;
  min-height: 300px;
}

/* Sidebar */
.branch-sidebar {
  width: 220px;
  flex-shrink: 0;
  background: var(--bg-primary);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border-subtle);
}

.sidebar-title {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 0;
}

.branch-count {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--accent-cyan);
  background: var(--accent-cyan-dim);
  padding: 2px 6px;
  border-radius: 10px;
}

.sidebar-loading, .sidebar-empty {
  padding: 20px 14px;
  font-size: 0.8rem;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: 8px;
}

.branch-tree {
  display: flex;
  flex-direction: column;
  padding: 8px;
  gap: 2px;
}

.tree-node {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s ease;
  font-size: 0.8rem;
}

.tree-node:hover {
  background: var(--bg-elevated);
}

.tree-node.selected {
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
}

.tree-node.child {
  padding-left: 24px;
}

.tree-connector {
  width: 10px;
  height: 1px;
  background: var(--border-default);
  flex-shrink: 0;
}

.node-icon {
  color: var(--text-muted);
  flex-shrink: 0;
  display: flex;
  align-items: center;
}

.tree-node.selected .node-icon {
  color: var(--accent-cyan);
}

.node-name {
  flex: 1;
  color: var(--text-primary);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.node-count {
  font-size: 0.7rem;
  color: var(--text-muted);
  flex-shrink: 0;
  font-family: var(--font-mono);
}

.tree-children {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

/* Messages Area */
.branch-messages {
  flex: 1;
  background: var(--bg-secondary);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

.messages-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-subtle);
}

.messages-title {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.messages-date {
  font-size: 0.75rem;
  color: var(--text-muted);
  font-family: var(--font-mono);
}

.messages-loading, .messages-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px 20px;
  color: var(--text-muted);
  font-size: 0.85rem;
}

.message-thread {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 16px;
}

.message-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid var(--border-subtle);
  transition: border-color 0.15s ease;
}

.message-item:hover {
  border-color: var(--border-default);
}

.message-item.user {
  background: var(--bg-primary);
}

.message-item.assistant {
  background: var(--bg-tertiary);
  border-left: 3px solid var(--accent-cyan);
}

.message-item.system {
  background: var(--bg-tertiary);
  border-left: 3px solid var(--text-muted);
}

.message-role {
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
}

.message-item.user .message-role {
  color: var(--accent-violet, #8b5cf6);
}

.message-item.assistant .message-role {
  color: var(--accent-cyan);
}

.message-content {
  font-size: 0.85rem;
  color: var(--text-secondary);
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.message-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.message-time {
  font-size: 0.7rem;
  color: var(--text-muted);
  font-family: var(--font-mono);
}

.fork-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  background: transparent;
  border: 1px solid rgba(139, 92, 246, 0.3);
  border-radius: 4px;
  color: var(--accent-violet, #8b5cf6);
  font-size: 0.7rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}

.fork-btn:hover {
  background: rgba(139, 92, 246, 0.15);
  border-color: var(--accent-violet, #8b5cf6);
}

.fork-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.fork-run-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  background: transparent;
  border: 1px solid var(--accent-cyan, #22d3ee);
  border-radius: 4px;
  color: var(--accent-cyan, #22d3ee);
  font-size: 0.7rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}

.fork-run-btn:hover:not(:disabled) {
  background: var(--accent-cyan-dim, rgba(34, 211, 238, 0.15));
}

.fork-run-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.fork-run-success {
  margin: 6px 0 0;
  font-size: 0.72rem;
  color: var(--accent-cyan, #22d3ee);
  font-family: var(--font-mono, monospace);
}

.fork-input-wrapper {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--border-subtle);
  animation: forkSlideIn 0.2s ease;
}

@keyframes forkSlideIn {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}

.fork-input {
  flex: 1;
  padding: 6px 10px;
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: 4px;
  color: var(--text-primary);
  font-size: 0.8rem;
  font-family: inherit;
  outline: none;
}

.fork-input:focus {
  border-color: var(--accent-violet, #8b5cf6);
}

.fork-input::placeholder {
  color: var(--text-muted);
}

.fork-submit, .fork-cancel {
  padding: 6px 12px;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}

.fork-submit {
  background: var(--accent-violet, #8b5cf6);
  border: none;
  color: white;
}

.fork-submit:hover {
  opacity: 0.9;
}

.fork-cancel {
  background: transparent;
  border: 1px solid var(--border-subtle);
  color: var(--text-tertiary);
}

.fork-cancel:hover {
  background: var(--bg-elevated);
  color: var(--text-primary);
}

/* Spinner */
.spinner-small {
  width: 14px;
  height: 14px;
  border: 2px solid var(--border-subtle);
  border-top-color: var(--accent-cyan);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
