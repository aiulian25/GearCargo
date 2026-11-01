import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import VehicleCharts from '../pages/vehicles/VehicleCharts'
import FinancialBasis from '../components/ui/FinancialBasis'
import { translations } from '../i18n/translations'
import { vehicleApi } from '../services/api'

vi.mock('../services/api', () => ({
  default: { get: vi.fn() },
  vehicleApi: { getById: vi.fn(), getCostAnalytics: vi.fn(), getForecast: vi.fn(), getExpenseSummary: vi.fn() },
}))
vi.mock('../contexts/LanguageContext', () => ({
  useTranslation: () => ({ t: key => key.split('.').reduce((v, k) => v?.[k], translations.en) || key }),
  // A browser language/location currency must not relabel GBP server totals.
  useCurrency: () => ({ currency: { code: 'USD', symbol: '$' }, language: 'en' }),
}))
const year = new Date().getFullYear()
const summary = {
  display_currency: 'GBP', as_of: `${year}-03-31`, converted: true,
  totals: { fuel: 0, service: 0, repair: 0, tax: 0, parking: 0, consumable: 80, insurance: 20, grand_total: 100 },
  monthly: [{ month: `${year}-03`, total: 100 }], available_years: [year],
}
afterEach(cleanup)
beforeEach(() => {
  vi.clearAllMocks()
  vehicleApi.getById.mockResolvedValue({ data: { id: 1, name: 'Only consumables and insurance' } })
  vehicleApi.getCostAnalytics.mockResolvedValue({ data: null })
  vehicleApi.getForecast.mockResolvedValue({ data: null })
})
function renderCharts() {
  return render(<MemoryRouter initialEntries={['/vehicles/1/charts']}><Routes>
    <Route path="/vehicles/:id/charts" element={<VehicleCharts />} />
  </Routes></MemoryRouter>)
}
it('renders all categories from server totals even without timeline detail rows', async () => {
  vehicleApi.getExpenseSummary.mockResolvedValue({ data: summary })
  renderCharts()
  await waitFor(() => expect(vehicleApi.getExpenseSummary).toHaveBeenCalledWith('1', { year }))
  expect(await screen.findByText('Consumables')).toBeTruthy()
  expect(screen.getByText('Insurance (estimate)')).toBeTruthy()
  expect(screen.getAllByText('100.00 GBP').length).toBeGreaterThan(0)
  expect(screen.queryByText('$100')).toBeNull()
  expect(screen.getByText(/insurance payments are not verified/)).toBeTruthy()
})
it('shows an error rather than a zero-cost result when totals cannot load', async () => {
  vehicleApi.getExpenseSummary.mockRejectedValue(new Error('offline'))
  renderCharts()
  expect(await screen.findByText(translations.en.financial.loadFailed)).toBeTruthy()
  expect(screen.queryByText('0.00 GBP')).toBeNull()
})
it('clearly labels partial FX totals and localizes the financial contract', () => {
  render(<FinancialBasis data={{ ...summary, converted: false, fx_applied: true }} />)
  expect(screen.getByText(translations.en.financial.partial)).toBeTruthy()
  expect(screen.getByText('Currency: GBP')).toBeTruthy()
  for (const language of ['ro', 'es']) {
    expect(Object.keys(translations[language].financial).sort()).toEqual(Object.keys(translations.en.financial).sort())
  }
})
it('labels historical totals through the selected period end', () => {
  render(<FinancialBasis data={{ ...summary, as_of: '2026-10-31', end_date: '2024-12-31' }} />)
  expect(screen.getByText('Through 31/12/2024')).toBeTruthy()
  expect(screen.queryByText('Through 31/10/2026')).toBeNull()
})
