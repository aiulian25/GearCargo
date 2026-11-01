import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import VehicleAlerts from '../pages/vehicles/VehicleAlerts'
import Calendar from '../pages/calendar/Calendar'
import { DateFormatProvider } from '../contexts/DateFormatContext'
import { useDateFormat } from '../hooks/useDateFormat'
import { translations } from '../i18n/translations'
import { calendarApi, vehicleApi } from '../services/api'

vi.mock('../services/api', () => ({ calendarApi: { getEntries: vi.fn() }, vehicleApi: { getAll: vi.fn(), getById: vi.fn(), getStats: vi.fn() } }))
vi.mock('../contexts/LanguageContext', () => {
  const t = key => key.split('.').reduce((v, k) => v?.[k], translations.en) || key
  return { useTranslation: () => ({ t }) }
})
afterEach(() => { cleanup(); vi.useRealTimers() })
beforeEach(() => {
  vi.clearAllMocks()
  vi.useFakeTimers({ toFake: ['Date'] })
  vehicleApi.getAll.mockResolvedValue({ data: { vehicles: [] } })
})

it.each([[2026, 6, 1, '2026-07-01', '2026-06-01', '2026-08-31'],
  [2026, 0, 1, '2026-01-01', '2025-12-01', '2026-02-28'],
  [2024, 1, 29, '2024-02-29', '2024-01-01', '2024-03-31'],
  [2026, 10, 30, '2026-11-30', '2026-10-01', '2026-12-31']])(
  'keeps grid, selected entry, month count and request bounds calendar-safe (%s-%s-%s)', async (year, month, day, date, start, end) => {
    vi.setSystemTime(new Date(year, month, day, 0, 5))
    calendarApi.getEntries.mockResolvedValue({ data: { entries: [{ id: 'fuel-1', date, type: 'fuel', title: 'Boundary fuel', vehicle_name: 'Test vehicle', amount: 5 }] } })
    const { container } = render(<DateFormatProvider language="ro"><MemoryRouter><Calendar /></MemoryRouter></DateFormatProvider>)
    await waitFor(() => expect(calendarApi.getEntries).toHaveBeenCalledWith(start, end, null))
    const cells = await screen.findAllByRole('button', { name: String(day), exact: true })
    const cell = cells.find(button => button.classList.contains('bg-transparent'))
    expect(cell.querySelector('.bg-amber-500')).toBeTruthy()
    expect(cell.querySelector('span').textContent).toBe(String(day))
    expect(screen.getByText(translations.en.calendar.entriesThisMonth).nextElementSibling.textContent.trim()).toBe('1')
    fireEvent.click(cell)
    expect(screen.getByText('Boundary fuel')).toBeTruthy()
    expect(container.querySelector('h2').textContent).toContain(String(day))
    expect(container.querySelector('h2').textContent).toContain(String(year))
  })

function Preview() {
  const { formatDate, formatDateTime, monthNames } = useDateFormat()
  return <output>{formatDate('2026-01-02')}|{formatDateTime('2026-01-01T00:30:00')}|{monthNames[0]}</output>
}
it('updates presentation immediately when preferences change and resets after logout', () => {
  const { rerender } = render(<DateFormatProvider language="en" dateFormat="DD/MM/YYYY" timezone="UTC"><Preview /></DateFormatProvider>)
  expect(screen.getByRole('status').textContent).toBe('02/01/2026|01/01/2026, 00:30:00|January')
  rerender(<DateFormatProvider language="ro" dateFormat="YYYY-MM-DD" timezone="America/Los_Angeles"><Preview /></DateFormatProvider>)
  expect(screen.getByRole('status').textContent).toBe('2026-01-02|2025-12-31, 16:30:00|ianuarie')
  rerender(<DateFormatProvider language="es"><Preview /></DateFormatProvider>)
  expect(screen.getByRole('status').textContent).toMatch(/^02\/01\/2026\|.*\|enero$/)
})

it('keeps loaded alert dates as calendar days and applies changed preferences without refetching', async () => {
  vi.setSystemTime(new Date(2026, 2, 28, 23, 55))
  vehicleApi.getById.mockResolvedValue({ data: { id: 1, name: 'DST fixture', tax_due_date: '2026-03-30', insurance_expiry: '2026-03-29' } })
  vehicleApi.getStats.mockResolvedValue({ data: {} })
  const view = dateFormat => <MemoryRouter initialEntries={['/vehicles/1/alerts']}><DateFormatProvider
    language="en" dateFormat={dateFormat} timezone="America/Los_Angeles"><Routes>
    <Route path="/vehicles/:id/alerts" element={<VehicleAlerts />} />
  </Routes></DateFormatProvider></MemoryRouter>
  const { rerender } = render(view('DD/MM/YYYY'))
  expect(await screen.findByText('30/03/2026')).toBeTruthy()
  expect(screen.getByText('29/03/2026')).toBeTruthy()
  expect(screen.getByText('2 days remaining')).toBeTruthy()
  rerender(view('YYYY-MM-DD'))
  expect(screen.getByText('2026-03-30')).toBeTruthy()
  expect(screen.getByText('2026-03-29')).toBeTruthy()
  expect(vehicleApi.getById).toHaveBeenCalledTimes(1)
})
