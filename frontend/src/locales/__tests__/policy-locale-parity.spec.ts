import { describe, it, expect } from 'vitest';
import en from '../en.json';
import ko from '../ko.json';
import ja from '../ja.json';
import zh from '../zh.json';

/** Flatten nested keys into dotted paths for set comparison. */
function flatKeys(obj: Record<string, unknown>, prefix = ''): string[] {
  return Object.entries(obj).flatMap(([k, v]) => {
    const key = `${prefix}${k}`;
    return v && typeof v === 'object' && !Array.isArray(v)
      ? flatKeys(v as Record<string, unknown>, `${key}.`)
      : [key];
  });
}

describe('policy.* locale parity (en/ko/ja/zh)', () => {
  const locales = { en, ko, ja, zh } as Record<string, { policy: Record<string, unknown> }>;

  it('every locale carries a policy namespace', () => {
    for (const [code, msgs] of Object.entries(locales)) {
      expect(msgs.policy, `${code} is missing the policy namespace`).toBeTruthy();
    }
  });

  it('policy.* key sets are identical across all four locales', () => {
    const ref = flatKeys((en as { policy: Record<string, unknown> }).policy).sort();
    for (const [code, msgs] of Object.entries(locales)) {
      const keys = flatKeys(msgs.policy).sort();
      expect(keys, `${code} policy keys drift from en`).toEqual(ref);
    }
    // Sanity: the namespace is non-trivial.
    expect(ref.length).toBeGreaterThan(20);
  });
});
