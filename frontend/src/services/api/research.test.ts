import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('./client', () => ({
  apiFetch: vi.fn(),
  createAuthenticatedEventSource: vi.fn(() => ({ close: vi.fn() })),
}));

import { apiFetch, createAuthenticatedEventSource } from './client';
import { researchApi } from './research';

beforeEach(() => {
  vi.clearAllMocks();
});

describe('researchApi', () => {
  it('startResearch POSTs question to /research/start', async () => {
    (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue({ session_id: 'sess-1' });
    await researchApi.startResearch('proj-1', 'why is the sky blue?');
    expect(apiFetch).toHaveBeenCalledWith('/api/projects/proj-1/research/start', {
      method: 'POST',
      body: JSON.stringify({ question: 'why is the sky blue?' }),
    });
  });

  it('startResearch appends optional knobs only when provided', async () => {
    (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue({ session_id: 'sess-2' });
    await researchApi.startResearch('proj-1', 'q', { max_iterations: 5, no_gates: true });
    expect(apiFetch).toHaveBeenCalledWith('/api/projects/proj-1/research/start', {
      method: 'POST',
      body: JSON.stringify({ question: 'q', max_iterations: 5, no_gates: true }),
    });
  });

  it('resumeThread POSTs to /research/{threadId}/resume with empty body by default', async () => {
    (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue({ session_id: 'sess-3' });
    await researchApi.resumeThread('proj-1', 'thread-9');
    expect(apiFetch).toHaveBeenCalledWith('/api/projects/proj-1/research/thread-9/resume', {
      method: 'POST',
      body: JSON.stringify({}),
    });
  });

  it('resumeThread carries optional knobs', async () => {
    (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue({ session_id: 'sess-4' });
    await researchApi.resumeThread('proj-1', 'thread-9', { max_iterations: 3 });
    expect(apiFetch).toHaveBeenCalledWith('/api/projects/proj-1/research/thread-9/resume', {
      method: 'POST',
      body: JSON.stringify({ max_iterations: 3 }),
    });
  });

  it('listThreads GETs /research/threads', async () => {
    (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue({ threads: [] });
    await researchApi.listThreads('proj-1');
    expect(apiFetch).toHaveBeenCalledWith('/api/projects/proj-1/research/threads');
  });

  it('getThread GETs /research/threads/{threadId}', async () => {
    (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: 'thread-9',
      thread: null,
      hypotheses: null,
      finding: null,
    });
    await researchApi.getThread('proj-1', 'thread-9');
    expect(apiFetch).toHaveBeenCalledWith('/api/projects/proj-1/research/threads/thread-9');
  });

  it('startResearch includes deep/ultracode only when set', async () => {
    (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue({ session_id: 'sess-d' });
    await researchApi.startResearch('proj-1', 'q', { deep: true, ultracode: true });
    expect(apiFetch).toHaveBeenCalledWith('/api/projects/proj-1/research/start', {
      method: 'POST',
      body: JSON.stringify({ question: 'q', deep: true, ultracode: true }),
    });
  });

  it('startResearch omits deep/ultracode when unset', async () => {
    (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue({ session_id: 'sess-l' });
    await researchApi.startResearch('proj-1', 'q');
    expect(apiFetch).toHaveBeenCalledWith('/api/projects/proj-1/research/start', {
      method: 'POST',
      body: JSON.stringify({ question: 'q' }),
    });
  });

  it('listDeepReports GETs /research/deep-reports', async () => {
    (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue({ reports: [] });
    await researchApi.listDeepReports('proj-1');
    expect(apiFetch).toHaveBeenCalledWith('/api/projects/proj-1/research/deep-reports');
  });

  it('getDeepReport GETs /research/deep-reports/{name} url-encoded', async () => {
    (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue({ name: 'a b.md', markdown: null });
    await researchApi.getDeepReport('proj-1', 'a b.md');
    expect(apiFetch).toHaveBeenCalledWith(
      '/api/projects/proj-1/research/deep-reports/a%20b.md',
    );
  });

  it('streamResearch opens the generic session-stream SSE URL', () => {
    researchApi.streamResearch('proj-1', 'sess-7');
    expect(createAuthenticatedEventSource).toHaveBeenCalledWith(
      '/api/projects/proj-1/sessions/sess-7/stream',
      undefined,
    );
  });
});
