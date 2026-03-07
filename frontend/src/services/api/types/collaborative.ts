/**
 * Collaborative viewer types.
 */

export interface ViewerInfo {
  viewer_id: string;
  name: string;
  joined_at: string;
}

export interface InlineComment {
  id: string;
  execution_id: string;
  viewer_id: string;
  viewer_name: string;
  line_number: number;
  content: string;
  created_at: string;
}
