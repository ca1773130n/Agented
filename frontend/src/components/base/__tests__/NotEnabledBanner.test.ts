import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import NotEnabledBanner from '../NotEnabledBanner.vue';

describe('NotEnabledBanner', () => {
  it('renders the feature name in the headline', () => {
    const w = mount(NotEnabledBanner, { props: { feature: 'Anomaly detection' } });
    expect(w.find('strong').text()).toBe('Anomaly detection is not yet enabled in this deployment.');
  });

  it('uses the default data-testid when none is provided', () => {
    const w = mount(NotEnabledBanner, { props: { feature: 'Quota enforcement' } });
    expect(w.find('[data-testid="not-enabled-banner"]').exists()).toBe(true);
  });

  it('honors a custom testid prop', () => {
    const w = mount(NotEnabledBanner, {
      props: { feature: 'Digest delivery', testid: 'digests-not-enabled' },
    });
    expect(w.find('[data-testid="digests-not-enabled"]').exists()).toBe(true);
    expect(w.find('[data-testid="not-enabled-banner"]').exists()).toBe(false);
  });

  it('renders the detail line when provided', () => {
    const w = mount(NotEnabledBanner, {
      props: { feature: 'X', detail: 'Backend handler ships in v0.8.' },
    });
    expect(w.find('p').text()).toBe('Backend handler ships in v0.8.');
  });

  it('omits the <p> when no detail is provided', () => {
    const w = mount(NotEnabledBanner, { props: { feature: 'X' } });
    expect(w.find('p').exists()).toBe(false);
  });

  it('uses role=status for assistive tech', () => {
    const w = mount(NotEnabledBanner, { props: { feature: 'X' } });
    expect(w.find('[role="status"]').exists()).toBe(true);
  });
});
