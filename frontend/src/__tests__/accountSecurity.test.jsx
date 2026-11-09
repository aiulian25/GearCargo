import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { translations } from '../i18n/translations'

const { api, authApi, auth, navigate, toast, confirm, confirmResult, backgroundSync, useBackgroundSync } = vi.hoisted(() => ({
  api: { get: vi.fn() },
  authApi: {
    getAvatars: vi.fn(), getSessions: vi.fn(), revokeSession: vi.fn(),
    revokeOtherSessions: vi.fn(), deleteAccount: vi.fn(),
  },
  auth: { user: {}, logout: vi.fn(), updateUser: vi.fn(), refreshUser: vi.fn() },
  navigate: vi.fn(),
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
  confirm: vi.fn(),
  confirmResult: { value: true },
  backgroundSync: { hasPendingSync: false, pausedCount: 0, receiptCount: 0 },
  useBackgroundSync: vi.fn(),
}))

vi.mock('../services/api', () => ({ default: api, authApi }))
vi.mock('react-hot-toast', () => ({ default: toast }))
vi.mock('react-router-dom', () => ({ useNavigate: () => navigate, useLocation: () => ({ state: null }) }))
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => auth }))
vi.mock('../contexts/LanguageContext', () => {
  const t = (key, params = {}) => {
    const value = key.split('.').reduce((item, part) => item?.[part], translations.en)
    if (typeof value !== 'string') throw new Error(`Missing translation: ${key}`)
    return value.replace(/\{(\w+)\}/g, (_, name) => params[name] ?? `{${name}}`)
  }
  return { useTranslation: () => ({ t }) }
})
vi.mock('../hooks/useDateFormat', () => ({
  useDateFormat: () => ({ formatDateTime: (value) => String(value).slice(0, 16) }),
}))
vi.mock('../hooks/useBackgroundSync', () => ({ useBackgroundSync }))
vi.mock('../components/ui/ConfirmDialog', () => ({ useConfirm: () => confirm }))
vi.mock('../components/settings/TwoFactorSetup', () => ({ default: () => null }))

const { default: Profile } = await import('../pages/settings/Profile')

const en = translations.en
const LANGUAGES = ['en', 'ro', 'es']
const SERVER_MESSAGE_KEYS = [
  'sessionChanged', 'deleteAccountPasswordInvalid', 'deleteAccountCodeInvalid',
  'deleteAccountLastAdmin', 'deleteAccountUnconfirmed', 'deleteAccountConflict',
]
const PAGE_KEYS = [
  'logoutOtherDevices', 'lastActive', 'sessionEnds', 'unknownDevice', 'signOutSession', 'signOutDevice',
  'signOutSessionTitle', 'signOutSessionConfirm', 'sessionSignedOut', 'logoutOtherDevicesTitle',
  'logoutOtherDevicesConfirm', 'otherDevicesSignedOut', 'noOtherSessions', 'deleteAccountDescription',
  'deleteAccountUnsentDrafts', 'deleteAccountConfirm', 'deletingAccount', 'accountDeleted',
  'deleteAccountMayHaveCompleted', 'deleteAccountTooManyAttempts', 'deleteAccountBusy',
]
const THIS_LAPTOP = {
  id: 1, browser: 'Firefox', os: 'Linux', is_current: true,
  last_active_at: '2026-11-09T08:00:00Z', expires_at: '2026-12-09T08:00:00Z',
}
const PHONE = {
  id: 9, browser: 'Chrome', os: 'Android', is_current: false,
  last_active_at: '2026-11-08T09:00:00Z', expires_at: '2026-12-08T09:00:00Z',
}
const PHONE_SIGN_OUT = 'Sign out Chrome · Android'
const PASSWORD = 'StrongPass123!'

