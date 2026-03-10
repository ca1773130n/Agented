import { describe, it, expect } from 'vitest';
import { useTokenFormatting } from '../useTokenFormatting';

describe('useTokenFormatting', () => {
  const { formatCurrency, formatTokenCount, parseWindowType } = useTokenFormatting();

  describe('formatCurrency', () => {
    it('formats a whole number with two decimal places', () => {
      expect(formatCurrency(5)).toBe('$5.00');
    });

    it('formats a decimal value', () => {
      expect(formatCurrency(12.5)).toBe('$12.50');
    });

    it('formats zero', () => {
      expect(formatCurrency(0)).toBe('$0.00');
    });
  });

  describe('formatTokenCount', () => {
    it('returns raw number for values under 1000', () => {
      expect(formatTokenCount(999)).toBe('999');
    });

    it('formats thousands as K', () => {
      expect(formatTokenCount(1500)).toBe('1.5K');
    });

    it('formats millions as M', () => {
      expect(formatTokenCount(2_500_000)).toBe('2.5M');
    });

    it('formats billions as B', () => {
      expect(formatTokenCount(3_000_000_000)).toBe('3.0B');
    });

    it('formats zero', () => {
      expect(formatTokenCount(0)).toBe('0');
    });
  });

  describe('parseWindowType', () => {
    it('parses Codex primary window', () => {
      expect(parseWindowType('GPT-5.3-Codex_primary_window')).toEqual({
        model: 'GPT-5.3-Codex',
        window: '5 Hour',
      });
    });

    it('parses Codex secondary window', () => {
      expect(parseWindowType('GPT-5.3-Codex-Spark_secondary_window')).toEqual({
        model: 'GPT-5.3-Codex-Spark',
        window: '7 Day',
      });
    });

    it('parses Claude five_hour window', () => {
      expect(parseWindowType('five_hour')).toEqual({ model: 'Opus', window: '5 Hour' });
    });

    it('parses Claude 5h_sliding window', () => {
      expect(parseWindowType('5h_sliding')).toEqual({ model: 'Opus', window: '5 Hour' });
    });

    it('parses Claude seven_day window', () => {
      expect(parseWindowType('seven_day')).toEqual({ model: 'Opus', window: '7 Day' });
    });

    it('parses Claude weekly window', () => {
      expect(parseWindowType('weekly')).toEqual({ model: 'Opus', window: '7 Day' });
    });

    it('parses seven_day_sonnet window', () => {
      expect(parseWindowType('seven_day_sonnet')).toEqual({ model: 'Sonnet', window: '7 Day' });
    });

    it('returns raw string as model for unknown window types (Gemini)', () => {
      expect(parseWindowType('gemini-2.0-flash')).toEqual({
        model: 'gemini-2.0-flash',
        window: '',
      });
    });
  });
});
