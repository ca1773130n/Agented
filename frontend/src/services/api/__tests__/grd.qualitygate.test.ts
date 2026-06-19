// frontend/src/services/api/__tests__/grd.qualitygate.test.ts
import { describe, it, expectTypeOf } from 'vitest';
import type { GoalLoopConfig } from '../grd';

describe('GoalLoopConfig quality-gate + sandbox', () => {
  it('accepts a quality_gate + sandbox', () => {
    const c: GoalLoopConfig = {
      goal: 'g',
      quality_gate: { kind: 'llm_judge', rubric: 'strict', judge_version: 'v2', min_confidence: 0.7 },
      sandbox: 'isolated',
    } as GoalLoopConfig;
    expectTypeOf(c.sandbox).toEqualTypeOf<'isolated' | 'inherit' | undefined>();
  });
});
