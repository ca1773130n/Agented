// frontend/src/const/loopTemplates.ts
import type { GoalLoopConfig, RalphConfig } from '../services/api/grd';
export type LoopExecutionType = 'goal_loop' | 'ralph_loop';
export interface LoopTemplate {
  id: 'agentic_task' | 'eval_refine' | 'custom';
  labelKey: string;        // loopBuilder.tpl.<id>.label
  descKey: string;         // loopBuilder.tpl.<id>.desc
  executionType: LoopExecutionType;
  config: Partial<GoalLoopConfig> | Partial<RalphConfig>;
}
export const LOOP_TEMPLATES: LoopTemplate[] = [
  { id: 'agentic_task', labelKey: 'loopBuilder.tpl.agentic_task.label', descKey: 'loopBuilder.tpl.agentic_task.desc',
    executionType: 'ralph_loop',
    config: { task_description: '', max_iterations: 50, no_progress_threshold: 3, completion_promise: 'COMPLETE' } },
  { id: 'eval_refine', labelKey: 'loopBuilder.tpl.eval_refine.label', descKey: 'loopBuilder.tpl.eval_refine.desc',
    executionType: 'goal_loop',
    config: { goal: '', max_iterations: 20, ouroboros: true, context_policy: 'carry',
      quality_gate: { kind: 'llm_judge', min_confidence: 0.7 }, sandbox: 'isolated' } },
  { id: 'custom', labelKey: 'loopBuilder.tpl.custom.label', descKey: 'loopBuilder.tpl.custom.desc',
    executionType: 'goal_loop', config: { goal: '', max_iterations: 20 } },
];