afterEach(cleanup)
beforeEach(() => {
  vi.clearAllMocks()
  auth.user = { name: 'Driver', email: 'driver@example.com', two_factor_enabled: false }
  authApi.getAvatars.mockResolvedValue({ data: { avatar_history: [] } })
  authApi.getSessions.mockResolvedValue({ data: { sessions: [THIS_LAPTOP, PHONE] } })
  api.get.mockResolvedValue({ data: { backup_codes_count: 5 } })
  confirm.mockImplementation(() => Promise.resolve(confirmResult.value))
  confirmResult.value = true
  Object.assign(backgroundSync, { hasPendingSync: false, pausedCount: 0, receiptCount: 0 })
  useBackgroundSync.mockReturnValue(backgroundSync)
})

const clickAndSettle = async (element) => {
  await act(async () => { fireEvent.click(element) })
}

const typeInto = (element, value) => fireEvent.change(element, { target: { value } })

const openSecurityTab = async () => {
  render(<Profile />)
  await clickAndSettle(screen.getByRole('button', { name: en.profile.security }))
  await waitFor(() => expect(screen.getByText('Firefox · Linux')).toBeTruthy())
}

const openDeletionForm = async () => {
  await openSecurityTab()
  await clickAndSettle(screen.getByRole('button', { name: en.profile.deleteAccount }))
}

const submitButton = () => screen.getByRole('button', { name: en.profile.deleteAccountConfirm })

const submitDeletion = async (code) => {
  await openDeletionForm()
  typeInto(screen.getByLabelText(en.common.password), PASSWORD)
  if (code) typeInto(screen.getByLabelText(en.twoFactor.disableCodeLabel), code)
  await clickAndSettle(submitButton())
}

describe('account security localization', () => {
  it('offers every new string in all supported languages with the same placeholders', () => {
    const placeholders = (text) => [...text.matchAll(/\{\w+\}/g)].map(([token]) => token).sort()
    for (const key of [...SERVER_MESSAGE_KEYS, ...PAGE_KEYS]) {
      for (const language of LANGUAGES) {
        const text = translations[language].profile[key]
        expect(typeof text, `${language}.profile.${key}`).toBe('string')
        expect(text.trim()).not.toBe('')
        expect(placeholders(text), `${language}.profile.${key}`).toEqual(placeholders(en.profile[key]))
      }
    }
  })

  it('drops the strings of the old static cards', () => {
    for (const language of LANGUAGES) {
      expect(translations[language].profile.logoutAllDevices).toBeUndefined()
      expect(translations[language].common.active).toBeUndefined()
    }
  })

  it('tells readers of the privacy policy where to delete their account', () => {
    for (const language of LANGUAGES) {
      const { privacy, profile } = translations[language]
      expect(privacy.dataAccessItem3).toContain(profile.security)
    }
  })
})

