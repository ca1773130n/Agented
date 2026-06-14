import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('./client', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from './client';
import { grdHarnessApi } from './grdHarness';

const mock = () => apiFetch as ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
  (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue({});
});

describe('grdHarnessApi — Group A (/api/projects/{id}/grd/*)', () => {
  it('getHealth GETs /grd/health', async () => {
    await grdHarnessApi.getHealth('p1');
    expect(mock()).toHaveBeenCalledWith('/api/projects/p1/grd/health');
  });

  it('think POSTs /grd/think', async () => {
    await grdHarnessApi.think('p1');
    expect(mock()).toHaveBeenCalledWith('/api/projects/p1/grd/think', { method: 'POST' });
  });

  it('addDeadEnd POSTs the entry body', async () => {
    await grdHarnessApi.addDeadEnd('p1', { approach: 'a', reason: 'r', phase: '3' });
    expect(mock()).toHaveBeenCalledWith('/api/projects/p1/grd/dead-ends', {
      method: 'POST',
      body: JSON.stringify({ approach: 'a', reason: 'r', phase: '3' }),
    });
  });

  it('promoteDeadEnds POSTs the phase route', async () => {
    await grdHarnessApi.promoteDeadEnds('p1', '4');
    expect(mock()).toHaveBeenCalledWith(
      '/api/projects/p1/grd/dead-ends/promote-from-phase/4',
      { method: 'POST' },
    );
  });

  it('listDeadEnds GETs /grd/dead-ends', async () => {
    await grdHarnessApi.listDeadEnds('p1');
    expect(mock()).toHaveBeenCalledWith('/api/projects/p1/grd/dead-ends');
  });

  it('getGenome GETs /grd/genome', async () => {
    await grdHarnessApi.getGenome('p1');
    expect(mock()).toHaveBeenCalledWith('/api/projects/p1/grd/genome');
  });

  it('snapshotGenome POSTs /grd/genome/snapshot', async () => {
    await grdHarnessApi.snapshotGenome('p1');
    expect(mock()).toHaveBeenCalledWith('/api/projects/p1/grd/genome/snapshot', {
      method: 'POST',
    });
  });

  it('listGenomeSnapshots GETs /grd/genome/snapshots', async () => {
    await grdHarnessApi.listGenomeSnapshots('p1');
    expect(mock()).toHaveBeenCalledWith('/api/projects/p1/grd/genome/snapshots');
  });

  it('latestGenomeSnapshot GETs /grd/genome/latest', async () => {
    await grdHarnessApi.latestGenomeSnapshot('p1');
    expect(mock()).toHaveBeenCalledWith('/api/projects/p1/grd/genome/latest');
  });

  it('verifyMechanical POSTs /grd/verify/mechanical/{phase}', async () => {
    await grdHarnessApi.verifyMechanical('p1', '5');
    expect(mock()).toHaveBeenCalledWith('/api/projects/p1/grd/verify/mechanical/5', {
      method: 'POST',
    });
  });

  it('listPhaseReflections GETs /grd/phases/{phaseId}/reflections', async () => {
    await grdHarnessApi.listPhaseReflections('p1', 'ph-9');
    expect(mock()).toHaveBeenCalledWith('/api/projects/p1/grd/phases/ph-9/reflections');
  });

  it('verdictCounts GETs /grd/verdict-counts', async () => {
    await grdHarnessApi.verdictCounts('p1');
    expect(mock()).toHaveBeenCalledWith('/api/projects/p1/grd/verdict-counts');
  });

  it('startEvolve POSTs /grd/evolve/start with config body', async () => {
    await grdHarnessApi.startEvolve('p1', { iterations: 3 });
    expect(mock()).toHaveBeenCalledWith('/api/projects/p1/grd/evolve/start', {
      method: 'POST',
      body: JSON.stringify({ iterations: 3 }),
    });
  });

  it('startEvolve defaults to empty body', async () => {
    await grdHarnessApi.startEvolve('p1');
    expect(mock()).toHaveBeenCalledWith('/api/projects/p1/grd/evolve/start', {
      method: 'POST',
      body: JSON.stringify({}),
    });
  });

  it('listEvolveRuns GETs /grd/evolve/runs with query', async () => {
    await grdHarnessApi.listEvolveRuns('p1', 'active', 5);
    expect(mock()).toHaveBeenCalledWith(
      '/api/projects/p1/grd/evolve/runs?status=active&limit=5',
    );
  });

  it('getEvolveRun GETs /grd/evolve/runs/{runId}', async () => {
    await grdHarnessApi.getEvolveRun('p1', 'run-7');
    expect(mock()).toHaveBeenCalledWith('/api/projects/p1/grd/evolve/runs/run-7');
  });

  it('stopEvolveRun POSTs /grd/evolve/runs/{runId}/stop', async () => {
    await grdHarnessApi.stopEvolveRun('p1', 'run-7');
    expect(mock()).toHaveBeenCalledWith('/api/projects/p1/grd/evolve/runs/run-7/stop', {
      method: 'POST',
    });
  });
});

