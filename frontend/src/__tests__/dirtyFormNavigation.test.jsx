import { StrictMode, useState } from 'react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { createMemoryRouter, RouterProvider, Routes, Route, Link } from 'react-router-dom'
import UnsavedChangesProvider from '../components/UnsavedChangesProvider'
import { ConfirmProvider } from '../components/ui/ConfirmDialog'
import useUnsavedExit from '../hooks/useUnsavedExit'
import EditVehicle from '../pages/vehicles/EditVehicle'
import AddVehicle from '../pages/vehicles/AddVehicle'
import AddVehicleTodo from '../pages/vehicles/AddVehicleTodo'
import AddVehicleReminder from '../pages/vehicles/AddVehicleReminder'
import AddVehicleFuel from '../pages/vehicles/AddVehicleFuel'
import AddVehicleService from '../pages/vehicles/AddVehicleService'
import AddVehicleConsumable from '../pages/vehicles/AddVehicleConsumable'
import api, { vehicleApi, fuelApi, serviceApi, reminderApi, attachmentApi } from '../services/api'
import { saveExpenseWithReceipt } from '../utils/receiptExpense'
import { translations } from '../i18n/translations'

const state = vi.hoisted(() => ({ language: 'en', user: { id: 1, currency: 'GBP', volume_unit: 'liters' } }))
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({ user: state.user }) }))
vi.mock('../contexts/LanguageContext', () => {
  const t = key => key.split('.').reduce((v, k) => v?.[k], translations[state.language]) || key
  return { useTranslation: () => ({ t, language: state.language }), useLanguage: () => ({ t, language: state.language }),
    useCurrency: () => ({ currency: { symbol: '£' } }) }
})
vi.mock('../services/api', () => ({ default: { get: vi.fn(), post: vi.fn(), put: vi.fn() },
  attachmentApi: { upload: vi.fn() },
  reminderApi: { create: vi.fn(), update: vi.fn(), get: vi.fn() },
  vehicleApi: { getById: vi.fn(), create: vi.fn(), update: vi.fn(), uploadPhoto: vi.fn(), deletePhoto: vi.fn() },
  fuelApi: { get: vi.fn(), update: vi.fn(), create: vi.fn() },
  serviceApi: { get: vi.fn(), update: vi.fn(), create: vi.fn() },
  consumableApi: { get: vi.fn(), update: vi.fn(), create: vi.fn() },
}))
vi.mock('../utils/receiptExpense', () => ({ saveExpenseWithReceipt: vi.fn() }))
vi.mock('../components/ui/ScanReceiptBanner', () => ({ default: () => null }))
vi.mock('../components/ReceiptUpload', () => ({ default: ({ onFileSelect, onFileChange }) => <input aria-label="Receipt file" type="file"
  onChange={event => (onFileSelect || onFileChange)(event.target.files[0])} /> }))
const vehicle = { id: 1, name: 'Original vehicle', revision: 1, distance_unit: 'km', make: 'Fixture', model: 'Car', year: 2026 }
const entry = { id: 5, revision: 1, date: '2026-01-01', liters: 10, price_per_liter: 2, total_price: 20, odometer: 100,
  full_tank: true, currency: 'GBP', notes: 'Original note' }
