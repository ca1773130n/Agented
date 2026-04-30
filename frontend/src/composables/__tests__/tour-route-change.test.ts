/**
 * Regression test for the wave 6 tour-overlay-loses-target bug.
 *
 * When a tour step's target lives on a route-param-bound page (e.g.
 * /backends/claude has [data-tour="add-account-btn"], same for /backends/codex),
 * a route change unmounts the old element and mounts a new one with the same
 * selector. The pre-wave-13 overlay held a stale Element ref; the post-wave-13
 * bus re-emits the new element automatically.
 *
 * This test simulates the unmount/remount cycle and asserts the bus delivers
 * the new element to subscribers without any retrigger from the parent.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { useTourTargetBus } from '../useTourTargetBus';

function flushMO() {
  return new Promise<void>((r) => queueMicrotask(() => queueMicrotask(r)));
}

function clearBody() {
  while (document.body.firstChild) {
    document.body.removeChild(document.body.firstChild);
  }
}

describe('tour bus — survives route-param-style remount', () => {
  beforeEach(() => clearBody());
  afterEach(() => clearBody());

  it('delivers a fresh element after the slot containing the old one is replaced', async () => {
    const bus = useTourTargetBus();
    const cb = vi.fn();

    // Initial route: /backends/claude — render slot with target
    const slot1 = document.createElement('section');
    slot1.dataset.route = 'claude';
    const target1 = document.createElement('button');
    target1.setAttribute('data-tour', 'add-account-btn');
    slot1.appendChild(target1);
    document.body.appendChild(slot1);

    const unsub = bus.subscribe('[data-tour="add-account-btn"]', cb);
    expect(cb).toHaveBeenLastCalledWith(target1);

    // Route change: /backends/codex — old slot unmounts, new slot with new
    // target mounts. Atomic swap simulates Vue Router's slot transition.
    const slot2 = document.createElement('section');
    slot2.dataset.route = 'codex';
    const target2 = document.createElement('button');
    target2.setAttribute('data-tour', 'add-account-btn');
    slot2.appendChild(target2);

    document.body.removeChild(slot1);
    document.body.appendChild(slot2);
    await flushMO();

    expect(cb).toHaveBeenLastCalledWith(target2);
    expect(target2).not.toBe(target1);

    unsub();
  });

  it('handles the unmount → gap → remount sequence', async () => {
    const bus = useTourTargetBus();
    const cb = vi.fn();

    const target1 = document.createElement('button');
    target1.setAttribute('data-tour', 'gap');
    document.body.appendChild(target1);

    const unsub = bus.subscribe('[data-tour="gap"]', cb);
    expect(cb).toHaveBeenLastCalledWith(target1);

    // Mid-transition: target gone for several frames.
    document.body.removeChild(target1);
    await flushMO();
    expect(cb).toHaveBeenLastCalledWith(null);

    // Some unrelated DOM churn during the transition window.
    const filler = document.createElement('div');
    document.body.appendChild(filler);
    await flushMO();

    // New page mounts the new target.
    const target2 = document.createElement('button');
    target2.setAttribute('data-tour', 'gap');
    document.body.appendChild(target2);
    await flushMO();

    expect(cb).toHaveBeenLastCalledWith(target2);

    unsub();
  });
});
