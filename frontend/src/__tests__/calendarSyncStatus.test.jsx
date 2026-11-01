import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import CalendarSyncStatus from '../components/settings/CalendarSyncStatus'
import { calendarApi } from '../services/api'
import { translations } from '../i18n/translations'

vi.mock('../services/api', () => ({ calendarApi: { getSyncJobStatus: vi.fn(), retrySync: vi.fn() } }))
vi.mock('../contexts/LanguageContext', () => ({ useTranslation: () => ({ t: key => key.split('.').reduce((value, part) => value?.[part], translations.en) || key }) }))
afterEach(() => { cleanup(); vi.restoreAllMocks() })
beforeEach(() => {
  vi.clearAllMocks()
  calendarApi.getSyncJobStatus.mockResolvedValue({ data: { sources: [
    { id: 'offline', name: 'Offline calendar', enabled: true, pending: 0, synced: 2, retrying: 1, failed: 0, paused: 0, next_attempt_at: '2028-01-01T12:00:00' },
    { id: 'working', name: 'Working calendar', enabled: true, pending: 0, synced: 3, retrying: 0, failed: 0, paused: 0 },
  ] } })
  calendarApi.retrySync.mockResolvedValue({ data: { queued: true } })
})

it('shows independent source progress and retries only the selected source', async () => {
  render(<CalendarSyncStatus />)
  expect(await screen.findByText('Offline calendar')).toBeTruthy()
  expect(screen.getByText('Working calendar')).toBeTruthy()
  expect(screen.getByText('Changes applied: 3 · Waiting: 0')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Retry changes' }))
  await waitFor(() => expect(calendarApi.retrySync).toHaveBeenCalledWith('offline'))
  await waitFor(() => expect(calendarApi.getSyncJobStatus).toHaveBeenCalledTimes(2))
})

it('makes disabled/paused work visible without offering a misleading retry', async () => {
  calendarApi.getSyncJobStatus.mockResolvedValue({ data: { sources: [
    { id: 'paused', name: 'Disabled calendar', enabled: false, pending: 0, synced: 0, retrying: 0, failed: 0, paused: 2 },
  ] } })
  render(<CalendarSyncStatus />)
  expect(await screen.findByText('Sync is disabled for this source.')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Retry changes' }).disabled).toBe(true)
})

it('reports a status failure without rendering provider exception text or credentials', async () => {
  calendarApi.getSyncJobStatus.mockRejectedValueOnce(new Error('https://user:secret@private.example.invalid'))
  render(<CalendarSyncStatus />)
  expect((await screen.findByRole('alert')).textContent).toBe(translations.en.calendarQueue.unavailable)
  expect(document.body.textContent).not.toContain('secret')
})

it('has queue status text in all supported languages', () => {
  for (const lang of ['ro', 'es']) expect(Object.keys(translations[lang].calendarQueue).sort()).toEqual(Object.keys(translations.en.calendarQueue).sort())
})
