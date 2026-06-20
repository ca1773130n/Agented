// frontend/src/services/api/__tests__/grd.loopcontrol.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
vi.mock('../client', () => ({ apiFetch: vi.fn() }));
import { apiFetch } from '../client';
import { grdApi } from '../grd';
const mock = () => apiFetch as ReturnType<typeof vi.fn>;
beforeEach(() => { vi.clearAllMocks(); (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue({}); });

describe('loop control client', () => {
  it('interveneLoop POSTs message', async () => {
    await grdApi.interveneLoop('p', 's', 'do X');
    expect(mock()).toHaveBeenCalledWith('/api/projects/p/sessions/s/loop/intervene',
      { method: 'POST', body: JSON.stringify({ message: 'do X' }) });
  });
  it('gateDecision POSTs decision + message', async () => {
    await grdApi.gateDecision('p', 's', 'modify', 'add test');
    expect(mock()).toHaveBeenCalledWith('/api/projects/p/sessions/s/loop/gate-decision',
      { method: 'POST', body: JSON.stringify({ decision: 'modify', message: 'add test' }) });
  });
});
