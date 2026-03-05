<script setup lang="ts">
import { ref, toRef } from 'vue';
import type { BranchTree } from '../../services/api';
import { useConversationBranch } from '../../composables/useConversationBranch';

const props = defineProps<{
  conversationId: string;
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
  addMessage,
} = useConversationBranch(conversationIdRef);

const forkingAtIndex = ref<number | null>(null);
const newBranchName = ref('');
const hoveredMessageIndex = ref<number | null>(null);

function handleFork(messageIndex: number) {
  forkingAtIndex.value = messageIndex;
  newBranchName.value = '';
}

async function submitFork() {
  if (forkingAtIndex.value === null) return;
  await createBranch(forkingAtIndex.value, newBranchName.value || undefined);
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
  return node.name || `Branch ${index + 1}`;
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleString('en-US', {
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
        <h4 class="sidebar-title">Branches</h4>
        <span v-if="branches.length > 0" class="branch-count">{{ branches.length }}</span>
      </div>

      <div v-if="isLoading && branches.length === 0" class="sidebar-loading">
        <div class="spinner-small"></div>
        Loading branches...
      </div>

      <div v-else-if="branches.length === 0" class="sidebar-empty">
        No branches yet. Fork from a message to create one.
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
            <span class="node-name">{{ branchTree.name || 'Main' }}</span>
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
            <span class="node-name">{{ branch.name || `Branch ${i + 1}` }}</span>
            <span class="node-count">{{ branch.message_count ?? 0 }}msg</span>
          </div>
        </template>
      </div>
    </div>

    <!-- Messages Area -->
    <div class="branch-messages">
      <div v-if="!selectedBranch" class="messages-empty">
        Select a branch to view its messages
      </div>

      <div v-else>
        <div class="messages-header">
          <h4 class="messages-title">{{ selectedBranch.name || 'Branch Messages' }}</h4>
          <span class="messages-date">{{ formatDate(selectedBranch.created_at) }}</span>
        </div>

        <div v-if="isLoading" class="messages-loading">
          <div class="spinner-small"></div>
          Loading messages...
        </div>

        <div v-else-if="messages.length === 0" class="messages-empty">
          No messages in this branch.
        </div>

        <div v-else class="message-thread">
          <div
            v-for="(msg, index) in messages"
            :key="msg.id"
            class="message-item"
            :class="msg.role"
            @mouseenter="hoveredMessageIndex = msg.message_index"
            @mouseleave="hoveredMessageIndex = null"
          >
            <div class="message-role">{{ msg.role }}</div>
            <div class="message-content">{{ msg.content }}</div>
            <div class="message-footer">
              <span class="message-time">{{ formatDate(msg.created_at) }}</span>
              <button
                v-if="hoveredMessageIndex === msg.message_index"
                class="fork-btn"
                @click.stop="handleFork(msg.message_index)"
                title="Fork from here"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
                  <path d="M6 3v12M18 9a3 3 0 100-6 3 3 0 000 6zM6 21a3 3 0 100-6 3 3 0 000 6zM18 9c-3 0-6 3-6 6v3"/>
                </svg>
                Fork
              </button>
            </div>

            <!-- Fork input (shown inline below the message) -->
            <div v-if="forkingAtIndex === msg.message_index" class="fork-input-wrapper">
              <input
                v-model="newBranchName"
                type="text"
                class="fork-input"
                placeholder="Branch name (optional)"
                autofocus
                @keydown="handleForkKeyDown"
              />
              <button class="fork-submit" @click="submitFork">Create</button>
              <button class="fork-cancel" @click="cancelFork">Cancel</button>
            </div>
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
