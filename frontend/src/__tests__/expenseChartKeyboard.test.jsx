import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import VehicleExpenses from '../pages/vehicles/VehicleExpenses'
import EditVehicle from '../pages/vehicles/EditVehicle'
import { DateFormatProvider } from '../contexts/DateFormatContext'
import { translations } from '../i18n/translations'
import { vehicleApi } from '../services/api'

const state = vi.hoisted(() => ({ language: 'en' }))
vi.mock('../services/api', () => {
  const list = { delete: vi.fn(), getAll: vi.fn(), getByVehicle: vi.fn() }
  return { default: { get: vi.fn() }, vehicleApi: { getById: vi.fn(), getExpenseSummary: vi.fn(), getExpenseRecords: vi.fn() },
    fuelApi: list, serviceApi: list, repairApi: list, taxApi: list, reminderApi: list, insuranceApi: list, consumableApi: list, parkingApi: list }
})
vi.mock('../contexts/LanguageContext', () => {
  const t = key => key.split('.').reduce((v, k) => v?.[k], translations[state.language]) || key
  return { useTranslation: () => ({ t, language: state.language }), useLanguage: () => ({ t, language: state.language }) }
})
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({ user: { currency: 'USD', volume_unit: 'liters' } }) }))
vi.mock('../components/ui/AttachmentViewer', () => ({ default: () => null }))
const summary = { display_currency: 'GBP', converted: true, as_of: '2026-12-31',
  totals: { fuel: 1272, grand_total: 1272 }, available_years: [2026],
  monthly: [{ month: '2026-01', total: 1234.5, breakdown: { fuel: 1234.5 } }, { month: '2026-02', total: 37.5, breakdown: { fuel: 37.5 } }] }
const vehicle = { id: 1, name: 'Accessible car', revision: 1, distance_unit: 'km', photo_url: '/photo.png' }
beforeEach(() => {
  vi.clearAllMocks(); state.language = 'en'
  vehicleApi.getById.mockResolvedValue({ data: vehicle })
  vehicleApi.getExpenseSummary.mockResolvedValue({ data: summary })
  vehicleApi.getExpenseRecords.mockResolvedValue({ data: { category: 'fuel', records: [], current_page: 1, pages: 1, total: 0, page_total: 0, display_currency: 'GBP' } })
})
afterEach(cleanup)
function page(component, path, language = 'en') {
  state.language = language
  return render(<DateFormatProvider language={language}><MemoryRouter initialEntries={['/vehicles/1', path]}>
    <Routes><Route path="/vehicles/:id/expenses" element={component} /><Route path="/vehicles/:id/edit" element={component} />
      <Route path="/vehicles/:id" element={<p>Vehicle home</p>} /></Routes>
  </MemoryRouter></DateFormatProvider>)
}

// Browser coverage exercises actual Tab/Enter/Space defaults. jsdom assertions
// verify native semantics and filter results without faking a keyboard click.
it.each([
  ['en', 'January 2026: 1,234.50 GBP', 'February 2026: 37.50 GBP', 'December'],
  ['ro', 'ianuarie 2026: 1.234,50 GBP', 'februarie 2026: 37,50 GBP', 'decembrie'],
  ['es', 'enero 2026: 1234,50 GBP', 'febrero 2026: 37,50 GBP', 'diciembre'],
])('has native localized month filters and complete tabular totals (%s)', async (language, january, february, december) => {
  page(<VehicleExpenses />, '/vehicles/1/expenses?year=2026', language)
  const first = await screen.findByRole('button', { name: january })
  const group = screen.getByRole('group', { name: translations[language].charts.monthlyExpenses })
  const buttons = within(group).getAllByRole('button')
  expect(buttons).toHaveLength(12)
  for (const button of buttons) {
    expect(button.tagName).toBe('BUTTON'); expect(button.type).toBe('button'); expect(button.tabIndex).toBe(0)
    expect(button.getAttribute('aria-pressed')).toBe('false')
  }
  await act(async () => { fireEvent.click(first) })
  await waitFor(() => expect(vehicleApi.getExpenseRecords).toHaveBeenLastCalledWith('1', expect.objectContaining({ year: 2026, month: 1, page: 1 })))
  expect(first.getAttribute('aria-pressed')).toBe('true')
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: february })) })
  expect(first.getAttribute('aria-pressed')).toBe('false')
  await waitFor(() => expect(vehicleApi.getExpenseRecords).toHaveBeenLastCalledWith('1', expect.objectContaining({ month: 2 })))
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: february })) })
  await waitFor(() => expect(vehicleApi.getExpenseRecords).toHaveBeenLastCalledWith('1', expect.objectContaining({ month: null })))
  await act(async () => { fireEvent.click(first) })
  const clear = screen.getByRole('button', { name: translations[language].expenses.fullYear })
  clear.focus(); await act(async () => { fireEvent.click(clear) })
  expect(document.activeElement).toBe(clear)
  expect(clear.getAttribute('aria-pressed')).toBe('true')
  await act(async () => { fireEvent.click(screen.getByText(translations[language].expenses.monthlyTotals, { exact: true })) })
  const table = screen.getByRole('table', { name: translations[language].expenses.monthlyTotalsYear.replace('{year}', 2026) })
  expect(within(table).getAllByRole('row')).toHaveLength(13)
  expect(within(table).getByRole('rowheader', { name: december })).toBeTruthy()
  expect(within(table).getAllByText(language === 'en' ? '0.00 GBP' : '0,00 GBP')).toHaveLength(10)
  expect(vehicleApi.getExpenseSummary).toHaveBeenCalledTimes(1)
})

it.each(['en', 'ro', 'es'])('names edit controls during loading and after loading (%s)', async language => {
  let resolveVehicle
  vehicleApi.getById.mockReturnValue(new Promise(resolve => { resolveVehicle = resolve }))
  page(<EditVehicle />, '/vehicles/1/edit', language)
  expect(screen.getByRole('button', { name: translations[language].common.close })).toBeTruthy()
  resolveVehicle({ data: vehicle })
  const remove = await screen.findByRole('button', { name: translations[language].vehicles.removePhoto })
  expect(remove.querySelector('span').getAttribute('aria-hidden')).toBe('true')
  await act(async () => { fireEvent.click(remove) })
  expect(screen.queryByRole('button', { name: translations[language].vehicles.removePhoto })).toBeNull()
  expect(screen.getByRole('button', { name: translations[language].common.save })).toBeTruthy()
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: translations[language].common.close })) })
  expect(await screen.findByText('Vehicle home')).toBeTruthy()
})
