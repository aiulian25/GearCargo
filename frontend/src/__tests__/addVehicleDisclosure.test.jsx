import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import AddVehicle from '../pages/vehicles/AddVehicle'
import { vehicleApi } from '../services/api'
import { translations } from '../i18n/translations'

const ESSENTIAL_FIELDS = ['name', 'make', 'model', 'year', 'fuel_type', 'current_mileage']
const MORE_DETAILS_FIELDS = ['license_plate', 'tank_capacity', 'engine_cc', 'vin', 'purchase_price', 'purchase_currency', 'purchase_date']
const SAVED_VEHICLE = { id: 1, revision: 1 }

const state = vi.hoisted(() => ({ language: 'en', navigate: vi.fn() }))
vi.mock('react-router-dom', () => ({ useNavigate: () => state.navigate }))
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({ user: { currency: 'GBP' } }) }))
vi.mock('../contexts/LanguageContext', () => {
  const t = key => {
    const value = key.split('.').reduce((item, part) => item?.[part], translations[state.language])
    if (typeof value !== 'string') throw new Error(`Missing translation: ${key}`)
    return value
  }
  return { useLanguage: () => ({ t }), useTranslation: () => ({ t }) }
})
vi.mock('../services/api', () => ({ vehicleApi: { create: vi.fn(), update: vi.fn(), uploadPhoto: vi.fn() } }))

beforeEach(() => { vehicleApi.create.mockResolvedValue({ data: { vehicle: SAVED_VEHICLE } }) })
afterEach(() => { cleanup(); vi.clearAllMocks(); state.language = 'en' })

const control = (view, name) => view.container.querySelector(`[name="${name}"]`)
async function fill(view, values) {
  for (const [name, value] of Object.entries(values)) {
    await act(async () => { fireEvent.change(control(view, name), { target: { value } }) })
  }
}
const click = element => act(async () => { fireEvent.click(element) })
const visibleControlNames = view => [...view.container.querySelectorAll('input, select, textarea')]
  .filter(element => !element.closest('details:not([open])'))
  .map(element => element.name)
const save = () => click(screen.getByRole('button', { name: translations.en.common.save }))
const navigated = () => waitFor(() => expect(state.navigate).toHaveBeenCalledWith(`/vehicles/${SAVED_VEHICLE.id}`))

it.each(['en', 'ro', 'es'])('shows only the essential fields until More details is opened (%s)', async language => {
  state.language = language
  const vehicles = translations[language].vehicles
  const view = render(<AddVehicle />)
  const details = view.container.querySelector('details')
  const summary = details.querySelector('summary')
  expect(details.open).toBe(false)
  expect(summary.textContent).toContain(vehicles.moreDetails)
  expect(summary.textContent).toContain(vehicles.moreDetailsHint)
  expect(visibleControlNames(view)).toEqual(ESSENTIAL_FIELDS)
  expect(screen.getByRole('button', { name: vehicles.miles }).closest('details')).toBeNull()

  await click(summary)
  expect(details.open).toBe(true)
  expect(visibleControlNames(view)).toEqual(expect.arrayContaining([...ESSENTIAL_FIELDS, ...MORE_DETAILS_FIELDS]))
})

it('saves every field, including those inside More details', async () => {
  const view = render(<AddVehicle />)
  await fill(view, { name: 'Daily', make: 'Skoda', model: 'Octavia', year: '2019', fuel_type: 'diesel', current_mileage: '42000' })
  await click(screen.getByRole('button', { name: translations.en.vehicles.miles }))
  await click(view.container.querySelector('summary'))
  await click(screen.getByText(translations.en.vehicles.dimensionsOptional))
  await fill(view, {
    license_plate: 'AB12 CDE', tank_capacity: '55.5', engine_cc: '1598', vin: 'TMBJJ7NE0K0000001',
    purchase_price: '12500', purchase_currency: 'EUR', purchase_date: '2025-03-01',
    vehicle_height_cm: '146', vehicle_width_cm: '181', vehicle_length_cm: '469', vehicle_weight_kg: '1340',
  })
  await save()
  await navigated()
  expect(vehicleApi.create).toHaveBeenCalledWith({
    name: 'Daily', make: 'Skoda', model: 'Octavia', year: 2019, license_plate: 'AB12 CDE', vin: 'TMBJJ7NE0K0000001',
    fuel_type: 'diesel', current_mileage: 42000, tank_capacity: 55.5, engine_cc: 1598,
    vehicle_height_cm: 146, vehicle_width_cm: 181, vehicle_length_cm: 469, vehicle_weight_kg: 1340,
    purchase_price: 12500, purchase_currency: 'EUR', purchase_date: '2025-03-01', distance_unit: 'miles',
  }, expect.anything())
})

it('sends the unchanged defaults when More details is never opened', async () => {
  const view = render(<AddVehicle />)
  await fill(view, { name: 'Daily', make: 'Skoda', model: 'Octavia' })
  await save()
  await navigated()
  expect(vehicleApi.create).toHaveBeenCalledWith({
    name: 'Daily', make: 'Skoda', model: 'Octavia', year: new Date().getFullYear(), license_plate: '', vin: '',
    fuel_type: 'petrol', current_mileage: 0, tank_capacity: null, engine_cc: null,
    vehicle_height_cm: null, vehicle_width_cm: null, vehicle_length_cm: null, vehicle_weight_kg: null,
    purchase_price: null, purchase_currency: 'GBP', purchase_date: null, distance_unit: 'km',
  }, expect.anything())
  expect(view.container.querySelector('details').open).toBe(false)
})

it('opens More details for an invalid hidden field, not for an invalid visible one', async () => {
  const view = render(<AddVehicle />)
  const details = view.container.querySelector('details')
  const summary = details.querySelector('summary')
  await save()
  expect(await screen.findByText(translations.en.vehicles.nameRequired)).toBeTruthy()
  expect(details.open).toBe(false)

  await fill(view, { name: 'Daily', make: 'Skoda', model: 'Octavia', year: '1800' })
  await save()
  expect(await screen.findByText(translations.en.vehicles.invalidYear)).toBeTruthy()
  expect(details.open).toBe(false)

  await fill(view, { year: '2019' })
  await click(summary)
  await fill(view, { tank_capacity: '-5' })
  await click(summary)
  expect(details.open).toBe(false)
  await save()
  await waitFor(() => expect(details.open).toBe(true))
  expect(document.activeElement).toBe(control(view, 'tank_capacity'))
  expect(vehicleApi.create).not.toHaveBeenCalled()
})

it('opens More details on a hidden field the server refused', async () => {
  vehicleApi.create.mockRejectedValueOnce({ response: { data: { error: 'Value is outside the allowed range', message_key: 'validation.invalidNumber', field: 'tank_capacity' } } })
  const view = render(<AddVehicle />)
  const details = view.container.querySelector('details')
  const summary = details.querySelector('summary')
  await fill(view, { name: 'Daily', make: 'Skoda', model: 'Octavia' })
  await click(summary)
  await fill(view, { tank_capacity: '10000' })
  await click(summary)
  await save()
  expect(await screen.findByText(translations.en.validation.invalidNumber)).toBeTruthy()
  expect(details.open).toBe(true)
  expect(document.activeElement).toBe(control(view, 'tank_capacity'))
})
