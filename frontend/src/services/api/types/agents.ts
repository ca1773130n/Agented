/**
 * Agent, AgentConversation, AgentDocument, and related conversation types.
 */

import type { ConversationStatus, ConversationMessage } from './common';

export type AgentCreationStatus = 'pending' | 'in_progress' | 'completed';
export type EffortLevel = 'low' | 'medium' | 'high' | 'max';
export type AgentLayer = 'backend' | 'frontend' | 'design' | 'analysis' | 'test' | 'management' | 'maintenance' | 'data' | 'mobile';
export type TeamMemberRole = 'leader' | 'member';

export interface AgentDocument {
  name: string;
  path?: string;
  type: 'file' | 'url' | 'inline';
  content?: string;
}

export interface Agent {
  id: string;
  name: string;
  description?: string;
  role?: string;
  goals?: string[];
  context?: string;
  backend_type: 'claude' | 'opencode' | 'gemini' | 'codex';
  enabled: number;
  skills?: string[];
  documents?: AgentDocument[];
  system_prompt?: string;
  creation_conversation_id?: string;
  creation_status: AgentCreationStatus;
  triggers?: string[];
  color?: string;
  icon?: string;
  model?: string;
  temperature?: number;
  tools?: string[];
  autonomous?: number;
  allowed_tools?: string[];
  preferred_model?: string;
  effort_level?: EffortLevel;
  layer?: AgentLayer;
  detected_role?: string;
  matched_skills?: string[];
  created_at?: string;
  updated_at?: string;
}

export interface AgentConversation {
  id: string;
  agent_id?: string;
  status: ConversationStatus;
  messages?: ConversationMessage[];
  messages_parsed?: ConversationMessage[];
  created_at?: string;
  updated_at?: string;
}

export interface SkillInfo {
  name: string;
  description: string;
  source_path?: string;
}

// Skill Conversation API
export interface SkillConversation {
  id: string;
  status: ConversationStatus;
  messages?: ConversationMessage[];
  messages_parsed?: ConversationMessage[];
  created_at?: string;
  updated_at?: string;
}

// Plugin Conversation API
export interface PluginConversation {
  id: string;
  status: ConversationStatus;
  messages?: ConversationMessage[];
  messages_parsed?: ConversationMessage[];
  created_at?: string;
  updated_at?: string;
}

// Hook Conversation API
export interface HookConversation {
  id: string;
  status: ConversationStatus;
  messages_parsed?: ConversationMessage[];
}

// Command Conversation API
export interface CommandConversation {
  id: string;
  status: ConversationStatus;
  messages_parsed?: ConversationMessage[];
}

// Rule Conversation API
export interface RuleConversation {
  id: string;
  status: ConversationStatus;
  messages_parsed?: ConversationMessage[];
}

export interface DesignConversationSummary {
  id: string;
  entity_type: string;
  entity_id: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}
