import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { translations } from '../i18n/translations'

const api = { get: vi.fn(), post: vi.fn(), delete: vi.fn() }
const startRegistration = vi.fn()

vi.mock('../services/api', () => ({ default: api }))
vi.mock('@simplewebauthn/browser', () => ({
  startRegistration: (...args) => startRegistration(...args),
  browserSupportsWebAuthn: () => true,
}))
vi.mock('../contexts/LanguageContext', () => ({
  useTranslation: () => ({
    t: (key, params = {}) => {
      const value = key.split('.').reduce((item, part) => item?.[part], translations.en)
      if (typeof value !== 'string') throw new Error(`Missing translation: ${key}`)
      return value.replace(/\{(\w+)\}/g, (_, name) => params[name] ?? `{${name}}`)
    },
  }),
}))
vi.mock('../hooks/useDateFormat', () => ({
  useDateFormat: () => ({ formatDate: (value) => String(value).slice(0, 10) }),
}))
const confirmResult = { value: true }
vi.mock('../components/ui/ConfirmDialog', () => ({
  useConfirm: () => () => Promise.resolve(confirmResult.value),
}))

const { default: PasskeySettings } = await import('../components/settings/PasskeySettings')

afterEach(cleanup)
beforeEach(() => {
  api.get.mockReset()
  api.post.mockReset()
  api.delete.mockReset()
  startRegistration.mockReset()
  confirmResult.value = true
})

const clickAndSettle = async (element) => {
  await act(async () => { fireEvent.click(element) })
}

const PASSKEY = {
  id: 7, name: 'Phone', backed_up: true,
  created_at: '2026-10-01T00:00:00Z', last_used_at: '2026-10-20T00:00:00Z',
  other_relying_party: null,
}

describe('passkey localization', () => {
  it('offers every passkey string in all supported languages', () => {
    const languages = ['en', 'ro', 'es']
    const keysOf = (language) => Object.keys(translations[language].passkeys ?? {}).sort()
    const expected = keysOf('en')

    expect(expected.length).toBeGreaterThan(0)
    for (const language of languages) {
      expect(keysOf(language), `${language} passkey keys`).toEqual(expected)
      for (const key of expected) {
        expect(typeof translations[language].passkeys[key], `${language}.${key}`).toBe('string')
        expect(translations[language].passkeys[key].trim()).not.toBe('')
      }
    }
  })

  it('keeps the refusal keys the server sends in step with the client', () => {
    // The backend answers with these exact keys; an unknown one would surface raw.
    const sentByServer = [
      'errorUnavailable', 'errorLimitReached',
      'errorNotAdded', 'errorRefused', 'errorNotFound',
    ]
    for (const key of sentByServer) {
      expect(Object.keys(translations.en.passkeys)).toContain(key)
    }
  })
})

describe('passkey settings panel', () => {
  it('explains why an address-only deployment cannot offer passkeys', async () => {
    api.get.mockResolvedValue({ data: { available: false, passkeys: [] } })
    render(<PasskeySettings />)

    await waitFor(() => expect(
      screen.getByText(translations.en.passkeys.unavailableHere)).toBeTruthy())
    expect(screen.getByRole('button', { name: translations.en.passkeys.add }).disabled).toBe(true)
  })

  it('lists a passkey and says when it was last used', async () => {
    api.get.mockResolvedValue({ data: { available: true, passkeys: [PASSKEY] } })
    render(<PasskeySettings />)

    await waitFor(() => expect(screen.getByText('Phone')).toBeTruthy())
    expect(screen.getByText(/Last used 2026-10-20/)).toBeTruthy()
  })

  it('marks a passkey made for another hostname as unusable here', async () => {
    api.get.mockResolvedValue({
      data: { available: true, passkeys: [{ ...PASSKEY, other_relying_party: 'old.example.net' }] },
    })
    render(<PasskeySettings />)

    await waitFor(() => expect(screen.getByText(/old\.example\.net/)).toBeTruthy())
  })

  it('asks the server for options, then hands the answer back to be stored', async () => {
    api.get.mockResolvedValue({ data: { available: true, passkeys: [] } })
    api.post
      .mockResolvedValueOnce({ data: { challenge: 'abc', rp: { id: 'cars.example.org' } } })
      .mockResolvedValueOnce({ data: { passkey: PASSKEY } })
    startRegistration.mockResolvedValue({ id: 'cred-1', response: {} })

    render(<PasskeySettings />)
    await waitFor(() => expect(screen.getByText(translations.en.passkeys.empty)).toBeTruthy())
    await clickAndSettle(screen.getByRole('button', { name: translations.en.passkeys.add }))

    await waitFor(() => expect(screen.getByText('Phone')).toBeTruthy())
    expect(api.post.mock.calls[0][0]).toBe('/auth/passkeys/options')
    // The browser's answer is forwarded verbatim; the server re-verifies it.
    expect(startRegistration).toHaveBeenCalledWith({
      optionsJSON: { challenge: 'abc', rp: { id: 'cars.example.org' } },
    })
    expect(api.post.mock.calls[1]).toEqual(['/auth/passkeys', { credential: { id: 'cred-1', response: {} } }])
  })

  it('treats a dismissed device prompt as a choice, not an error', async () => {
    api.get.mockResolvedValue({ data: { available: true, passkeys: [] } })
    api.post.mockResolvedValueOnce({ data: { challenge: 'abc' } })
    const dismissed = new Error('cancelled')
    dismissed.name = 'NotAllowedError'
    startRegistration.mockRejectedValue(dismissed)

    render(<PasskeySettings />)
    await waitFor(() => expect(screen.getByText(translations.en.passkeys.empty)).toBeTruthy())
    await clickAndSettle(screen.getByRole('button', { name: translations.en.passkeys.add }))

    await waitFor(() => expect(
      screen.getByRole('button', { name: translations.en.passkeys.add })).toBeTruthy())
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('shows the server refusal in the reader language', async () => {
    api.get.mockResolvedValue({ data: { available: true, passkeys: [] } })
    api.post.mockRejectedValue({
      response: { data: { message_key: 'passkeys.errorLimitReached' } },
    })

    render(<PasskeySettings />)
    await waitFor(() => expect(screen.getByText(translations.en.passkeys.empty)).toBeTruthy())
    await clickAndSettle(screen.getByRole('button', { name: translations.en.passkeys.add }))

    await waitFor(() => expect(
      screen.getByRole('alert').textContent).toBe(translations.en.passkeys.errorLimitReached))
  })

  it('keeps a passkey when the removal is not confirmed', async () => {
    api.get.mockResolvedValue({ data: { available: true, passkeys: [PASSKEY] } })
    confirmResult.value = false

    render(<PasskeySettings />)
    await waitFor(() => expect(screen.getByText('Phone')).toBeTruthy())
    await clickAndSettle(screen.getByRole('button', { name: translations.en.passkeys.remove }))

    expect(api.delete).not.toHaveBeenCalled()
    expect(screen.getByText('Phone')).toBeTruthy()
  })

  it('removes a passkey once the removal is confirmed', async () => {
    api.get.mockResolvedValue({ data: { available: true, passkeys: [PASSKEY] } })
    api.delete.mockResolvedValue({ data: {} })

    render(<PasskeySettings />)
    await waitFor(() => expect(screen.getByText('Phone')).toBeTruthy())
    await clickAndSettle(screen.getByRole('button', { name: translations.en.passkeys.remove }))

    await waitFor(() => expect(screen.queryByText('Phone')).toBeNull())
    expect(api.delete).toHaveBeenCalledWith('/auth/passkeys/7')
  })
})