describe('signed-in devices', () => {
  it('lists each device with when it was last active and when its session ends', async () => {
    await openSecurityTab()

    expect(screen.getByText(en.profile.currentDevice)).toBeTruthy()
    expect(screen.getByText('Chrome · Android')).toBeTruthy()
    expect(screen.getByText('Last active 2026-11-08T09:00')).toBeTruthy()
    expect(screen.getByText('Session ends 2026-12-08T09:00')).toBeTruthy()
    expect(screen.getAllByRole('button', { name: /^Sign out / })).toHaveLength(1)
    expect(screen.getByRole('button', { name: PHONE_SIGN_OUT })).toBeTruthy()
    expect(screen.getByRole('button', { name: en.profile.logoutOtherDevices })).toBeTruthy()
  })

  it('keeps the device when the sign-out is not confirmed', async () => {
    confirmResult.value = false
    await openSecurityTab()

    await clickAndSettle(screen.getByRole('button', { name: PHONE_SIGN_OUT }))

    expect(confirm).toHaveBeenCalledWith(expect.objectContaining({
      title: 'Sign out Chrome · Android?', destructive: true,
    }))
    expect(authApi.revokeSession).not.toHaveBeenCalled()
  })

  it('signs out one device once confirmed and reloads the list', async () => {
    authApi.revokeSession.mockResolvedValue({ data: {} })
    await openSecurityTab()
    authApi.getSessions.mockResolvedValue({ data: { sessions: [THIS_LAPTOP] } })

    await clickAndSettle(screen.getByRole('button', { name: PHONE_SIGN_OUT }))

    expect(authApi.revokeSession).toHaveBeenCalledWith(PHONE.id)
    await waitFor(() => expect(screen.getByRole('status').textContent).toBe(en.profile.sessionSignedOut))
    expect(screen.queryByRole('button', { name: PHONE_SIGN_OUT })).toBeNull()
    expect(screen.queryByRole('button', { name: en.profile.logoutOtherDevices })).toBeNull()
    expect(screen.getByText(en.profile.noOtherSessions)).toBeTruthy()
    expect(document.activeElement).toBe(screen.getByRole('heading', { name: en.profile.activeSessions }))
  })

  it('signs out every other device and keeps this one', async () => {
    authApi.revokeOtherSessions.mockResolvedValue({ data: { revoked: 1 } })
    await openSecurityTab()
    authApi.getSessions.mockResolvedValue({ data: { sessions: [THIS_LAPTOP] } })

    await clickAndSettle(screen.getByRole('button', { name: en.profile.logoutOtherDevices }))

    expect(authApi.revokeOtherSessions).toHaveBeenCalledTimes(1)
    await waitFor(() => expect(screen.getByRole('status').textContent).toBe(en.profile.otherDevicesSignedOut))
    expect(authApi.getSessions).toHaveBeenCalledTimes(2)
  })

  it('reloads the list when that device signed in again meanwhile', async () => {
    authApi.revokeSession.mockRejectedValue({ response: { status: 404, data: { message_key: 'profile.sessionChanged' } } })
    await openSecurityTab()
    authApi.getSessions.mockResolvedValue({ data: { sessions: [THIS_LAPTOP, { ...PHONE, id: 10 }] } })

    await clickAndSettle(screen.getByRole('button', { name: PHONE_SIGN_OUT }))

    await waitFor(() => expect(screen.getByRole('alert').textContent).toBe(en.profile.sessionChanged))
    expect(authApi.getSessions).toHaveBeenCalledTimes(2)
    expect(screen.getByRole('button', { name: PHONE_SIGN_OUT })).toBeTruthy()
  })
})

