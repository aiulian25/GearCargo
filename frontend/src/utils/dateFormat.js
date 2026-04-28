/**
 * Centralised date formatting — always dd/mm/yyyy (en-GB).
 * Import these helpers instead of calling toLocaleDateString() directly.
 */

const LOCALE = 'en-GB'

/**
 * Format a date value as dd/mm/yyyy  (e.g. 28/04/2026)
 * @param {string|Date|null} value
 * @returns {string}
 */
export function formatDate(value) {
  if (!value) return '-'
  const d = value instanceof Date ? value : new Date(value)
  if (isNaN(d.getTime())) return '-'
  return d.toLocaleDateString(LOCALE)
}

/**
 * Format a date as "28 April 2026" (long month, no weekday)
 */
export function formatDateLong(value) {
  if (!value) return '-'
  const d = value instanceof Date ? value : new Date(value)
  if (isNaN(d.getTime())) return '-'
  return d.toLocaleDateString(LOCALE, { day: 'numeric', month: 'long', year: 'numeric' })
}

/**
 * Format a date with weekday, e.g. "Monday, 28 April 2026"
 */
export function formatDateWithWeekday(value) {
  if (!value) return '-'
  const d = value instanceof Date ? value : new Date(value)
  if (isNaN(d.getTime())) return '-'
  return d.toLocaleDateString(LOCALE, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
}

/**
 * Format a date as "Apr 2026" (month + year only, used for timeline group labels)
 */
export function formatMonthYear(value) {
  if (!value) return '-'
  const d = value instanceof Date ? value : new Date(value)
  if (isNaN(d.getTime())) return '-'
  return d.toLocaleDateString(LOCALE, { year: 'numeric', month: 'long' })
}

/**
 * Format a date as "28 Apr 2026" (short month)
 */
export function formatDateShort(value) {
  if (!value) return '-'
  const d = value instanceof Date ? value : new Date(value)
  if (isNaN(d.getTime())) return '-'
  return d.toLocaleDateString(LOCALE, { day: 'numeric', month: 'short', year: 'numeric' })
}

/**
 * Format a datetime as localised date + time  (e.g. 28/04/2026, 14:30:00)
 */
export function formatDateTime(value) {
  if (!value) return '-'
  const d = value instanceof Date ? value : new Date(value)
  if (isNaN(d.getTime())) return '-'
  return d.toLocaleString(LOCALE)
}
