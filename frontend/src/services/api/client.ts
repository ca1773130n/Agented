/**
 * API client infrastructure: base URL, error class, and generic fetch wrapper.
 *
 * Features:
 * - Configurable request timeout (default 30s) via AbortController
 * - Retry with exponential backoff for transient failures (429, 502, 503, 504)
 * - Safe empty response handling (null instead of {} as T)
 * - API key authentication via X-API-Key header (read from localStorage)
 * - Authenticated SSE streams via @microsoft/fetch-event-source
 */

import { fetchEventSource } from '@microsoft/fetch-event-source';

export const API_BASE = '';  // Use proxy in development, same origin in production

/** Read the API key from localStorage. Returns null when unset. */
export function getApiKey(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return localStorage.getItem('agented-api-key');
  } catch {
    return null;
  }
}

const DEFAULT_TIMEOUT_MS = 30000;
const DEFAULT_MAX_RETRIES = 3;
const DEFAULT_RETRY_STATUSES = [429, 502, 503, 504];
const MAX_BACKOFF_MS = 10000;
const JITTER_MAX_MS = 500;

// API error class
export class ApiError extends Error {
  status: number;
  /** Seconds to wait before retrying, parsed from Retry-After header (429 only). */
  retryAfter?: number;

  constructor(status: number, message: string, retryAfter?: number) {
    super(message);
    this.status = status;
    this.name = 'ApiError';
    if (retryAfter !== undefined) this.retryAfter = retryAfter;
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
    const apiKey = getApiKey();
    const authHeaders: Record<string, string> = {};
    if (apiKey) authHeaders['X-API-Key'] = apiKey;

    const response = await fetch(`${API_BASE}${url}`, {
      ...fetchOptions,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders,
        ...fetchOptions?.headers,
      },
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      let retryAfter: number | undefined;
      if (response.status === 429) {
        const headerVal = response.headers.get('Retry-After');
        if (headerVal) {
          const seconds = Number(headerVal);
          if (!isNaN(seconds) && seconds >= 0) {
            retryAfter = seconds;
          } else {
            // Try parsing as HTTP date
            const date = new Date(headerVal);
            if (!isNaN(date.getTime())) retryAfter = Math.max(0, (date.getTime() - Date.now()) / 1000);
          }
        }
      }
      throw new ApiError(response.status, data.error || `HTTP ${response.status}`, retryAfter);
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

// SSE backoff constants
const SSE_INITIAL_DELAY_MS = 1000;
const SSE_MAX_DELAY_MS = 30000;
const SSE_MAX_ATTEMPTS = 10;
const SSE_JITTER_MS = 500;

// SSE backpressure: max queued events before oldest are dropped
const SSE_MAX_QUEUE_SIZE = 500;
// Number of events to dispatch per animation frame when draining the queue
const SSE_DRAIN_BATCH_SIZE = 20;
// Minimum ms between queue warnings to avoid log spam
const SSE_QUEUE_WARN_INTERVAL_MS = 5000;
// Fraction of SSE_MAX_QUEUE_SIZE at which a pre-saturation warning is emitted
const SSE_QUEUE_WARN_THRESHOLD = 0.75;

/**
 * Authenticated SSE connection with backoff, backpressure, and API key injection.
 * Replaces native EventSource to support custom headers (X-API-Key).
 * Supports property-assignment callbacks (.onmessage, .onerror, .onopen)
 * and addEventListener for named SSE events.
 */
/** Handler type for SSE addEventListener - always receives MessageEvent. */
export type SSEEventListener = (event: MessageEvent) => void;

export interface AuthenticatedEventSource {
  onmessage: ((event: MessageEvent) => void) | null;
  onerror: ((event: Event) => void) | null;
  onopen: (() => void) | null;
  addEventListener(type: string, listener: SSEEventListener): void;
  removeEventListener(type: string, listener: SSEEventListener): void;
  close(): void;
  readonly queueDepth: number;
}

/** Backward-compatible alias. */
export type BackoffEventSource = AuthenticatedEventSource;

/** Options for createAuthenticatedEventSource. */
export interface AuthenticatedEventSourceOptions {
  onGiveUp?: () => void;
  onQueueOverflow?: (dropCount: number) => void;
}

/** Backward-compatible alias. */
export type BackoffEventSourceOptions = AuthenticatedEventSourceOptions;

/** Fatal error that stops SSE reconnection (e.g. 401 Unauthorized). */
class FatalSSEError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'FatalSSEError';
  }
}

/**
 * Creates an authenticated SSE connection using @microsoft/fetch-event-source.
 *
 * Unlike native EventSource, this supports custom headers (X-API-Key) for
 * authenticated SSE streams. Features:
 *   1. Injects X-API-Key from localStorage on every connection/reconnection.
 *   2. Exponential backoff with jitter on connection failures.
 *   3. Stops reconnecting after SSE_MAX_ATTEMPTS consecutive failures.
 *   4. Fatal 401 responses stop retrying immediately.
 *   5. Backpressure queue drains events in rAF batches.
 *   6. Property-assignment compatibility (.onmessage, .onerror, .onopen).
 */
export function createAuthenticatedEventSource(
  url: string,
  options?: AuthenticatedEventSourceOptions,
): AuthenticatedEventSource {
  let closed = false;
  let attempt = 0;
  let abortController = new AbortController();
  let retryTimeout: ReturnType<typeof setTimeout> | null = null;

  // Property-assigned callbacks (like native EventSource)
  let _onmessage: ((event: MessageEvent) => void) | null = null;
  let _onerror: ((event: Event) => void) | null = null;
  let _onopen: (() => void) | null = null;

  // addEventListener registry
  const registeredListeners = new Map<string, Set<(event: MessageEvent) => void>>();

  // ---- Backpressure queue ----
  interface QueuedEvent { type: string; event: Event }
  const eventQueue: QueuedEvent[] = [];
  let drainScheduled = false;
  let lastQueueWarnAt = 0;
  let lastQueueThresholdWarnAt = 0;
  let overflowDropCount = 0;

  function drainEventQueue() {
    drainScheduled = false;
    const batch = eventQueue.splice(0, SSE_DRAIN_BATCH_SIZE);
    for (const { type, event } of batch) {
      const handlers = registeredListeners.get(type);
      if (handlers) {
        for (const h of handlers) {
          h(event as MessageEvent);
        }
      }
    }
    if (eventQueue.length > 0) {
      drainScheduled = true;
      requestAnimationFrame(drainEventQueue);
    }
  }

  function enqueueEvent(type: string, event: Event) {
    const queueSize = eventQueue.length;

    if (queueSize >= SSE_MAX_QUEUE_SIZE * SSE_QUEUE_WARN_THRESHOLD && queueSize < SSE_MAX_QUEUE_SIZE) {
      const now = Date.now();
      if (now - lastQueueThresholdWarnAt >= SSE_QUEUE_WARN_INTERVAL_MS) {
        lastQueueThresholdWarnAt = now;
        console.warn(
          `[SSE] Event queue at ${Math.round((queueSize / SSE_MAX_QUEUE_SIZE) * 100)}% capacity (${queueSize}/${SSE_MAX_QUEUE_SIZE}). UI rendering may be falling behind.`
        );
      }
    }

    if (eventQueue.length >= SSE_MAX_QUEUE_SIZE) {
      eventQueue.shift();
      overflowDropCount++;
      const now = Date.now();
      if (now - lastQueueWarnAt >= SSE_QUEUE_WARN_INTERVAL_MS) {
        lastQueueWarnAt = now;
        console.warn(
          `[SSE] Event queue full (${SSE_MAX_QUEUE_SIZE} events). Oldest events are being dropped — UI may miss execution log entries.`
        );
        if (options?.onQueueOverflow) {
          try { options.onQueueOverflow(overflowDropCount); } catch { /* ignore callback errors */ }
          overflowDropCount = 0;
        }
      }
    }
    eventQueue.push({ type, event });
    if (!drainScheduled) {
      drainScheduled = true;
      requestAnimationFrame(drainEventQueue);
    }
  }
  // ---- end backpressure queue ----

  function scheduleReconnect() {
    if (closed) return;
    attempt++;
    if (attempt > SSE_MAX_ATTEMPTS) {
      if (options?.onGiveUp) {
        try { options.onGiveUp(); } catch { /* ignore */ }
      }
      return;
    }
    const base = Math.min(SSE_INITIAL_DELAY_MS * Math.pow(2, attempt - 1), SSE_MAX_DELAY_MS);
    const delay = base + Math.random() * SSE_JITTER_MS;
    retryTimeout = setTimeout(() => {
      retryTimeout = null;
      connect();
    }, delay);
  }

  function connect() {
    if (closed) return;
    abortController = new AbortController();

    const apiKey = getApiKey();
    const headers: Record<string, string> = {};
    if (apiKey) headers['X-API-Key'] = apiKey;

    const fullUrl = url.startsWith('http') ? url : `${API_BASE}${url}`;

    fetchEventSource(fullUrl, {
      signal: abortController.signal,
      headers,
      openWhenHidden: true,
      async onopen(response) {
        if (response.ok) {
          attempt = 0;
          _onopen?.();
          return;
        }
        if (response.status === 401) {
          throw new FatalSSEError('Unauthorized');
        }
        throw new Error(`HTTP ${response.status}`);
      },
      onmessage(ev) {
        const eventType = ev.event || 'message';
        const msgEvent = new MessageEvent(eventType, {
          data: ev.data,
          lastEventId: ev.id ?? '',
        });

        // Property-assigned onmessage: fires for default/message events only
        if (!ev.event || ev.event === 'message') {
          _onmessage?.(msgEvent);
        }

        // addEventListener handlers via backpressure queue
        if (registeredListeners.has(eventType)) {
          enqueueEvent(eventType, msgEvent);
        }
      },
      onerror(err) {
        if (err instanceof FatalSSEError) {
          _onerror?.(new Event('error'));
          throw err; // Stop retrying
        }
        // Stop fetchEventSource's built-in retry; we manage our own backoff.
        throw err;
      },
      onclose() {
        if (!closed) {
          // Server closed the connection — schedule reconnect with backoff.
          throw new Error('Connection closed by server');
        }
      },
    }).catch((err) => {
      if (err instanceof FatalSSEError || closed) return;
      _onerror?.(new Event('error'));
      scheduleReconnect();
    });
  }

  // Start the initial connection
  connect();

  // Build the public interface object with property-assignment support
  const source: AuthenticatedEventSource = {
    get onmessage() { return _onmessage; },
    set onmessage(fn) { _onmessage = fn; },
    get onerror() { return _onerror; },
    set onerror(fn) { _onerror = fn; },
    get onopen() { return _onopen; },
    set onopen(fn) { _onopen = fn; },

    addEventListener(type: string, handler: SSEEventListener) {
      if (!registeredListeners.has(type)) registeredListeners.set(type, new Set());
      const listeners = registeredListeners.get(type)!;
      if (listeners.has(handler)) return; // Prevent duplicate registration
      listeners.add(handler);
    },

    removeEventListener(type: string, handler: SSEEventListener) {
      registeredListeners.get(type)?.delete(handler);
    },

    close() {
      closed = true;
      abortController.abort();
      if (retryTimeout !== null) {
        clearTimeout(retryTimeout);
        retryTimeout = null;
      }
      registeredListeners.clear();
      eventQueue.length = 0;
    },

    get queueDepth() { return eventQueue.length; },
  };

  return source;
}

/** Backward-compatible alias. */
export const createBackoffEventSource = createAuthenticatedEventSource;

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
      if (err instanceof ApiError && err.status === 429 && err.retryAfter !== undefined) {
        delay = Math.min(err.retryAfter * 1000, MAX_BACKOFF_MS);
      }

      // Add random jitter to avoid thundering herd
      delay += Math.random() * JITTER_MAX_MS;

      await new Promise(r => setTimeout(r, delay));
    }
  }

  throw lastError!;
}
