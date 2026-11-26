import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { fuelApi, vehicleApi } from '../services/api'
import AddVehicleFuel from '../pages/vehicles/AddVehicleFuel'
import { privateNavigationState } from '../utils/privateNavigation'

const { session, mutation } = vi.hoisted(() => ({
  session: {
    user: { currency: 'GBP', volume_unit: 'liters' },
    identity: { owner_id: 1, owner_key: 'a'.repeat(64), generation: 'b'.repeat(64) },
    symbols: { GBP: '£', EUR: '€' },
  },
  mutation: { capture: vi.fn(), options: () => ({}) },
}))
vi.mock('../services/api', () => ({ fuelApi: { get: vi.fn(), create: vi.fn(), update: vi.fn() }, vehicleApi: { getById: vi.fn() } }))
vi.mock('../utils/offlineIdentity', () => ({
  getBoundIdentity: () => session.identity, requireCurrentIdentity: vi.fn(), workerMessage: vi.fn(),
}))
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({ user: session.user }) }))
vi.mock('../contexts/LanguageContext', () => ({
  useTranslation: () => ({ t: key => key }),
  useCurrency: () => ({
    currency: { code: session.user.currency, symbol: session.symbols[session.user.currency] },
    symbolFor: code => session.symbols[code || session.user.currency],
  }),
}))
vi.mock('../hooks/useMutationIntent', () => ({ useMutationIntent: () => mutation }))
vi.mock('../hooks/useUnsavedChanges', () => ({ useUnsavedChanges: () => () => true }))
vi.mock('../components/ReceiptUpload', () => ({ default: () => null }))
vi.mock('../components/ui/ScanReceiptBanner', () => ({ default: () => null }))

const ADD_FUEL_PATH = '/vehicles/1/fuel/add'
const VEHICLE = { id: 1, name: 'Daily', make: 'Fixture', model: 'Car', distance_unit: 'km', current_mileage: 84312 }
const STATEMENT_ROW = { date: '2026-10-01', amount: 60, currency: 'EUR', vendor: 'Station abroad' }
const LITERS = '40'
const PRICE_PER_LITER = '1.5'

function renderForm(navigationState = null) {
  return render(<MemoryRouter initialEntries={[{ pathname: ADD_FUEL_PATH, state: navigationState }]}>
    <Routes>
      <Route path="/vehicles/:id/fuel/add" element={<AddVehicleFuel />} />
      <Route path="*" element={<p>Destination</p>} />
    </Routes>
  </MemoryRouter>)
}
async function fillAndSave(view) {
  const input = name => waitFor(() => {
    const element = view.container.querySelector(`[name="${name}"]`)
    expect(element).toBeTruthy()
    return element
  })
  fireEvent.change(await input('liters'), { target: { value: LITERS } })
  fireEvent.change(await input('price_per_liter'), { target: { value: PRICE_PER_LITER } })
  fireEvent.submit(view.container.querySelector('form'))
}
const savedCurrency = () => waitFor(() => {
  expect(fuelApi.create).toHaveBeenCalled()
  return fuelApi.create.mock.calls[0][0].currency
})

beforeEach(() => {
  vi.clearAllMocks()
  vehicleApi.getById.mockResolvedValue({ data: VEHICLE })
  fuelApi.create.mockResolvedValue({ data: {} })
})
afterEach(cleanup)

it('asks for no currency and saves a new entry in the currency of the profile', async () => {
  const view = renderForm()
  await fillAndSave(view)

  expect(await savedCurrency()).toBe(session.user.currency)
  expect(view.container.querySelector('[name="currency"]')).toBeNull()
})

it('keeps the currency of the bank statement row an entry is drafted from', async () => {
  const view = renderForm(privateNavigationState({ prefill: STATEMENT_ROW }))
  await waitFor(() => expect(view.container.textContent).toContain(`addFuel.totalCost (${session.symbols[STATEMENT_ROW.currency]})`))
  await fillAndSave(view)

  expect(await savedCurrency()).toBe(STATEMENT_ROW.currency)
})
