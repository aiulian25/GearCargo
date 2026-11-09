import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Calendar from '../pages/calendar/Calendar'
import Reminders from '../pages/reminders/Reminders'
import CurrencySelect from '../components/ui/CurrencySelect'
import { DateFormatProvider } from '../contexts/DateFormatContext'
import { translations } from '../i18n/translations'
import { calendarApi, reminderApi, vehicleApi } from '../services/api'

vi.mock('../services/api', () => ({
  calendarApi: { getEntries: vi.fn() },
  vehicleApi: { getAll: vi.fn() },
  reminderApi: { getAll: vi.fn(), getStats: vi.fn() },
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

const NEW_KEYS = ['common.previous', 'auth.showPassword', 'receipt.remove', 'integrations.copyConfig']
const translate = (language, key) => key.split('.').reduce((item, part) => item?.[part], translations[language])

afterEach(cleanup)
beforeEach(() => {
  vi.clearAllMocks()
  calendarApi.getEntries.mockResolvedValue({ data: { entries: [] } })
  vehicleApi.getAll.mockResolvedValue({ data: { vehicles: [{ id: 1, name: 'Test car' }] } })
  reminderApi.getStats.mockResolvedValue({ data: { total: 1, upcoming: 1, overdue: 0, completed: 0 } })
  reminderApi.getAll.mockResolvedValue({ data: { reminders: [{ id: 5, title: 'Oil', due_date: '2099-01-01', vehicle_name: 'Test car' }] } })
})

it.each(['en', 'ro', 'es'])('defines every new accessible-name key in %s', language => {
  for (const key of NEW_KEYS) expect(typeof translate(language, key)).toBe('string')
})

it('names the calendar month navigation and the vehicle filter', async () => {
  render(<DateFormatProvider language="en"><MemoryRouter><Calendar /></MemoryRouter></DateFormatProvider>)
  expect(await screen.findByRole('button', { name: 'Previous' })).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Next' })).toBeTruthy()
  expect(screen.getByRole('combobox', { name: 'Vehicle' })).toBeTruthy()
})

it('names icon-only reminder actions by their localized titles, not by the icon ligatures', async () => {
  render(<MemoryRouter initialEntries={['/reminders']}><Reminders /></MemoryRouter>)
  expect(await screen.findByRole('button', { name: 'Snooze 7 days' })).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Mark complete' })).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'snooze' })).toBeNull()
  expect(screen.queryByRole('button', { name: 'check' })).toBeNull()
})

it('labels the shared currency picker through its own id', () => {
  render(<CurrencySelect register={name => ({ name })} />)
  expect(screen.getByRole('combobox', { name: translations.en.settings.currency }).getAttribute('name')).toBe('currency')
})
