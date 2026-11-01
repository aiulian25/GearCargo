import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import VehicleTires from '../pages/vehicles/VehicleTires'
import { translations } from '../i18n/translations'
import { isOfflineWrite } from '../utils/offlinePolicy'
import { mutationTarget, validMutation } from '../utils/mutationProtocol'
const api = vi.hoisted(() => ({ list: vi.fn(), create: vi.fn(), update: vi.fn(), event: vi.fn(), reading: vi.fn(), correctEvent: vi.fn(), deleteReading: vi.fn(), delete: vi.fn(), undoEvent: vi.fn() }))
const toast = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }))
const vehicle = { id: 1, name: 'Winter car', distance_unit: 'miles', current_mileage: 5000 }
vi.mock('../services/api', () => ({ tireApi: api, vehicleApi: { getById: async () => ({ data: vehicle }) }, consumableApi: { getByVehicle: async () => ({ data: { entries: [], pages: 1 } }) } }))
vi.mock('react-hot-toast', () => ({ default: toast }))
vi.mock('../contexts/LanguageContext', () => ({ useTranslation: () => ({ t: key => key.split('.').reduce((v, k) => v?.[k], translations.en) || key }) }))
vi.mock('../hooks/useDateFormat', () => ({ useDateFormat: () => ({ formatDate: value => value }) }))
vi.mock('../components/ui/ConfirmDialog', () => ({ useConfirm: () => async () => true }))
const sample = { id: 2, revision: 1, name: 'Summer', season: 'summer', storage_location: 'Garage', distance_unit: 'miles', known_distance: 1000, unknown_intervals: 0,
  installed: false, positions: { FL: 'A', FR: 'B', RL: 'C', RR: 'D' }, tires: ['A','B','C','D'].map((identifier, index) => ({ id: index + 1, identifier })),
  events: [], readings: [], alerts: [], tread_unit: 'mm', rotation_remaining: null }
function mount() { return render(<MemoryRouter initialEntries={['/vehicles/1/tires']}><Routes><Route path="/vehicles/:id/tires" element={<VehicleTires />} /></Routes></MemoryRouter>) }
beforeEach(() => { vi.clearAllMocks(); api.list.mockResolvedValue({ data: { sets: [sample] } }) })
afterEach(cleanup)
it('creates four identities and links purchases without posting a new expense', async () => {
  api.list.mockResolvedValue({ data: { sets: [] } }); api.create.mockResolvedValue({ data: sample })
  mount(); fireEvent.click(await screen.findByRole('button', { name: 'Add set' }))
  fireEvent.change(screen.getByLabelText('Set name'), { target: { value: 'Summer' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save', exact: true }))
  await waitFor(() => expect(api.create).toHaveBeenCalled())
  expect(api.create.mock.calls[0][0]).toMatchObject({ vehicle_id: 1, name: 'Summer', tires: ['A','B','C','D'], purchase_entry_id: null })
  expect(api.create.mock.calls[0][1].headers['Idempotency-Key']).toBeTruthy()
})
it('previews rotation positions and blocks duplicate tire placement', async () => {
  api.list.mockResolvedValue({ data: { sets: [{ ...sample, installed: true }] } })
  api.event.mockResolvedValue({ data: { ...sample, installed: true } })
  mount(); fireEvent.click(await screen.findByRole('button', { name: 'Rotate' }))
  fireEvent.change(screen.getByLabelText('Front left'), { target: { value: 'C' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save', exact: true }))
  await screen.findByRole('alert'); expect(api.event).not.toHaveBeenCalled()
  fireEvent.change(screen.getByLabelText('Rear left'), { target: { value: 'A' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save', exact: true }))
  await waitFor(() => expect(api.event).toHaveBeenCalled())
  expect(api.event.mock.calls[0][1].positions).toEqual({ FL: 'C', FR: 'B', RL: 'A', RR: 'D' })
  expect(api.event.mock.calls[0][2].headers['If-Match']).toBe('"1"')
})
it('retains reading identity and selected units when acknowledged by the offline queue', async () => {
  api.reading.mockRejectedValue({ code: 'OFFLINE_QUEUED', response: { data: { code: 'OFFLINE_QUEUED' } } })
  mount(); fireEvent.click(await screen.findByRole('button', { name: 'Add tread reading' }))
  fireEvent.change(screen.getByLabelText('Tire identifier'), { target: { value: '3' } })
  fireEvent.change(screen.getByLabelText('Measured tread depth'), { target: { value: '6' } })
  fireEvent.change(screen.getByLabelText('Measurement unit'), { target: { value: '32nds' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save', exact: true }))
  await waitFor(() => expect(api.reading).toHaveBeenCalled())
  expect(api.reading.mock.calls[0][1]).toMatchObject({ tire_id: 3, depth: '6', unit: '32nds' })
  await waitFor(() => expect(screen.queryByRole('form')).toBeNull())
  expect(toast.success).toHaveBeenCalled()
})
it('distinguishes unknown distance, uses stored state, and provides a reminder link', async () => {
  api.list.mockResolvedValue({ data: { sets: [{ ...sample, unknown_intervals: 1 }] } })
  mount(); await screen.findByText('Additional distance unknown', { exact: false })
  expect(screen.getByRole('button', { name: 'Install' })).toBeTruthy()
  expect(screen.getByRole('link', { name: 'Create maintenance reminder' }).getAttribute('href')).toContain('type=tire_rotation')
})
it('restricts offline queueing to revision-checked tread observations', () => {
  const origin = 'https://garage.example'
  const readings = new URL('/api/tire-sets/2/readings', origin)
  expect(isOfflineWrite(readings, 'POST', origin)).toBe(true)
  expect(isOfflineWrite(new URL('/api/tire-sets/2/events', origin), 'POST', origin)).toBe(false)
  expect(isOfflineWrite(new URL('/api/tire-sets', origin), 'POST', origin)).toBe(false)
  expect(mutationTarget(readings, 'POST', origin)).toEqual({ resource: 'tire-sets', id: '2' })
  const headers = new Headers({ 'X-GearCargo-Mutation-Version': '1', 'Idempotency-Key': 'a'.repeat(32) })
  expect(validMutation({ url: readings.href, headers })).toBe(false)
  headers.set('If-Match', '"1"'); expect(validMutation({ url: readings.href, headers })).toBe(true)
})
it('has complete matching English, Romanian and Spanish feature messages', () => {
  for (const language of ['ro','es']) expect(Object.keys(translations[language].tires).sort()).toEqual(Object.keys(translations.en.tires).sort())
  for (const language of ['en','ro','es']) expect(translations[language].due.kind.tire_tread).toBeTruthy()
})