const offlineQueued = () => ({ code: 'OFFLINE_QUEUED', response: { data: { code: 'OFFLINE_QUEUED' } } })
const routers = []
beforeEach(() => {
  vi.clearAllMocks(); state.language = 'en'
  vehicleApi.getById.mockResolvedValue({ data: vehicle }); vehicleApi.update.mockResolvedValue({ data: { vehicle: { ...vehicle, revision: 2 } } }); vehicleApi.create.mockResolvedValue({ data: { vehicle } })
  vehicleApi.uploadPhoto.mockResolvedValue({ data: {} }); vehicleApi.deletePhoto.mockResolvedValue({ data: {} })
  fuelApi.get.mockResolvedValue({ data: entry }); fuelApi.update.mockResolvedValue({ data: {} })
  serviceApi.get.mockResolvedValue({ data: { ...entry, service_types: ['oil_change'] } })
  api.post.mockResolvedValue({ data: { todo: { id: 7, revision: 1 } } }); api.put.mockResolvedValue({ data: { todo: { id: 7, revision: 2 } } })
  reminderApi.create.mockResolvedValue({ data: { reminder: { id: 7, revision: 1 } } }); reminderApi.update.mockResolvedValue({ data: { reminder: { id: 7, revision: 2 } } })
  attachmentApi.upload.mockResolvedValue({ data: { id: 8 } })
  saveExpenseWithReceipt.mockResolvedValue({ receiptPending: true })
})
afterEach(() => { cleanup(); for (const router of routers.splice(0)) router.dispose() })
function ExitButton({ onLogout }) {
  const confirmExit = useUnsavedExit()
  return <button onClick={async () => { if (await confirmExit()) onLogout() }}>Sign out</button>
}
function Shell() {
  const [account, setAccount] = useState(1)
  if (account === 0) return <p>Signed out</p>
  return <><button onClick={() => setAccount(x => x + 1)}>Change account</button>
    <UnsavedChangesProvider key={account}>
      <Link to="/sidebar">Sidebar</Link><ExitButton onLogout={() => setAccount(0)} />
      <Routes>
        <Route path="/vehicles/:id/todo/add" element={<AddVehicleTodo />} />
        <Route path="/vehicles/:id/reminder/add" element={<AddVehicleReminder />} />
        <Route path="/vehicles/add" element={<AddVehicle />} />
        <Route path="/vehicles/:id/edit" element={<EditVehicle />} />
        <Route path="/vehicles/:id/fuel/add" element={<AddVehicleFuel />} />
        <Route path="/vehicles/:id/service/add" element={<AddVehicleService />} />
        <Route path="/vehicles/:id/consumable/add" element={<AddVehicleConsumable />} />
        <Route path="*" element={<p>Destination</p>} />
      </Routes>
    </UnsavedChangesProvider>
  </>
}
function mount(path = '/vehicles/1/edit', options = {}) {
  const router = createMemoryRouter([{ path: '*', element: <ConfirmProvider><Shell /></ConfirmProvider> }], {
    initialEntries: ['/vehicles/1/expenses?year=2025&month=2&category=fuel&page=3', options.state ? { pathname: path.split('?')[0], search: '?' + path.split('?')[1], state: options.state } : path],
  })
  routers.push(router)
  const view = render(<StrictMode><RouterProvider router={router} /></StrictMode>)
  return { ...view, router }
}
async function field(view, name, value) {
  const el = await waitFor(() => { const input = view.container.querySelector(`[name="${name}"]`); expect(input).toBeTruthy(); return input })
  if (value !== undefined) await act(async () => { fireEvent.change(el, { target: { value } }) })
  return el
}
async function choose(label) { await act(async () => { fireEvent.click(screen.getByRole('button', { name: label, exact: true })) }) }
const stay = () => choose(translations[state.language].unsavedChanges.stay)
const discard = () => choose(translations[state.language].unsavedChanges.discard)
const dialog = () => screen.findByRole('dialog', { name: translations[state.language].unsavedChanges.title })

it.each(['close', 'sidebar', 'history', 'query'])('preserves typed values on %s, then proceeds only after discard', async exit => {
  const view = mount(); const name = await field(view, 'name', 'Keep this vehicle')
  const leave = async () => {
    if (exit === 'close') await choose('Close')
    if (exit === 'sidebar') await act(async () => { fireEvent.click(screen.getByText('Sidebar')) })
    if (exit === 'history') await act(async () => { await view.router.navigate(-1) })
    if (exit === 'query') await act(async () => { await view.router.navigate('/vehicles/1/edit?tab=other') })
  }
  await leave(); await dialog()
  expect(document.activeElement.textContent).toBe('Keep editing')
  await stay(); expect(name.value).toBe('Keep this vehicle'); expect(view.router.state.location.pathname).toBe('/vehicles/1/edit')
  await leave(); await dialog(); await discard()
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(view.router.state.location.pathname + view.router.state.location.search).toBe(exit === 'sidebar' ? '/sidebar' : exit === 'query' ? '/vehicles/1/edit?tab=other' : '/vehicles/1/expenses?year=2025&month=2&category=fuel&page=3')
})

