import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { translations } from '../i18n/translations'
import ReportSharePreview from '../components/settings/ReportSharePreview'
import SharedReport from '../pages/SharedReport'
import { reportsApi } from '../services/api'

vi.mock('react-router-dom', () => ({ useParams: () => ({ token: 'public-token' }) }))
vi.mock('../services/api', () => ({ reportsApi: {
  getSharedReport: vi.fn(), sharedPdfUrl: token => `/api/reports/shared/${token}/pdf`,
} }))
vi.mock('../contexts/LanguageContext', () => ({ useTranslation: () => ({
  language: 'en', t: key => {
    const value = key.split('.').reduce((object, part) => object?.[part], translations.en)
    if (typeof value !== 'string') throw new Error(`Missing translation: ${key}`)
    return value
  },
}) }))
afterEach(() => { cleanup(); vi.clearAllMocks() })

const preview = {
  period_label: 'June 2026', start_date: '2026-06-01', end_date: '2026-06-30',
  vehicle_count: 1, vehicles: [{ name: 'Daily', make: 'Ford', model: 'Focus', id: 19288,
    license_plate: 'PRIVATE_PLATE', vin: 'PRIVATE_VIN' }],
  entry_counts: { fuel: 2, total: 2 }, totals: { fuel: 12.34, grand_total: 12.34 },
  currency: 'GBP', converted: true, owner_email: 'PRIVATE_EMAIL', notes: 'PRIVATE_NOTE',
}

it('requires a current preview and explains disclosure and downloaded copies', () => {
  render(<ReportSharePreview />)
  expect(screen.getByText(translations.en.reportShare.previewRequired)).toBeTruthy()
  expect(screen.getByText(translations.en.reportShare.excluded)).toBeTruthy()
  expect(screen.getByText(translations.en.reportShare.downloadWarning)).toBeTruthy()
})

it('shows the approved fields and totals without private preview extras', () => {
  const { container } = render(<ReportSharePreview preview={preview} />)
  expect(screen.getByText(/Daily.*Ford Focus/)).toBeTruthy()
  expect(screen.getAllByText('12.34 GBP').length).toBe(2)
  expect(screen.getByText(/June 2026/)).toBeTruthy()
  expect(container.textContent).not.toContain('PRIVATE_')
  expect(container.textContent).not.toContain('19288')
})

it('clears the displayed data when the selected report loses its preview', () => {
  const view = render(<ReportSharePreview preview={preview} />)
  view.rerender(<ReportSharePreview />)
  expect(screen.queryByText(/Daily.*Ford/)).toBeNull()
  expect(screen.getByText(translations.en.reportShare.previewRequired)).toBeTruthy()
})

it.each(['en', 'ro', 'es'])('has complete sharing-disclosure messages in %s', language => {
  for (const key of ['previewTitle','disclosure','excluded','freeText','downloadWarning','previewRequired','rateWarning']) {
    expect(typeof translations[language].reportShare[key]).toBe('string')
    expect(translations[language].reportShare[key].length).toBeGreaterThan(10)
  }
})

it('aligns the public page and aggregate PDF action with the disclosure', async () => {
  reportsApi.getSharedReport.mockResolvedValue({ data: { ...preview, app_name: 'GearCargo',
    totals: { fuel: 12.34, insurance: 6.66, grand_total: 19 }, entry_counts: { fuel: 2, insurance: 1, total: 3 },
  } })
  const { container } = render(<SharedReport />)
  await waitFor(() => expect(screen.getByRole('link', { name: 'Download aggregate PDF' })).toBeTruthy())
  expect(screen.getByRole('link').getAttribute('href')).toBe('/api/reports/shared/public-token/pdf')
  expect(screen.getByText(translations.en.reportShare.downloadWarning)).toBeTruthy()
  expect(screen.getByText(translations.en.financial.insurance)).toBeTruthy()
  expect(container.textContent).not.toContain('PRIVATE_')
})

it.each(['expired','revoked','invalid'])('offers no PDF download for an %s link', async status => {
  reportsApi.getSharedReport.mockRejectedValue({ response: { status: 410, data: { status } } })
  render(<SharedReport />)
  await waitFor(() => expect(screen.getByText(translations.en.sharedReport.unavailableTitle)).toBeTruthy())
  expect(screen.queryByRole('link')).toBeNull()
})
