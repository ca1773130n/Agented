/**
 * Centralized API error handler with user-friendly messages, error codes, and suggested actions.
 *
 * Provides:
 * - STATUS_MAP: Maps HTTP status codes to structured error info (code, message, action)
 * - formatApiError(): Formats a status code into a user-facing string with error code and action
 * - handleApiError(): Shows a toast notification for any error and returns the formatted message
 */

import { ApiError } from './client';

export interface ErrorMapping {
  code: string;
  message: string;
  action: string;
}

export const STATUS_MAP: Record<number, ErrorMapping> = {
  0: {
    code: 'ERR-TIMEOUT',
    message: 'Request timed out',
    action: 'Check your connection and try again.',
  },
  401: {
    code: 'ERR-401',
    message: 'Unauthorized',
    action: 'Check your API key in Settings.',
  },
  403: {
    code: 'ERR-403',
    message: 'Forbidden',
    action: 'You do not have permission for this action.',
  },
  404: {
    code: 'ERR-404',
    message: 'Not found',
    action: 'The resource may have been deleted. Return to the list.',
  },
  409: {
    code: 'ERR-409',
    message: 'Conflict',
    action: 'The resource was modified. Refresh and try again.',
  },
  422: {
    code: 'ERR-422',
    message: 'Validation error',
    action: 'Check your input and try again.',
  },
  429: {
    code: 'ERR-429',
    message: 'Rate limited',
    action: 'Wait a moment and try again.',
  },
  500: {
    code: 'ERR-500',
    message: 'Server error',
    action: 'The server encountered an error. Try again later.',
  },
  503: {
    code: 'ERR-503',
    message: 'Service unavailable',
    action: 'The service is temporarily down. Try again shortly.',
  },
};

/**
 * Format an HTTP status code into a user-facing error string.
 *
 * If the status is in STATUS_MAP, returns:
 *   "{message}{detail} ({code}). {action}"
 * where detail includes the serverMessage if it differs from the generic "HTTP {status}".
 *
 * If not in STATUS_MAP, returns the serverMessage or a generic fallback.
 */
export function formatApiError(status: number, serverMessage?: string): string {
  const mapping = STATUS_MAP[status];

  if (mapping) {
    const genericHttp = `HTTP ${status}`;
    const detail =
      serverMessage && serverMessage !== genericHttp ? `: ${serverMessage}` : '';
    return `${mapping.message}${detail} (${mapping.code}). ${mapping.action}`;
  }

  return serverMessage || `Unexpected error (ERR-${status}). Try again or contact support.`;
}

/**
 * PR-G — detects a 501 "Feature not yet enabled" response from a backend stub.
 *
 * Used by `AnomalyDetectionCard` so it can render a static "not yet enabled" banner
 * instead of falling through to a generic error toast or — worse — the
 * legacy demo-on-failure fallback that masked the missing feature.
 *
 * Accepts both our `ApiError` (where `status` is a top-level field) and
 * raw `fetch`-style errors where the caller hung a `response.status` on
 * the thrown object.
 */
export function isNotImplemented(err: unknown): boolean {
  if (!err || typeof err !== 'object') return false;
  if (err instanceof ApiError) return err.status === 501;
  const e = err as { status?: number; response?: { status?: number } };
  if (e.status === 501) return true;
  if (e.response && e.response.status === 501) return true;
  return false;
}

/**
 * Connection-level failures that no source change can fix: the server is
 * unreachable, a CORS preflight was denied, or the request was aborted.
 *
 * These must not reach the autofix pipeline. It exists to act on defects in
 * *our* code, and a network blip is indistinguishable from one once it has been
 * flattened into a message string — so every dropped connection becomes an
 * error report that autofix can never resolve.
 *
 * `fetch` rejects with a bare `TypeError` for all of these (the spec gives no
 * distinguishable subclass), and an aborted request surfaces as a DOMException
 * named AbortError.
 */
function isTransientNetworkError(error: unknown): boolean {
  if (error instanceof TypeError && /fetch|network/i.test(error.message)) {
    return true;
  }
  if (
    typeof DOMException !== 'undefined' &&
    error instanceof DOMException &&
    error.name === 'AbortError'
  ) {
    return true;
  }
  return false;
}

/**
 * Handle any error by showing a toast notification and returning the formatted message.
 *
 * - ApiError: uses formatApiError with the status and message
 * - Transient network error (TypeError: Failed to fetch / AbortError):
 *   shows an 'infrastructure' toast and skips backend reporting
 * - Generic Error: shows the error message with ERR-UNKNOWN
 * - Other: shows the fallbackMessage with ERR-UNKNOWN
 *
 * Always returns the formatted string so callers can set local error state.
 */
export function handleApiError(
  error: unknown,
  showToast: (msg: string, type: 'success' | 'error' | 'info' | 'infrastructure') => void,
  fallbackMessage?: string,
): string {
  let formatted: string;
  const transient = isTransientNetworkError(error);

  if (error instanceof ApiError) {
    formatted = formatApiError(error.status, error.message);
  } else if (transient) {
    // "TypeError: Failed to fetch" tells the user nothing actionable.
    formatted = 'Cannot reach the server (ERR-NETWORK). Check your connection and try again.';
  } else if (error instanceof Error) {
    formatted = `${error.message} (ERR-UNKNOWN). Try again.`;
  } else {
    formatted = `${fallbackMessage || 'An unexpected error occurred'} (ERR-UNKNOWN). Try again.`;
  }

  showToast(formatted, transient ? 'infrastructure' : 'error');

  // A transient network failure is not a defect, and reporting it would also
  // be the one report most likely to fail to send anyway.
  if (transient) {
    return formatted;
  }

  // Report error to backend (fire-and-forget)
  try {
    import('./system').then(({ systemErrorApi }) => {
      systemErrorApi.reportError({
        source: 'frontend',
        category: 'frontend_error',
        message: formatted,
        stack_trace: error instanceof Error ? error.stack : undefined,
        context_json: JSON.stringify({ url: typeof window !== 'undefined' ? window.location.href : '' }),
      }).catch(() => { /* silently ignore reporting failures */ });
    }).catch(() => { /* If import fails, skip reporting */ });
  } catch {
    // If import fails, skip reporting
  }

  return formatted;
}
