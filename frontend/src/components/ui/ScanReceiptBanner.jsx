import { useState, useEffect, useRef } from 'react'
import { receiptUploadKey } from '../../utils/receiptProtocol'
import { getBoundIdentity } from '../../utils/offlineIdentity'
import { ocrFailed, ocrLabel } from '../../utils/ocrStatus'
import { attachmentApi } from '../../services/api'
import { useTranslation } from '../../contexts/LanguageContext'

/**
 * Shown below the ReceiptUpload widget once a receipt is selected. It uploads the file at
 * once, so text recognition can start, and says what happens to it until that is finished.
 *
 * receiptFile        File | null   – the image or PDF selected in ReceiptUpload
 * vehicleId          number        – the vehicle the receipt belongs to
 * onUploadComplete   (id) => void  – called once the file is saved; the parent links it
 *                                    instead of uploading it again on submit
 */

const Icons = {
  spinner: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="animate-spin">
      <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
    </svg>
  ),
  warning: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
      <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
    </svg>
  ),
}

const MAX_POLL_ATTEMPTS = 12
const POLL_INTERVAL_MS = 3000
const SCANNABLE_PDF_TYPE = 'application/pdf'
const QUIET_PHASES = ['idle', 'done']
const FAILED_PHASES = ['error', 'scan_failed']

const isScannable = file => Boolean(file) && (file.type.startsWith('image/') || file.type === SCANNABLE_PDF_TYPE)

export default function ScanReceiptBanner({ receiptFile, vehicleId, onUploadComplete }) {
  const { t } = useTranslation()
  // idle → uploading → scanning → done | scan_failed; error when the upload or a status check fails
  const [phase, setPhase] = useState('idle')
  const [scanStatus, setScanStatus] = useState(null)
  const pollTimerRef = useRef(null)
  const pollAttemptsRef = useRef(0)
  const prevFileRef = useRef(null)

  useEffect(() => () => { if (pollTimerRef.current) clearTimeout(pollTimerRef.current) }, [])

  useEffect(() => {
    if (prevFileRef.current === receiptFile) return
    prevFileRef.current = receiptFile
    if (pollTimerRef.current) clearTimeout(pollTimerRef.current)
    pollAttemptsRef.current = 0
    setScanStatus(null)
    if (!isScannable(receiptFile)) {
      setPhase('idle')
      return
    }

    setPhase('uploading')
    let active = true
    attachmentApi.upload(receiptFile, { vehicleId, operationKey: receiptUploadKey(receiptFile), identity: getBoundIdentity() })
      .then(res => {
        if (!active || prevFileRef.current !== receiptFile) return
        const attachment = res.data?.attachment
        if (!attachment?.id) { setPhase('error'); return }
        if (onUploadComplete) onUploadComplete(attachment.id)
        setScanStatus(attachment)
        if (ocrFailed(attachment)) { setPhase('scan_failed'); return }
        setPhase('scanning')
        pollOcr(attachment.id)
      })
      .catch(() => { if (active) setPhase('error') })
    return () => { active = false }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [receiptFile])

  function pollOcr(id) {
    // Recognition goes on in the background; after this long there is nothing left to tell.
    if (pollAttemptsRef.current >= MAX_POLL_ATTEMPTS) {
      setPhase('done')
      return
    }
    pollAttemptsRef.current += 1
    pollTimerRef.current = setTimeout(async () => {
      try {
        const { data } = await attachmentApi.getOcr(id)
        setScanStatus(data)
        if (ocrFailed(data)) { setPhase('scan_failed'); return }
        if (data.ocr_processed) { setPhase('done'); return }
        pollOcr(id)
      } catch {
        setPhase('error')
      }
    }, POLL_INTERVAL_MS)
  }

  if (QUIET_PHASES.includes(phase)) return null

  const failed = FAILED_PHASES.includes(phase)
  const tone = failed ? 'border-red-500/30 bg-red-500/5' : 'border-(--color-border) bg-(--color-bg-tertiary)'
  const iconTone = failed ? 'text-red-400' : 'text-(--color-text-secondary)'

  return (
    <div className={`mt-3 flex items-center gap-2 rounded-xl border px-3 py-2.5 ${tone}`}>
      <span className={`shrink-0 ${iconTone}`}>{failed ? Icons.warning : Icons.spinner}</span>
      <span className="flex-1 text-sm text-(--color-text-primary)">
        {phase === 'uploading' && t('receipt.scanBannerUploading')}
        {phase === 'scanning' && ocrLabel(scanStatus, t)}
        {phase === 'scan_failed' && `${t('ocrQueue.saved')} ${ocrLabel(scanStatus, t)} ${t('ocrQueue.retryDocuments')}`}
        {phase === 'error' && t('receipt.scanBannerError')}
      </span>
    </div>
  )
}
