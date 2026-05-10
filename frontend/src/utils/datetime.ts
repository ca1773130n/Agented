/**
 * Centralized safe-date formatting helpers.
 *
 * Background — every page in the app rolls its own ``new Date(x).toLocale*()``
 * calls, and ``new Date('2026-05-10 12:34:56')`` (SQLite's default
 * timestamp format without the ISO ``T`` / ``Z``) silently returns an
 * Invalid Date object on some engines. ``toLocaleString()`` on an
 * Invalid Date doesn't throw — it returns the literal string ``"Invalid
 * Date"``, which then leaks into the UI.
 *
 * These helpers guard with ``Number.isNaN(d.getTime())`` so unparseable
 * timestamps render as a stable fallback (``""`` by default) instead.
 * Use these everywhere; never call ``new Date(x).toLocale*()`` inline.
 */

/** Internal — parse and validate a timestamp. */
function parseSafe(input: string | number | Date | null | undefined): Date | null {
  if (input === null || input === undefined || input === '') return null;
  const d = input instanceof Date ? input : new Date(input);
  if (Number.isNaN(d.getTime())) return null;
  return d;
}

/**
 * Format a timestamp as a localized full date+time string.
 *
 * Use for "show the user when this happened" surfaces (timeline rows,
 * activity logs, audit records). Returns ``fallback`` when the input
 * is missing or unparseable.
 */
export function safeFormatDateTime(
  input: string | number | Date | null | undefined,
  fallback = '',
  options?: Intl.DateTimeFormatOptions,
): string {
  const d = parseSafe(input);
  if (!d) return fallback;
  return options ? d.toLocaleString(undefined, options) : d.toLocaleString();
}

/**
 * Format a timestamp as a localized date-only string.
 *
 * Use when the time component would be noise (charts, install
 * dates, due dates).
 */
export function safeFormatDate(
  input: string | number | Date | null | undefined,
  fallback = '',
  options?: Intl.DateTimeFormatOptions,
  locale?: string | string[],
): string {
  const d = parseSafe(input);
  if (!d) return fallback;
  if (options || locale) return d.toLocaleDateString(locale, options);
  return d.toLocaleDateString();
}

/**
 * Format a timestamp as a localized time-only string (HH:MM:SS).
 *
 * Use for chat bubbles / message stamps where the date is implicit
 * from the surrounding context.
 */
export function safeFormatTime(
  input: string | number | Date | null | undefined,
  fallback = '',
  options?: Intl.DateTimeFormatOptions,
): string {
  const d = parseSafe(input);
  if (!d) return fallback;
  return options ? d.toLocaleTimeString(undefined, options) : d.toLocaleTimeString();
}

/**
 * Format a duration (in seconds) as a compact ``Xh Ym Zs`` /
 * ``Ym Zs`` / ``Zs`` string.
 *
 * Use for execution durations and rate-limit countdowns. Returns
 * the fallback when the input is non-finite or negative.
 */
export function safeFormatDuration(
  seconds: number | null | undefined,
  fallback = '',
): string {
  if (seconds === null || seconds === undefined) return fallback;
  if (!Number.isFinite(seconds) || seconds < 0) return fallback;
  const total = Math.floor(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h}h ${m}m ${s}s`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

/**
 * Format a timestamp as a relative-to-now phrase ("just now", "5m ago",
 * "2h ago", "3d ago"). Falls back to a localized date for older entries.
 *
 * Use for activity feeds and recency indicators where the absolute
 * time is less interesting than how recent something is.
 */
export function safeFormatRelative(
  input: string | number | Date | null | undefined,
  fallback = '',
): string {
  const d = parseSafe(input);
  if (!d) return fallback;
  const diffMs = Date.now() - d.getTime();
  if (diffMs < 0) return safeFormatDateTime(d, fallback);
  const diffSec = Math.floor(diffMs / 1000);
  if (diffSec < 30) return 'just now';
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
  if (diffSec < 86400 * 7) return `${Math.floor(diffSec / 86400)}d ago`;
  return d.toLocaleDateString();
}

/**
 * Returns ``true`` when the given input would parse to a valid Date.
 * Useful in templates to gate display of a stamp.
 */
export function isValidTimestamp(
  input: string | number | Date | null | undefined,
): boolean {
  return parseSafe(input) !== null;
}
