import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { useTourTargetBus } from '../useTourTargetBus';

function flushMO() {
  // happy-dom processes MutationObservers on a microtask; await two ticks.
  return new Promise<void>((r) => queueMicrotask(() => queueMicrotask(r)));
}

function clearBody() {
  while (document.body.firstChild) {
    document.body.removeChild(document.body.firstChild);
  }
}

describe('useTourTargetBus', () => {
  let cleanup: Array<() => void> = [];

  beforeEach(() => {
    cleanup = [];
    clearBody();
  });

  afterEach(() => {
    cleanup.forEach((fn) => fn());
    cleanup = [];
    clearBody();
  });

  it('resolves an existing element synchronously on subscribe', () => {
    const target = document.createElement('div');
    target.setAttribute('data-tour', 'foo');
    document.body.appendChild(target);

    const bus = useTourTargetBus();
    const cb = vi.fn();
    cleanup.push(bus.subscribe('[data-tour="foo"]', cb));

    expect(cb).toHaveBeenCalledTimes(1);
    expect(cb).toHaveBeenCalledWith(target);
  });

  it('reports null when the selector matches nothing initially', () => {
    const bus = useTourTargetBus();
    const cb = vi.fn();
    cleanup.push(bus.subscribe('[data-tour="missing"]', cb));

    expect(cb).toHaveBeenCalledTimes(1);
    expect(cb).toHaveBeenCalledWith(null);
  });

  it('emits when a late-mounted element appears', async () => {
    const bus = useTourTargetBus();
    const cb = vi.fn();
    cleanup.push(bus.subscribe('[data-tour="late"]', cb));
    expect(cb).toHaveBeenLastCalledWith(null);

    const el = document.createElement('button');
    el.setAttribute('data-tour', 'late');
    document.body.appendChild(el);
    await flushMO();

    expect(cb).toHaveBeenCalledWith(el);
  });

  it('re-emits with the new element when the matching node remounts', async () => {
    const bus = useTourTargetBus();
    const cb = vi.fn();
    const original = document.createElement('div');
    original.setAttribute('data-tour', 'remount');
    document.body.appendChild(original);

    cleanup.push(bus.subscribe('[data-tour="remount"]', cb));
    expect(cb).toHaveBeenLastCalledWith(original);

    document.body.removeChild(original);
    await flushMO();
    expect(cb).toHaveBeenLastCalledWith(null);

    const replacement = document.createElement('div');
    replacement.setAttribute('data-tour', 'remount');
    document.body.appendChild(replacement);
    await flushMO();

    expect(cb).toHaveBeenLastCalledWith(replacement);
    expect(replacement).not.toBe(original);
  });

  it('unsubscribe stops further callbacks', async () => {
    const bus = useTourTargetBus();
    const cb = vi.fn();
    const unsub = bus.subscribe('[data-tour="x"]', cb);
    cleanup.push(unsub);
    cb.mockClear();

    unsub();

    const el = document.createElement('div');
    el.setAttribute('data-tour', 'x');
    document.body.appendChild(el);
    await flushMO();

    expect(cb).not.toHaveBeenCalled();
  });

  it('multiple subscribers on the same selector each get notified', async () => {
    const bus = useTourTargetBus();
    const cb1 = vi.fn();
    const cb2 = vi.fn();
    cleanup.push(bus.subscribe('[data-tour="multi"]', cb1));
    cleanup.push(bus.subscribe('[data-tour="multi"]', cb2));

    const el = document.createElement('div');
    el.setAttribute('data-tour', 'multi');
    document.body.appendChild(el);
    await flushMO();

    expect(cb1).toHaveBeenCalledWith(el);
    expect(cb2).toHaveBeenCalledWith(el);
  });
});
