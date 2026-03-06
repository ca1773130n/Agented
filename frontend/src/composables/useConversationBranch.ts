import { ref, watch, type Ref } from 'vue';
import type { ConversationBranch, BranchMessage, BranchTree } from '../services/api';
import { branchApi } from '../services/api';

/**
 * Composable for managing conversation branch state.
 *
 * Handles branch CRUD, tree navigation, and message loading
 * for forked conversation branches.
 *
 * @param conversationId - Reactive conversation ID to watch
 */
export function useConversationBranch(conversationId: Ref<string>) {
  const branches = ref<ConversationBranch[]>([]);
  const selectedBranch = ref<ConversationBranch | null>(null);
  const messages = ref<BranchMessage[]>([]);
  const branchTree = ref<BranchTree | null>(null);
  const isLoading = ref(false);

  /** Fetch branches list and tree for the current conversation. */
  async function loadBranches() {
    if (!conversationId.value) return;
    isLoading.value = true;
    try {
      const [branchResult, treeResult] = await Promise.all([
        branchApi.getBranches(conversationId.value),
        branchApi.getBranchTree(conversationId.value).catch(() => null),
      ]);
      branches.value = branchResult?.branches ?? [];
      branchTree.value = treeResult;
    } catch {
      branches.value = [];
      branchTree.value = null;
    } finally {
      isLoading.value = false;
    }
  }

  /** Select a branch and load its messages. */
  async function selectBranch(branchId: string) {
    const branch = branches.value.find(b => b.id === branchId) ?? null;
    selectedBranch.value = branch;
    if (!branch) {
      messages.value = [];
      return;
    }

    isLoading.value = true;
    try {
      const result = await branchApi.getMessages(branchId);
      messages.value = result?.messages ?? [];
    } catch {
      messages.value = [];
    } finally {
      isLoading.value = false;
    }
  }

  /** Create a new branch forking from a specific message index. */
  async function createBranch(forkMessageIndex: number, name?: string) {
    if (!conversationId.value) return;
    isLoading.value = true;
    try {
      const newBranch = await branchApi.createBranch(conversationId.value, {
        fork_message_index: forkMessageIndex,
        name,
      });
      // Refresh the full list and tree
      await loadBranches();
      // Auto-select the new branch
      if (newBranch?.id) {
        await selectBranch(newBranch.id);
      }
    } catch {
      // Branch creation failed
    } finally {
      isLoading.value = false;
    }
  }

  /** Add a message to the currently selected branch. */
  async function addMessage(role: string, content: string) {
    if (!selectedBranch.value) return;
    try {
      const msg = await branchApi.addMessage(selectedBranch.value.id, { role, content });
      if (msg) {
        messages.value.push(msg);
      }
    } catch (e) {
      console.warn('[useConversationBranch] Failed to add message:', e);
    }
  }

  // Reload branches when conversationId changes
  watch(conversationId, (newId) => {
    if (newId) {
      selectedBranch.value = null;
      messages.value = [];
      loadBranches();
    } else {
      branches.value = [];
      selectedBranch.value = null;
      messages.value = [];
      branchTree.value = null;
    }
  });

  return {
    branches,
    selectedBranch,
    messages,
    branchTree,
    isLoading,
    loadBranches,
    selectBranch,
    createBranch,
    addMessage,
  };
}
