/**
 * Sketch types.
 */

export type SketchStatus = 'draft' | 'classified' | 'routed' | 'in_progress' | 'completed' | 'archived';

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
