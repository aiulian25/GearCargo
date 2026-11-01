import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, waitFor } from '@testing-library/react'
import AddVehicleFuel from '../pages/vehicles/AddVehicleFuel'
import { fuelApi, vehicleApi } from '../services/api'

const state = vi.hoisted(() => ({ user: { volume_unit: 'gallons_us', currency: 'GBP' },
  navigate: vi.fn(), mutation: { capture: vi.fn(), options: () => ({}) } }))
vi.mock('../services/api', () => ({ fuelApi: { get: vi.fn(), update: vi.fn() }, vehicleApi: { getById: vi.fn() } }))
vi.mock('react-router-dom', () => ({ useNavigate: () => state.navigate, useParams: () => ({ id: '1' }),
  useSearchParams: () => [new URLSearchParams('edit=5')], useLocation: () => ({ state: null }) }))
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({ user: state.user }) }))
vi.mock('../contexts/LanguageContext', () => ({ useTranslation: () => ({ t: key => key }), useCurrency: () => ({ currency: { symbol: '£' } }) }))
vi.mock('../hooks/useMutationIntent', () => ({ useMutationIntent: () => state.mutation }))
vi.mock('../hooks/useUnsavedChanges', () => ({ useUnsavedChanges: () => () => true }))
vi.mock('../components/ReceiptUpload', () => ({ default: () => null }))
vi.mock('../components/ui/ScanReceiptBanner', () => ({ default: () => null }))
vi.mock('../components/ui/CurrencySelect', () => ({ default: () => null }))
afterEach(() => { cleanup(); vi.clearAllMocks() })

it.each([
  { liters: 37.85, price_per_liter: 1.321, total_price: 49.99, odometer: 1000 },
  { liters: 0, price_per_liter: -1.321, total_price: -10, odometer: 0 },
  { liters: null, price_per_liter: null, total_price: null, odometer: null },
])('notes-only edit preserves quantities through the actual form: %j', async quantities => {
  vehicleApi.getById.mockResolvedValue({ data: { id: 1, name: 'Miles car', distance_unit: 'miles' } })
  fuelApi.get.mockResolvedValue({ data: { id: 5, revision: 1, date: '2026-01-01',
    ...quantities, currency: 'GBP', full_tank: true, notes: 'Original' } })
  fuelApi.update.mockResolvedValue({ data: {} })
  const view = render(<AddVehicleFuel />)
  await waitFor(() => expect(view.container.querySelector('textarea[name="notes"]')).toBeTruthy())
  const total = view.container.querySelector('input[name="total_cost"]')
  expect(total.value).toBe(String(quantities.total_price ?? ''))
  fireEvent.change(view.container.querySelector('textarea[name="notes"]'), { target: { value: 'Edited note' } })
  fireEvent.submit(view.container.querySelector('form'))
  await waitFor(() => expect(fuelApi.update).toHaveBeenCalledWith('5', { notes: 'Edited note', vehicle_id: 1 }, {}))
  expect(state.navigate).toHaveBeenCalledWith('/vehicles/1')
  // Navigation wrappers must remain stable as form values change: a new
  // callback would reload/reset this form on every render.
  expect(vehicleApi.getById).toHaveBeenCalledTimes(1)
  expect(fuelApi.get).toHaveBeenCalledTimes(1)
})
