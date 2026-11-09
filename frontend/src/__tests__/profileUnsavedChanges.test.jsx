import { StrictMode } from 'react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { createMemoryRouter, RouterProvider, Routes, Route, Link } from 'react-router-dom'
import UnsavedChangesProvider from '../components/UnsavedChangesProvider'
import { ConfirmProvider } from '../components/ui/ConfirmDialog'
import Profile from '../pages/settings/Profile'
import { authApi } from '../services/api'
import { translations } from '../i18n/translations'
import { LOCATION_SETTINGS_ANCHOR, MANUAL_LOCATION_STATE_KEY } from '../config/location'

const auth = vi.hoisted(() => ({ user: null, updateUser: vi.fn(), refreshUser: vi.fn() }))
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => auth }))
vi.mock('../contexts/LanguageContext', () => {
  // One stable t(), like the real useCallback: PasswordStrength re-runs an effect whenever t changes.
  const t = (key, params = {}) => {
    const value = key.split('.').reduce((item, part) => item?.[part], translations.en)
    if (typeof value !== 'string') throw new Error(`Missing translation: ${key}`)
    return value.replace(/\{(\w+)\}/g, (_, name) => params[name] ?? `{${name}}`)
  }
  return { useTranslation: () => ({ t, language: 'en' }) }
})
vi.mock('../services/api', () => ({
  default: { get: vi.fn() },
  authApi: {
    getAvatars: vi.fn(), updateProfile: vi.fn(), changePassword: vi.fn(), validatePassword: vi.fn(), getSessions: vi.fn(),
  },
}))
vi.mock('../hooks/useBackgroundSync', () => ({
  useBackgroundSync: () => ({ hasPendingSync: false, pausedCount: 0, receiptCount: 0 }),
}))
vi.mock('../components/settings/TwoFactorSetup', () => ({ default: () => null }))

const en = translations.en
const SETTINGS_PATH = '/settings'
const PROFILE_PATH = '/settings/profile'
const DESTINATION = 'Destination'
const SIDEBAR_PATH = '/sidebar'
const SIDEBAR_LINK = 'Sidebar'
const EDITED_CURRENCY = 'USD'
const EDITED_DISTANCE_UNIT = 'mi'
const SAVE_REFUSAL = 'Save rejected'
// A 401 would sign the user out before the guard matters; validation refusals are 400.
const VALIDATION_REFUSAL_STATUS = 400
const EDITED_NAME = 'Edited Driver'
const CURRENT_PASSWORD = 'Current-password-1'
const NEW_PASSWORD = 'New-password-2026'
const SAVED_LATITUDE = 44.4268
const LOCATION_SETTINGS_ENTRY = { pathname: PROFILE_PATH, hash: `#${LOCATION_SETTINGS_ANCHOR}` }
const MANUAL_LOCATION_ENTRY = { ...LOCATION_SETTINGS_ENTRY, state: { [MANUAL_LOCATION_STATE_KEY]: true } }
const fixtureUser = {
  id: 1, name: 'Fixture Driver', username: 'fixture', email: 'fixture@example.test', language: 'en',
  currency: 'EUR', distance_unit: 'km', volume_unit: 'liters', location_auto_detect: true,
  location_lat: null, location_lon: null, two_factor_enabled: false, email_verified: true,
}

const routers = []
beforeEach(() => {
  vi.clearAllMocks()
  auth.user = fixtureUser
  authApi.getAvatars.mockResolvedValue({ data: { avatar_history: [] } })
  authApi.updateProfile.mockResolvedValue({ data: { user: fixtureUser } })
  authApi.changePassword.mockResolvedValue({ data: {} })
  authApi.validatePassword.mockResolvedValue({ data: { strength: 'strong', strength_score: 90, errors: [] } })
  authApi.getSessions.mockResolvedValue({ data: { sessions: [] } })
})
afterEach(() => { cleanup(); for (const router of routers.splice(0)) router.dispose() })

function mount(profileEntry = PROFILE_PATH, { strict = true } = {}) {
  const router = createMemoryRouter([{ path: '*', element: (
    <ConfirmProvider>
      <UnsavedChangesProvider>
        <Link to={SIDEBAR_PATH}>{SIDEBAR_LINK}</Link>
        <Routes>
          <Route path={PROFILE_PATH} element={<Profile />} />
          <Route path="*" element={<p>{DESTINATION}</p>} />
        </Routes>
      </UnsavedChangesProvider>
    </ConfirmProvider>
  ) }], { initialEntries: [SETTINGS_PATH, profileEntry] })
  routers.push(router)
  const app = <RouterProvider router={router} />
  const view = render(strict ? <StrictMode>{app}</StrictMode> : app)
  return { ...view, router }
}
async function field(view, name, value) {
  const element = await waitFor(() => {
    const input = view.container.querySelector(`[name="${name}"]`)
    expect(input).toBeTruthy()
    return input
  })
  if (value !== undefined) await act(async () => { fireEvent.change(element, { target: { value } }) })
  return element
}
const click = element => act(async () => { fireEvent.click(element) })
// React Hook Form's setFocus focuses in a zero-delay timer; this one runs after it.
const runFocusTimers = () => act(() => new Promise(resolve => setTimeout(resolve)))
const choose = label => click(screen.getByRole('button', { name: label, exact: true }))
const leave = () => click(screen.getByText(SIDEBAR_LINK))
const dialog = () => screen.findByRole('dialog', { name: en.unsavedChanges.title })
const unloadIsBlocked = () => {
  const event = new Event('beforeunload', { cancelable: true })
  window.dispatchEvent(event)
  return event.defaultPrevented
}
const expectLeftWithoutPrompt = async () => {
  expect(await screen.findByText(DESTINATION)).toBeTruthy()
  expect(screen.queryByRole('dialog')).toBeNull()
}