it('leaves a clean loaded form without confirmation and restores focus after Escape on a dirty one', async () => {
  const view = mount(); await field(view, 'name'); await choose('Close')
  expect(screen.queryByRole('dialog')).toBeNull()
  await act(async () => { await view.router.navigate('/vehicles/1/edit') })
  await field(view, 'name', 'Edited')
  const close = screen.getByRole('button', { name: 'Close' }); close.focus(); await choose('Close'); await dialog()
  await act(async () => { fireEvent.keyDown(document, { key: 'Escape' }) })
  expect(document.activeElement).toBe(close); expect((await field(view, 'name')).value).toBe('Edited')
})

it.each(['en', 'ro', 'es'])('localizes the discard confirmation (%s)', async language => {
  state.language = language; const view = mount(); await field(view, 'name', 'Changed')
  await choose(translations[language].common.close); await dialog(); await stay()
  expect((await field(view, 'name')).value).toBe('Changed')
})

it('protects a photo-only edit and preserves it after an upload failure', async () => {
  const view = mount(); await field(view, 'name')
  vehicleApi.uploadPhoto.mockRejectedValueOnce(new Error('Photo rejected'))
  const file = new File(['receipt'], 'photo.png', { type: 'image/png' })
  await act(async () => { fireEvent.change(view.container.querySelector('input[type="file"]'), { target: { files: [file] } }) })
  await choose('Close'); await dialog(); await stay()
  await choose('Save'); await waitFor(() => expect(vehicleApi.uploadPhoto).toHaveBeenCalled())
  expect(view.router.state.location.pathname).toBe('/vehicles/1/edit')
  await choose('Close'); await dialog(); await stay()
  await field(view, 'name', 'Edited after partial save')
  await choose('Save'); await screen.findByText('Destination'); expect(vehicleApi.uploadPhoto).toHaveBeenLastCalledWith('1', file)
  expect(vehicleApi.update).toHaveBeenLastCalledWith('1', expect.objectContaining({ name: 'Edited after partial save' }), expect.objectContaining({ headers: expect.objectContaining({ 'If-Match': '"2"' }) }))
})

it('keeps failed updates dirty and releases both route and unload guards only after success', async () => {
  const view = mount(); await field(view, 'name', 'Changed')
  const unload = () => { const event = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(event); return event.defaultPrevented }
  expect(unload()).toBe(true)
  vehicleApi.update.mockRejectedValueOnce({ response: { data: { error: 'Save rejected' } } })
  await choose('Save'); await screen.findByText('Save rejected'); expect(unload()).toBe(true)
  await choose('Close'); await dialog(); await stay()
  await choose('Save'); await screen.findByText('Destination'); expect(unload()).toBe(false)
  expect(screen.queryByRole('dialog')).toBeNull()
})

it.each(['online', 'queued'])('returns to exact expense filters after a durable %s save', async mode => {
  if (mode === 'queued') fuelApi.update.mockRejectedValueOnce(offlineQueued())
  const target = '/vehicles/1/expenses?year=2025&month=2&category=fuel&page=3'
  const view = mount('/vehicles/1/fuel/add?edit=5', { state: { expenseReturnTo: target } })
  await field(view, 'notes', 'Saved note'); await choose('Save'); await screen.findByText('Destination')
  expect(view.router.state.location.pathname + view.router.state.location.search).toBe(target)
  expect(screen.queryByRole('dialog')).toBeNull()
})

