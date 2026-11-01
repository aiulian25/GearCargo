import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import AddVehicleReminder from '../pages/vehicles/AddVehicleReminder'
import AddReminder from '../pages/reminders/AddReminder'
import Reminders from '../pages/reminders/Reminders'
import { reminderApi, vehicleApi } from '../services/api'
import { translations } from '../i18n/translations'

const state = vi.hoisted(() => ({ mutation: { capture: vi.fn(), options: () => ({}) } }))
vi.mock('../services/api', () => ({
  reminderApi: { get: vi.fn(), getAll: vi.fn(), getStats: vi.fn(), create: vi.fn(), update: vi.fn(), complete: vi.fn() },
  vehicleApi: { getById: vi.fn(), getAll: vi.fn() }, attachmentApi: { upload: vi.fn() },
}))
vi.mock('../contexts/LanguageContext', () => ({ useTranslation: () => ({ t: key => key.split('.').reduce((v, k) => v?.[k], translations.en) || key }) }))
vi.mock('../hooks/useMutationIntent', () => ({ useMutationIntent: () => state.mutation }))
vi.mock('../hooks/useUnsavedChanges', () => ({ useUnsavedChanges: () => () => true }))
vi.mock('../components/ReceiptUpload', () => ({ default: () => null }))

const record = { id: 5, revision: 1, title: 'Oil', reminder_type: 'custom', due_date: '2028-02-29',
  due_mileage: 0, repeat_interval: '1_month', repeat_mileage: 5000,
  notify_days_before: 0, notify_push: false, notify_email: false, vehicle_id: 1, vehicle_distance_unit: 'miles' }
function mount(path, Component) {
  return render(<MemoryRouter initialEntries={[path]}><Routes>
    <Route path="/vehicles/:id/reminder/add" element={<Component />} />
    <Route path="/reminders/add" element={<Component />} />
    <Route path="/reminders" element={<Component />} />
    <Route path="/vehicles/:id" element={<p>Saved reminder</p>} />
  </Routes></MemoryRouter>)
}
afterEach(() => { cleanup(); vi.restoreAllMocks() })
beforeEach(() => {
  vi.clearAllMocks()
  vehicleApi.getById.mockResolvedValue({ data: { id: 1, name: 'Miles car', distance_unit: 'miles' } })
  vehicleApi.getAll.mockResolvedValue({ data: { vehicles: [{ id: 1, name: 'Miles car', distance_unit: 'miles' }] } })
  reminderApi.get.mockResolvedValue({ data: record })
  reminderApi.update.mockResolvedValue({ data: { reminder: record } })
  reminderApi.create.mockResolvedValue({ data: { reminder: record } })
  reminderApi.getAll.mockResolvedValue({ data: { reminders: [record] } })
  reminderApi.getStats.mockResolvedValue({ data: { total: 1, upcoming: 1, overdue: 0, completed: 0 } })
})

it('loads and saves explicit zero lead, disabled channels and mileage recurrence without losing zero mileage', async () => {
  const view = mount('/vehicles/1/reminder/add?edit=5', AddVehicleReminder)
  const lead = await screen.findByRole('spinbutton', { name: 'Days before the due date' })
  expect(lead.value).toBe('0')
  expect(screen.getByRole('checkbox', { name: 'Push notification' }).checked).toBe(false)
  expect(screen.getByRole('checkbox', { name: 'Email notification' }).checked).toBe(false)
  expect(view.container.querySelector('[name="repeat_mileage"]').value).toBe('5000')
  fireEvent.change(lead, { target: { value: '3' } })
  fireEvent.click(screen.getByRole('checkbox', { name: 'Email notification' }))
  fireEvent.submit(view.container.querySelector('form'))
  await waitFor(() => expect(reminderApi.update).toHaveBeenCalledWith('5', expect.objectContaining({
    due_mileage: 0, repeat_mileage: 5000, repeat_interval: '1_month', notify_days_before: 3, notify_push: false, notify_email: true,
  }), {}))
  expect(vehicleApi.getById).toHaveBeenCalledTimes(1)
})

it('explains the required calendar interval before accepting mileage recurrence', async () => {
  const view = mount('/vehicles/1/reminder/add?edit=5', AddVehicleReminder)
  await screen.findByRole('spinbutton', { name: 'Days before the due date' })
  fireEvent.change(view.container.querySelector('[name="repeat_interval"]'), { target: { value: '' } })
  fireEvent.change(view.container.querySelector('[name="repeat_mileage"]'), { target: { value: '5000' } })
  fireEvent.submit(view.container.querySelector('form'))
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', translations.en.reminderDelivery.intervalRequired)
  expect(reminderApi.update).not.toHaveBeenCalled()
})

it('the standalone creation form sends its selected lead time and channels', async () => {
  const view = mount('/reminders/add', AddReminder)
  await waitFor(() => expect(view.container.querySelector('[name="vehicle_id"] option[value="1"]')).toBeTruthy())
  fireEvent.change(view.container.querySelector('[name="vehicle_id"]'), { target: { value: '1' } })
  fireEvent.change(view.container.querySelector('[name="title"]'), { target: { value: 'Oil' } })
  fireEvent.change(view.container.querySelector('[name="due_date"]'), { target: { value: '2028-02-29' } })
  fireEvent.change(screen.getByRole('spinbutton', { name: 'Days before the due date' }), { target: { value: '14' } })
  fireEvent.click(screen.getByRole('checkbox', { name: 'Push notification' }))
  fireEvent.submit(view.container.querySelector('form'))
  await waitFor(() => expect(reminderApi.create).toHaveBeenCalledWith(expect.objectContaining({
    vehicle_id: 1, notify_days_before: 14, notify_push: false, notify_email: true,
  }), {}))
})

it('asks for an explicit next threshold when completing a legacy mileage reminder', async () => {
  reminderApi.complete.mockRejectedValueOnce({ response: { data: { code: 'MILEAGE_RECURRENCE_REQUIRED', minimum_next_mileage: 12001 } } })
    .mockResolvedValueOnce({ data: { reminder: { ...record, completed: true } } })
  const prompt = vi.spyOn(window, 'prompt').mockReturnValue('17000')
  vi.spyOn(console, 'error').mockImplementation(() => {})
  mount('/reminders', Reminders)
  fireEvent.click(await screen.findByTitle(translations.en.reminders.markComplete))
  await waitFor(() => expect(reminderApi.complete).toHaveBeenCalledTimes(2))
  expect(prompt).toHaveBeenCalledWith(expect.stringContaining('(miles), at least 12001'))
  expect(reminderApi.complete).toHaveBeenLastCalledWith(5, { next_due_mileage: 17000 }, expect.any(Object))
})

it('keeps notification and recurrence explanations available in every supported language', () => {
  for (const lang of ['ro', 'es']) expect(Object.keys(translations[lang].reminderDelivery).sort()).toEqual(Object.keys(translations.en.reminderDelivery).sort())
})

it('sends an explicit next threshold at the top level while retaining the old mileage argument contract', async () => {
  const { default: api, reminderApi: transport } = await vi.importActual('../services/api')
  const post = vi.spyOn(api, 'post').mockResolvedValue({ data: {} })
  const options = { headers: { 'If-Match': '1' } }
  await transport.complete(5, { next_due_mileage: 17000 }, options)
  expect(post).toHaveBeenLastCalledWith('/reminders/5/complete', { next_due_mileage: 17000 }, options)
  await transport.complete(5, 12000, options)
  expect(post).toHaveBeenLastCalledWith('/reminders/5/complete', { mileage: 12000 }, options)
})
