/**
 * Sketch types.
 */

export type SketchStatus = 'draft' | 'classified' | 'routed' | 'in_progress' | 'collaborating' | 'completed' | 'archived';

export interface Delegation {
  super_agent_id: string;
  name: string;
  task: string;
  status: 'pending' | 'in_progress' | 'completed' | 'error';
}

export interface Sketch {
  id: string;
  title: string;
  content: string;
  project_id?: string;
  status: SketchStatus;
  classification_json?: string;
  routing_json?: string;
  parent_sketch_id?: string;
  created_at?: string;
  updated_at?: string;
}
