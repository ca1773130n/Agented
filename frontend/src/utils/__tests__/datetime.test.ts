import { describe, it, expect, beforeAll, afterAll, vi } from 'vitest'
import {
  safeFormatDateTime,
  safeFormatDate,
  safeFormatTime,
  safeFormatDuration,
  safeFormatRelative,
  isValidTimestamp,
} from '../datetime'

describe('datetime — safe formatters', () => {
  describe('null / undefined / empty inputs', () => {
    it('returns fallback for nullish or empty', () => {
      expect(safeFormatDateTime(null)).toBe('')
      expect(safeFormatDateTime(undefined)).toBe('')
      expect(safeFormatDateTime('')).toBe('')
      expect(safeFormatDate(null)).toBe('')
      expect(safeFormatTime(null)).toBe('')
      expect(safeFormatRelative(null)).toBe('')
    })

    it('honors a custom fallback', () => {
      expect(safeFormatDateTime(null, '—')).toBe('—')
      expect(safeFormatDate(undefined, 'never')).toBe('never')
      expect(safeFormatTime(null, '--:--')).toBe('--:--')
    })
  })

  describe('Invalid Date inputs (the bug class this exists to prevent)', () => {
    // These inputs would silently produce ``"Invalid Date"`` from
    // ``toLocaleString()`` on most engines; the safe formatters must
    // return the fallback instead.
    const bad = [
      'not-a-date',
      'abcdef',
      '99/99/9999',
      'tomorrow',
    ]

    for (const input of bad) {
      it(`omits "Invalid Date" for ${JSON.stringify(input)}`, () => {
        expect(safeFormatDateTime(input)).not.toContain('Invalid')
        expect(safeFormatDate(input)).not.toContain('Invalid')
        expect(safeFormatTime(input)).not.toContain('Invalid')
        expect(safeFormatRelative(input)).not.toContain('Invalid')
      })
    }

    it('returns fallback for the literal Invalid Date object', () => {
      const d = new Date('garbage')
      expect(safeFormatDateTime(d, '—')).toBe('—')
    })
  })

  describe('valid inputs', () => {
    it('renders ISO timestamps as a non-empty localized string', () => {
      const out = safeFormatDateTime('2026-05-10T12:34:56Z')
      expect(out).not.toBe('')
      expect(out).not.toContain('Invalid')
    })

    it('handles SQLite "YYYY-MM-DD HH:MM:SS" format too', () => {
      // The whole reason this utility exists — engines that accept
      // this form must still render a non-Invalid string. Engines that
      // reject it must still produce the fallback (no leaked
      // "Invalid Date").
      const out = safeFormatDateTime('2026-05-10 12:34:56', '—')
      expect(out).not.toContain('Invalid')
      // Either successfully parsed (some engines accept this) or
      // fell back — both are correct outcomes for this utility.
      expect(out !== '' || out === '—').toBe(true)
    })

    it('passes through option overrides on safeFormatDate', () => {
      const out = safeFormatDate('2026-05-10T12:00:00Z', '', {
        month: 'short',
        day: 'numeric',
      })
      expect(out).not.toBe('')
      expect(out).not.toContain('Invalid')
    })
  })

  describe('safeFormatDuration', () => {
    it('formats hours/minutes/seconds compactly', () => {
      expect(safeFormatDuration(0)).toBe('0s')
      expect(safeFormatDuration(45)).toBe('45s')
      expect(safeFormatDuration(60)).toBe('1m 0s')
      expect(safeFormatDuration(3600)).toBe('1h 0m 0s')
      expect(safeFormatDuration(3661)).toBe('1h 1m 1s')
    })

    it('rejects negative / non-finite / nullish input', () => {
      expect(safeFormatDuration(null)).toBe('')
      expect(safeFormatDuration(undefined)).toBe('')
      expect(safeFormatDuration(-1)).toBe('')
      expect(safeFormatDuration(Infinity)).toBe('')
      expect(safeFormatDuration(NaN)).toBe('')
      expect(safeFormatDuration(-1, 'n/a')).toBe('n/a')
    })
  })

  describe('safeFormatRelative', () => {
    beforeAll(() => {
      // Pin "now" so the bucket boundaries are deterministic.
      vi.useFakeTimers()
      vi.setSystemTime(new Date('2026-05-10T12:00:00Z'))
    })
    afterAll(() => {
      vi.useRealTimers()
    })

    it('renders "just now" for sub-30s diffs', () => {
      expect(safeFormatRelative('2026-05-10T11:59:50Z')).toBe('just now')
    })

    it('renders Xm ago for sub-hour diffs', () => {
      expect(safeFormatRelative('2026-05-10T11:55:00Z')).toBe('5m ago')
    })

    it('renders Xh ago for sub-day diffs', () => {
      expect(safeFormatRelative('2026-05-10T09:00:00Z')).toBe('3h ago')
    })

    it('renders Xd ago for sub-week diffs', () => {
      expect(safeFormatRelative('2026-05-08T12:00:00Z')).toBe('2d ago')
    })

    it('falls back to a localized date for older entries', () => {
      const out = safeFormatRelative('2026-04-01T12:00:00Z')
      expect(out).not.toContain('ago')
      expect(out).not.toContain('Invalid')
      expect(out).not.toBe('')
    })
  })

  describe('isValidTimestamp', () => {
    it('returns true for parseable timestamps', () => {
      expect(isValidTimestamp('2026-05-10T12:34:56Z')).toBe(true)
      expect(isValidTimestamp(Date.now())).toBe(true)
      expect(isValidTimestamp(new Date())).toBe(true)
    })

    it('returns false for null / Invalid Date / garbage', () => {
      expect(isValidTimestamp(null)).toBe(false)
      expect(isValidTimestamp(undefined)).toBe(false)
      expect(isValidTimestamp('')).toBe(false)
      expect(isValidTimestamp('garbage')).toBe(false)
      expect(isValidTimestamp(new Date('bad'))).toBe(false)
    })
  })
})
