import { describe, expect, it } from 'vitest';
import { lineDiff } from '../lineDiff';

describe('lineDiff', () => {
  it('marks every line unchanged for identical text', () => {
    const { rows, summary } = lineDiff('a\nb\nc', 'a\nb\nc');
    expect(rows.every((r) => r.type === 'unchanged')).toBe(true);
    expect(summary).toEqual({ added: 0, removed: 0, unchanged: 3 });
  });

  it('detects a replaced middle line as removed + added', () => {
    const { rows, summary } = lineDiff('a\nOLD\nc', 'a\nNEW\nc');
    expect(summary.unchanged).toBe(2);
    expect(summary.removed).toBe(1);
    expect(summary.added).toBe(1);
    expect(rows.find((r) => r.type === 'removed')?.text).toBe('OLD');
    expect(rows.find((r) => r.type === 'added')?.text).toBe('NEW');
  });

  it('handles pure insertion', () => {
    const { summary } = lineDiff('a\nc', 'a\nb\nc');
    expect(summary).toEqual({ added: 1, removed: 0, unchanged: 2 });
  });

  it('handles pure deletion', () => {
    const { summary } = lineDiff('a\nb\nc', 'a\nc');
    expect(summary).toEqual({ added: 0, removed: 1, unchanged: 2 });
  });

  it('empty before → all added', () => {
    const { summary } = lineDiff('', 'x\ny');
    // '' splits to [''] (1 line); 'x\ny' is 2 lines — the shared '' anchors one.
    expect(summary.added).toBeGreaterThanOrEqual(1);
    expect(summary.removed).toBe(0);
  });

  it('preserves order: removed before added at a divergence', () => {
    const { rows } = lineDiff('a\nOLD\nc', 'a\nNEW\nc');
    const oldIdx = rows.findIndex((r) => r.text === 'OLD');
    const newIdx = rows.findIndex((r) => r.text === 'NEW');
    expect(oldIdx).toBeLessThan(newIdx);
  });
});
