/**
 * SuperAgent types.
 */

export type SuperAgentStatus = 'active' | 'idle' | 'terminated';
export type SessionStatus = 'active' | 'paused' | 'completed' | 'terminated';
export type DocumentType = 'SOUL' | 'IDENTITY' | 'MEMORY' | 'ROLE';
export type AgentMessageType = 'message' | 'broadcast' | 'request' | 'response' | 'artifact' | 'shutdown';
export type AgentMessagePriority = 'low' | 'normal' | 'high';
export type AgentMessageStatus = 'pending' | 'delivered' | 'read' | 'expired';

export interface SuperAgent {
  id: string;
  name: string;
  description?: string;
  backend_type: string;
  preferred_model?: string;
  team_id?: string;
  parent_super_agent_id?: string;
  max_concurrent_sessions: number;
  enabled: number;
  config_json?: string;
  created_at?: string;
  updated_at?: string;
}

export interface SuperAgentDocument {
  id: number;
  super_agent_id: string;
  doc_type: DocumentType;
  title: string;
  content: string;
  version: number;
  created_at?: string;
  updated_at?: string;
}

export interface SuperAgentSession {
  id: string;
  super_agent_id: string;
  status: SessionStatus;
  conversation_log?: string;
  summary?: string;
  token_count: number;
  last_compacted_at?: string;
  started_at?: string;
  ended_at?: string;
}

export interface AgentMessage {
  id: string;
  from_agent_id: string;
  to_agent_id?: string;
  message_type: AgentMessageType;
  priority: AgentMessagePriority;
  subject?: string;
  content: string;
  status: AgentMessageStatus;
  ttl_seconds?: number;
  expires_at?: string;
  created_at?: string;
  delivered_at?: string;
  read_at?: string;
}
