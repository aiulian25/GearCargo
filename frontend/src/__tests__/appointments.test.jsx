import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import VehicleAppointments from '../pages/vehicles/VehicleAppointments'
import { translations } from '../i18n/translations'
import { appointmentTime } from '../utils/appointmentTime'
import { isOfflineWrite } from '../utils/offlinePolicy'
import { mutationTarget } from '../utils/mutationProtocol'
const api = vi.hoisted(() => ({ list: vi.fn(), work: vi.fn(), create: vi.fn(), update: vi.fn(), action: vi.fn() }))
const confirm = vi.hoisted(() => vi.fn(async () => true))
const vehicle = { id: 1, name: 'Visit car' }
const expense = { id: 9, title: 'Brake invoice', date: '2026-11-01', amount: 200, currency: 'GBP', type: 'service' }
vi.mock('../services/api', () => ({ appointmentApi: api, vehicleApi: { getById: async () => ({ data: vehicle }) }, serviceApi: { getByVehicle: async () => ({ data: { entries: [expense], pages: 1 } }) }, repairApi: { getByVehicle: async () => ({ data: { entries: [], pages: 1 } }) } }))
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({ user: { timezone: 'Europe/London' } }) }))
vi.mock('../contexts/LanguageContext', () => ({ useTranslation: () => ({ language: 'en', t: key => key.split('.').reduce((v, k) => v?.[k], translations.en) || key }) }))
vi.mock('../components/ui/ConfirmDialog', () => ({ useConfirm: () => confirm }))
const sample = { id: 2, revision: 1, title: 'Annual check', status: 'requested', time_zone: 'Europe/London', start_at: '2027-06-15T08:30:00Z', end_at: '2027-06-15T16:00:00Z', start_local: '2027-06-15T09:30', end_local: '2027-06-15T17:00', prepare_minutes: 1440, tasks: [], expenses: [] }
function mount() { return render(<MemoryRouter initialEntries={['/vehicles/1/appointments']}><Routes><Route path="/vehicles/:id/appointments" element={<VehicleAppointments />} /></Routes></MemoryRouter>) }
beforeEach(() => { vi.clearAllMocks(); api.list.mockResolvedValue({ data: { appointments: [sample] } }); api.work.mockResolvedValue({ data: { work: [{ title: 'Oil due', reminder_id: 7 }] } }) })
afterEach(cleanup)
it('creates a requested draft with a named timezone and selected due work', async () => {
  api.create.mockResolvedValue({ data: sample }); mount()
  fireEvent.click(await screen.findByRole('button', { name: 'Plan workshop visit' }))
  for (const [label,value] of [['Visit title','Annual check'],['Proposed drop-off','2027-06-15T09:30'],['Proposed pick-up','2027-06-15T17:00']]) fireEvent.change(screen.getByLabelText(label), { target: { value } })
  fireEvent.click(screen.getByRole('button', { name: 'Oil due' }))
  fireEvent.click(screen.getByRole('button', { name: 'Save', exact: true }))
  await waitFor(() => expect(api.create).toHaveBeenCalled())
  const [payload, options] = api.create.mock.calls[0]
  expect(payload).toMatchObject({ time_zone: 'Europe/London', start_local: '2027-06-15T09:30', start_fold: null, tasks: [{ title: 'Oil due', reminder_id: 7 }] })
  expect(payload.status).toBeUndefined(); expect(options.headers['Idempotency-Key']).toBeTruthy()
})
it('asks for explicit owner confirmation and sends the displayed revision', async () => {
  api.action.mockResolvedValue({ data: { ...sample, status: 'confirmed', revision: 2 } }); mount()
  fireEvent.click(await screen.findByRole('button', { name: 'Mark confirmed' }))
  await waitFor(() => expect(api.action).toHaveBeenCalled())
  expect(confirm.mock.calls[0][0].message).toContain('does not contact the workshop')
  expect(api.action.mock.calls[0]).toMatchObject([2, 'confirm', { arranged_externally: true }, { headers: { 'If-Match': '"1"' } }])
})
it('completes only selected expenses and linked work', async () => {
  const record = { ...sample, status: 'confirmed', dropoff_at: '2026-11-01T09:00:00Z', tasks: [{ id: 3, title: 'Oil due', reminder_id: 7, done: false }, { id: 4, title: 'Later work', done: false }] }
  api.list.mockResolvedValue({ data: { appointments: [record] } }); api.action.mockResolvedValue({ data: { ...record, status: 'completed', expenses: [expense] } }); mount()
  fireEvent.click(await screen.findByRole('button', { name: 'Complete visit' }))
  fireEvent.click(screen.getByLabelText('Brake invoice · 2026-11-01 · 200 GBP'))
  fireEvent.click(screen.getByLabelText('Oil due'))
  fireEvent.click(screen.getByRole('button', { name: 'Complete visit' }))
  await waitFor(() => expect(api.action).toHaveBeenCalled())
  expect(api.action.mock.calls[0][2]).toEqual({ entry_ids: [9], resolved_task_ids: [3], no_cost: false })
})
it('keeps user input when the server flags an ambiguous hour', async () => {
  api.update.mockRejectedValue({ response: { status: 400, data: { message_key: 'appointments.ambiguousTime' } } }); mount()
  fireEvent.click(await screen.findByRole('button', { name: 'Edit' }))
  fireEvent.change(screen.getByLabelText('Proposed drop-off'), { target: { value: '2027-10-31T01:30' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save', exact: true }))
  expect((await screen.findByRole('alert')).textContent).toContain('occurs twice')
  expect(screen.getByLabelText('Proposed drop-off').value).toBe('2027-10-31T01:30')
})
it('queues new drafts only and closes only after offline acknowledgment', async () => {
  api.create.mockRejectedValue({ code: 'OFFLINE_QUEUED', response: { data: { code: 'OFFLINE_QUEUED' } } }); mount()
  fireEvent.click(await screen.findByRole('button', { name: 'Plan workshop visit' }))
  for (const [label,value] of [['Visit title','Offline request'],['Proposed drop-off','2027-06-15T09:30'],['Proposed pick-up','2027-06-15T17:00']]) fireEvent.change(screen.getByLabelText(label), { target: { value } })
  fireEvent.click(screen.getByRole('button', { name: 'Save', exact: true }))
  await waitFor(() => expect(api.create).toHaveBeenCalled()); await waitFor(() => expect(screen.queryByRole('form')).toBeNull())
  const origin = 'https://test.invalid'
  expect(isOfflineWrite(new URL('/api/appointments', origin), 'POST', origin)).toBe(true)
  expect(isOfflineWrite(new URL('/api/appointments/2/confirm', origin), 'POST', origin)).toBe(false)
  expect(mutationTarget(new URL('/api/appointments/2/complete', origin), 'POST', origin)).toEqual({ resource: 'appointments', id: '2' })
})
it('renders the appointment timezone independently of device timezone, with complete translations', () => {
  expect(appointmentTime('2027-06-15T08:30:00Z','Europe/London','en-GB')).toContain('09:30')
  expect(appointmentTime('2027-06-15T08:30:00Z','America/New_York','en-GB')).toContain('04:30')
  for (const lang of ['ro','es']) expect(Object.keys(translations[lang].appointments).sort()).toEqual(Object.keys(translations.en.appointments).sort())
})

it('distinguishes both occurrences of a repeated local hour in the visit display', () => {
  const earlier = appointmentTime('2027-10-31T00:30:00Z','Europe/London','en-GB')
  const later = appointmentTime('2027-10-31T01:30:00Z','Europe/London','en-GB')
  expect(earlier).toContain('01:30'); expect(later).toContain('01:30'); expect(earlier).not.toBe(later)
})
