import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Outlet, useLocation, useNavigate } from 'react-router-dom'
import App from '../App'
import { reminderApi } from '../services/api'
import { translations } from '../i18n/translations'
import { reminderAuthPath, reminderReturnPath } from '../utils/reminderRoutes'

const auth = vi.hoisted(() => ({ isAuthenticated: true, isLoading: false, user: { id: 1 } }))
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => auth }))
vi.mock('../contexts/LanguageContext', () => ({ useTranslation: () => ({ t: key => key.split('.').reduce((v, k) => v?.[k], translations.en) || key }) }))
vi.mock('../layouts/AppLayout', () => ({ default: () => <Outlet /> }))
vi.mock('../layouts/AuthLayout', () => ({ default: ({ children }) => children }))
vi.mock('../components/PWA', () => ({ InstallPrompt: () => null, UpdatePrompt: () => null, PullToRefresh: () => null }))
vi.mock('../components/PWA/UpdateModal', () => ({ default: () => null }))
vi.mock('../pages/Dashboard', () => ({ default: () => <h1>Dashboard fallback</h1> }))
vi.mock('../pages/auth/Login', () => ({ default: () => <Location /> }))
vi.mock('../pages/auth/ForcePasswordChange', () => ({ default: () => <Location /> }))
vi.mock('../services/api', () => ({ reminderApi: { get: vi.fn(), getAll: vi.fn(), getStats: vi.fn(), complete: vi.fn(), snooze: vi.fn() } }))

afterEach(() => { cleanup(); vi.restoreAllMocks() })
beforeEach(() => {
  vi.clearAllMocks()
  auth.isAuthenticated = true
  auth.user = { id: 1 }
  reminderApi.get.mockResolvedValue({ data: { id: 42, title: 'Named reminder', vehicle_id: 7, vehicle_name: 'Blue car',
    due_date: '2028-02-29', due_mileage: 12000, vehicle_distance_unit: 'miles', description: 'Inspect brakes' } })
})
const mount = path => render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>)
function Location() { const location = useLocation(); return <p>{location.pathname + location.search}</p> }

it('resolves a delivered reminder URL in the actual App router and loads its owner-scoped record', async () => {
  mount('/reminders/42')
  expect(await screen.findByRole('heading', { name: 'Named reminder' })).toBeTruthy()
  expect(reminderApi.get).toHaveBeenCalledWith('42')
  expect(screen.getByRole('link', { name: 'Blue car' }).getAttribute('href')).toBe('/vehicles/7')
  expect(screen.queryByText('Dashboard fallback')).toBeNull()
})

it.each([403, 404, 410])('shows a useful unavailable state for HTTP %s without displaying another record', async status => {
  reminderApi.get.mockRejectedValueOnce({ response: { status } })
  mount('/reminders/42')
  expect((await screen.findByRole('alert')).textContent).toBe(translations.en.reminderDetail.unavailable)
  expect(screen.getByRole('link', { name: 'All reminders' }).getAttribute('href')).toBe('/reminders')
  expect(screen.queryByText('Named reminder')).toBeNull()
})

it('keeps a failed read distinct from a missing record and allows retry', async () => {
  reminderApi.get.mockRejectedValueOnce(new Error('offline'))
  mount('/reminders/42')
  expect((await screen.findByRole('alert')).textContent).toContain(translations.en.reminderDetail.loadFailed)
  fireEvent.click(screen.getByRole('button', { name: 'Reload reminder' }))
  expect(await screen.findByRole('heading', { name: 'Named reminder' })).toBeTruthy()
})

it('retains the reminder through sign-in and required password change', async () => {
  auth.isAuthenticated = false
  mount('/reminders/42')
  expect(await screen.findByText('/login?reminder=42')).toBeTruthy()
  expect(reminderApi.get).not.toHaveBeenCalled()
  cleanup()
  auth.isAuthenticated = true
  auth.user.must_change_password = true
  mount('/reminders/42')
  expect(await screen.findByText('/change-password?reminder=42')).toBeTruthy()
})

it('returns an already signed-in login visit to the requested reminder', async () => {
  mount('/login?reminder=42')
  expect(await screen.findByRole('heading', { name: 'Named reminder' })).toBeTruthy()
})

it.each(['//evil.test', '/reminders/42', '42&next=bad', '0', '-1', 'abc'])('does not accept %s as an authentication return ID', value => {
  expect(reminderAuthPath('/login', value)).toBe('/login')
  expect(reminderReturnPath(`?reminder=${encodeURIComponent(value)}`)).toBe('/')
})

