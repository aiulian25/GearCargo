import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { translations } from '../i18n/translations'
import { fuelApi, vehicleApi } from '../services/api'
import AddVehicleFuel from '../pages/vehicles/AddVehicleFuel'
import AddFuel from '../pages/fuel/AddFuel'
import FuelEntries from '../pages/fuel/FuelEntries'
import { belowLatestReadingHint } from '../utils/fuelMeasurement'

const { toast, user, mutation } = vi.hoisted(() => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
  user: { currency: 'GBP', volume_unit: 'liters' },
  mutation: { capture: vi.fn(), options: () => ({}) },
}))
vi.mock('react-hot-toast', () => ({ default: toast }))
vi.mock('../services/api', () => ({
  fuelApi: { get: vi.fn(), create: vi.fn(), update: vi.fn(), getAll: vi.fn(), getByVehicle: vi.fn(), getStations: vi.fn() },
  vehicleApi: { getById: vi.fn(), getAll: vi.fn() },
}))
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({ user }) }))
vi.mock('../contexts/LanguageContext', () => {
  const t = (key, params = {}) => {
    const value = key.split('.').reduce((item, part) => item?.[part], translations.en)
    if (typeof value !== 'string') throw new Error(`Missing translation: ${key}`)
    return value.replace(/\{(\w+)\}/g, (_, name) => params[name] ?? `{${name}}`)
  }
  return { useTranslation: () => ({ t }), useCurrency: () => ({ currency: { symbol: '£' } }) }
})
vi.mock('../hooks/useMutationIntent', () => ({ useMutationIntent: () => mutation }))
vi.mock('../hooks/useUnsavedChanges', () => ({ useUnsavedChanges: () => () => true }))
vi.mock('../components/ReceiptUpload', () => ({ default: () => null }))
vi.mock('../components/ui/ScanReceiptBanner', () => ({ default: () => null }))
vi.mock('../components/ui/CurrencySelect', () => ({ default: () => null }))

const LATEST_READING = 84312
const TYPO = '8431'
const vehicle = { id: 1, name: 'Daily', make: 'Fixture', model: 'Car', distance_unit: 'km', current_mileage: LATEST_READING }
const saved = { data: { entry: { id: 9 }, warnings: [{ code: 'odometer_regression', previous: LATEST_READING }] } }
const english = (key, params = {}) => key.split('.').reduce((item, part) => item?.[part], translations.en)
  .replace(/\{(\w+)\}/g, (_, name) => params[name])
const LATEST_READING_TEXT = LATEST_READING.toLocaleString()
const hintText = english('addFuel.odometerBelowLatest', { reading: `${LATEST_READING_TEXT} km` })
const warningText = english('fuel.warningTypes.odometer_regression', { previous: `${LATEST_READING_TEXT} km` })

function renderPage(initialEntries) {
  return render(<MemoryRouter initialEntries={initialEntries} initialIndex={initialEntries.length - 1}>
    <Routes>
      <Route path="/vehicles/:id/fuel/add" element={<AddVehicleFuel />} />
      <Route path="/fuel/add" element={<AddFuel />} />
      <Route path="/fuel" element={<FuelEntries />} />
      <Route path="*" element={<p>Destination</p>} />
    </Routes>
  </MemoryRouter>)
}
async function field(view, name) {
  return waitFor(() => {
    const input = view.container.querySelector(`[name="${name}"]`)
    expect(input).toBeTruthy()
    return input
  })
}
function typeAndLeave(input, value) {
  fireEvent.change(input, { target: { value } })
  fireEvent.blur(input)
}
async function fillQuantitiesAndSave(view) {
  fireEvent.change(await field(view, 'liters'), { target: { value: '40' } })
  fireEvent.change(await field(view, 'price_per_liter'), { target: { value: '1.5' } })
  fireEvent.submit(view.container.querySelector('form'))
}

beforeEach(() => vi.clearAllMocks())
afterEach(cleanup)

it.each([['', LATEST_READING], [null, LATEST_READING], [String(LATEST_READING), LATEST_READING],
  ['90000', LATEST_READING], ['abc', LATEST_READING], ['100', null], ['100', 0]])(
  'gives no hint for %j against a latest reading of %j', (value, latestReading) => {
    expect(belowLatestReadingHint(value, latestReading, 'km', english)).toBeNull()
  })

it('names the latest reading and its unit when the typed one is lower', () => {
  expect(belowLatestReadingHint(TYPO, LATEST_READING, 'km', english)).toBe(hintText)
})

it('hints after leaving the odometer, still saves, and reports the server warning', async () => {
  vehicleApi.getById.mockResolvedValue({ data: vehicle })
  fuelApi.create.mockResolvedValue(saved)
  const view = renderPage(['/vehicles/1/fuel/add'])
  const odometer = await field(view, 'mileage')
  const hint = screen.getByRole('status')
  expect(hint.textContent).toBe('')
  expect(odometer.getAttribute('aria-describedby')).toBe(hint.id)
  fireEvent.change(odometer, { target: { value: TYPO } })
  expect(hint.textContent).toBe('')
  fireEvent.blur(odometer)
  expect(hint.textContent).toBe(hintText)
  await fillQuantitiesAndSave(view)
  await waitFor(() => expect(fuelApi.create).toHaveBeenCalledWith(expect.objectContaining({ mileage: Number(TYPO), vehicle_id: vehicle.id }), {}))
  expect(await screen.findByText('Destination')).toBeTruthy()
  expect(toast).toHaveBeenCalledWith(warningText, expect.anything())
})

