import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import VehicleExpenses from '../pages/vehicles/VehicleExpenses'
import { translations } from '../i18n/translations'
import api, { vehicleApi, fuelApi } from '../services/api'
import useExpenseNavigation from '../hooks/useExpenseNavigation'

vi.mock('../services/api', () => {
  const list = () => ({ delete: vi.fn().mockResolvedValue({ data: {} }), getAll: vi.fn().mockResolvedValue({ data: { entries: [], policies: [], reminders: [], todos: [] } }), getByVehicle: vi.fn().mockResolvedValue({ data: { entries: [], policies: [], reminders: [], todos: [] } }) })
  return { default: { get: vi.fn() }, vehicleApi: { getById: vi.fn(), getExpenseSummary: vi.fn(), getExpenseRecords: vi.fn() },
    fuelApi: list(), serviceApi: list(), repairApi: list(), taxApi: list(), reminderApi: list(), insuranceApi: list(), consumableApi: list(),
    parkingApi: { ...list(), getFines: vi.fn().mockResolvedValue({ data: { fines: [] } }) } }
})
vi.mock('../contexts/LanguageContext', () => ({ useTranslation: () => ({
  t: key => key.split('.').reduce((v, k) => v?.[k], translations.en) || key,
}) }))
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({ user: { currency: 'GBP', volume_unit: 'liters' } }) }))
vi.mock('../components/ui/AttachmentViewer', () => ({ default: () => null }))
const year = new Date().getFullYear()
const summary = { display_currency: 'GBP', as_of: `${year}-12-31`, converted: true,
  totals: { fuel: 450, service: 0, repair: 0, tax: 0, parking: 0, consumable: 0, insurance: 0, grand_total: 450 },
  monthly: [{ month: `${year}-01`, total: 450, breakdown: { fuel: 450 } }], available_years: [year, 2020] }
const pageData = page => ({ category: 'fuel', records: Array.from({ length: page === 3 ? 5 : 20 }, (_, i) => ({
  id: (page - 1) * 20 + i + 1, revision: 1, date: `${year}-01-01`, total_price: 10, currency: 'GBP',
  station: `Station ${(page - 1) * 20 + i + 1}`, attachments: [],
})), current_page: page, pages: 3, total: 45, per_page: 20, display_currency: 'GBP', page_total: 200, converted: true })
function Location() {
  const location = useLocation(), navigate = useNavigate()
  return <><output data-testid="location">{location.pathname}{location.search}</output><button onClick={() => navigate(-1)}>Browser back</button></>
}
function Edit() {
  const navigate = useExpenseNavigation('1')
  return <button onClick={() => navigate('/vehicles/1')}>Save edit</button>
}
function renderPage(url = `/vehicles/1/expenses?year=${year}&tab=fuel`) {
  return render(<MemoryRouter initialEntries={[url]}><Location /><Routes>
    <Route path="/vehicles/:id/expenses" element={<VehicleExpenses />} />
    <Route path="/vehicles/:id/fuel/add" element={<Edit />} />
    <Route path="/vehicles/:id" element={<p>Vehicle home</p>} />
  </Routes></MemoryRouter>)
}
afterEach(cleanup)
beforeEach(() => {
  vi.clearAllMocks()
  vehicleApi.getById.mockResolvedValue({ data: { id: 1, name: 'Long history', distance_unit: 'km' } })
  vehicleApi.getExpenseSummary.mockResolvedValue({ data: summary })
  vehicleApi.getExpenseRecords.mockImplementation((_id, filters) => Promise.resolve({ data: pageData(filters.page || 1) }))
  api.get.mockImplementation(url => Promise.resolve({ data: url.includes('expenses-summary') ? summary : { entries: [], todos: [], fines: [] } }))
  fuelApi.getByVehicle.mockResolvedValue({ data: { ...pageData(1), entries: pageData(1).records } })
})
it('lets the owner reach records beyond the first page without refetching whole-history totals', async () => {
  renderPage()
  expect(await screen.findByText('Station 20')).toBeTruthy()
  const next = screen.getByRole('button', { name: 'Next page' })
  fireEvent.click(next)
  expect(await screen.findByText('Station 21')).toBeTruthy()
  expect(screen.queryByText('Station 1')).toBeNull()
  expect(vehicleApi.getExpenseRecords).toHaveBeenLastCalledWith('1', expect.objectContaining({ category: 'fuel', year, page: 2 }))
  expect(vehicleApi.getExpenseSummary).toHaveBeenCalledTimes(1)
  expect(screen.getByTestId('location').textContent).toContain('page=2')
  expect(screen.getByText(`${translations.en.expensePages.periodTotal}: 450.00 GBP`)).toBeTruthy()
  expect(vehicleApi.getById).toHaveBeenCalledTimes(1)
  expect(vehicleApi.getExpenseRecords).toHaveBeenCalledTimes(2)
  expect(fuelApi.getByVehicle).not.toHaveBeenCalled()
})