it('leaves an untouched or toggled-back profile silently, keeps edits on stay and leaves only after discard', async () => {
  const view = mount()
  const autoDetect = await field(view, 'location_auto_detect')
  await click(autoDetect)
  await field(view, 'location_lat')
  await click(autoDetect)
  expect(unloadIsBlocked()).toBe(false)
  await leave()
  await expectLeftWithoutPrompt()

  await act(async () => { await view.router.navigate(PROFILE_PATH) })
  const name = await field(view, 'name', EDITED_NAME)
  await leave(); await dialog(); await choose(en.unsavedChanges.stay)
  expect(name.value).toBe(EDITED_NAME)
  expect(view.router.state.location.pathname).toBe(PROFILE_PATH)

  await act(async () => { await view.router.navigate(-1) }); await dialog(); await choose(en.unsavedChanges.discard)
  expect(await screen.findByText(DESTINATION)).toBeTruthy()
  expect(view.router.state.location.pathname).toBe(SIDEBAR_PATH)
})

it('stays guarded after a failed save, releases after a successful one and re-arms for later edits', async () => {
  authApi.updateProfile.mockRejectedValueOnce({ response: { status: VALIDATION_REFUSAL_STATUS, data: { error: SAVE_REFUSAL } } })
  const view = mount()
  const currency = await field(view, 'currency', EDITED_CURRENCY)
  await choose(en.profile.saveChanges)
  expect(await screen.findByText(SAVE_REFUSAL)).toBeTruthy()
  expect(unloadIsBlocked()).toBe(true)

  await choose(en.profile.saveChanges)
  expect(await screen.findByText(en.profile.profileUpdated)).toBeTruthy()
  expect(authApi.updateProfile).toHaveBeenLastCalledWith(expect.objectContaining({ currency: EDITED_CURRENCY }))
  expect(currency.value).toBe(EDITED_CURRENCY)
  expect(unloadIsBlocked()).toBe(false)

  await field(view, 'distance_unit', EDITED_DISTANCE_UNIT)
  expect(unloadIsBlocked()).toBe(true)
  await leave(); await dialog(); await choose(en.unsavedChanges.discard)
  expect(await screen.findByText(DESTINATION)).toBeTruthy()
})

it('keeps an edit made while the save is in flight and stays guarded until it is undone', async () => {
  let finishSave
  authApi.updateProfile.mockImplementationOnce(() => new Promise(resolve => { finishSave = resolve }))
  const view = mount()
  const currency = await field(view, 'currency', EDITED_CURRENCY)
  await choose(en.profile.saveChanges)
  const distanceUnit = await field(view, 'distance_unit', EDITED_DISTANCE_UNIT)
  await act(async () => { finishSave({ data: { user: fixtureUser } }) })
  expect(await screen.findByText(en.profile.profileUpdated)).toBeTruthy()
  expect(authApi.updateProfile).toHaveBeenLastCalledWith(
    expect.objectContaining({ currency: EDITED_CURRENCY, distance_unit: fixtureUser.distance_unit }))
  expect([currency.value, distanceUnit.value]).toEqual([EDITED_CURRENCY, EDITED_DISTANCE_UNIT])
  expect(unloadIsBlocked()).toBe(true)

  await field(view, 'distance_unit', fixtureUser.distance_unit)
  expect(unloadIsBlocked()).toBe(false)
})

it('releases the guard after a save confirmed in the password-verification modal', async () => {
  const view = mount()
  await field(view, 'name', EDITED_NAME)
  await choose(en.profile.saveChanges)
  expect(await screen.findByText(en.profile.verifyIdentity)).toBeTruthy()
  expect(unloadIsBlocked()).toBe(true)

  // The modal's input has no name; it is the only password input while the Profile tab is shown.
  const verificationPassword = view.container.querySelector('input[type="password"]')
  await act(async () => { fireEvent.change(verificationPassword, { target: { value: CURRENT_PASSWORD } }) })
  await choose(en.common.confirm)
  expect(await screen.findByText(en.profile.profileUpdated)).toBeTruthy()
  expect(authApi.updateProfile).toHaveBeenLastCalledWith(
    expect.objectContaining({ name: EDITED_NAME, current_password: CURRENT_PASSWORD }))
  expect(unloadIsBlocked()).toBe(false)
  await leave()
  await expectLeftWithoutPrompt()
})

