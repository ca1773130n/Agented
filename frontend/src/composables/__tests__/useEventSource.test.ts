import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount } from '@vue/test-utils';
import { defineComponent, nextTick } from 'vue';
import { useEventSource, safeParseSSE, type UseEventSourceOptions, type SSEStatus } from '../useEventSource';

// Mock the API client module so tests don't make real network requests.
vi.mock('../../services/api/client', () => ({
  createAuthenticatedEventSource: vi.fn(),
}));

// Import the mocked function for assertions.
import { createAuthenticatedEventSource } from '../../services/api/client';
const mockCreateSource = vi.mocked(createAuthenticatedEventSource);

// Mock AuthenticatedEventSource factory.
// Each call returns a fresh mock with controllable lifecycle events.
function createMockSource() {
  const mockSource = {
    onopen: null as (() => void) | null,
    onerror: null as ((event: Event) => void) | null,
    onmessage: null as ((event: MessageEvent) => void) | null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    close: vi.fn(),
    queueDepth: 0,
    // Test helpers to trigger lifecycle events
    _triggerOpen() { if (mockSource.onopen) mockSource.onopen(); },
    _triggerError(event?: Event) {
      if (mockSource.onerror) mockSource.onerror(event ?? new Event('error'));
    },
  };
  return mockSource;
}

// Create a test wrapper component for the composable following the useDataPage.test.ts pattern.
function createTestComponent(options: UseEventSourceOptions) {
  return defineComponent({
    setup() {
      return useEventSource(options);
    },
    template: '<div />',
  });
}