it('keeps month, year and tab in navigation and restores the exact page after editing', async () => {
  const url = '/vehicles/1/expenses?year=2020&month=1&tab=fuel&page=2'
  renderPage(url)
  expect(await screen.findByText('Station 21')).toBeTruthy()
  expect(vehicleApi.getExpenseRecords).toHaveBeenLastCalledWith('1', expect.objectContaining({ year: 2020, month: 1, category: 'fuel', page: 2 }))
  fireEvent.click(screen.getAllByTitle('Edit')[0])
  fireEvent.click(await screen.findByRole('button', { name: 'Save edit' }))
  expect(await screen.findByText('Station 21')).toBeTruthy()
  expect(screen.getByTestId('location').textContent).toBe(url)
  fireEvent.click(screen.getByRole('button', { name: 'February 2020: 0.00 GBP' }))
  await waitFor(() => expect(vehicleApi.getExpenseRecords).toHaveBeenLastCalledWith('1', expect.objectContaining({ year: 2020, month: 2, page: 1 })))
  fireEvent.click(screen.getByRole('button', { name: 'Browser back' }))
  await waitFor(() => expect(screen.getByTestId('location').textContent).toBe(url))
  expect(await screen.findByText('Station 21')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Service' }))
  await waitFor(() => expect(vehicleApi.getExpenseRecords).toHaveBeenLastCalledWith('1', expect.objectContaining({ year: 2020, month: 1, category: 'service', page: 1 })))
})

it('exposes older years even when the current detail category has no records', async () => {
  vehicleApi.getExpenseRecords.mockResolvedValue({ data: { ...pageData(1), records: [], total: 0, pages: 0 } })
  renderPage()
  const option = await screen.findByRole('option', { name: '2020' })
  fireEvent.change(option.parentElement, { target: { value: '2020' } })
  await waitFor(() => expect(vehicleApi.getExpenseSummary).toHaveBeenLastCalledWith('1', { year: 2020 }))
  expect(vehicleApi.getExpenseRecords).toHaveBeenLastCalledWith('1', expect.objectContaining({ year: 2020, month: null, page: 1 }))
})

it('keeps totals visible when details fail, and offers a retry instead of a false empty result', async () => {
  vehicleApi.getExpenseRecords.mockRejectedValueOnce(new Error('offline'))
  renderPage()
  expect(await screen.findByText(translations.en.expensePages.loadFailed)).toBeTruthy()
  expect(screen.queryByText(translations.en.expenses.noEntries)).toBeNull()
  expect(screen.getAllByText('450.00 GBP').length).toBeGreaterThan(0)
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
  expect(await screen.findByText('Station 20')).toBeTruthy()
})

it('ignores a late detail response after filters change', async () => {
  let finishOldPage
  vehicleApi.getExpenseRecords.mockImplementationOnce(() => new Promise(resolve => { finishOldPage = resolve }))
  renderPage()
  fireEvent.click(await screen.findByRole('button', { name: 'Service' }))
  await waitFor(() => expect(vehicleApi.getExpenseRecords).toHaveBeenCalledTimes(2))
  await act(async () => finishOldPage({ data: pageData(1) }))
  expect(screen.queryByText('Station 1')).toBeNull()
  expect(screen.getByTestId('location').textContent).toContain('tab=service')
})

it('recovers an out-of-range page without walking every prior page', async () => {
  vehicleApi.getExpenseRecords.mockImplementation((_id, filters) => Promise.resolve({ data: filters.page === 999
    ? { ...pageData(3), records: [] } : pageData(filters.page) }))
  renderPage(`/vehicles/1/expenses?year=${year}&page=999`)
  expect(await screen.findByText('Station 41')).toBeTruthy()
  expect(vehicleApi.getExpenseRecords).toHaveBeenCalledTimes(2)
  expect(screen.getByTestId('location').textContent).toContain('page=3')
})

it('reloads totals and recovers to the last remaining page after deleting its final row', async () => {
  vi.spyOn(window, 'confirm').mockReturnValue(true)
  vehicleApi.getExpenseRecords.mockImplementation((_id, filters) => Promise.resolve({ data: filters.page === 3
    ? { ...pageData(3), records: pageData(3).records.slice(0, 1), total: 41 } : pageData(filters.page) }))
  renderPage(`/vehicles/1/expenses?year=${year}&page=3`)
  await screen.findByText('Station 41')
  vehicleApi.getExpenseRecords.mockImplementation((_id, filters) => Promise.resolve({ data: {
    ...pageData(filters.page), records: filters.page > 2 ? [] : pageData(filters.page).records, total: 40, pages: 2,
  } }))
  fireEvent.click(screen.getAllByTitle('Delete')[0])
  expect(await screen.findByText('Station 21')).toBeTruthy()
  expect(screen.getByTestId('location').textContent).toContain('page=2')
  expect(vehicleApi.getExpenseSummary).toHaveBeenCalledTimes(2)
  window.confirm.mockRestore()
})

it('fetches outstanding fines only on the parking tab and reports failures separately', async () => {
  renderPage()
  await screen.findByText('Station 20')
  expect(vehicleApi.getExpenseRecords).toHaveBeenCalledTimes(1)
  vehicleApi.getExpenseRecords.mockImplementation((_id, filters) => filters.scope === 'outstanding'
    ? Promise.reject(new Error('offline')) : Promise.resolve({ data: { ...pageData(1), records: [], total: 0, pages: 0 } }))
  fireEvent.click(screen.getByRole('button', { name: 'Parking' }))
  expect(await screen.findByText(translations.en.expensePages.finesFailed)).toBeTruthy()
  expect(vehicleApi.getExpenseRecords).toHaveBeenCalledTimes(3)
})

it('rejects edit-return state pointing at another vehicle', async () => {
  renderPage({ pathname: '/vehicles/1/fuel/add', state: { expenseReturnTo: '/vehicles/2/expenses?year=2020' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save edit' }))
  expect(await screen.findByText('Vehicle home')).toBeTruthy()
})

it('provides the new pagination and error messages in every supported language', () => {
  for (const lang of ['ro', 'es']) expect(Object.keys(translations[lang].expensePages).sort()).toEqual(Object.keys(translations.en.expensePages).sort())
})
