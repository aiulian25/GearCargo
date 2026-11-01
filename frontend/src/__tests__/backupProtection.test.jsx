import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { translations } from '../i18n/translations'
import BackupSettings from '../components/settings/BackupSettings'

const api = vi.hoisted(() => ({ getStatus: vi.fn(), getRecoveryStatus: vi.fn(), export: vi.fn(),
  runNow: vi.fn(), updateSchedule: vi.fn(), import: vi.fn(), uploadBackup: vi.fn() }))
const toast = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }))
vi.mock('../services/api', () => ({ backupApi: api }))
vi.mock('react-hot-toast', () => ({ default: toast }))
vi.mock('../contexts/LanguageContext', () => ({ useTranslation: () => ({
  t: key => key.split('.').reduce((value, part) => value?.[part], translations.en) || key,
}) }))
const p = translations.en.backup.protection
const key = 'a separate backup passphrase'
const fieldset = title => screen.getByRole('group', { name: title })
function setKey(title, value = key, confirmation = value) {
  const group = within(fieldset(title))
  if (!group.getByRole('checkbox').checked) fireEvent.click(group.getByRole('checkbox'))
  fireEvent.change(group.getByLabelText(p.passphrase), { target: { value } })
  fireEvent.change(group.getByLabelText(p.confirm), { target: { value: confirmation } })
}
beforeEach(() => {
  vi.clearAllMocks()
  api.getStatus.mockResolvedValue({ data: { schedule: null, available_backups: [] } })
  api.getRecoveryStatus.mockResolvedValue({ data: { maintenance: false } })
  api.runNow.mockResolvedValue({ data: {} })
  api.updateSchedule.mockResolvedValue({ data: {} })
  vi.stubGlobal('URL', { createObjectURL: vi.fn(() => 'blob:backup'), revokeObjectURL: vi.fn() })
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })
it('shows plaintext warning and keeps manual encryption opt-in', async () => {
  render(<MemoryRouter><BackupSettings /></MemoryRouter>)
  await screen.findByRole('group', { name: p.manualTitle })
  expect(within(fieldset(p.manualTitle)).getByText(p.plainWarning)).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: translations.en.backup.backupNow }))
  await waitFor(() => expect(api.runNow).toHaveBeenCalledWith(true, false, { encrypt: false }))
  expect(screen.getByText(p.csv, { exact: false })).toBeTruthy()
})
it('blocks mismatched keys, encrypts the actual manual request and clears inputs', async () => {
  render(<MemoryRouter><BackupSettings /></MemoryRouter>)
  await screen.findByRole('group', { name: p.manualTitle })
  setKey(p.manualTitle, key, 'a different backup passphrase')
  fireEvent.click(screen.getByRole('button', { name: translations.en.backup.backupNow }))
  await waitFor(() => expect(toast.error).toHaveBeenCalledWith(p.keyMismatch))
  expect(api.runNow).not.toHaveBeenCalled()
  setKey(p.manualTitle)
  fireEvent.click(screen.getByRole('button', { name: translations.en.backup.backupNow }))
  await waitFor(() => expect(api.runNow).toHaveBeenCalledWith(true, false, { encrypt: true, passphrase: key }))
  await waitFor(() => expect(within(fieldset(p.manualTitle)).getByLabelText(p.passphrase).value).toBe(''))
  expect(localStorage.getItem('backupPassphrase')).toBeNull()
})
it('retains the saved schedule key without returning or resubmitting it', async () => {
  api.getStatus.mockResolvedValue({ data: { schedule: { encryption_enabled: true, has_backup_passphrase: true }, available_backups: [] } })
  render(<MemoryRouter><BackupSettings /></MemoryRouter>)
  await screen.findByText(p.savedKey)
  fireEvent.click(screen.getByRole('button', { name: translations.en.backup.saveSettings }))
  await waitFor(() => expect(api.updateSchedule).toHaveBeenCalled())
  const payload = api.updateSchedule.mock.calls[0][0]
  expect(payload.encryption_enabled).toBe(true)
  expect(payload.passphrase).toBeUndefined()
  expect(payload.external_destinations).toEqual([])
  expect(within(fieldset(p.manualTitle)).getByRole('checkbox').checked).toBe(false)
})
it('saves a confirmed schedule key and clears it after success', async () => {
  render(<MemoryRouter><BackupSettings /></MemoryRouter>)
  await screen.findByRole('group', { name: p.scheduleTitle })
  setKey(p.scheduleTitle)
  fireEvent.click(screen.getByRole('button', { name: translations.en.backup.saveSettings }))
  await waitFor(() => expect(api.updateSchedule).toHaveBeenCalledWith(expect.objectContaining({
    encryption_enabled: true, passphrase: key,
  })))
  await waitFor(() => expect(within(fieldset(p.scheduleTitle)).getByLabelText(p.passphrase).value).toBe(''))
})
it('passes the restore key to preview and apply and clears it after success', async () => {
  api.import.mockImplementation(form => Promise.resolve({ data: form.get('preview') === 'true'
    ? { preview: { preview_token: 'verified', new_records: 1, conflicts: 0, records: [] } }
    : { imported: { vehicles: 1 } } }))
  render(<MemoryRouter><BackupSettings /></MemoryRouter>)
  await screen.findByRole('group', { name: p.manualTitle })
  fireEvent.change(screen.getByLabelText(p.restoreKey, { exact: false }), { target: { value: key } })
  const input = document.querySelector('input[accept=".json,.zip,.gcb"]')
  fireEvent.change(input, { target: { files: [new File(['ciphertext'], 'saved.zip.gcb')] } })
  await waitFor(() => expect(api.import).toHaveBeenCalledTimes(1))
  expect(api.import.mock.calls[0][0].get('passphrase')).toBe(key)
  fireEvent.click(screen.getByRole('button', { name: translations.en.backup.importReview.apply }))
  await waitFor(() => expect(api.import).toHaveBeenCalledTimes(2))
  expect(api.import.mock.calls[1][0].get('passphrase')).toBe(key)
  await waitFor(() => expect(screen.getByLabelText(p.restoreKey, { exact: false }).value).toBe(''))
})
it('localizes all protection and recovery strings', () => {
  for (const locale of ['ro', 'es']) {
    expect(Object.keys(translations[locale].backup.protection).sort()).toEqual(Object.keys(p).sort())
    for (const value of Object.values(translations[locale].backup.protection)) expect(value).toBeTruthy()
  }
})

it('does not log a failed request containing the backup passphrase', async () => {
  const logger = vi.spyOn(console, 'error').mockImplementation(() => {})
  api.runNow.mockRejectedValueOnce({ message: 'Request failed', config: { data: { passphrase: key } },
    response: { data: { error: 'Backup failed' } } })
  try {
    render(<MemoryRouter><BackupSettings /></MemoryRouter>)
    await screen.findByRole('group', { name: p.manualTitle })
    setKey(p.manualTitle)
    fireEvent.click(screen.getByRole('button', { name: translations.en.backup.backupNow }))
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Backup failed'))
    expect(logger).not.toHaveBeenCalled()
  } finally { logger.mockRestore() }
})
