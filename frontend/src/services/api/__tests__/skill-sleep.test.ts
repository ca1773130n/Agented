import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../client', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '../client';
import { skillSleepApi } from '../skill-sleep';
// Barrel resolution: the api must also be reachable from the package root.
import { skillSleepApi as barrelApi } from '../index';

const mockFetch = apiFetch as ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
  mockFetch.mockResolvedValue({});
});

describe('skillSleepApi', () => {
  it('is re-exported from the package barrel', () => {
    expect(barrelApi).toBe(skillSleepApi);
  });

  describe('listRuns', () => {
    it('GETs the project-scoped skill-sleep path', async () => {
      await skillSleepApi.listRuns('proj-1');
      expect(apiFetch).toHaveBeenCalledWith('/admin/projects/proj-1/skill-sleep');
    });

    it('encodes the project id', async () => {
      await skillSleepApi.listRuns('proj with space');
      expect(apiFetch).toHaveBeenCalledWith('/admin/projects/proj%20with%20space/skill-sleep');
    });
  });

  describe('adopt', () => {
    it('POSTs to the run-scoped adopt path with no body', async () => {
      await skillSleepApi.adopt('proj-1', 42);
      expect(apiFetch).toHaveBeenCalledWith(
        '/admin/projects/proj-1/skill-sleep/42/adopt',
        { method: 'POST' },
      );
    });
  });

  describe('sleepCandidate', () => {
    it('POSTs candidate_body and includes only set optionals', async () => {
      await skillSleepApi.sleepCandidate('proj-1', 'deploy', {
        candidate_body: 'BODY',
        n: 8,
      });
      const [url, opts] = mockFetch.mock.calls[0];
      expect(url).toBe('/admin/projects/proj-1/skills/deploy/sleep');
      expect(opts.method).toBe('POST');
      const body = JSON.parse(opts.body as string);
      expect(body).toEqual({ candidate_body: 'BODY', n: 8 });
      expect('seed' in body).toBe(false);
      expect('measure' in body).toBe(false);
    });

    it('encodes the skill name', async () => {
      await skillSleepApi.sleepCandidate('p', 'a/b skill', { candidate_body: 'x' });
      expect(mockFetch.mock.calls[0][0]).toBe('/admin/projects/p/skills/a%2Fb%20skill/sleep');
    });
  });

  describe('runRound', () => {
    it('POSTs an empty body by default', async () => {
      await skillSleepApi.runRound('proj-1', 'deploy');
      const [url, opts] = mockFetch.mock.calls[0];
      expect(url).toBe('/admin/projects/proj-1/skills/deploy/sleep/round');
      expect(JSON.parse(opts.body as string)).toEqual({});
    });

    it('spreads only the set optionals (n, edit_budget) into the body', async () => {
      await skillSleepApi.runRound('proj-1', 'deploy', { n: 6, edit_budget: 4 });
      const body = JSON.parse(mockFetch.mock.calls[0][1].body as string);
      expect(body).toEqual({ n: 6, edit_budget: 4 });
      expect('seed' in body).toBe(false);
      expect('measure' in body).toBe(false);
    });

    it('serialises measure=false (a set optional, not omitted)', async () => {
      await skillSleepApi.runRound('proj-1', 'deploy', { measure: false });
      const body = JSON.parse(mockFetch.mock.calls[0][1].body as string);
      expect(body).toEqual({ measure: false });
    });
  });
});
