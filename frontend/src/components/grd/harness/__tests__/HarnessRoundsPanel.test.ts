import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import HarnessRoundsPanel from '../panels/HarnessRoundsPanel.vue';
import { grdHarnessApi } from '../../../../services/api';

vi.mock('../../../../services/api', () => ({
  grdHarnessApi: {
    listHarnessRounds: vi.fn(),
    runHarnessRound: vi.fn(),
    revertHarnessRound: vi.fn(),
  },
}));

const mockApi = () => grdHarnessApi as unknown as Record<string, ReturnType<typeof vi.fn>>;

describe('HarnessRoundsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApi().listHarnessRounds.mockResolvedValue({
      rounds: [
        { round_id: '20260614-120000', status: 'applied', summary: 'tweak', confidence: 0.7, applied_sha: 'sha9' },
        { round_id: '20260614-110000', status: 'rejected', summary: 'noop', confidence: 0.2 },
      ],
    });
    mockApi().runHarnessRound.mockResolvedValue({ status: 'running' });
    mockApi().revertHarnessRound.mockResolvedValue({ success: true });
  });

  it('lists rounds on mount', async () => {
    const w = mount(HarnessRoundsPanel, { props: { projectId: 'p1' } });
    await flushPromises();
    expect(mockApi().listHarnessRounds).toHaveBeenCalledWith('p1');
    expect(w.text()).toContain('20260614-120000');
    expect(w.text()).toContain('applied');
  });

  it('runs a round (with the auto flag) from the Run button', async () => {
    const w = mount(HarnessRoundsPanel, { props: { projectId: 'p1' } });
    await flushPromises();
    await w.find('input[type="checkbox"]').setValue(true);
    await w.find('[data-testid="run-round"]').trigger('click');
    await flushPromises();
    expect(mockApi().runHarnessRound).toHaveBeenCalledWith('p1', { auto: true });
  });

  it('reverts only applied rounds', async () => {
    const w = mount(HarnessRoundsPanel, { props: { projectId: 'p1' } });
    await flushPromises();
    // Applied round has a revert button; the rejected one does not.
    expect(w.find('[data-testid="revert-20260614-110000"]').exists()).toBe(false);
    await w.find('[data-testid="revert-20260614-120000"]').trigger('click');
    await flushPromises();
    expect(mockApi().revertHarnessRound).toHaveBeenCalledWith('p1', '20260614-120000');
  });
});