describe('useEventSource', () => {
  let mockSource: ReturnType<typeof createMockSource>;

  beforeEach(() => {
    vi.clearAllMocks();
    mockSource = createMockSource();
    mockCreateSource.mockReturnValue(mockSource as any);
  });

  it('starts with idle status', () => {
    const wrapper = mount(createTestComponent({ url: '/test' }));
    expect(wrapper.vm.status).toBe('idle' satisfies SSEStatus);
    wrapper.unmount();
  });

  it('does not auto-connect by default (no autoConnect option)', () => {
    mount(createTestComponent({ url: '/test' }));
    expect(mockCreateSource).not.toHaveBeenCalled();
  });

  it('auto-connects when autoConnect is true', async () => {
    const wrapper = mount(createTestComponent({ url: '/test', autoConnect: true }));
    await nextTick();
    expect(mockCreateSource).toHaveBeenCalledWith('/test');
    wrapper.unmount();
  });

  it('transitions to "connecting" status on connect()', () => {
    const wrapper = mount(createTestComponent({ url: '/test' }));
    wrapper.vm.connect();
    expect(wrapper.vm.status).toBe('connecting' satisfies SSEStatus);
    wrapper.unmount();
  });

  it('transitions to "open" when source fires onopen', async () => {
    const wrapper = mount(createTestComponent({ url: '/test' }));
    wrapper.vm.connect();
    // Simulate the SSE connection opening
    mockSource._triggerOpen();
    await nextTick();
    expect(wrapper.vm.status).toBe('open' satisfies SSEStatus);
    wrapper.unmount();
  });

  it('transitions to "error" when source fires onerror', async () => {
    const wrapper = mount(createTestComponent({ url: '/test' }));
    wrapper.vm.connect();
    // Simulate a connection error
    mockSource._triggerError();
    await nextTick();
    expect(wrapper.vm.status).toBe('error' satisfies SSEStatus);
    wrapper.unmount();
  });

  it('transitions to "closed" on close() and calls source.close()', () => {
    const wrapper = mount(createTestComponent({ url: '/test' }));
    wrapper.vm.connect();
    mockSource._triggerOpen();
    wrapper.vm.close();
    expect(wrapper.vm.status).toBe('closed' satisfies SSEStatus);
    expect(mockSource.close).toHaveBeenCalledTimes(1);
    wrapper.unmount();
  });

  it('registers named event listeners from events map on connect()', () => {
    const messageHandler = vi.fn();
    const customHandler = vi.fn();
    const wrapper = mount(createTestComponent({
      url: '/test',
      events: { message: messageHandler, 'custom-event': customHandler },
    }));
    wrapper.vm.connect();
    expect(mockSource.addEventListener).toHaveBeenCalledWith('message', messageHandler);
    expect(mockSource.addEventListener).toHaveBeenCalledWith('custom-event', customHandler);
    wrapper.unmount();
  });

  it('calls close() on existing source before reconnecting', () => {
    const firstSource = createMockSource();
    const secondSource = createMockSource();
    mockCreateSource
      .mockReturnValueOnce(firstSource as any)
      .mockReturnValueOnce(secondSource as any);

    const wrapper = mount(createTestComponent({ url: '/test' }));
    wrapper.vm.connect(); // First connection
    wrapper.vm.connect(); // Second connection — should close first

    expect(firstSource.close).toHaveBeenCalledTimes(1);
    expect(mockCreateSource).toHaveBeenCalledTimes(2);
    wrapper.unmount();
  });

  it('calls source.close() on component unmount', () => {
    const wrapper = mount(createTestComponent({ url: '/test' }));
    wrapper.vm.connect();
    wrapper.unmount();
    expect(mockSource.close).toHaveBeenCalledTimes(1);
  });

  it('supports function-form URL (getter function)', () => {
    const wrapper = mount(createTestComponent({ url: () => '/dynamic/url' }));
    wrapper.vm.connect();
    expect(mockCreateSource).toHaveBeenCalledWith('/dynamic/url');
    wrapper.unmount();
  });

  it('calls onOpen callback when connection opens', async () => {
    const onOpen = vi.fn();
    const wrapper = mount(createTestComponent({ url: '/test', onOpen }));
    wrapper.vm.connect();
    mockSource._triggerOpen();
    await nextTick();
    expect(onOpen).toHaveBeenCalledTimes(1);
    wrapper.unmount();
  });

  it('calls onError callback when connection errors', async () => {
    const onError = vi.fn();
    const wrapper = mount(createTestComponent({ url: '/test', onError }));
    wrapper.vm.connect();
    const errorEvent = new Event('error');
    mockSource._triggerError(errorEvent);
    await nextTick();
    expect(onError).toHaveBeenCalledWith(errorEvent);
    wrapper.unmount();
  });

  it('uses sourceFactory option instead of url when provided', () => {
    const factorySource = createMockSource();
    const sourceFactory = vi.fn().mockReturnValue(factorySource);
    const wrapper = mount(createTestComponent({ sourceFactory }));
    wrapper.vm.connect();
    expect(sourceFactory).toHaveBeenCalledTimes(1);
    expect(mockCreateSource).not.toHaveBeenCalled();
    wrapper.unmount();
  });

  it('sets status to "error" when neither url nor sourceFactory is provided', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const wrapper = mount(createTestComponent({}));
    wrapper.vm.connect();
    expect(wrapper.vm.status).toBe('error' satisfies SSEStatus);
    warnSpy.mockRestore();
    wrapper.unmount();
  });

  it('getSource() returns the active source after connecting', () => {
    const wrapper = mount(createTestComponent({ url: '/test' }));
    expect(wrapper.vm.getSource()).toBeNull();
    wrapper.vm.connect();
    expect(wrapper.vm.getSource()).toBe(mockSource);
    wrapper.unmount();
  });

  it('getSource() returns null after close()', () => {
    const wrapper = mount(createTestComponent({ url: '/test' }));
    wrapper.vm.connect();
    wrapper.vm.close();
    expect(wrapper.vm.getSource()).toBeNull();
    wrapper.unmount();
  });

  it('auto-connect triggers with dynamic URL from function', async () => {
    const wrapper = mount(createTestComponent({
      url: () => '/api/stream/123',
      autoConnect: true,
    }));
    await nextTick();
    expect(mockCreateSource).toHaveBeenCalledWith('/api/stream/123');
    wrapper.unmount();
  });

  it('assigns onmessage callback as property on source', () => {
    const messageHandler = vi.fn();
    const wrapper = mount(createTestComponent({
      url: '/test',
      onMessage: messageHandler,
    }));
    wrapper.vm.connect();
    expect(mockSource.onmessage).toBe(messageHandler);
    wrapper.unmount();
  });
});

describe('safeParseSSE', () => {
  it('parses valid JSON and returns the object', () => {
    const event = new MessageEvent('message', { data: '{"status":"ok"}' });
    const result = safeParseSSE<{ status: string }>(event);
    expect(result).toEqual({ status: 'ok' });
  });

  it('returns null and warns on invalid JSON', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const event = new MessageEvent('message', { data: 'not json' });
    const result = safeParseSSE(event, 'test/label');
    expect(result).toBeNull();
    expect(warnSpy).toHaveBeenCalledWith(
      '[SSE test/label] Received non-JSON event data:',
      'not json',
    );
    warnSpy.mockRestore();
  });

  it('returns null on empty string data', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const event = new MessageEvent('message', { data: '' });
    const result = safeParseSSE(event);
    expect(result).toBeNull();
    warnSpy.mockRestore();
  });
});
