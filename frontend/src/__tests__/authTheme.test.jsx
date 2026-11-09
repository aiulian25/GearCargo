import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { translations } from '../i18n/translations'

const auth = { login: vi.fn(), loginWithPasskey: vi.fn() }
const authApi = { requestPasswordReset: vi.fn(), verifyPasswordReset: vi.fn() }

// ResetPassword's strength meter re-runs whenever t changes, so t must be one stable function.
function translate(key) {
  const value = key.split('.').reduce((item, part) => item?.[part], translations.en)
  if (typeof value !== 'string') throw new Error(`Missing translation: ${key}`)
  return value
}

vi.mock('../contexts/LanguageContext', () => ({ useLanguage: () => ({ t: translate }) }))
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => auth }))
vi.mock('../services/api', () => ({ default: { get: vi.fn() }, authApi }))
vi.mock('@simplewebauthn/browser', () => ({ browserSupportsWebAuthn: () => false }))
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))

const { default: Login } = await import('../pages/auth/Login')
const { default: ForgotPassword } = await import('../pages/auth/ForgotPassword')
const { default: ResetPassword } = await import('../pages/auth/ResetPassword')
const { default: AuthLayout } = await import('../layouts/AuthLayout')

const ACCENT_TOKEN = '--color-auth-accent'
const ACCENT_HOVER_TOKEN = '--color-auth-accent-hover'
const ACCENT_CLASS = `bg-(${ACCENT_TOKEN})`
const ACCENT_HOVER_CLASS = `hover:bg-(${ACCENT_HOVER_TOKEN})`
const SIGN_IN_ACCENT = '#1a3a3a'
const SIGN_IN_ACCENT_HOVER = '#152e2e'
const LIGHT_THEME_CLASS = 'light'
const PRIMARY_TEXT_CLASS = 'text-(--color-text-primary)'
const EMAIL = 'driver@example.invalid'
const STRONG_PASSWORD = 'Correct-horse-42'
const RESET_TOKEN = 'reset-token'
const LOGIN_PATH = '/login'
const FORGOT_PASSWORD_PATH = '/forgot-password'
const RESET_PASSWORD_PATH = '/reset-password'
const RESET_PASSWORD_LINK = `${RESET_PASSWORD_PATH}?token=${RESET_TOKEN}`
const STYLESHEET_PATH = resolve(import.meta.dirname, '../index.css')

const text = translations.en.auth
const SIGN_IN_BUTTON = text.login.toUpperCase()

const renderAt = (path, page) => render(<MemoryRouter initialEntries={[path]}>{page}</MemoryRouter>)

const declares = (token, value) => new RegExp(`${token}:\\s*${value};`)

// The colour has to come from the tokens, never from inline styles that script swaps on hover.
const expectTokenAccent = (element, { hover }) => {
  expect(element.getAttribute('style')).toBeNull()
  expect(element.classList).toContain(ACCENT_CLASS)
  expect(element.classList.contains(ACCENT_HOVER_CLASS), element.className).toBe(hover)
  fireEvent.mouseOver(element)
  expect(element.getAttribute('style')).toBeNull()
}

afterEach(cleanup)
beforeEach(() => {
  auth.login.mockReset()
  auth.loginWithPasskey.mockReset()
  authApi.requestPasswordReset.mockReset()
  authApi.verifyPasswordReset.mockReset()
})

describe('auth page actions use the sign-in accent tokens', () => {
  it('styles the sign-in button with the tokens', () => {
    renderAt(LOGIN_PATH, <Login />)

    expectTokenAccent(screen.getByRole('button', { name: SIGN_IN_BUTTON }), { hover: true })
  })

  it('styles the two-factor verify button with the tokens', async () => {
    auth.login.mockResolvedValue({ requires2FA: true })
    renderAt(LOGIN_PATH, <Login />)
    fireEvent.change(screen.getByPlaceholderText(text.username), { target: { value: EMAIL } })
    fireEvent.change(screen.getByPlaceholderText(text.password), { target: { value: STRONG_PASSWORD } })
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: SIGN_IN_BUTTON })) })

    expectTokenAccent(await screen.findByRole('button', { name: text.verify }), { hover: true })
  })

  it('styles the send-reset-link button with the tokens', () => {
    renderAt(FORGOT_PASSWORD_PATH, <ForgotPassword />)

    expectTokenAccent(screen.getByRole('button', { name: text.sendResetLink }), { hover: true })
  })

  it('styles the reset-password button with the tokens', () => {
    renderAt(RESET_PASSWORD_LINK, <ResetPassword />)

    expectTokenAccent(screen.getByRole('button', { name: text.resetPassword }), { hover: true })
  })

  it('styles the request-new-link action with the accent and no hover, as before', async () => {
    renderAt(RESET_PASSWORD_PATH, <ResetPassword />)

    expectTokenAccent(await screen.findByRole('link', { name: text.requestNewLink }), { hover: false })
  })

  it('styles the continue-to-login action with the accent and no hover, as before', async () => {
    authApi.verifyPasswordReset.mockResolvedValue({})
    renderAt(RESET_PASSWORD_LINK, <ResetPassword />)
    fireEvent.change(screen.getByPlaceholderText(text.newPassword), { target: { value: STRONG_PASSWORD } })
    fireEvent.change(screen.getByPlaceholderText(text.confirmPassword), { target: { value: STRONG_PASSWORD } })
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: text.resetPassword })) })

    expectTokenAccent(await screen.findByRole('link', { name: text.continueToLogin }), { hover: false })
  })
})

describe('auth theme tokens', () => {
  it('defines the auth accent tokens with the sign-in page colours', () => {
    const stylesheet = readFileSync(STYLESHEET_PATH, 'utf8')

    expect(stylesheet).toMatch(declares(ACCENT_TOKEN, SIGN_IN_ACCENT))
    expect(stylesheet).toMatch(declares(ACCENT_HOVER_TOKEN, SIGN_IN_ACCENT_HOVER))
  })

  it('keeps the light tokens on the auth layout so token-styled auth pages stay legible in dark mode', () => {
    const { container } = render(<AuthLayout><h1>{text.createAccount}</h1></AuthLayout>)

    expect(container.firstElementChild.classList).toContain(LIGHT_THEME_CLASS)
    expect(container.firstElementChild.classList).toContain(PRIMARY_TEXT_CLASS)
  })
})
