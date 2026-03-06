import { ref, onUnmounted, type Ref } from 'vue';
import {
  createAuthenticatedEventSource,
  type AuthenticatedEventSource,
} from '../services/api/client';

/**
 * Safely parse SSE event data as JSON.
 *
 * Returns the parsed object on success, or `null` if the data is not valid
 * JSON.  Logs a warning with the event type and raw data so malformed
 * server messages are visible in devtools without crashing the consumer.
 */
export function safeParseSSE<T = unknown>(event: MessageEvent, label?: string): T | null {
  try {
    return JSON.parse(event.data) as T;
  } catch {
    console.warn(
      `[SSE${label ? ` ${label}` : ''}] Received non-JSON event data:`,
      event.data,
    );
    return null;
  }
}

/**
 * Reactive SSE connection status.
 * - idle: no connection attempt made yet
 * - connecting: connection initiated but not yet open
 * - open: connection established and receiving events
 * - error: connection encountered an error (may auto-reconnect)
 * - closed: connection explicitly closed
 */
export type SSEStatus = 'idle' | 'connecting' | 'open' | 'error' | 'closed';

/**
 * Options for the useEventSource composable.
 *
 * Exactly one of `url` or `sourceFactory` must be provided:
 * - `url` — A static or dynamic URL string; the composable calls
 *   createAuthenticatedEventSource internally.
 * - `sourceFactory` — A function that returns an already-created
 *   AuthenticatedEventSource. Useful when the API layer manages
 *   EventSource creation (e.g., api.stream(), chatStream()).
 */
export interface UseEventSourceOptions {
  /** Static URL or getter function. Composable calls createAuthenticatedEventSource(url). */
  url?: string | (() => string);
  /** Factory that returns an already-connected AuthenticatedEventSource. */
  sourceFactory?: () => AuthenticatedEventSource;
  /** Named event handlers mapped by SSE event type. */
  events?: Record<string, (event: MessageEvent) => void>;
  /** Called when the SSE connection opens successfully. */
  onOpen?: () => void;
  /** Called on SSE connection error. */
  onError?: (event: Event) => void;
  /** Called on default/message events (property-assignment style). */
  onMessage?: (event: MessageEvent) => void;
  /** If true, connect immediately on composable creation. Default: false. */
  autoConnect?: boolean;
}

export interface UseEventSourceReturn {
  /** Reactive connection status. */
  status: Ref<SSEStatus>;
  /** Open or re-open the SSE connection. Closes any existing connection first. */
  connect: () => void;
  /** Close the current SSE connection. */
  close: () => void;
  /** Access the underlying AuthenticatedEventSource for advanced use. */
  getSource: () => AuthenticatedEventSource | null;
}

/**
 * Shared SSE composable that encapsulates connection lifecycle:
 * connect, disconnect, status tracking, event registration, and
 * automatic cleanup on component unmount.
 *
 * Event-specific parsing stays in each consumer composable --
 * this composable does NOT dictate message formats or parsing logic.
 */
export function useEventSource(options: UseEventSourceOptions): UseEventSourceReturn {
  const status = ref<SSEStatus>('idle');
  let source: AuthenticatedEventSource | null = null;

  function connect() {
    // Close any existing connection first
    close();

    status.value = 'connecting';

    // Create the source via factory or URL
    if (options.sourceFactory) {
      source = options.sourceFactory();
    } else if (options.url) {
      const resolvedUrl = typeof options.url === 'function' ? options.url() : options.url;
      source = createAuthenticatedEventSource(resolvedUrl);
    } else {
      console.warn('[useEventSource] Neither url nor sourceFactory provided');
      status.value = 'error';
      return;
    }

    // Wire up lifecycle callbacks
    source.onopen = () => {
      status.value = 'open';
      options.onOpen?.();
    };

    source.onerror = (event: Event) => {
      status.value = 'error';
      options.onError?.(event);
    };

    // Property-assignment onmessage for default/message events
    if (options.onMessage) {
      source.onmessage = options.onMessage;
    }

    // Register named event handlers
    if (options.events) {
      for (const [eventName, handler] of Object.entries(options.events)) {
        source.addEventListener(eventName, handler);
      }
    }
  }

  function close() {
    if (source) {
      source.close();
      source = null;
    }
    if (status.value !== 'idle') {
      status.value = 'closed';
    }
  }

  function getSource(): AuthenticatedEventSource | null {
    return source;
  }

  // Auto-connect if requested
  if (options.autoConnect === true) {
    connect();
  }

  // Automatic cleanup on component unmount
  onUnmounted(close);

  return { status, connect, close, getSource };
}
