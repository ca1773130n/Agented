/**
 * Workflow and WorkflowExecution types.
 */

export type WorkflowExecutionStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled' | 'pending_approval';
export type WorkflowNodeType = 'trigger' | 'skill' | 'command' | 'agent' | 'script' | 'conditional' | 'transform' | 'approval_gate';
export type NodeExecutionStatus = 'pending' | 'running' | 'completed' | 'failed' | 'skipped' | 'pending_approval';

export interface Workflow {
  id: string;
  name: string;
  description?: string;
  trigger_type: string;
  trigger_config?: string;
  enabled: number;
  created_at?: string;
  updated_at?: string;
}

export interface WorkflowVersion {
  id: number;
  workflow_id: string;
  version: number;
  graph_json: string;
  is_draft: number;
  created_at?: string;
}

export interface WorkflowExecution {
  id: string;
  workflow_id: string;
  version: number;
  status: WorkflowExecutionStatus;
  input_json?: string;
  output_json?: string;
  error?: string;
  started_at?: string;
  ended_at?: string;
}

export interface WorkflowNodeExecution {
  id: number;
  execution_id: string;
  node_id: string;
  node_type: WorkflowNodeType;
  status: NodeExecutionStatus;
  input_json?: string;
  output_json?: string;
  error?: string;
  started_at?: string;
  ended_at?: string;
}
