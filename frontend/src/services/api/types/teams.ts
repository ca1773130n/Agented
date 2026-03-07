/**
 * Team, TeamMember, TeamEdge, TopologyConfig, and related types.
 */

import type { EntityType } from './common';
import type { TriggerSource } from './triggers';

export type TopologyType = 'sequential' | 'parallel' | 'coordinator' | 'generator_critic' | 'hierarchical' | 'human_in_loop' | 'composite';
export type TeamEdgeType = 'delegation' | 'reporting' | 'messaging' | 'approval_gate';
export type CanvasEdgeType = 'command' | 'report' | 'peer' | 'inter_team' | 'messaging';

export interface TeamMember {
  id: number;
  team_id: string;
  name: string;
  email?: string;
  role: string;
  layer?: string;
  description?: string;
  agent_id?: string;
  super_agent_id?: string;
  member_type?: string;        // 'agent' | 'super_agent' | 'manual'
  agent_name?: string;         // from JOIN
  super_agent_name?: string;   // from JOIN
  tier?: string;               // 'leader' | 'senior' | 'member'
  created_at?: string;
}

export interface TeamConnection {
  id: number;
  source_team_id: string;
  target_team_id: string;
  connection_type: string;
  description?: string;
  created_at?: string;
}

export interface TeamEdge {
  id: number;
  team_id: string;
  source_member_id: number;
  target_member_id: number;
  edge_type: TeamEdgeType;
  label?: string;
  weight: number;
  created_at?: string;
}

export interface TeamAgentAssignment {
  id: number;
  team_id: string;
  agent_id: string;
  entity_type: EntityType;
  entity_id: string;
  entity_name?: string;
  created_at?: string;
}

export interface CanvasPosition {
  x: number;
  y: number;
}

export interface CanvasPositions {
  [agentId: string]: CanvasPosition;
}

export interface TopologyConfig {
  order?: string[];           // sequential
  agents?: string[];          // parallel
  coordinator?: string;       // coordinator
  workers?: string[];         // coordinator
  generator?: string;         // generator_critic
  critic?: string;            // generator_critic
  max_iterations?: number;    // generator_critic
  aggregation?: string;       // parallel
  lead?: string;              // hierarchical
  approval_nodes?: string[];  // human_in_loop
  sub_groups?: {              // composite
    topology: TopologyType;
    config: Record<string, unknown>;
    members?: string[];
  }[];
  positions?: CanvasPositions; // Canvas node positions
  edges?: { id?: string; source: string; target: string; label?: string; type?: string }[];
}

export interface Team {
  id: string;
  name: string;
  description?: string;
  color: string;
  leader_id?: string;
  leader_name?: string;
  member_count: number;
  source?: string;  // 'ui_created' or 'github_sync'
  topology?: TopologyType;
  topology_config?: string;
  trigger_source?: TriggerSource;
  trigger_config?: string;
  enabled?: number;
  created_at?: string;
  updated_at?: string;
  members?: TeamMember[];
}

// Generated team config types
export interface GeneratedAgentConfig {
  agent_id: string | null;
  name: string;
  role: string;
  valid?: boolean;
  assignments: {
    entity_type: EntityType;
    entity_id: string;
    entity_name: string;
    valid?: boolean;
    needs_creation?: boolean;
  }[];
}

export interface GeneratedTeamConfig {
  name: string;
  description: string;
  topology: TopologyType;
  topology_config: TopologyConfig;
  color: string;
  agents: GeneratedAgentConfig[];
}