it('does not treat network errors as queued success', async () => {
  fuelApi.update.mockRejectedValueOnce(new Error('Network unavailable'))
  const view = mount('/vehicles/1/fuel/add?edit=5'); await field(view, 'notes', 'Still here')
  await choose('Save'); await screen.findByText('Network unavailable')
  await act(async () => { fireEvent.click(screen.getByText('Sidebar')) }); await dialog(); await stay()
  expect((await field(view, 'notes')).value).toBe('Still here')
})

it('retains a receipt-only edit until the receipt store acknowledges its save', async () => {
  let complete
  saveExpenseWithReceipt.mockImplementationOnce(() => new Promise(resolve => { complete = resolve }))
  const view = mount('/vehicles/1/fuel/add?edit=5'); await field(view, 'notes')
  const file = new File(['original bytes'], 'receipt.pdf', { type: 'application/pdf' })
  await act(async () => { fireEvent.change(screen.getByLabelText('Receipt file'), { target: { files: [file] } }) })
  await act(async () => { fireEvent.click(screen.getByText('Sidebar')) }); await dialog(); await stay()
  await choose('Save'); await waitFor(() => expect(complete).toBeTypeOf('function'))
  expect(view.router.state.location.pathname).toBe('/vehicles/1/fuel/add')
  await act(async () => { fireEvent.click(screen.getByText('Sidebar')) }); await dialog()
  await act(async () => { complete({ receiptPending: true }) }); await screen.findByText('Destination')
  expect(screen.queryByRole('dialog')).toBeNull(); expect(view.router.state.location.pathname).toBe('/vehicles/1')
  expect(saveExpenseWithReceipt).toHaveBeenCalledWith(expect.objectContaining({ file }))
})

it('retains receipt bytes after storage refusal', async () => {
  saveExpenseWithReceipt.mockRejectedValueOnce(new Error('Storage full'))
  const view = mount('/vehicles/1/fuel/add?edit=5'); await field(view, 'notes')
  const file = new File(['bytes'], 'receipt.pdf')
  await act(async () => { fireEvent.change(screen.getByLabelText('Receipt file'), { target: { files: [file] } }) })
  await choose('Save'); await screen.findByText('Storage full')
  await act(async () => { fireEvent.click(screen.getByText('Sidebar')) }); await dialog(); await stay()
  await choose('Save'); await screen.findByText('Destination')
  expect(saveExpenseWithReceipt).toHaveBeenLastCalledWith(expect.objectContaining({ file }))
})

it('guards custom service-type selections and consumable inputs', async () => {
  const view = mount('/vehicles/1/service/add?edit=5'); await field(view, 'notes')
  await choose('Tire Rotation')
  await act(async () => { fireEvent.click(screen.getByText('Sidebar')) }); await dialog(); await discard()
  await act(async () => { await view.router.navigate('/vehicles/1/consumable/add') })
  await field(view, 'brand', 'Keep brand')
  await act(async () => { fireEvent.click(screen.getByText('Sidebar')) }); await dialog(); await stay()
  expect((await field(view, 'brand')).value).toBe('Keep brand')
})

it('dismisses an old-account dialog and remounts without its private input', async () => {
  const view = mount(); await field(view, 'name', 'Private account A')
  await choose('Close'); await dialog(); await choose('Change account')
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  expect((await field(view, 'name')).value).toBe('Original vehicle')
  await choose('Close'); await screen.findByText('Destination')
  expect(screen.queryByRole('dialog')).toBeNull()
})

it('asks before explicit sign-out and keeps edits if canceled', async () => {
  const view = mount(); await field(view, 'name', 'Stay signed in')
  await choose('Sign out'); await dialog(); await stay()
  expect((await field(view, 'name')).value).toBe('Stay signed in')
  await choose('Sign out'); await dialog(); await discard()
  await screen.findByText('Signed out'); expect(screen.queryByRole('dialog')).toBeNull()
})