describe('account deletion', () => {
  it('asks for the password, and for a code only while two-factor sign-in is on', async () => {
    await openDeletionForm()

    expect(screen.queryByLabelText(en.twoFactor.disableCodeLabel)).toBeNull()
    expect(submitButton().disabled).toBe(true)
    typeInto(screen.getByLabelText(en.common.password), PASSWORD)
    expect(submitButton().disabled).toBe(false)

    cleanup()
    auth.user = { ...auth.user, two_factor_enabled: true }
    await openDeletionForm()
    typeInto(screen.getByLabelText(en.common.password), PASSWORD)
    expect(submitButton().disabled).toBe(true)
    typeInto(screen.getByLabelText(en.twoFactor.disableCodeLabel), '123456')
    expect(submitButton().disabled).toBe(false)
  })

  it('moves focus into the form and back to Delete Account on Cancel', async () => {
    await openDeletionForm()

    const password = screen.getByLabelText(en.common.password)
    expect(document.activeElement).toBe(password)
    expect(password.getAttribute('aria-describedby')).toBeTruthy()
    expect(document.getElementById(password.getAttribute('aria-describedby')).textContent)
      .toBe(en.profile.deleteAccountDescription)

    await clickAndSettle(screen.getByRole('button', { name: en.common.cancel }))

    expect(document.activeElement).toBe(screen.getByRole('button', { name: en.profile.deleteAccount }))
  })

  it('cannot be cancelled while the deletion request is running', async () => {
    authApi.deleteAccount.mockReturnValue(new Promise(() => {}))

    await submitDeletion()

    expect(screen.getByRole('button', { name: en.profile.deletingAccount }).disabled).toBe(true)
    expect(screen.getByRole('button', { name: en.common.cancel }).disabled).toBe(true)
  })

  it.each([
    ['123456', { totp_code: '123456' }],
    ['dead-beef', { backup_code: 'dead-beef' }],
  ])('sends %s the way disabling two-factor sign-in does', async (code, secondFactor) => {
    auth.user = { ...auth.user, two_factor_enabled: true }
    authApi.deleteAccount.mockResolvedValue({ data: { cleanup: { state: 'completed' } } })

    await submitDeletion(code)

    expect(authApi.deleteAccount).toHaveBeenCalledWith({ password: PASSWORD, ...secondFactor })
  })

  it('signs out locally and lands on the sign-in page', async () => {
    authApi.deleteAccount.mockResolvedValue({ data: { cleanup: { state: 'completed' } } })

    await submitDeletion()

    expect(toast.success).toHaveBeenCalledWith(en.profile.accountDeleted)
    expect(auth.logout).toHaveBeenCalledWith({ sessionEndedByServer: true })
    expect(navigate).toHaveBeenCalledWith('/login', { replace: true })
  })

  it('says when file cleanup is still pending', async () => {
    authApi.deleteAccount.mockResolvedValue({ data: { cleanup: { state: 'pending' } } })

    await submitDeletion()

    expect(toast).toHaveBeenCalledWith(en.common.deletionCleanupPending, expect.anything())
    expect(toast.success).not.toHaveBeenCalled()
    expect(navigate).toHaveBeenCalledWith('/login', { replace: true })
  })

  it.each([
    [{ status: 403, data: { message_key: 'profile.deleteAccountPasswordInvalid', error: 'Password verification failed' } },
      en.profile.deleteAccountPasswordInvalid],
    [{ status: 409, data: { message_key: 'profile.deleteAccountConflict', error: 'Invalid media path. Ask an administrator to repair it before deleting.' } },
      en.profile.deleteAccountConflict],
    [{ status: 429, data: { error: 'Rate limit exceeded' } }, en.profile.deleteAccountTooManyAttempts],
    [{ status: 503, data: { error: 'Restore maintenance is active. Retry shortly.', recovery: { state: 'maintenance' } } },
      en.profile.deleteAccountBusy],
    // Unknown outcome: signing out here could leave a still-valid session in the browser.
    [{ status: 503, data: { code: 'AUTH_UNAVAILABLE', error: 'Sign-in verification is temporarily unavailable.' } },
      en.profile.deleteAccountMayHaveCompleted],
  ])('stays signed in and explains a refusal', async (response, message) => {
    authApi.deleteAccount.mockRejectedValue({ response })

    await submitDeletion()

    expect(screen.getByRole('alert').textContent).toBe(message)
    expect(auth.logout).not.toHaveBeenCalled()
    expect(navigate).not.toHaveBeenCalled()
  })

  it('shows the code field when two-factor sign-in was turned on elsewhere', async () => {
    authApi.deleteAccount.mockRejectedValue({
      response: { status: 403, data: { message_key: 'profile.deleteAccountCodeInvalid' } },
    })
    auth.refreshUser.mockImplementation(async () => {
      auth.user = { ...auth.user, two_factor_enabled: true }
    })

    await submitDeletion()

    expect(auth.refreshUser).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('alert').textContent).toBe(en.profile.deleteAccountCodeInvalid)
    expect(screen.getByLabelText(en.twoFactor.disableCodeLabel)).toBeTruthy()
  })

  it('looks for unsent drafts only while the form is open', async () => {
    await openSecurityTab()
    expect(useBackgroundSync).not.toHaveBeenCalled()

    await clickAndSettle(screen.getByRole('button', { name: en.profile.deleteAccount }))

    expect(useBackgroundSync).toHaveBeenCalled()
  })

  it('warns that unsent drafts stay on this device without blocking deletion', async () => {
    backgroundSync.receiptCount = 1
    await openDeletionForm()

    expect(screen.getByText(en.profile.deleteAccountUnsentDrafts, { exact: false })).toBeTruthy()
    typeInto(screen.getByLabelText(en.common.password), PASSWORD)
    expect(submitButton().disabled).toBe(false)
  })
})
