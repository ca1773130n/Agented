import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { defineComponent, h } from 'vue';
import { mount } from '@vue/test-utils';
import { useFocusRefresh } from '../useFocusRefresh';

const visibility = { state: 'visible' as DocumentVisibilityState };
function setVisibility(state: DocumentVisibilityState) {
  visibility.state = state;
  Object.defineProperty(document, 'visibilityState', {
    configurable: true,
    get: () => visibility.state,
  });
  document.dispatchEvent(new Event('visibilitychange'));
}

beforeEach(() => {
  Object.defineProperty(document, 'visibilityState', {
    configurable: true,
    get: () => visibility.state,
  });
});

afterEach(() => {
  visibility.state = 'visible';
});

function makeHost(fn: () => void, immediate: boolean = false) {
  return defineComponent({
    setup() {
      useFocusRefresh(fn, { immediate });
      return () => h('div');
    },
  });
}

describe('useFocusRefresh', () => {
  it('does not call fn on mount unless immediate is true', () => {
    const fn = vi.fn();
    mount(makeHost(fn));
    expect(fn).not.toHaveBeenCalled();
  });

  it('calls fn once on mount when immediate: true', () => {
    const fn = vi.fn();
    mount(makeHost(fn, true));
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it('calls fn when visibilityState becomes visible', () => {
    const fn = vi.fn();
    setVisibility('hidden'); // start hidden
    mount(makeHost(fn));
    setVisibility('visible');
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it('does not call fn when visibilityState becomes hidden', () => {
    const fn = vi.fn();
    setVisibility('visible');
    mount(makeHost(fn));
    setVisibility('hidden');
    expect(fn).not.toHaveBeenCalled();
  });

  it('removes the listener on unmount', () => {
    const fn = vi.fn();
    setVisibility('hidden');
    const wrapper = mount(makeHost(fn));
    wrapper.unmount();
    setVisibility('visible');
    expect(fn).not.toHaveBeenCalled();
  });

  it('calls fn each time visibility transitions to visible', () => {
    const fn = vi.fn();
    setVisibility('hidden');
    mount(makeHost(fn));
    setVisibility('visible');
    setVisibility('hidden');
    setVisibility('visible');
    expect(fn).toHaveBeenCalledTimes(2);
  });
});
