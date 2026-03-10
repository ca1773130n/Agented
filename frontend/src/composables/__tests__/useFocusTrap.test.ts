import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ref, nextTick } from 'vue';

// Mock lifecycle hooks
vi.mock('vue', async () => {
  const actual = await vi.importActual<typeof import('vue')>('vue');
  return {
    ...actual,
    onUnmounted: vi.fn(),
  };
});

import { useFocusTrap } from '../useFocusTrap';

function createContainer(): HTMLElement {
  const container = document.createElement('div');
  container.setAttribute('tabindex', '-1');
  container.focus = vi.fn();

  const btn1 = document.createElement('button');
  btn1.textContent = 'First';
  btn1.focus = vi.fn();
  Object.defineProperty(btn1, 'offsetParent', { value: container });

  const btn2 = document.createElement('button');
  btn2.textContent = 'Second';
  btn2.focus = vi.fn();
  Object.defineProperty(btn2, 'offsetParent', { value: container });

  container.appendChild(btn1);
  container.appendChild(btn2);
  document.body.appendChild(container);

  return container;
}

describe('useFocusTrap', () => {
  let container: HTMLElement;

  beforeEach(() => {
    document.body.textContent = '';
    container = createContainer();
  });

  it('focuses the container when activated', async () => {
    const containerRef = ref<HTMLElement | null>(container);
    const isActive = ref(false);

    useFocusTrap(containerRef, isActive);

    isActive.value = true;
    await nextTick();

    expect(container.focus).toHaveBeenCalled();
  });

  it('wraps focus from last to first element on Tab', async () => {
    const containerRef = ref<HTMLElement | null>(container);
    const isActive = ref(true);

    useFocusTrap(containerRef, isActive);
    await nextTick();

    const buttons = container.querySelectorAll('button');
    const lastBtn = buttons[buttons.length - 1];
    const firstBtn = buttons[0];

    // Simulate focus on last button
    Object.defineProperty(document, 'activeElement', { value: lastBtn, configurable: true });

    const event = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true });
    Object.defineProperty(event, 'preventDefault', { value: vi.fn() });
    container.dispatchEvent(event);

    expect(event.preventDefault).toHaveBeenCalled();
    expect(firstBtn.focus).toHaveBeenCalled();
  });

  it('wraps focus from first to last element on Shift+Tab', async () => {
    const containerRef = ref<HTMLElement | null>(container);
    const isActive = ref(true);

    useFocusTrap(containerRef, isActive);
    await nextTick();

    const buttons = container.querySelectorAll('button');
    const firstBtn = buttons[0];
    const lastBtn = buttons[buttons.length - 1];

    Object.defineProperty(document, 'activeElement', { value: firstBtn, configurable: true });

    const event = new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true });
    Object.defineProperty(event, 'preventDefault', { value: vi.fn() });
    container.dispatchEvent(event);

    expect(event.preventDefault).toHaveBeenCalled();
    expect(lastBtn.focus).toHaveBeenCalled();
  });

  it('ignores non-Tab keys', async () => {
    const containerRef = ref<HTMLElement | null>(container);
    const isActive = ref(true);

    useFocusTrap(containerRef, isActive);
    await nextTick();

    const event = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true });
    Object.defineProperty(event, 'preventDefault', { value: vi.fn() });
    container.dispatchEvent(event);

    expect(event.preventDefault).not.toHaveBeenCalled();
  });

  it('prevents Tab when no focusable elements exist', async () => {
    // Empty container
    const emptyContainer = document.createElement('div');
    emptyContainer.focus = vi.fn();
    document.body.appendChild(emptyContainer);

    const containerRef = ref<HTMLElement | null>(emptyContainer);
    const isActive = ref(true);

    useFocusTrap(containerRef, isActive);
    await nextTick();

    const event = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true });
    Object.defineProperty(event, 'preventDefault', { value: vi.fn() });
    emptyContainer.dispatchEvent(event);

    expect(event.preventDefault).toHaveBeenCalled();
  });
});
