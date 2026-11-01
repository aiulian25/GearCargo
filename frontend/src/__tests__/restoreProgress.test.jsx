import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { translations } from '../i18n/translations'
import RestoreProgress from '../components/settings/RestoreProgress'
import { backupApi } from '../services/api'

vi.mock('../services/api', () => ({ backupApi: { getRecoveryStatus: vi.fn() } }))
vi.mock('../contexts/LanguageContext', () => ({
  useTranslation: () => ({ t: (key, params = {}) => {
    const value = key.split('.').reduce((item, part) => item?.[part], translations.en)
    if (typeof value !== 'string') throw new Error(`Missing translation: ${key}`)
    return value.replace(/\{(\w+)\}/g, (_, name) => params[name] ?? `{${name}}`)
  } }),
}))
afterEach(() => { cleanup(); vi.clearAllMocks() })

it('shows validation and maintenance until a final result is available', async () => {
  backupApi.getRecoveryStatus.mockResolvedValue({ data: { maintenance: true, phase: 'validating_database' } })
  render(<RestoreProgress active />)
  await waitFor(() => expect(screen.getByRole('status').textContent).toContain('Checking the backup'))
  expect(screen.getByRole('status').textContent).toContain('temporarily paused')
})

it('keeps a recovery-required failure visible with its reference', async () => {
  backupApi.getRecoveryStatus.mockResolvedValue({ data: { maintenance: true, phase: 'rolling_back' } })
  render(<RestoreProgress active={false} failure={{ state: 'recovery_required', id: 'restore-reference' }} />)
  await waitFor(() => expect(backupApi.getRecoveryStatus).toHaveBeenCalled())
  expect(screen.getByRole('alert').textContent).toContain('Do not delete the recovery files')
  expect(screen.getByRole('alert').textContent).toContain('restore-reference')
})

it('distinguishes a completed rollback from an unresolved recovery', async () => {
  backupApi.getRecoveryStatus.mockResolvedValue({ data: { maintenance: false, phase: 'idle' } })
  render(<RestoreProgress active={false} failure={{ state: 'rolled_back' }} />)
  await waitFor(() => expect(backupApi.getRecoveryStatus).toHaveBeenCalled())
  expect(screen.getByRole('alert').textContent).toContain('previous database and files were restored')
  expect(screen.queryByText(/needs recovery/)).toBeNull()
})

it('has matching recovery translations in every supported language', () => {
  for (const language of ['ro', 'es']) {
    expect(Object.keys(translations[language].backup.recovery).sort())
      .toEqual(Object.keys(translations.en.backup.recovery).sort())
  }
})

it('shows operator recovery when a journal has no running restore owner', async () => {
  backupApi.getRecoveryStatus.mockResolvedValue({ data: { maintenance: true, phase: 'recovery_required' } })
  render(<RestoreProgress active={false} />)
  await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('administrator'))
  expect(screen.queryByRole('status')).toBeNull()
})
