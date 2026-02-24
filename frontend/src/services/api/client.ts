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

/** EventSource extended with a queue depth accessor for debugging backpressure. */
export interface BackoffEventSource extends EventSource {
  /** Current number of events waiting to be dispatched to UI handlers. */
  readonly queueDepth: number;
}

/** Options for createBackoffEventSource. */
export interface BackoffEventSourceOptions {
  /**
   * Called when all SSE_MAX_ATTEMPTS reconnection attempts have been exhausted.
   * Use this to surface a "connection lost" message in the UI and offer a manual retry.
   */
  onGiveUp?: () => void;
  /**
   * Called when the backpressure queue is full and events are being dropped.
   * Receives the current drop count (number of events dropped in this overflow window).
   * Use this to surface a warning in the UI that log entries may be missing.
   */
  onQueueOverflow?: (dropCount: number) => void;
}

/**
 * Creates an EventSource with exponential backoff reconnection and backpressure.
 *
 * The browser's native EventSource reconnects immediately by default, which can
 * flood a backend that is under load or restarting.  This wrapper instead:
 *   1. Closes the EventSource on the first onerror callback.
 *   2. Waits with exponential backoff + jitter before opening a new EventSource.
 *   3. Stops reconnecting after SSE_MAX_ATTEMPTS consecutive failures.
 *   4. Queues incoming events and drains them in batches via requestAnimationFrame
 *      so that slow UI rendering cannot cause unbounded memory accumulation.
 *      When the queue exceeds SSE_MAX_QUEUE_SIZE the oldest events are dropped.
 *
 * The returned object mirrors the EventSource interface so callers can swap
 * `new EventSource(url)` with `createBackoffEventSource(url)` transparently.
 * The extra `queueDepth` property exposes current queue size for debugging.
 *
 * @param options.onGiveUp - Called when all reconnection attempts are exhausted.
 * @param options.onQueueOverflow - Called when events are dropped due to queue saturation.
 */
export function createBackoffEventSource(url: string, options?: BackoffEventSourceOptions): BackoffEventSource {
  let attempt = 0;
  let retryTimeout: ReturnType<typeof setTimeout> | null = null;
  let closed = false;

  // We return the first EventSource directly so the caller can attach listeners
  // synchronously — the wrapper replaces it transparently on reconnection.
  let current = new EventSource(url);

  function reconnect() {
    if (closed) return;
    attempt++;
    if (attempt > SSE_MAX_ATTEMPTS) {
      // Give up — prevent thundering-herd on a permanently unavailable server.
      if (options?.onGiveUp) {
        try { options.onGiveUp(); } catch { /* ignore callback errors */ }
      }
      return;
    }
    const base = Math.min(SSE_INITIAL_DELAY_MS * Math.pow(2, attempt - 1), SSE_MAX_DELAY_MS);
    const delay = base + Math.random() * SSE_JITTER_MS;

    retryTimeout = setTimeout(() => {
      retryTimeout = null;  // Timer has fired; clear the handle so close() won't double-cancel.
      if (closed) return;
      // Re-open and re-attach all listeners that were registered on the proxy.
      const next = new EventSource(url);
      // Copy all named-event listeners (via their queue wrappers) to the new source.
      for (const [type, handlers] of registeredListeners) {
        for (const handler of handlers) {
          const wrapper = handlerWrappers.get(handler);
          next.addEventListener(type, wrapper ?? (handler as EventListener));
        }
      }
      next.onerror = current.onerror;
      next.onopen = current.onopen;
      next.onmessage = current.onmessage;
      current = next;
      // Attach backoff error handler to new source.
      attachBackoff(next);
    }, delay);
  }

  function attachBackoff(es: EventSource) {
    const originalOnerror = es.onerror;
    es.onerror = (ev: Event) => {
      es.close();
      if (originalOnerror) originalOnerror.call(es, ev);
      reconnect();
    };
    es.onopen = () => {
      // Reset backoff counter on a successful connection.
      attempt = 0;
    };
  }

  // Track addEventListener calls so we can re-attach them after reconnection.
  const registeredListeners = new Map<string, Set<EventListenerOrEventListenerObject>>();

  // ---- Backpressure queue ----
  // Events are pushed here and drained in batches via requestAnimationFrame.
  // This prevents slow UI rendering from causing unbounded memory accumulation.
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
          if (typeof h === 'function') h(event);
          else h.handleEvent(event);
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

    // Warn before saturation to allow proactive intervention
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
      // Drop the oldest event to bound memory usage
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

  attachBackoff(current);

  // Map from caller-supplied handler → queuing wrapper, so removeEventListener can clean up.
  const handlerWrappers = new Map<EventListenerOrEventListenerObject, EventListener>();

  // Return a proxy that intercepts addEventListener/removeEventListener so that
  // listeners registered before the first reconnection are preserved across reconnects,
  // and routes events through the backpressure queue.
  const proxy = new Proxy(current, {
    get(_, prop) {
      if (prop === 'addEventListener') {
        return (type: string, handler: EventListenerOrEventListenerObject, opts?: boolean | AddEventListenerOptions) => {
          if (!registeredListeners.has(type)) registeredListeners.set(type, new Set());
          const listeners = registeredListeners.get(type)!;
          // Skip if already registered to prevent duplicate listeners and memory leaks on reconnect
          if (listeners.has(handler)) return;
          listeners.add(handler);
          // Wrap the handler to go through the backpressure queue
          const wrapper: EventListener = (event: Event) => enqueueEvent(type, event);
          handlerWrappers.set(handler, wrapper);
          current.addEventListener(type, wrapper, opts);
        };
      }
      if (prop === 'removeEventListener') {
        return (type: string, handler: EventListenerOrEventListenerObject, opts?: boolean | EventListenerOptions) => {
          registeredListeners.get(type)?.delete(handler);
          const wrapper = handlerWrappers.get(handler);
          if (wrapper) {
            handlerWrappers.delete(handler);
            current.removeEventListener(type, wrapper, opts);
          } else {
            current.removeEventListener(type, handler, opts);
          }
        };
      }
      if (prop === 'close') {
        return () => {
          closed = true;
          if (retryTimeout !== null) {
            clearTimeout(retryTimeout);
            retryTimeout = null;
          }
          registeredListeners.clear();
          handlerWrappers.clear();
          eventQueue.length = 0;
          current.close();
        };
      }
      if (prop === 'queueDepth') {
        return eventQueue.length;
      }
      const val = (current as unknown as Record<string | symbol, unknown>)[prop];
      return typeof val === 'function' ? val.bind(current) : val;
    },
    set(_, prop, value) {
      (current as unknown as Record<string | symbol, unknown>)[prop] = value;
      return true;
    },
  }) as BackoffEventSource;

  return proxy;
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
