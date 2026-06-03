/**
 * API client infrastructure: base URL, error class, and generic fetch wrapper.
 *
 * Features:
 * - Configurable request timeout (default 30s) via AbortController
 * - Retry with exponential backoff for transient failures (429, 502, 503, 504)
 * - Safe empty response handling (null instead of {} as T)
 * - API key authentication via X-API-Key header (read from sessionStorage)
 * - Authenticated SSE streams via @microsoft/fetch-event-source
 */

import { fetchEventSource } from '@microsoft/fetch-event-source';

export const API_BASE = '';  // Use proxy in development, same origin in production

const API_KEY_STORAGE_KEY = 'agented-api-key';

// [08.H1-residual] The long-lived admin API key used to live in localStorage,
// where it was readable by any XSS payload for the lifetime of the origin.
// It now lives in sessionStorage (cleared when the tab closes) so the exposure
// window is one tab session instead of forever, and an in-memory cache holds it
// for the current page so reads don't keep hitting storage. We deliberately
// migrate any pre-existing localStorage key forward (read-once, then delete) so
// already-onboarded users aren't logged out by this change. Cookie+CSRF is the
// preferred auth path for new sessions; this key remains only for the legacy
// api-key flow (welcome-page bootstrap, SSE headers).
let _apiKeyMemo: string | null = null;

/** Read the API key. Returns null when unset. */
export function getApiKey(): string | null {
  if (typeof window === 'undefined') return null;
  if (_apiKeyMemo !== null) return _apiKeyMemo;
  try {
    const fromSession = sessionStorage.getItem(API_KEY_STORAGE_KEY);
    if (fromSession) {
      _apiKeyMemo = fromSession;
      return fromSession;
    }
    // One-time migration of a legacy localStorage key into sessionStorage.
    const legacy = localStorage.getItem(API_KEY_STORAGE_KEY);
    if (legacy) {
      try {
        sessionStorage.setItem(API_KEY_STORAGE_KEY, legacy);
        localStorage.removeItem(API_KEY_STORAGE_KEY);
      } catch {
        // ignore migration failures — return the legacy value regardless
      }
      _apiKeyMemo = legacy;
      return legacy;
    }
    return null;
  } catch {
    return null;
  }
}

/** Store the API key in sessionStorage (cleared on tab close) for subsequent requests. */
export function setApiKey(key: string): void {
  if (typeof window === 'undefined') return;
  _apiKeyMemo = key;
  try {
    sessionStorage.setItem(API_KEY_STORAGE_KEY, key);
  } catch {
    // sessionStorage unavailable or full — in-memory memo still serves reads
  }
}

/** Remove the stored API key (from both storages and the in-memory cache). */
export function clearApiKey(): void {
  _apiKeyMemo = null;
  if (typeof window === 'undefined') return;
  try {
    sessionStorage.removeItem(API_KEY_STORAGE_KEY);
    // Also clear any stale legacy copy.
    localStorage.removeItem(API_KEY_STORAGE_KEY);
  } catch {
    // ignore
  }
}

const SESSION_TOKEN_STORAGE_KEY = 'agented-session-token';

/** Read the session token (Authorization: Bearer) from localStorage. */
export function getSessionToken(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return localStorage.getItem(SESSION_TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

/** Store a session token for subsequent requests (set after login). */
export function setSessionToken(token: string): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(SESSION_TOKEN_STORAGE_KEY, token);
  } catch {
    // ignore
  }
}

/** Remove the stored session token (call on logout). */
export function clearSessionToken(): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.removeItem(SESSION_TOKEN_STORAGE_KEY);
  } catch {
    // ignore
  }
}

const CSRF_COOKIE = 'agented_csrf';

/** Read the readable (non-HttpOnly) CSRF token from the cookie jar. The session
 *  cookie itself is HttpOnly and never visible here — only the CSRF token is. */
export function getCsrfToken(): string | null {
  if (typeof document === 'undefined') return null;
  for (const part of document.cookie.split(';')) {
    const [name, ...rest] = part.trim().split('=');
    if (name === CSRF_COOKIE) return decodeURIComponent(rest.join('='));
  }
  return null;
}

const DEFAULT_TIMEOUT_MS = 120000;
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
 * Supports an external AbortSignal (via options.signal) combined with the
 * internal timeout signal so callers can cancel requests on component unmount.
 */
