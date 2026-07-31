import { describe, it, expect, vi } from 'vitest';
import { formatApiError, handleApiError } from '../api/error-handler';
import { ApiError } from '../api/client';

describe('formatApiError', () => {
  describe('known status codes from STATUS_MAP', () => {
    it.each([
      [401, 'ERR-401'],
      [403, 'ERR-403'],
      [404, 'ERR-404'],
      [409, 'ERR-409'],
      [422, 'ERR-422'],
      [429, 'ERR-429'],
      [500, 'ERR-500'],
      [503, 'ERR-503'],
      [0, 'ERR-TIMEOUT'],
    ])('formats status %i with code %s', (status, expectedCode) => {
      const result = formatApiError(status);
      expect(result).toContain(expectedCode);
    });
  });

  it('includes server message when it differs from generic HTTP status', () => {
    const result = formatApiError(404, 'Agent not found');
    expect(result).toContain('Agent not found');
    expect(result).toContain('ERR-404');
  });

  it('excludes redundant server message that matches generic HTTP status format', () => {
    const result = formatApiError(404, 'HTTP 404');
    // The server message "HTTP 404" is the generic message, so it should NOT appear as a detail
    expect(result).not.toContain(': HTTP 404');
    expect(result).toContain('ERR-404');
  });

  it('handles unknown status codes with ERR-{status} fallback', () => {
    const result = formatApiError(418);
    expect(result).toContain('ERR-418');
  });

  it('includes server message for unknown status codes', () => {
    const result = formatApiError(418, "I'm a teapot");
    expect(result).toContain("I'm a teapot");
  });

  it('returns generic fallback for unknown status when no server message', () => {
    const result = formatApiError(999);
    expect(result).toContain('ERR-999');
    expect(result).toContain('Try again');
  });

  it('includes actionable suggestion for known status 401', () => {
    const result = formatApiError(401);
    // Should mention Settings or API key per STATUS_MAP action for 401
    expect(result.toLowerCase()).toMatch(/settings|api key/);
  });

  it('includes action for 404', () => {
    const result = formatApiError(404);
    expect(result).toContain('ERR-404');
    // Should include action text about returning to list
    expect(result.length).toBeGreaterThan('Not found (ERR-404).'.length);
  });

  it('formats 0 (timeout) with ERR-TIMEOUT code', () => {
    const result = formatApiError(0);
    expect(result).toContain('ERR-TIMEOUT');
    expect(result).toContain('connection');
  });
});

describe('handleApiError', () => {
  it('calls showToast with "error" type for ApiError', () => {
    const mockShowToast = vi.fn();
    handleApiError(new ApiError(404, 'Not found'), mockShowToast);
    expect(mockShowToast).toHaveBeenCalledTimes(1);
    expect(mockShowToast).toHaveBeenCalledWith(expect.any(String), 'error');
  });

  it('returns formatted message string containing error code for ApiError', () => {
    const mockShowToast = vi.fn();
    const result = handleApiError(new ApiError(404, 'Not found'), mockShowToast);
    expect(result).toContain('ERR-404');
  });

  it('handles generic Error objects with ERR-UNKNOWN code', () => {
    const mockShowToast = vi.fn();
    const result = handleApiError(new Error('Network failed'), mockShowToast);
    expect(mockShowToast).toHaveBeenCalledWith(expect.stringContaining('ERR-UNKNOWN'), 'error');
    expect(result).toContain('ERR-UNKNOWN');
    expect(result).toContain('Network failed');
  });

  it('uses fallback message for non-Error objects', () => {
    const mockShowToast = vi.fn();
    const result = handleApiError('string error', mockShowToast, 'Fallback message');
    expect(mockShowToast).toHaveBeenCalledWith(expect.stringContaining('ERR-UNKNOWN'), 'error');
    expect(result).toContain('Fallback message');
    expect(result).toContain('ERR-UNKNOWN');
  });

  it('uses default fallback message when no fallbackMessage provided for non-Error', () => {
    const mockShowToast = vi.fn();
    const result = handleApiError(42, mockShowToast);
    expect(result).toContain('ERR-UNKNOWN');
    expect(result).toContain('unexpected error');
  });

  it('returns the same formatted string that is passed to showToast', () => {
    const mockShowToast = vi.fn();
    const result = handleApiError(new ApiError(500, 'Internal error'), mockShowToast);
    expect(mockShowToast).toHaveBeenCalledWith(result, 'error');
  });

  it('formats ApiError with server message detail', () => {
    const mockShowToast = vi.fn();
    const result = handleApiError(new ApiError(404, 'Specific resource not found'), mockShowToast);
    expect(result).toContain('Specific resource not found');
    expect(result).toContain('ERR-404');
  });

  it('always calls showToast regardless of error type', () => {
    const mockShowToast = vi.fn();
    handleApiError(new ApiError(401, 'Unauthorized'), mockShowToast);
    handleApiError(new Error('Something'), mockShowToast);
    handleApiError(null, mockShowToast);
    expect(mockShowToast).toHaveBeenCalledTimes(3);
  });
});

describe('handleApiError — transient network failures', () => {
  // These must never reach the autofix pipeline: it acts on defects in our
  // code, and no source change can fix a dropped connection.
  it('does not report a failed fetch to the backend', async () => {
    const reportError = vi.fn().mockResolvedValue(undefined);
    vi.doMock('../api/system', () => ({ systemErrorApi: { reportError } }));

    handleApiError(new TypeError('Failed to fetch'), vi.fn());
    await new Promise((r) => setTimeout(r, 0));

    expect(reportError).not.toHaveBeenCalled();
    vi.doUnmock('../api/system');
  });

  it('shows an infrastructure toast, not an error toast', () => {
    const showToast = vi.fn();
    handleApiError(new TypeError('Failed to fetch'), showToast);
    expect(showToast).toHaveBeenCalledWith(expect.any(String), 'infrastructure');
  });

  it('replaces the unactionable "Failed to fetch" with something a user can act on', () => {
    const result = handleApiError(new TypeError('Failed to fetch'), vi.fn());
    expect(result).toContain('ERR-NETWORK');
    expect(result).not.toContain('Failed to fetch');
  });

  it('treats an aborted request as transient', () => {
    const showToast = vi.fn();
    const abort = new DOMException('The user aborted a request.', 'AbortError');
    handleApiError(abort, showToast);
    expect(showToast).toHaveBeenCalledWith(expect.any(String), 'infrastructure');
  });

  it('still reports a genuine application error', async () => {
    const showToast = vi.fn();
    const result = handleApiError(new Error('Cannot read property of undefined'), showToast);
    expect(showToast).toHaveBeenCalledWith(expect.any(String), 'error');
    expect(result).toContain('ERR-UNKNOWN');
  });

  it('does not misclassify an unrelated TypeError as a network failure', () => {
    const showToast = vi.fn();
    handleApiError(new TypeError('x.map is not a function'), showToast);
    expect(showToast).toHaveBeenCalledWith(expect.any(String), 'error');
  });
});
