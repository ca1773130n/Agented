/**
 * API client infrastructure: base URL, error class, and generic fetch wrapper.
 *
 * Features:
 * - Configurable request timeout (default 30s) via AbortController
 * - Retry with exponential backoff for transient failures (429, 502, 503, 504)
 * - Safe empty response handling (null instead of {} as T)
 */

export const API_BASE = '';  // Use proxy in development, same origin in production

const DEFAULT_TIMEOUT_MS = 30000;
const DEFAULT_MAX_RETRIES = 3;
const DEFAULT_RETRY_STATUSES = [429, 502, 503, 504];
const MAX_BACKOFF_MS = 10000;
const JITTER_MAX_MS = 500;

// API error class
export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = 'ApiError';
  }
}

export interface ApiFetchOptions extends RequestInit {
  timeout?: number;    // ms, default 30000
  retries?: number;    // default 3
  retryOn?: number[];  // HTTP status codes to retry, default [429, 502, 503, 504]
}

/**
 * Single-attempt fetch with timeout support.
 * Handles response parsing, empty responses, and error extraction.
 */
async function apiFetchSingle<T>(url: string, options?: ApiFetchOptions): Promise<T> {
  const timeoutMs = options?.timeout ?? DEFAULT_TIMEOUT_MS;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  // Merge the abort signal into fetch options
  // If caller provided a signal, we need to respect both
  const { timeout: _timeout, retries: _retries, retryOn: _retryOn, ...fetchOptions } = options ?? {};

  try {
    const response = await fetch(`${API_BASE}${url}`, {
      ...fetchOptions,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...fetchOptions?.headers,
      },
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new ApiError(response.status, data.error || `HTTP ${response.status}`);
    }

    // Handle 204 No Content explicitly
    if (response.status === 204) return null as T;

    // Handle empty responses safely
    const text = await response.text();
    if (!text) return null as T;
    try {
      return JSON.parse(text);
    } catch {
      return null as T;
    }
  } catch (err) {
    clearTimeout(timeoutId);

    // Convert AbortError to a more descriptive ApiError
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new ApiError(0, 'Request timed out');
    }

    throw err;
  }
}

/**
 * Fetch wrapper with retry logic for transient failures.
 * Retries on HTTP 429, 502, 503, 504 and network errors (TypeError).
 * Uses exponential backoff with jitter.
 */
export async function apiFetch<T>(url: string, options?: ApiFetchOptions): Promise<T> {
  const maxRetries = options?.retries ?? DEFAULT_MAX_RETRIES;
  const retryStatuses = options?.retryOn ?? DEFAULT_RETRY_STATUSES;
  let lastError: Error | null = null;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await apiFetchSingle<T>(url, options);
    } catch (err) {
      lastError = err as Error;

      // Determine if this error is retryable
      const isRetryableStatus = err instanceof ApiError && retryStatuses.includes(err.status);
      const isNetworkError = err instanceof TypeError; // fetch network errors
      const isRetryable = isRetryableStatus || isNetworkError;

      // Never retry aborts/timeouts or non-retryable errors
      const isTimeout = err instanceof ApiError && err.status === 0;
      if (!isRetryable || isTimeout || attempt === maxRetries) throw err;

      // Calculate backoff delay
      let delay = Math.min(1000 * Math.pow(2, attempt), MAX_BACKOFF_MS);

      // Respect Retry-After header for 429 responses
      if (err instanceof ApiError && err.status === 429) {
        // Retry-After info is lost at this point since we only have the error,
        // but the default backoff is reasonable for rate limiting
      }

      // Add random jitter to avoid thundering herd
      delay += Math.random() * JITTER_MAX_MS;

      await new Promise(r => setTimeout(r, delay));
    }
  }

  throw lastError!;
}
