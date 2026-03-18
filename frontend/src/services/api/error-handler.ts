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
 * Handle any error by showing a toast notification and returning the formatted message.
 *
 * - ApiError: uses formatApiError with the status and message
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

  if (error instanceof ApiError) {
    formatted = formatApiError(error.status, error.message);
  } else if (error instanceof Error) {
    formatted = `${error.message} (ERR-UNKNOWN). Try again.`;
  } else {
    formatted = `${fallbackMessage || 'An unexpected error occurred'} (ERR-UNKNOWN). Try again.`;
  }

  showToast(formatted, 'error');

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
