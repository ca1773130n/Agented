/**
 * Conversation branch types.
 */

export interface ConversationBranch {
  id: string;
  conversation_id: string;
  parent_branch_id: string | null;
  fork_message_id: string | null;
  name: string | null;
  status: string;
  created_at: string;
  message_count?: number;
}

export interface BranchMessage {
  id: string;
  conversation_id: string;
  branch_id: string;
  parent_message_id: string | null;
  message_index: number;
  role: string;
  content: string;
  created_at: string;
}

export interface BranchTree {
  branch_id: string;
  name: string | null;
  message_count: number;
  children: BranchTree[];
}
