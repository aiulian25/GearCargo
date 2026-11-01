import { describe, expect, it } from 'vitest'
import { addCalendarYears, calendarDate, calendarDaysBetween, formatDate, formatDateLong, formatDateTime,
  formatDateWithWeekday, formatMonthYear, localDate, monthNames, parseCalendarDate, parseInstant } from '../utils/dateFormat'

describe('calendar dates (run under UTC, Europe/London, America/Los_Angeles and Pacific/Auckland)', () => {
  it.each(['2026-01-01', '2024-02-29', '2026-07-01', '2026-03-29', '2026-10-25', '2026-12-31'])(
    'preserves %s in every display zone', value => {
      for (const timezone of ['UTC', 'Europe/London', 'America/Los_Angeles', 'Pacific/Auckland']) {
        expect(formatDate(value, { timezone, date_format: 'YYYY-MM-DD' })).toBe(value)
        expect(formatDateTime(value, { timezone, date_format: 'YYYY-MM-DD' })).toBe(value)
      }
    })
  it.each(['2025-02-29', '2026-04-31', '2026-13-01', '2026-00-12', '0000-01-01', 'no date'])(
    'rejects an invalid calendar date %s', value => {
      expect(parseCalendarDate(value)).toBeNull()
      expect(formatDate(value)).toBe('-')
    })
  it('uses local date fields at both sides of midnight, including DST and New Year', () => {
    for (const [year, month, day] of [[2026, 0, 1], [2024, 1, 29], [2026, 6, 1], [2026, 2, 29], [2026, 11, 31]]) {
      expect(localDate(new Date(year, month, day, 0, 5))).toBe(calendarDate(year, month, day))
      expect(localDate(new Date(year, month, day, 23, 55))).toBe(calendarDate(year, month, day))
    }
  })
  it('normalizes month boundaries and clamps leap-day anniversaries without timezone conversion', () => {
    expect(calendarDate(2026, -1, 1)).toBe('2025-12-01')
    expect(calendarDate(2026, 12, 0)).toBe('2026-12-31')
    expect(calendarDate(2024, 2, 0)).toBe('2024-02-29')
    expect(calendarDate(2026, 2, 0)).toBe('2026-02-28')
    expect(addCalendarYears('2024-02-29', 1)).toBe('2025-02-28')
    expect(addCalendarYears('2024-02-29', 4)).toBe('2028-02-29')
    expect(calendarDate(99, 0, 1)).toBe('0099-01-01')
  })
})

it.each([
  ['en', 'January', 'Jan', '1 January 2026'],
  ['ro', 'ianuarie', 'ian.', '1 ianuarie 2026'],
  ['es', 'enero', 'ene', '1 de enero de 2026'],
])('uses %s month/weekday names and independent numeric date preferences', (language, january, short, long) => {
  expect(monthNames({ language })[0]).toBe(january)
  expect(monthNames({ language }, 'short')[0]).toBe(short)
  expect(formatDateLong('2026-01-01', { language })).toBe(long)
  expect(formatMonthYear('2026-01-01', { language })).toContain(january)
  expect(formatDateWithWeekday('2026-01-01', { language })).toContain(january)
  expect(formatDate('2026-01-02', { language, date_format: 'MM/DD/YYYY' })).toBe('01/02/2026')
  expect(formatDate('2026-01-02', { language, date_format: 'YYYY-MM-DD' })).toBe('2026-01-02')
  expect(formatDate('2026-01-02', { language, date_format: 'DD/MM/YYYY' })).toBe('02/01/2026')
})

it('interprets legacy naive timestamps as UTC, honors explicit offsets and the display timezone', () => {
  const preferences = { language: 'en', date_format: 'YYYY-MM-DD', timezone: 'America/Los_Angeles' }
  for (const value of ['2026-01-01T00:30:00', '2026-01-01T00:30:00Z', '2026-01-01T02:30:00+02:00']) {
    expect(formatDateTime(value, preferences)).toBe('2025-12-31, 16:30:00')
    expect(parseInstant(value).toISOString()).toBe('2026-01-01T00:30:00.000Z')
  }
  expect(formatDateTime('2026-07-01T00:30:00Z', { ...preferences, timezone: 'Europe/London' })).toBe('2026-07-01, 01:30:00')
  expect(formatDateTime('2026-12-31T12:30:00Z', { ...preferences, timezone: 'Pacific/Auckland' })).toBe('2027-01-01, 01:30:00')
  expect(parseInstant('2026-01-01')).toBeNull()
})
it('handles missing values and invalid legacy preferences without throwing', () => {
  for (const value of [null, undefined, '', 'invalid', '01/02/2026', '2026-02-30T00:00:00Z', new Date(NaN)]) expect(formatDateTime(value)).toBe('-')
  expect(formatDateTime('2026-01-01T00:30:00', { language: 'unknown', date_format: 'unknown', timezone: 'bad/zone' })).toBe('01/01/2026, 00:30:00')
})

it('counts calendar days across DST, New Year and leap day without elapsed-hour rounding', () => {
  for (const [start, end] of [['2026-03-28', '2026-03-30'], ['2026-10-24', '2026-10-26'],
    ['2025-12-31', '2026-01-02'], ['2024-02-28', '2024-03-01']]) {
    expect(calendarDaysBetween(end, start)).toBe(2)
    expect(calendarDaysBetween(start, end)).toBe(-2)
  }
  expect(calendarDaysBetween('2026-01-01', '2026-01-01')).toBe(0)
})