it('retains the named completed reminder after completing it', async () => {
  reminderApi.complete.mockResolvedValue({ data: { reminder: { id: 42, title: 'Named reminder', due_date: '2028-02-29', completed: true } } })
  mount('/reminders/42')
  fireEvent.click(await screen.findByRole('button', { name: 'Mark complete' }))
  expect(await screen.findByText('Completed')).toBeTruthy()
  expect(screen.getByRole('heading', { name: 'Named reminder' })).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'Mark complete' })).toBeNull()
})

it('requires a legacy threshold and keeps cancellation from completing the reminder', async () => {
  reminderApi.complete.mockRejectedValue({ response: { data: { code: 'MILEAGE_RECURRENCE_REQUIRED', minimum_next_mileage: 15001 } } })
  const prompt = vi.spyOn(window, 'prompt').mockReturnValueOnce(null).mockReturnValueOnce('18000')
  mount('/reminders/42')
  fireEvent.click(await screen.findByRole('button', { name: 'Mark complete' }))
  await waitFor(() => expect(prompt).toHaveBeenCalledTimes(1))
  expect(reminderApi.complete).toHaveBeenCalledTimes(1)
  await waitFor(() => expect(screen.getByRole('button', { name: 'Mark complete' }).disabled).toBe(false))
  reminderApi.complete.mockRejectedValueOnce({ response: { data: { code: 'MILEAGE_RECURRENCE_REQUIRED', minimum_next_mileage: 15001 } } })
    .mockResolvedValueOnce({ data: { reminder: { id: 42, title: 'Named reminder', due_date: '2028-02-29', completed: true } } })
  fireEvent.click(screen.getByRole('button', { name: 'Mark complete' }))
  expect(await screen.findByText('Completed')).toBeTruthy()
  expect(reminderApi.complete).toHaveBeenLastCalledWith(42, { next_due_mileage: 18000 }, expect.any(Object))
})

it('clears an obsolete record when a failed action is followed by a missing-record reload', async () => {
  reminderApi.snooze.mockRejectedValueOnce({ response: { status: 409 } })
  mount('/reminders/42')
  fireEvent.click(await screen.findByRole('button', { name: 'Snooze 7 days' }))
  await screen.findByRole('alert')
  reminderApi.get.mockRejectedValueOnce({ response: { status: 404 } })
  fireEvent.click(screen.getByRole('button', { name: 'Reload reminder' }))
  await waitFor(() => expect(screen.getByRole('alert').textContent).toBe(translations.en.reminderDetail.unavailable))
  expect(screen.queryByText('Named reminder')).toBeNull()
})

it('shows an already completed or dismissed standalone reminder without actions', async () => {
  reminderApi.get.mockResolvedValue({ data: { id: 42, title: 'Old standalone', due_date: '2020-01-01', dismissed: true } })
  mount('/reminders/42')
  expect(await screen.findByText('Dismissed')).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'Mark complete' })).toBeNull()
})

it('does not show a previous reminder or let its late response replace the new ID', async () => {
  let resolveOld
  reminderApi.get.mockImplementation(id => id === '42' ? new Promise(resolve => { resolveOld = resolve })
    : Promise.resolve({ data: { id: 43, title: 'New notification', due_date: '2028-03-01' } }))
  function Switch() { const navigate = useNavigate(); return <button onClick={() => navigate('/reminders/43')}>Switch notification</button> }
  render(<MemoryRouter initialEntries={['/reminders/42']}><Switch /><App /></MemoryRouter>)
  await waitFor(() => expect(reminderApi.get).toHaveBeenCalledWith('42'))
  fireEvent.click(screen.getByText('Switch notification'))
  expect(await screen.findByRole('heading', { name: 'New notification' })).toBeTruthy()
  resolveOld({ data: { id: 42, title: 'Stale notification', due_date: '2028-01-01' } })
  await waitFor(() => expect(screen.queryByText('Stale notification')).toBeNull())
})

it('keeps detail messages available in every supported language', () => {
  for (const lang of ['ro', 'es']) expect(Object.keys(translations[lang].reminderDetail).sort()).toEqual(Object.keys(translations.en.reminderDetail).sort())
})

it('opens workshop preparation from a delivered reminder without offering independent schedule editing', async () => {
  reminderApi.get.mockResolvedValue({ data: { id: 42, title: 'Prepare workshop visit', vehicle_id: 7, reminder_type: 'workshop_preparation', due_date: '2028-02-29' } })
  mount('/reminders/42')
  expect((await screen.findByRole('link', { name: 'Workshop visits' })).getAttribute('href')).toBe('/vehicles/7/appointments')
  expect(screen.queryByRole('link', { name: translations.en.reminderDetail.edit })).toBeNull()
})
