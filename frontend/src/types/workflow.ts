/**
 * Workflow node data types — typed interfaces for Vue Flow node data.
 *
 * Vue Flow uses `Record<string, unknown>` for node data. These interfaces
 * provide typed access to our known workflow node data shape, replacing
 * unsafe `as any` casts with intentional type narrowing.
 */

export interface WorkflowNodeData {
  label?: string
  config?: Record<string, unknown>
  error_mode?: 'stop' | 'continue' | 'continue_with_error'
  retry_max?: number
  retry_backoff_seconds?: number
  executionStatus?: string
}
