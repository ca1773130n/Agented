/**
 * Conversation branch API module.
 *
 * Provides functions for creating, listing, and navigating conversation branches
 * and their messages. Supports tree-based navigation of forked conversations.
 */
import { apiFetch } from './client';
import type { ConversationBranch, BranchMessage, BranchTree } from './types';

export const branchApi = {
  /** Create a new branch forking from a specific message index. */
  createBranch: (conversationId: string, data: { fork_message_index: number; name?: string }) =>
    apiFetch<ConversationBranch>(
      `/admin/conversations/${conversationId}/branches`,
      { method: 'POST', body: JSON.stringify(data) }
    ),

  /** List all branches for a conversation. */
  getBranches: (conversationId: string) =>
    apiFetch<{ branches: ConversationBranch[] }>(
      `/admin/conversations/${conversationId}/branches`
    ),

  /** Get the branch tree structure for a conversation. */
  getBranchTree: (conversationId: string) =>
    apiFetch<BranchTree>(
      `/admin/conversations/${conversationId}/branch-tree`
    ),

  /** Get all messages in a specific branch. */
  getMessages: (branchId: string) =>
    apiFetch<{ messages: BranchMessage[] }>(
      `/admin/branches/${branchId}/messages`
    ),

  /** Add a message to a specific branch. */
  addMessage: (branchId: string, data: { role: string; content: string }) =>
    apiFetch<BranchMessage>(
      `/admin/branches/${branchId}/messages`,
      { method: 'POST', body: JSON.stringify(data) }
    ),
};
