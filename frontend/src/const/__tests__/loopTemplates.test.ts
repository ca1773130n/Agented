// loopTemplates.test.ts
import { LOOP_TEMPLATES } from '../loopTemplates';
import { describe, it, expect } from 'vitest';
describe('LOOP_TEMPLATES', () => {
  it('has the three patterns with correct execution types', () => {
    const ids = LOOP_TEMPLATES.map(t => t.id);
    expect(ids).toEqual(['agentic_task', 'eval_refine', 'custom']);
    expect(LOOP_TEMPLATES.find(t => t.id === 'agentic_task')!.executionType).toBe('ralph_loop');
    expect(LOOP_TEMPLATES.find(t => t.id === 'eval_refine')!.executionType).toBe('goal_loop');
    expect(LOOP_TEMPLATES.find(t => t.id === 'custom')!.executionType).toBe('goal_loop');
  });
  it('eval_refine seeds an llm_judge quality gate + min_confidence', () => {
    const t = LOOP_TEMPLATES.find(x => x.id === 'eval_refine')!;
    expect((t.config as any).quality_gate.kind).toBe('llm_judge');
    expect((t.config as any).quality_gate.min_confidence).toBeGreaterThan(0);
  });
});
