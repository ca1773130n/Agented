import { describe, it, expect } from 'vitest';

import { legacyIdToKind, kindToLegacyId, toLocalKind } from '../backend-management';

// Agented keeps "gemini" as its internal backend kind; the ai-accounts sidecar
// (0.4.0) renamed it to "antigravity". These helpers are the single boundary
// where that translation must happen (in BOTH directions).
describe('backend kind boundary: gemini ↔ antigravity', () => {
  it('maps Agented gemini kind/id → sidecar antigravity', () => {
    expect(legacyIdToKind('gemini')).toBe('antigravity');
    expect(legacyIdToKind('backend-gemini')).toBe('antigravity');
  });

  it('maps sidecar antigravity → Agented backend-gemini (inverse)', () => {
    expect(kindToLegacyId('antigravity')).toBe('backend-gemini');
  });

  it('toLocalKind maps sidecar antigravity → local gemini (display direction)', () => {
    expect(toLocalKind('antigravity')).toBe('gemini');
    expect(toLocalKind('backend-antigravity')).toBe('gemini');
    expect(toLocalKind('gemini')).toBe('gemini');
  });

  it('passes other kinds through unchanged', () => {
    for (const k of ['claude', 'codex', 'opencode']) {
      expect(legacyIdToKind(k)).toBe(k);
      expect(legacyIdToKind(`backend-${k}`)).toBe(k);
      expect(kindToLegacyId(k)).toBe(`backend-${k}`);
      expect(toLocalKind(k)).toBe(k);
      expect(toLocalKind(`backend-${k}`)).toBe(k);
    }
  });
});
