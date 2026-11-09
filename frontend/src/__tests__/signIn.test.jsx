import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AuthProvider } from '../contexts/AuthContext'
import Login from '../pages/auth/Login'
import { translations } from '../i18n/translations'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))

vi.mock('../services/api', () => ({ default: api }))
vi.mock('../utils/privateStorage', () => ({
  migratePrivateStorage: vi.fn(), readPrivateProfile: vi.fn(), savePrivateProfile: vi.fn(),
  privateSessionValid: vi.fn(), clearPrivatePageStorage: vi.fn(),
}))
vi.mock('../db/mutationQueue', () => ({ getQueueState: async () => ({}) }))
vi.mock('../utils/offlineIdentity', () => ({
  beginIdentityTransition: async () => ({}), establishOfflineIdentity: vi.fn(), restoreOfflineIdentity: vi.fn(),
  forgetBoundIdentity: vi.fn(), getBoundIdentity: vi.fn(),
}))
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))
vi.mock('../contexts/LanguageContext', () => ({ useLanguage: () => ({ t: translate }) }))

function translate(key) {
  const value = key.split('.').reduce((item, part) => item?.[part], translations.en)
  if (typeof value !== 'string') throw new Error(`Missing translation: ${key}`)
  return value
}

const LOGIN_PATH = '/login'
const HOME_PATH = '/'
const HOME_PAGE_TEXT = 'Signed in'
const LOGIN_ENDPOINT = '/auth/login'
const UNAUTHENTICATED_STATUS = 401
const EMAIL = 'driver@example.invalid'
const PASSWORD = 'correct horse battery staple'
const AUTHENTICATOR_CODE = '123456'
const TYPED_BACKUP_CODE = 'abcd1234'
const SUBMITTED_BACKUP_CODE = 'ABCD1234'
const SIGNED_IN_RESPONSE = { data: { user: { id: 7 } } }
const TWO_FACTOR_CHALLENGE = { data: { requires_2fa: true } }
const SIGN_IN_BUTTON = translations.en.auth.login.toUpperCase()

const expectedBody = (codes = {}) => ({ email: EMAIL, password: PASSWORD, totp_code: null, backup_code: null, ...codes })

const mount = () => act(async () => {
  render(
    <MemoryRouter initialEntries={[LOGIN_PATH]}>
      <AuthProvider>
        <Routes>
          <Route path={LOGIN_PATH} element={<Login />} />
          <Route path={HOME_PATH} element={<p>{HOME_PAGE_TEXT}</p>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
})

const submitPassword = () => act(async () => {
  fireEvent.change(screen.getByPlaceholderText(translations.en.auth.username), { target: { value: EMAIL } })
  fireEvent.change(screen.getByPlaceholderText(translations.en.auth.password), { target: { value: PASSWORD } })
  fireEvent.click(screen.getByRole('button', { name: SIGN_IN_BUTTON }))
})

// Login submits the code on its own once it reaches full length.
const enterCode = value => act(async () => {
  fireEvent.change(screen.getByRole('textbox'), { target: { value } })
})

const reachTwoFactorStep = async () => {
  api.post.mockResolvedValueOnce(TWO_FACTOR_CHALLENGE).mockResolvedValueOnce(SIGNED_IN_RESPONSE)
  await mount()
  await submitPassword()
  await screen.findByRole('heading', { name: translations.en.auth.twoFactorAuth })
}

afterEach(cleanup)
beforeEach(() => {
  api.get.mockReset()
  api.get.mockRejectedValue({ response: { status: UNAUTHENTICATED_STATUS } })
  api.post.mockReset()
})

it('offers no remember-password control', async () => {
  await mount()

  expect(screen.queryByRole('checkbox')).toBeNull()
  expect(screen.getByRole('button', { name: SIGN_IN_BUTTON })).toBeTruthy()
})

it('signs in with the email and password alone', async () => {
  api.post.mockResolvedValueOnce(SIGNED_IN_RESPONSE)
  await mount()
  await submitPassword()

  expect(await screen.findByText(HOME_PAGE_TEXT)).toBeTruthy()
  expect(api.post).toHaveBeenCalledTimes(1)
  expect(api.post).toHaveBeenCalledWith(LOGIN_ENDPOINT, expectedBody())
})

it('sends an authenticator code as totp_code', async () => {
  await reachTwoFactorStep()
  await enterCode(AUTHENTICATOR_CODE)

  expect(await screen.findByText(HOME_PAGE_TEXT)).toBeTruthy()
  expect(api.post).toHaveBeenCalledTimes(2)
  expect(api.post).toHaveBeenLastCalledWith(LOGIN_ENDPOINT, expectedBody({ totp_code: AUTHENTICATOR_CODE }))
})

it('sends a backup code as backup_code', async () => {
  await reachTwoFactorStep()
  fireEvent.click(screen.getByRole('button', { name: translations.en.auth.useBackupCodeInstead }))
  await enterCode(TYPED_BACKUP_CODE)

  expect(await screen.findByText(HOME_PAGE_TEXT)).toBeTruthy()
  expect(api.post).toHaveBeenCalledTimes(2)
  expect(api.post).toHaveBeenLastCalledWith(LOGIN_ENDPOINT, expectedBody({ backup_code: SUBMITTED_BACKUP_CODE }))
})