it('ignores a late save redirect after account change unmounts the old form', async () => {
  let finish
  vehicleApi.update.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
  const view = mount(); await field(view, 'name', 'Old account save'); await choose('Save')
  await waitFor(() => expect(finish).toBeTypeOf('function')); await choose('Change account')
  await field(view, 'name')
  await act(async () => { finish({ data: { vehicle } }) })
  expect(view.router.state.location.pathname).toBe('/vehicles/1/edit')
  expect((await field(view, 'name')).value).toBe('Original vehicle')
})

it('does not discard a pending photo when only the parent update was queued', async () => {
  vehicleApi.update.mockRejectedValueOnce(offlineQueued())
  const view = mount(); await field(view, 'name')
  const file = new File(['photo'], 'photo.png', { type: 'image/png' })
  await act(async () => { fireEvent.change(view.container.querySelector('input[type="file"]'), { target: { files: [file] } }) })
  await choose('Save'); await screen.findByText(translations.en.unsavedChanges.fileNotSaved)
  expect(vehicleApi.uploadPhoto).not.toHaveBeenCalled()
  await choose('Close'); await dialog(); await stay()
  await choose('Save'); await screen.findByText('Destination')
  expect(vehicleApi.uploadPhoto).toHaveBeenCalledWith('1', file)
})

it('retries a new vehicle photo against the created record, including subsequent edits', async () => {
  vehicleApi.uploadPhoto.mockRejectedValueOnce(new Error('Photo upload failed'))
  const view = mount('/vehicles/add'); await field(view, 'name', 'First name'); await field(view, 'make', 'Make'); await field(view, 'model', 'Model')
  const file = new File(['photo'], 'photo.png', { type: 'image/png' })
  await act(async () => { fireEvent.change(view.container.querySelector('input[type="file"]'), { target: { files: [file] } }) })
  await choose('Save'); await waitFor(() => expect(vehicleApi.uploadPhoto).toHaveBeenCalledTimes(1))
  await field(view, 'name', 'Revised name'); await choose('Save'); await screen.findByText('Destination')
  expect(vehicleApi.create).toHaveBeenCalledTimes(1)
  expect(vehicleApi.update).toHaveBeenCalledWith(1, expect.objectContaining({ name: 'Revised name' }), expect.anything())
  expect(vehicleApi.uploadPhoto).toHaveBeenLastCalledWith(1, file)
})

it.each(['todo', 'reminder'])('retains a failed %s document and retries the same saved parent', async resource => {
  attachmentApi.upload.mockRejectedValueOnce(new Error('Document upload failed'))
  const view = mount(`/vehicles/1/${resource}/add`)
  if (resource === 'reminder') { await field(view, 'reminder_type', 'custom'); await field(view, 'due_date', '2026-12-31') }
  await field(view, 'title', 'First title')
  const file = new File(['original document'], 'document.pdf')
  await act(async () => { fireEvent.change(screen.getByLabelText('Receipt file'), { target: { files: [file] } }) })
  await choose('Save'); await waitFor(() => expect(attachmentApi.upload).toHaveBeenCalledTimes(1))
  await act(async () => { fireEvent.click(screen.getByText('Sidebar')) }); await dialog(); await stay()
  await field(view, 'title', 'Revised title'); await choose('Save'); await screen.findByText('Destination')
  const create = resource === 'todo' ? api.post : reminderApi.create
  const update = resource === 'todo' ? api.put : reminderApi.update
  expect(create).toHaveBeenCalledTimes(1)
  expect(update).toHaveBeenCalledWith(resource === 'todo' ? '/todos/7' : 7, expect.objectContaining({ title: 'Revised title' }), expect.objectContaining({ headers: expect.objectContaining({ 'If-Match': '"1"' }) }))
  expect(attachmentApi.upload).toHaveBeenLastCalledWith(file, expect.objectContaining({ entryId: 7 }))
})
