// frontend/src/services/api/__tests__/grd.loopconfig.test.ts
import { describe, it, expectTypeOf } from 'vitest';
import type { GoalLoopConfig } from '../grd';

describe('GoalLoopConfig has unified-loop fields', () => {
  it('accepts max_tokens / context_policy / stagnation', () => {
    const c: GoalLoopConfig = {
      goal: 'g', max_iterations: 10, max_tokens: 500000,
      context_policy: 'reset', stagnation_no_progress_for: 3,
    } as GoalLoopConfig;
    expectTypeOf(c.context_policy).toEqualTypeOf<'carry' | 'reset' | undefined>();
  });
});
