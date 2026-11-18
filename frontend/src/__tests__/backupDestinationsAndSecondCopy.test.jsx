import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { supportedLanguages, translations } from '../i18n/translations'
import { BACKUP_MIRROR_GUIDE_URL } from '../config/brand'
import BackupSettings from '../components/settings/BackupSettings'

const api = vi.hoisted(() => ({ getStatus: vi.fn(), getRecoveryStatus: vi.fn(), updateSchedule: vi.fn() }))
const toast = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }))
vi.mock('../services/api', () => ({ backupApi: api }))
vi.mock('react-hot-toast', () => ({ default: toast }))
vi.mock('../contexts/LanguageContext', () => ({ useTranslation: () => ({
  t: (key, params = {}) => {
    const text = key.split('.').reduce((value, part) => value?.[part], translations.en) || key
    return Object.entries(params).reduce((result, [name, value]) => result.replaceAll(`{${name}}`, value), text)
  },
}) }))

const texts = translations.en.backup
const SAVED_NAME = 'Nextcloud at home'
const savedDestination = {
  id: 'destination_1', name: SAVED_NAME, provider: 'webdav', enabled: true,
  external_url: 'https://nextcloud.example.com', external_path: '/GearCargo', has_external_api_key: true,
}
const scheduleWithOneDestination = {
  external_enabled: true, external_url: savedDestination.external_url, external_path: '/GearCargo',
  has_external_api_key: true, external_destinations: [savedDestination],
}

function showBackupScreen({ schedule = null, mirror = null, isAdmin = false } = {}) {
  api.getStatus.mockResolvedValue({ data: { schedule, available_backups: [], mirror } })
  render(<MemoryRouter><BackupSettings isAdmin={isAdmin} /></MemoryRouter>)
  return screen.findByRole('button', { name: texts.saveSettings })
}

async function savedPayload() {
  fireEvent.click(screen.getByRole('button', { name: texts.saveSettings }))
  await waitFor(() => expect(api.updateSchedule).toHaveBeenCalled())
  return api.updateSchedule.mock.calls[0][0]
}

beforeEach(() => {
  vi.clearAllMocks()
  api.getRecoveryStatus.mockResolvedValue({ data: { maintenance: false } })
  api.updateSchedule.mockResolvedValue({ data: {} })
})
afterEach(cleanup)

describe('removing an external destination', () => {
  it('removes the only destination and saves external backup as off', async () => {
    await showBackupScreen({ schedule: scheduleWithOneDestination })

    fireEvent.click(screen.getByRole('button', { name: texts.removeDestination }))

    expect(screen.queryByDisplayValue(SAVED_NAME)).toBeNull()
    const payload = await savedPayload()
    expect(payload.external_destinations).toEqual([])
    expect(payload.external_enabled).toBe(false)
    expect(toast.error).not.toHaveBeenCalled()
  })

  it('removes the first destination while a second one is still empty', async () => {
    await showBackupScreen({ schedule: scheduleWithOneDestination })
    fireEvent.click(screen.getByRole('button', { name: `+ ${texts.addDestination}` }))

    fireEvent.click(screen.getAllByRole('button', { name: texts.removeDestination })[0])

    const payload = await savedPayload()
    expect(payload.external_destinations).toEqual([])
    expect(payload.external_enabled).toBe(false)
    expect(toast.error).not.toHaveBeenCalled()
  })

  it('keeps the destination that was not removed', async () => {
    await showBackupScreen({ schedule: scheduleWithOneDestination })
    fireEvent.click(screen.getByRole('button', { name: `+ ${texts.addDestination}` }))

    fireEvent.click(screen.getAllByRole('button', { name: texts.removeDestination })[1])

    const payload = await savedPayload()
    expect(payload.external_destinations.map(destination => destination.id)).toEqual([savedDestination.id])
    expect(payload.external_enabled).toBe(true)
  })
})

describe('setting up the second copy', () => {
  it('shows an administrator how to set it up while none is configured', async () => {
    await showBackupScreen({ isAdmin: true })

    const card = screen.getByText(texts.mirror.setup.title).closest('details')
    expect(card.textContent).toContain(texts.mirror.setup.state)
    expect(card.textContent).toContain('.gearcargo-backup-mirror')
    expect(card.textContent).toContain('BACKUP_MIRROR_FOLDER=/mnt/backup-mirror')
    expect(card.textContent).toContain('docker compose up -d')
    expect(screen.getByRole('link', { name: texts.mirror.setup.guide }).getAttribute('href')).toBe(BACKUP_MIRROR_GUIDE_URL)
  })

  it('shows nothing about it to someone who cannot set it up', async () => {
    await showBackupScreen({ isAdmin: false })

    expect(screen.queryByText(texts.mirror.setup.title)).toBeNull()
  })

  it('gives way to the state once a second copy is configured', async () => {
    await showBackupScreen({ isAdmin: true, mirror: { state: 'waiting', last_copied_at: null } })

    expect(screen.queryByText(texts.mirror.setup.title)).toBeNull()
    expect(screen.getByRole('status').textContent).toContain(texts.mirror.waiting)
  })

  it.each(supportedLanguages)('has every step in %s, with the names it fills in', (language) => {
    const setup = translations[language].backup.mirror.setup
    const placeholders = { storage: '{marker}', mount: '{id}', compose: '{file}', start: '{command}' }

    expect(Object.keys(setup).sort()).toEqual(Object.keys(translations.en.backup.mirror.setup).sort())
    for (const [step, placeholder] of Object.entries(placeholders)) expect(setup[step]).toContain(placeholder)
  })
})