it('leaves the unit out when the vehicle declares none', async () => {
  vehicleApi.getById.mockResolvedValue({ data: { ...vehicle, distance_unit: null } })
  fuelApi.create.mockResolvedValue(saved)
  const view = renderPage(['/vehicles/1/fuel/add'])
  typeAndLeave(await field(view, 'mileage'), TYPO)
  expect(screen.getByRole('status').textContent).toBe(english('addFuel.odometerBelowLatest', { reading: LATEST_READING_TEXT }))
  await fillQuantitiesAndSave(view)
  expect(await screen.findByText('Destination')).toBeTruthy()
  expect(toast).toHaveBeenCalledWith(english('fuel.warningTypes.odometer_regression', { previous: LATEST_READING_TEXT }), expect.anything())
})

it('does not hint while editing an older fill', async () => {
  vehicleApi.getById.mockResolvedValue({ data: vehicle })
  fuelApi.get.mockResolvedValue({ data: { id: 5, revision: 1, date: '2024-01-01', odometer: 50000, liters: 40,
    price_per_liter: 1.5, total_price: 60, currency: 'GBP', full_tank: true } })
  const view = renderPage(['/vehicles/1/fuel/add?edit=5'])
  const odometer = await field(view, 'mileage')
  await waitFor(() => expect(odometer.value).toBe('50000'))
  typeAndLeave(odometer, TYPO)
  expect(screen.getByRole('status').textContent).toBe('')
})

it('gives the PWA Add Fuel shortcut form the same hint and save feedback', async () => {
  vehicleApi.getAll.mockResolvedValue({ data: { vehicles: [vehicle] } })
  fuelApi.create.mockResolvedValue(saved)
  const view = renderPage(['/origin', '/fuel/add'])
  await screen.findByRole('option', { name: vehicle.name })
  // The single-vehicle auto-select is written before its <option> exists, so the
  // select still shows the placeholder; choose the vehicle as a user has to.
  fireEvent.change(await field(view, 'vehicle_id'), { target: { value: String(vehicle.id) } })
  const odometer = await field(view, 'mileage')
  const hint = screen.getByRole('status')
  expect(odometer.getAttribute('aria-describedby')).toBe(hint.id)
  typeAndLeave(odometer, TYPO)
  expect(hint.textContent).toBe(hintText)
  typeAndLeave(odometer, '85000')
  expect(hint.textContent).toBe('')
  typeAndLeave(odometer, TYPO)
  await fillQuantitiesAndSave(view)
  await waitFor(() => expect(fuelApi.create).toHaveBeenCalledWith(expect.objectContaining({ mileage: Number(TYPO), vehicle_id: vehicle.id }), {}))
  expect(await screen.findByText('Destination')).toBeTruthy()
  expect(toast).toHaveBeenCalledWith(warningText, expect.anything())
})

it('shows each fill’s consumption, or why it has none', async () => {
  vehicleApi.getAll.mockResolvedValue({ data: { vehicles: [{ id: 1, name: 'Daily', distance_unit: 'km' }] } })
  fuelApi.getStations.mockResolvedValue({ data: { stations: [] } })
  fuelApi.getAll.mockResolvedValue({ data: { entries: [
    { id: 1, vehicle_id: 1, date: '2024-01-03', liters: 40, odometer: 51000, fuel_efficiency: 6.5, measurement_status: 'measured' },
    { id: 2, vehicle_id: 1, date: '2024-01-04', liters: 40, odometer: 5100, fuel_efficiency: null, measurement_status: 'odometer_regression' },
    { id: 3, vehicle_id: 1, date: '2024-01-05', liters: 20, odometer: 5200, fuel_efficiency: null, measurement_status: 'partial' },
  ] } })
  renderPage(['/fuel'])
  expect(await screen.findByText('6.5 L/100km')).toBeTruthy()
  expect(screen.getByText(new RegExp(`${(51000).toLocaleString()} km`))).toBeTruthy()
  expect(screen.getByText(english('fuel.measurementStatus.odometer_regression'))).toBeTruthy()
  expect(screen.getByText(english('fuel.measurementStatus.partial'))).toBeTruthy()
})

it('names every measurement outcome and warning in all three languages', () => {
  expect(Object.keys(translations.en.fuel.measurementStatus).sort()).toEqual(['distance_unit_unknown', 'first_full_fill',
    'odometer_invalid', 'odometer_missing', 'odometer_regression', 'partial', 'volume_invalid'])
  for (const language of ['en', 'ro', 'es']) {
    for (const group of ['measurementStatus', 'warningTypes']) {
      expect(Object.keys(translations[language].fuel[group]).sort()).toEqual(Object.keys(translations.en.fuel[group]).sort())
      for (const text of Object.values(translations[language].fuel[group])) expect(text).toMatch(/\S/)
    }
    expect(translations[language].addFuel.odometerBelowLatest.match(/\{\w+\}/g)).toEqual(['{reading}'])
    expect(translations[language].fuel.warningTypes.odometer_regression.match(/\{\w+\}/g)).toEqual(['{previous}'])
  }
})
