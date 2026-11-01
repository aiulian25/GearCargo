/**
 * Calendar dates stay YYYY-MM-DD; only instants undergo timezone conversion.
 * Legacy API datetimes without an offset mean UTC (the database convention).
 * Pure helpers accept preferences; React callers use DateFormatContext.
 */
const LOCALES = { en: 'en-GB', ro: 'ro-RO', es: 'es-ES' }
const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/
const NAIVE_INSTANT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/

// UTC is an arithmetic carrier here, never a conversion of local midnight.
export function calendarDate(year, month, day = 1) {
  const date = new Date(0)
  date.setUTCFullYear(year, month, day) // month is zero-based; overflow is deliberate
  return date.toISOString().slice(0, 10)
}

export function parseCalendarDate(value) {
  if (typeof value !== 'string' || !DATE_ONLY.test(value)) return null
  const [year, month, day] = value.split('-').map(Number)
  if (year < 1 || month < 1 || month > 12 || day < 1 || day > 31) return null
  return calendarDate(year, month - 1, day) === value ? { year, month, day } : null
}

/** Input defaults follow the device's local calendar day, not UTC. */
export function localDate(value = new Date()) {
  return calendarDate(value.getFullYear(), value.getMonth(), value.getDate())
}

/** Whole calendar days, unaffected by 23/25-hour daylight-saving days. */
export function calendarDaysBetween(value, reference) {
  if (!parseCalendarDate(value) || !parseCalendarDate(reference)) return NaN
  return (Date.parse(`${value}T00:00:00Z`) - Date.parse(`${reference}T00:00:00Z`)) / 86400000
}

/** Clamp anniversaries to the last day of the target month (Feb 29 → Feb 28). */
export function addCalendarYears(value, years) {
  const parts = parseCalendarDate(value)
  if (!parts) return null
  const year = parts.year + years
  const lastDay = Number(calendarDate(year, parts.month, 0).slice(8))
  return calendarDate(year, parts.month - 1, Math.min(parts.day, lastDay))
}

export function parseInstant(value) {
  if (value == null || value === '' || (typeof value === 'string' && DATE_ONLY.test(value))) return null
  if (typeof value === 'string' && (!/^\d{4}-\d{2}-\d{2}T/.test(value) || !parseCalendarDate(value.slice(0, 10)))) return null
  const date = value instanceof Date ? value : new Date(
    typeof value === 'string' && NAIVE_INSTANT.test(value) ? `${value}Z` : value,
  )
  return Number.isNaN(date.getTime()) ? null : date
}

function locale(preferences) {
  return LOCALES[preferences.language] || LOCALES.en
}

function timeZone(preferences) {
  if (!preferences.timezone) return undefined // browser zone before sign-in
  try {
    new Intl.DateTimeFormat('en', { timeZone: preferences.timezone })
    return preferences.timezone
  } catch {
    return 'UTC' // legacy invalid saved preferences must not crash rendering
  }
}

function displayDate(value, preferences) {
  if (typeof value === 'string' && DATE_ONLY.test(value)) {
    return parseCalendarDate(value) ? { date: new Date(`${value}T00:00:00Z`), timeZone: 'UTC' } : null
  }
  const date = parseInstant(value)
  return date ? { date, timeZone: timeZone(preferences) } : null
}

function namedDate(value, preferences, options) {
  const parsed = displayDate(value, preferences)
  return parsed ? new Intl.DateTimeFormat(locale(preferences), { ...options, timeZone: parsed.timeZone }).format(parsed.date) : '-'
}

export function formatDate(value, preferences = {}) {
  const parsed = displayDate(value, preferences)
  if (!parsed) return '-'
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-GB', {
    timeZone: parsed.timeZone, year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(parsed.date).map(part => [part.type, part.value]))
  const yyyy = parts.year.padStart(4, '0'), mm = parts.month, dd = parts.day
  switch (preferences.date_format) {
    case 'MM/DD/YYYY': return `${mm}/${dd}/${yyyy}`
    case 'YYYY-MM-DD': return `${yyyy}-${mm}-${dd}`
    case 'DD.MM.YYYY': return `${dd}.${mm}.${yyyy}`
    default: return `${dd}/${mm}/${yyyy}` // established DD/MM/YYYY default
  }
}

export function formatDateLong(value, preferences = {}) {
  return namedDate(value, preferences, { day: 'numeric', month: 'long', year: 'numeric' })
}
export function formatDateWithWeekday(value, preferences = {}) {
  return namedDate(value, preferences, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
}
export function formatMonthYear(value, preferences = {}) {
  return namedDate(value, preferences, { year: 'numeric', month: 'long' })
}
export function formatDateShort(value, preferences = {}) {
  return namedDate(value, preferences, { day: 'numeric', month: 'short', year: 'numeric' })
}
export function formatDateTime(value, preferences = {}) {
  // A calendar date has no time or zone. Do not invent midnight for it.
  if (typeof value === 'string' && DATE_ONLY.test(value)) return formatDate(value, preferences)
  const date = parseInstant(value)
  if (!date) return '-'
  const time = new Intl.DateTimeFormat(locale(preferences), {
    timeZone: timeZone(preferences), hour: '2-digit', minute: '2-digit', second: '2-digit',
  }).format(date)
  return `${formatDate(date, preferences)}, ${time}`
}
export function monthNames(preferences = {}, width = 'long') {
  return Array.from({ length: 12 }, (_, month) => namedDate(calendarDate(2000, month), preferences, { month: width }))
}

export function createDateFormatters(preferences = {}) {
  return Object.fromEntries(Object.entries({ formatDate, formatDateLong, formatDateWithWeekday,
    formatMonthYear, formatDateShort, formatDateTime }).map(([name, formatter]) => [name, value => formatter(value, preferences)]).concat([
    ['monthNames', monthNames(preferences)], ['monthNamesShort', monthNames(preferences, 'short')],
  ]))
}