describe('grdHarnessApi — Group B (/admin/* admin-gated)', () => {
  it('getAutonomy GETs the /admin base', async () => {
    await grdHarnessApi.getAutonomy('p1');
    const url = mock().mock.calls[0][0] as string;
    expect(url).toBe('/admin/projects/p1/autonomy');
    expect(url.startsWith('/admin/')).toBe(true);
  });

  it('setAutonomy PUTs {policy} to the /admin base', async () => {
    await grdHarnessApi.setAutonomy('p1', { auto_apply: true });
    expect(mock()).toHaveBeenCalledWith('/admin/projects/p1/autonomy', {
      method: 'PUT',
      body: JSON.stringify({ policy: { auto_apply: true } }),
    });
  });

  it('listProjectRounds GETs /admin project rounds', async () => {
    await grdHarnessApi.listProjectRounds('p1', 10);
    expect(mock()).toHaveBeenCalledWith('/admin/projects/p1/evolution/rounds?limit=10');
  });

  it('listAllRounds GETs /admin/evolution/rounds', async () => {
    await grdHarnessApi.listAllRounds(50, 'applied');
    expect(mock()).toHaveBeenCalledWith('/admin/evolution/rounds?limit=50&status=applied');
  });

  it('getRoundDetail GETs /admin/evolution/rounds/{rid}', async () => {
    await grdHarnessApi.getRoundDetail('r-1');
    expect(mock()).toHaveBeenCalledWith('/admin/evolution/rounds/r-1');
  });

  it('getRoundImpact GETs /admin .../impact', async () => {
    await grdHarnessApi.getRoundImpact('r-1', 30);
    expect(mock()).toHaveBeenCalledWith('/admin/evolution/rounds/r-1/impact?window=30');
  });

  it('approveRound POSTs /admin .../apply', async () => {
    await grdHarnessApi.approveRound('r-1');
    expect(mock()).toHaveBeenCalledWith('/admin/evolution/rounds/r-1/apply', {
      method: 'POST',
    });
  });

  it('abortRound POSTs /admin .../abort with reason', async () => {
    await grdHarnessApi.abortRound('r-1', 'bad');
    expect(mock()).toHaveBeenCalledWith('/admin/evolution/rounds/r-1/abort', {
      method: 'POST',
      body: JSON.stringify({ reason: 'bad' }),
    });
  });

  it('revertRound POSTs /admin .../revert (destructive)', async () => {
    await grdHarnessApi.revertRound('r-1', true);
    expect(mock()).toHaveBeenCalledWith('/admin/evolution/rounds/r-1/revert', {
      method: 'POST',
      body: JSON.stringify({ force: true }),
    });
  });

  it('listSharedForge GETs /admin/shared-forge', async () => {
    await grdHarnessApi.listSharedForge();
    expect(mock()).toHaveBeenCalledWith('/admin/shared-forge');
  });

  it('adoptShared POSTs /admin .../adopt-shared/{bindingId}', async () => {
    await grdHarnessApi.adoptShared('p1', 42);
    expect(mock()).toHaveBeenCalledWith('/admin/projects/p1/adopt-shared/42', {
      method: 'POST',
    });
  });

  it('every Group B method targets the /admin base', async () => {
    vi.clearAllMocks();
    (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue({});
    await grdHarnessApi.getAutonomy('p1');
    await grdHarnessApi.setAutonomy('p1', {});
    await grdHarnessApi.listProjectRounds('p1');
    await grdHarnessApi.listAllRounds();
    await grdHarnessApi.getRoundDetail('r');
    await grdHarnessApi.getRoundImpact('r');
    await grdHarnessApi.approveRound('r');
    await grdHarnessApi.abortRound('r');
    await grdHarnessApi.revertRound('r');
    await grdHarnessApi.listSharedForge();
    await grdHarnessApi.adoptShared('p1', 1);
    for (const call of mock().mock.calls) {
      expect((call[0] as string).startsWith('/admin/')).toBe(true);
    }
  });
});

describe('grdHarnessApi — life-harness rounds', () => {
  it('runHarnessRound POSTs /grd/harness/round with opts', async () => {
    await grdHarnessApi.runHarnessRound('p1', { auto: true });
    expect(mock()).toHaveBeenCalledWith('/api/projects/p1/grd/harness/round', {
      method: 'POST',
      body: JSON.stringify({ auto: true }),
    });
  });

  it('runHarnessRound defaults to empty body', async () => {
    await grdHarnessApi.runHarnessRound('p1');
    expect(mock()).toHaveBeenCalledWith('/api/projects/p1/grd/harness/round', {
      method: 'POST',
      body: JSON.stringify({}),
    });
  });

  it('listHarnessRounds GETs /grd/harness/rounds with limit', async () => {
    await grdHarnessApi.listHarnessRounds('p1', 10);
    expect(mock()).toHaveBeenCalledWith('/api/projects/p1/grd/harness/rounds?limit=10');
  });

  it('getHarnessRound GETs the round', async () => {
    await grdHarnessApi.getHarnessRound('p1', '20260614-120000');
    expect(mock()).toHaveBeenCalledWith('/api/projects/p1/grd/harness/rounds/20260614-120000');
  });

  it('revertHarnessRound POSTs revert', async () => {
    await grdHarnessApi.revertHarnessRound('p1', 'r1');
    expect(mock()).toHaveBeenCalledWith('/api/projects/p1/grd/harness/rounds/r1/revert', {
      method: 'POST',
    });
  });

  it('harnessStatus GETs status', async () => {
    await grdHarnessApi.harnessStatus('p1');
    expect(mock()).toHaveBeenCalledWith('/api/projects/p1/grd/harness/status');
  });
});
