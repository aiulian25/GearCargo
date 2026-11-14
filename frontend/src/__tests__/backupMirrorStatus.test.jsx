import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import BackupMirrorStatus from '../components/settings/BackupMirrorStatus'
import { supportedLanguages, translations } from '../i18n/translations'

const { locale } = vi.hoisted(() => ({ locale: { language: 'en' } }))

vi.mock('../contexts/LanguageContext', () => ({
  useTranslation: () => ({
    t: (key, params = {}) => {
      const text = key.split('.').reduce((node, part) => node?.[part], translations[locale.language])
      if (typeof text !== 'string') throw new Error(`Missing translation: ${key}`)
      return Object.entries(params).reduce((result, [name, value]) => result.replaceAll(`{${name}}`, value), text)
    },
  }),
}))
vi.mock('../hooks/useDateFormat', () => ({ useDateFormat: () => ({ formatDateTime: value => `at ${value}` }) }))

const COPIED_AT = '2026-11-14T03:15:00Z'

afterEach(() => { cleanup(); locale.language = 'en' })

describe('backup mirror status', () => {
  it.each([
    [{ state: 'current', last_copied_at: COPIED_AT }, `Second copy: Up to date. Last copied at ${COPIED_AT}.`],
    [{ state: 'current', last_copied_at: null }, 'Second copy: Waiting for the first backup to copy.'],
    [{ state: 'waiting', last_copied_at: null }, 'Second copy: Waiting for the first backup to copy.'],
    [{ state: 'unavailable', last_copied_at: COPIED_AT }, `Second copy: ${translations.en.backup.mirror.unavailable}`],
    [{ state: 'failed', last_copied_at: COPIED_AT }, `Second copy: ${translations.en.backup.mirror.failed}`],
  ])('says what %j means for the person', (mirror, expected) => {
    render(<BackupMirrorStatus mirror={mirror} />)

    expect(screen.getByRole('status').textContent).toBe(expected)
  })

  it.each(supportedLanguages)('has every state in %s', (language) => {
    locale.language = language
    for (const state of ['current', 'waiting', 'unavailable', 'failed']) {
      const { unmount } = render(<BackupMirrorStatus mirror={{ state, last_copied_at: COPIED_AT }} />)
      expect(screen.getByRole('status').textContent).toContain(translations[language].backup.mirror.title)
      unmount()
    }
  })

  it('keeps the date placeholder in every language', () => {
    for (const language of supportedLanguages) {
      expect(translations[language].backup.mirror.current).toContain('{date}')
    }
  })

  it('does not break on a state it does not know', () => {
    render(<BackupMirrorStatus mirror={{ state: 'something-new', last_copied_at: null }} />)

    expect(screen.getByRole('status').textContent).toBe('Second copy: Waiting for the first backup to copy.')
  })
})