it('guards a half-typed password change on every tab and releases it once the password is changed', async () => {
  const view = mount()
  await choose(en.common.password)
  await field(view, 'current_password', CURRENT_PASSWORD)
  expect(unloadIsBlocked()).toBe(true)

  await choose(en.profile.title)
  expect(screen.queryByRole('dialog')).toBeNull()
  await leave(); await dialog(); await choose(en.unsavedChanges.stay)
  await choose(en.common.password)
  expect((await field(view, 'current_password')).value).toBe(CURRENT_PASSWORD)

  await field(view, 'new_password', NEW_PASSWORD)
  await field(view, 'confirm_password', NEW_PASSWORD)
  await choose(en.profile.changePassword)
  expect(await screen.findByText(en.profile.passwordChanged)).toBeTruthy()
  expect(authApi.changePassword).toHaveBeenCalledWith(
    expect.objectContaining({ current_password: CURRENT_PASSWORD, new_password: NEW_PASSWORD }))
  expect(unloadIsBlocked()).toBe(false)
  await leave()
  await expectLeftWithoutPrompt()
})

it('keeps a manual location without saved coordinates clean until a real edit, and saves typed ones as numbers', async () => {
  auth.user = { ...fixtureUser, location_auto_detect: false }
  const view = mount()
  await field(view, 'location_lat')
  expect(unloadIsBlocked()).toBe(false)

  await field(view, 'currency', EDITED_CURRENCY)
  expect(unloadIsBlocked()).toBe(true)
  await field(view, 'currency', fixtureUser.currency)
  expect(unloadIsBlocked()).toBe(false)

  await field(view, 'location_lat', String(SAVED_LATITUDE))
  await choose(en.profile.saveChanges)
  expect(await screen.findByText(en.profile.profileUpdated)).toBeTruthy()
  // The server reads '' as "no coordinate".
  expect(authApi.updateProfile).toHaveBeenLastCalledWith(
    expect.objectContaining({ location_lat: SAVED_LATITUDE, location_lon: '' }))
  expect(unloadIsBlocked()).toBe(false)
  await leave()
  await expectLeftWithoutPrompt()
})

// Also without StrictMode: its second, development-only effect pass marks the form dirty by itself.
it.each([true, false])('opens Location Settings in manual mode from the location dialog, focused and guarded until saved (StrictMode: %s)', async strict => {
  const view = mount(MANUAL_LOCATION_ENTRY, { strict })
  const locationName = await screen.findByLabelText(en.profile.locationName)
  expect(screen.getByLabelText(en.profile.latitude)).toBeTruthy()
  expect(screen.getByLabelText(en.profile.longitude)).toBeTruthy()
  const autoDetect = screen.getByRole('checkbox', { name: en.profile.autoDetectLocation })
  expect(autoDetect.checked).toBe(false)
  await waitFor(() => expect(document.activeElement).toBe(locationName))
  expect(authApi.updateProfile).not.toHaveBeenCalled()
  expect(unloadIsBlocked()).toBe(true)
  expect(view.router.state.location).toMatchObject({ ...LOCATION_SETTINGS_ENTRY, state: null })

  // Only on arrival: switching auto-detect off again later leaves focus on the switch.
  autoDetect.focus()
  await click(autoDetect); await click(autoDetect)
  await runFocusTimers()
  expect(document.activeElement).toBe(autoDetect)

  await leave(); await dialog(); await choose(en.unsavedChanges.stay)
  expect(view.router.state.location.pathname).toBe(PROFILE_PATH)
})

it('does not re-apply an undone manual-location request when the person comes Back to that entry', async () => {
  const view = mount(MANUAL_LOCATION_ENTRY)
  await screen.findByLabelText(en.profile.locationName)
  await click(screen.getByRole('checkbox', { name: en.profile.autoDetectLocation }))
  await leave()
  await expectLeftWithoutPrompt()

  await act(async () => { await view.router.navigate(-1) })
  expect((await screen.findByRole('checkbox', { name: en.profile.autoDetectLocation })).checked).toBe(true)
  expect(screen.queryByLabelText(en.profile.locationName)).toBeNull()
  await runFocusTimers()
  expect(document.activeElement).toBe(document.body)
  expect(unloadIsBlocked()).toBe(false)
})

it('leaves auto-detect, focus and the guard alone when Location Settings is opened without that request', async () => {
  mount(LOCATION_SETTINGS_ENTRY)
  expect((await screen.findByRole('checkbox', { name: en.profile.autoDetectLocation })).checked).toBe(true)
  expect(screen.queryByLabelText(en.profile.locationName)).toBeNull()
  await runFocusTimers()
  expect(document.activeElement).toBe(document.body)
  expect(unloadIsBlocked()).toBe(false)
  await leave()
  await expectLeftWithoutPrompt()
})

it('does not treat a half-typed account-deletion password as an unsaved edit', async () => {
  mount()
  await choose(en.profile.security)
  await choose(en.profile.deleteAccount)
  await act(async () => { fireEvent.change(screen.getByLabelText(en.common.password), { target: { value: CURRENT_PASSWORD } }) })
  expect(unloadIsBlocked()).toBe(false)
  await leave()
  await expectLeftWithoutPrompt()
})