async function apiFetchSingle<T>(url: string, options?: ApiFetchOptions): Promise<T> {
  const timeoutMs = options?.timeout ?? DEFAULT_TIMEOUT_MS;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  // Merge the abort signal into fetch options
  const { timeout: _timeout, retries: _retries, retryOn: _retryOn, signal: externalSignal, ...fetchOptions } = options ?? {};

  // If the caller provided an external signal, forward its abort to our controller
  // so a single signal drives both timeout and caller-initiated cancellation.
  if (externalSignal) {
    if (externalSignal.aborted) {
      clearTimeout(timeoutId);
      throw new DOMException('The operation was aborted.', 'AbortError');
    }
    const onExternalAbort = () => controller.abort();
    externalSignal.addEventListener('abort', onExternalAbort, { once: true });
    // Clean up the listener when our controller aborts (timeout or completion)
    controller.signal.addEventListener('abort', () => {
      externalSignal.removeEventListener('abort', onExternalAbort);
    }, { once: true });
  }

  try {
    const apiKey = getApiKey();
    const sessionToken = getSessionToken();
    const authHeaders: Record<string, string> = {};
    if (apiKey) authHeaders['X-API-Key'] = apiKey;
    // Bearer header kept only for any pre-migration localStorage token; new
    // sessions authenticate via the HttpOnly cookie (sent automatically).
    if (sessionToken) authHeaders['Authorization'] = `Bearer ${sessionToken}`;

    // Double-submit CSRF: echo the readable CSRF cookie in a header on mutating
    // requests so the cookie-authenticated session can't be ridden cross-site.
    const method = (fetchOptions?.method || 'GET').toUpperCase();
    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
      const csrf = getCsrfToken();
      if (csrf) authHeaders['X-CSRF-Token'] = csrf;
    }

    const response = await fetch(`${API_BASE}${url}`, {
      ...fetchOptions,
      signal: controller.signal,
      // Send the HttpOnly session + CSRF cookies on every request.
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders,
        ...fetchOptions?.headers,
      },
    });

    clearTimeout(timeoutId);

    // [08.H1-residual] Session-token rotation now happens via Set-Cookie on the
    // HttpOnly session cookie, so we no longer persist the rotated token from the
    // ``x-new-session-token`` header into localStorage (it would only re-introduce
    // an XSS-readable bearer credential). Any pre-migration localStorage token is
    // still read below for backward-compat, but new sessions never write one.

    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      const retryAfter = response.status === 429 ? parseRetryAfter(response.headers) : undefined;
      // Litestar's default error shape is ``{error: {code, message, ...}}`` —
      // not a flat string. Without unwrapping, the message coerces to
      // ``[object Object]`` (dogfood found this on a 404 from the
      // takeaways card). Try ordered: top-level ``message`` →
      // nested ``error.message`` → flat string ``error`` →
      // ``detail`` (FastAPI-style) → HTTP status fallback.
      const errObj = data && typeof data === 'object' ? data : {};
      const nested = errObj.error && typeof errObj.error === 'object'
        ? errObj.error
        : null;
      const message: string =
        (typeof errObj.message === 'string' && errObj.message) ||
        (nested && typeof nested.message === 'string' && nested.message) ||
        (typeof errObj.error === 'string' && errObj.error) ||
        (typeof errObj.detail === 'string' && errObj.detail) ||
        `HTTP ${response.status}`;
      throw new ApiError(response.status, message, retryAfter);
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

    // Convert AbortError to a more descriptive error
    if (err instanceof DOMException && err.name === 'AbortError') {
      // Distinguish caller-initiated abort from timeout
      if (externalSignal?.aborted) {
        throw err; // Re-throw as AbortError so composables can ignore it
      }
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
 * Parse the Retry-After header value into seconds.
 * Supports both integer seconds and HTTP-date formats.
 * Returns undefined if the header is absent or unparseable.
 */
function parseRetryAfter(headers: Headers): number | undefined {
  const headerVal = headers.get('Retry-After');
  if (!headerVal) return undefined;
  const seconds = Number(headerVal);
  if (!isNaN(seconds) && seconds >= 0) return seconds;
  // Try parsing as HTTP date
  const date = new Date(headerVal);
  if (!isNaN(date.getTime())) return Math.max(0, (date.getTime() - Date.now()) / 1000);
  return undefined;
}

interface EventQueue {
  enqueue(type: string, event: Event, onOverflow?: (dropCount: number) => void): void;
  drain(handlers: Map<string, Set<(event: MessageEvent) => void>>): void;
  readonly length: number;
  clear(): void;
}

/**
 * Creates an event queue object with backpressure management.
 * Enqueues SSE events and drains them in rAF batches.
 */
function createEventQueue(): EventQueue {
  interface QueuedEvent { type: string; event: Event }
  const eventQueue: QueuedEvent[] = [];
  let drainScheduled = false;
  let lastQueueWarnAt = 0;
  let lastQueueThresholdWarnAt = 0;
  let overflowDropCount = 0;
  let _handlers: Map<string, Set<(event: MessageEvent) => void>> | null = null;

  function drainBatch() {
    drainScheduled = false;
    if (!_handlers) return;
    const batch = eventQueue.splice(0, SSE_DRAIN_BATCH_SIZE);
    for (const { type, event } of batch) {
      const listeners = _handlers.get(type);
      if (listeners) {
        for (const h of listeners) {
          h(event as MessageEvent);
        }
      }
    }
    if (eventQueue.length > 0) {
      drainScheduled = true;
      requestAnimationFrame(drainBatch);
    }
  }

  return {
    enqueue(type: string, event: Event, onOverflow?: (dropCount: number) => void): void {
      const queueSize = eventQueue.length;

      if (queueSize >= SSE_MAX_QUEUE_SIZE * SSE_QUEUE_WARN_THRESHOLD && queueSize < SSE_MAX_QUEUE_SIZE) {
        const now = Date.now();
        if (now - lastQueueThresholdWarnAt >= SSE_QUEUE_WARN_INTERVAL_MS) {
          lastQueueThresholdWarnAt = now;
          // [08.L1] Diagnostic only — gate behind DEV so prod stays quiet.
          if (import.meta.env.DEV) {
            console.warn(
              `[SSE] Event queue at ${Math.round((queueSize / SSE_MAX_QUEUE_SIZE) * 100)}% capacity (${queueSize}/${SSE_MAX_QUEUE_SIZE}). UI rendering may be falling behind.`
            );
          }
        }
      }

      if (eventQueue.length >= SSE_MAX_QUEUE_SIZE) {
        eventQueue.shift();
        overflowDropCount++;
        const now = Date.now();
        if (now - lastQueueWarnAt >= SSE_QUEUE_WARN_INTERVAL_MS) {
          lastQueueWarnAt = now;
          // [08.L1] Diagnostic only — gate behind DEV so prod stays quiet.
          if (import.meta.env.DEV) {
            console.warn(
              `[SSE] Event queue full (${SSE_MAX_QUEUE_SIZE} events). Oldest events are being dropped — UI may miss execution log entries.`
            );
          }
          if (onOverflow) {
            try { onOverflow(overflowDropCount); } catch { /* ignore callback errors */ }
            overflowDropCount = 0;
          }
        }
      }
      eventQueue.push({ type, event });
      if (!drainScheduled) {
        drainScheduled = true;
        requestAnimationFrame(drainBatch);
      }
    },

    drain(handlers: Map<string, Set<(event: MessageEvent) => void>>): void {
      _handlers = handlers;
    },

    get length() { return eventQueue.length; },

    clear(): void {
      eventQueue.length = 0;
      drainScheduled = false;
    },
  };
}

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
 *   1. Injects X-API-Key (from sessionStorage) on every connection/reconnection.
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

  // Backpressure queue — drains events in rAF batches
  const queue = createEventQueue();
  queue.drain(registeredListeners);

  function scheduleReconnect() {
    if (closed) return;
    attempt++;
    if (attempt > SSE_MAX_ATTEMPTS) {
      // [08.L3] Give-up must never be silent. Always log in DEV so a missing
      // onGiveUp wiring is visible during development, then forward to the
      // consumer so it can surface a "connection lost" state to the user.
      if (import.meta.env.DEV) {
        console.warn(
          `[SSE] Giving up after ${SSE_MAX_ATTEMPTS} reconnect attempts for ${url}. The stream is now disconnected.`,
        );
      }
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
          queue.enqueue(eventType, msgEvent, options?.onQueueOverflow);
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
      queue.clear();
    },

    get queueDepth() { return queue.length; },
  };

  return source;
}

/** Backward-compatible alias. */
export const createBackoffEventSource = createAuthenticatedEventSource;

/**
 * Check if an error is an AbortError (from AbortController cancellation).
 * Composables use this to silently ignore cancelled requests on unmount.
 */
export function isAbortError(err: unknown): boolean {
  return err instanceof DOMException && err.name === 'AbortError';
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
      const isAbort = isAbortError(err);
      const isTimeout = err instanceof ApiError && err.status === 0;
      if (!isRetryable || isAbort || isTimeout || attempt === maxRetries) throw err;

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
