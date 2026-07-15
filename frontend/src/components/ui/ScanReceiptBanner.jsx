/**
 * ScanReceiptBanner
 *
 * Shown below the ReceiptUpload widget when the user selects an image.
 * Uploads the image immediately so OCR can run in the background, then
 * polls until scanning is done.  When text is found it shows a banner
 * with an "Extract data" action that calls the Ollama parse endpoint and
 * lets the user pre-fill the parent form with one tap.
 *
 * Props
 * ─────
 * receiptFile        File | null   – the image File selected in ReceiptUpload
 * vehicleId          number        – needed for the upload call
 * onPrefill          (data) => void  – called with parsed OCR fields
 * onUploadComplete   (id) => void    – called once the file is saved; the
 *                                      parent can skip re-uploading on submit
 */

import { useState, useEffect, useRef } from 'react'
import { attachmentApi } from '../../services/api'
import { useTranslation } from '../../contexts/LanguageContext'

// ─── Icons ──────────────────────────────────────────────────────────────────

const Icons = {
  scan: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="4 7 4 4 7 4"/><polyline points="4 17 4 20 7 20"/>
      <polyline points="17 4 20 4 20 7"/><polyline points="17 20 20 20 20 17"/>
      <line x1="4" y1="12" x2="20" y2="12"/>
    </svg>
  ),
  spinner: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="animate-spin">
      <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
    </svg>
  ),
  wand: (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M15 4V2"/><path d="M15 16v-2"/><path d="M8 9h2"/><path d="M20 9h2"/>
      <path d="M17.8 11.8 19 13"/><path d="M15 9h.01"/><path d="M17.8 6.2 19 5"/>
      <path d="m3 21 9-9"/><path d="M12.2 6.2 11 5"/>
    </svg>
  ),
  prefill: (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
    </svg>
  ),
  check: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  ),
  chevronDown: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="6 9 12 15 18 9"/>
    </svg>
  ),
  chevronUp: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="18 15 12 9 6 15"/>
    </svg>
  ),
  warning: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
      <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
    </svg>
  ),
}

// ─── Constants ───────────────────────────────────────────────────────────────

const MAX_POLL_ATTEMPTS = 12   // 12 × 3 s = 36 s max wait
const POLL_INTERVAL_MS = 3000

// ─── Component ───────────────────────────────────────────────────────────────

