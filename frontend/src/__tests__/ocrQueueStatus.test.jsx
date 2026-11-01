import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import ScanReceiptBanner from '../components/ui/ScanReceiptBanner'
import AttachmentViewer from '../components/ui/AttachmentViewer'
import { attachmentApi } from '../services/api'
import { translations } from '../i18n/translations'
import { ocrFinished, ocrLabel } from '../utils/ocrStatus'

vi.mock('../services/api', () => ({ attachmentApi: { upload: vi.fn(), getOcr: vi.fn(), retryOcr: vi.fn(),
  getViewUrl: () => '/receipt.pdf', download: vi.fn().mockResolvedValue({ data: new Blob(['pdf']) }) } }))
vi.mock('../contexts/LanguageContext', () => ({ useTranslation: () => ({ t: key => key.split('.').reduce((v, k) => v?.[k], translations.en) || key }) }))
vi.mock('../utils/offlineIdentity', () => ({ getBoundIdentity: () => null }))
afterEach(() => { cleanup(); vi.clearAllMocks(); vi.useRealTimers() })

it('keeps the saved attachment when scanning is full and explains retry', async () => {
  attachmentApi.upload.mockResolvedValue({ data: { attachment: { id: 17, ocr_state: 'failed', ocr_error: 'queue_full' } } })
  const saved = vi.fn()
  render(<ScanReceiptBanner receiptFile={new File(['pdf'], 'receipt.pdf', { type: 'application/pdf' })}
    vehicleId={1} onUploadComplete={saved} />)
  await waitFor(() => expect(saved).toHaveBeenCalledWith(17))
  expect(screen.getByText(/File saved.*Scan queue is full.*Documents/)).toBeTruthy()
  expect(attachmentApi.getOcr).not.toHaveBeenCalled()
})

it.each([false, true])('shows PDF scan failure with a retry (auto-open=%s)', async (initialShowOcr) => {
  attachmentApi.getOcr.mockResolvedValue({ data: { ocr_state: 'failed', ocr_processed: false, ocr_error: 'processing_failed' } })
  render(<AttachmentViewer isOpen initialShowOcr={initialShowOcr} onClose={() => {}} attachments={[
    { id: 18, filename: 'receipt.pdf', file_type: 'application/pdf', is_pdf: true, view_url: '/receipt.pdf' },
  ]} />)
  if (!initialShowOcr) fireEvent.click(screen.getByTitle(translations.en.attachments.ocrText))
  expect(await screen.findByText('Scan failed')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Re-scan' })).toBeTruthy()
})

it('distinguishes queued, running, retrying and terminal states in every language', () => {
  for (const lang of ['en', 'ro', 'es']) {
    const t = key => key.split('.').reduce((value, part) => value?.[part], translations[lang])
    for (const state of ['queued', 'running', 'retry', 'failed', 'unavailable']) {
      expect(ocrLabel({ ocr_state: state }, t)).toBeTruthy()
      expect(ocrFinished({ ocr_state: state })).toBe(['failed', 'unavailable'].includes(state))
    }
    expect(ocrFinished({ ocr_processed: true })).toBe(true)
  }
})