export default function ScanReceiptBanner({ receiptFile, vehicleId, onPrefill, onUploadComplete }) {
  const { t } = useTranslation()

  // phase drives the entire UI state machine
  // idle → uploading → scanning → ready | no_text | scanning_slow
  // ready → extracting → extracted | ready (on error)
  const [phase, setPhase] = useState('idle')

  const [attachmentId, setAttachmentId] = useState(null)
  const [parsedData, setParsedData] = useState(null)
  const [parseError, setParseError] = useState('')
  const [expanded, setExpanded] = useState(false)
  const [prefilled, setPrefilled] = useState(false)

  const pollTimerRef = useRef(null)
  const pollAttemptsRef = useRef(0)
  const prevFileRef = useRef(null)

  // Cleanup on unmount
  useEffect(() => () => { if (pollTimerRef.current) clearTimeout(pollTimerRef.current) }, [])

  // React to receiptFile changes
  useEffect(() => {
    // Images run tesseract OCR server-side; PDFs get their embedded text
    // layer extracted (F32) — both land in the same ocr_text field, so the
    // upload → poll → extract flow is identical.
    const isScannable = receiptFile && (
      receiptFile.type.startsWith('image/') || receiptFile.type === 'application/pdf'
    )

    if (!isScannable) {
      if (prevFileRef.current !== receiptFile) {
        prevFileRef.current = receiptFile
        _resetState()
      }
      return
    }

    // Same file object — already handled
    if (prevFileRef.current === receiptFile) return
    prevFileRef.current = receiptFile

    // New image selected — start fresh
    if (pollTimerRef.current) clearTimeout(pollTimerRef.current)
    pollAttemptsRef.current = 0
    _resetState()

    setPhase('uploading')

    attachmentApi.upload(receiptFile, { vehicleId })
      .then(res => {
        const id = res.data?.attachment?.id
        if (!id) { setPhase('error'); return }
        setAttachmentId(id)
        if (onUploadComplete) onUploadComplete(id)
        setPhase('scanning')
        _pollOcr(id)
      })
      .catch(() => setPhase('error'))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [receiptFile])

  function _resetState() {
    setPhase('idle')
    setAttachmentId(null)
    setParsedData(null)
    setParseError('')
    setExpanded(false)
    setPrefilled(false)
  }

  function _pollOcr(id) {
    if (pollAttemptsRef.current >= MAX_POLL_ATTEMPTS) {
      setPhase('scanning_slow')
      return
    }
    pollAttemptsRef.current += 1
    pollTimerRef.current = setTimeout(async () => {
      try {
        const res = await attachmentApi.getOcr(id)
        const d = res.data
        if (d.ocr_processed) {
          setPhase(d.has_text ? 'ready' : 'no_text')
        } else {
          _pollOcr(id)
        }
      } catch {
        setPhase('error')
      }
    }, POLL_INTERVAL_MS)
  }

  const handleExtract = async () => {
    if (!attachmentId) return
    setPhase('extracting')
    setParseError('')
    try {
      const res = await attachmentApi.parseOcr(attachmentId)
      setParsedData(res.data)
      setPhase('extracted')
      setExpanded(true)
    } catch (err) {
      const status = err.response?.status
      setParseError(
        status === 429
          ? (t('attachments.ocrParseRateLimited') || 'Too many requests. Please wait.')
          : status === 503
            ? (t('attachments.ocrAiDisabled') || 'AI extraction is not available.')
            : (err.response?.data?.error || t('attachments.ocrParseError') || 'Could not extract data.')
      )
      setPhase('ready')
    }
  }

  const handlePrefill = () => {
    if (parsedData && onPrefill) {
      onPrefill(parsedData)
      setPrefilled(true)
      setTimeout(() => setPrefilled(false), 3000)
    }
  }

  // Nothing to show
  if (phase === 'idle' || phase === 'no_text') return null

  // ─── Banner colour ───────────────────────────────────────────────────────
  const isError = phase === 'error'
  const isSuccess = prefilled
  const borderCls = isError
    ? 'border-red-500/30 bg-red-500/5'
    : isSuccess
      ? 'border-green-500/30 bg-green-500/5'
      : 'border-purple-500/30 bg-purple-500/5'
  const iconCls = isError
    ? 'text-red-400'
    : isSuccess
      ? 'text-green-400'
      : 'text-purple-400'
  const isBusy = phase === 'uploading' || phase === 'scanning' || phase === 'extracting'

  return (
    <div className={`mt-3 rounded-xl border transition-all overflow-hidden ${borderCls}`}>
      {/* ── Banner row ── */}
      <div className="flex items-center gap-2 px-3 py-2.5">
        {/* Leading icon */}
        <span className={`flex-shrink-0 ${iconCls}`}>
          {isBusy ? Icons.spinner : isSuccess ? Icons.check : isError ? Icons.warning : Icons.scan}
        </span>

        {/* Status text */}
        <span className="flex-1 text-sm text-[var(--color-text-primary)]">
          {phase === 'uploading' && (t('receipt.scanBannerUploading') || 'Uploading receipt…')}
          {phase === 'scanning' && (t('receipt.scanBannerScanning') || 'Scanning receipt…')}
          {phase === 'scanning_slow' && (t('receipt.scanBannerSlow') || 'Still scanning — check back shortly')}
          {phase === 'ready' && !isSuccess && (t('receipt.scanBanner') || 'Receipt scanned — extract data to pre-fill form')}
          {phase === 'extracting' && (t('receipt.scanBannerExtracting') || 'Extracting data…')}
          {phase === 'extracted' && !isSuccess && (t('receipt.scanBannerExtracted') || 'Data extracted — tap to pre-fill')}
          {phase === 'error' && (t('receipt.scanBannerError') || 'Failed to process receipt')}
          {isSuccess && (t('receipt.scanBannerPrefilled') || 'Form pre-filled ✓')}
        </span>

        {/* Trailing action */}
        {phase === 'ready' && (
          <button
            type="button"
            onClick={handleExtract}
            className="flex-shrink-0 flex items-center gap-1.5 text-xs bg-purple-600 hover:bg-purple-700 active:bg-purple-800 text-white px-2.5 py-1.5 rounded-lg transition-colors font-medium touch-manipulation"
          >
            {Icons.wand}
            {t('receipt.scanBannerExtract') || 'Extract'}
          </button>
        )}
        {phase === 'extracted' && (
          <button
            type="button"
            onClick={() => setExpanded(v => !v)}
            className={`flex-shrink-0 transition-colors ${iconCls} hover:opacity-70`}
            aria-label={expanded ? 'Collapse' : 'Expand'}
          >
            {expanded ? Icons.chevronUp : Icons.chevronDown}
          </button>
        )}
        {phase === 'scanning_slow' && (
          <button
            type="button"
            onClick={() => { pollAttemptsRef.current = 0; _pollOcr(attachmentId) }}
            className="flex-shrink-0 text-xs text-purple-400 underline hover:text-purple-300 transition-colors"
          >
            {t('receipt.scanBannerCheck') || 'Check'}
          </button>
        )}
      </div>

      {/* ── Parse error ── */}
      {parseError && (
        <p className="px-3 pb-2.5 text-xs text-red-400">{parseError}</p>
      )}

      {/* ── Extracted data card ── */}
      {phase === 'extracted' && expanded && parsedData && (
        <div className="border-t border-purple-500/20 px-3 pb-3 pt-2.5 space-y-3">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
            {parsedData.date && (
              <>
                <dt className="text-[var(--color-text-muted)]">{t('attachments.ocrDate') || 'Date'}</dt>
                <dd className="text-[var(--color-text-primary)] font-medium">{parsedData.date}</dd>
              </>
            )}
            {parsedData.vendor && (
              <>
                <dt className="text-[var(--color-text-muted)]">{t('attachments.ocrVendor') || 'Vendor'}</dt>
                <dd className="text-[var(--color-text-primary)] font-medium truncate">{parsedData.vendor}</dd>
              </>
            )}
            {parsedData.amount != null && (
              <>
                <dt className="text-[var(--color-text-muted)]">{t('attachments.ocrAmount') || 'Amount'}</dt>
                <dd className="text-[var(--color-text-primary)] font-medium">{parsedData.amount}</dd>
              </>
            )}
            {parsedData.line_items?.[0]?.description && (
              <>
                <dt className="text-[var(--color-text-muted)]">{t('attachments.ocrLineItems') || 'Items'}</dt>
                <dd className="text-[var(--color-text-primary)] truncate">{parsedData.line_items[0].description}</dd>
              </>
            )}
          </dl>

          {onPrefill && (
            <button
              type="button"
              onClick={handlePrefill}
              className="w-full flex items-center justify-center gap-2 text-sm bg-purple-600 hover:bg-purple-700 active:bg-purple-800 text-white px-3 py-2.5 rounded-xl transition-colors font-semibold touch-manipulation"
            >
              {Icons.prefill}
              {t('receipt.scanBannerPrefill') || 'Pre-fill Form'}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
