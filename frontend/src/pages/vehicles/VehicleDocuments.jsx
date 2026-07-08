/**
 * VehicleDocuments — per-vehicle documents & receipts page with OCR text search
 *
 * Route: /vehicles/:vehicleId/search
 * Linked from VehicleDetail's "Search" action button.
 *
 * Features:
 *  - Debounced search box (300 ms) — queries GET /api/attachments?q=...&vehicle_id=X
 *  - Results show thumbnails, OCR badge (scanned / no-text / pending), OCR snippet
 *  - Tapping a result opens AttachmentViewer; tapping OCR badge auto-opens OCR panel
 *  - Infinite-scroll / "Load more" pagination
 *  - Empty states: no documents yet / no search results
 *  - PWA-optimised: touch targets ≥ 44 px, overscroll-contain, no modals
 *
 * Security:
 *  - All queries are scoped to the current user via the API (server-side enforcement)
 *  - `q` is sanitised on the server; the component never sets innerHTML
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { vehicleApi, attachmentApi } from '../../services/api'
import { useTranslation } from '../../contexts/LanguageContext'
import AttachmentViewer from '../../components/ui/AttachmentViewer'

// ── Icons ─────────────────────────────────────────────────────────────────────
const Icons = {
  back: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M19 12H5M12 5l-7 7 7 7"/>
    </svg>
  ),
  search: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>
    </svg>
  ),
  clear: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
    </svg>
  ),
  scan: (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="4 7 4 4 7 4"/><polyline points="4 17 4 20 7 20"/>
      <polyline points="17 4 20 4 20 7"/><polyline points="17 20 20 20 20 17"/>
      <line x1="4" y1="12" x2="20" y2="12"/>
    </svg>
  ),
  file: (
    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><polyline points="13 2 13 9 20 9"/>
    </svg>
  ),
  image: (
    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/>
      <polyline points="21 15 16 10 5 21"/>
    </svg>
  ),
  emptyBox: (
    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" className="opacity-40">
      <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
      <polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/>
    </svg>
  ),
  spinner: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="animate-spin">
      <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
    </svg>
  ),
  upload: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
      <polyline points="17 8 12 3 7 8"/>
      <line x1="12" y1="3" x2="12" y2="15"/>
    </svg>
  ),
  close: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
    </svg>
  ),
  wand: (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M15 4V2"/><path d="M15 16v-2"/><path d="M8 9h2"/><path d="M20 9h2"/>
      <path d="M17.8 11.8 19 13"/><path d="M15 9h.01"/><path d="M17.8 6.2 19 5"/>
      <path d="m3 21 9-9"/><path d="M12.2 6.2 11 5"/>
    </svg>
  ),
}

// ── Category label ─────────────────────────────────────────────────────────────
function CategoryBadge({ category }) {
  const colours = {
    receipt:  'bg-amber-500/15 text-amber-400',
    document: 'bg-blue-500/15 text-blue-400',
    photo:    'bg-green-500/15 text-green-400',
    manual:   'bg-purple-500/15 text-purple-400',
    invoice:  'bg-rose-500/15 text-rose-400',
  }
  const cls = colours[category] || 'bg-[var(--color-bg-tertiary)] text-[var(--color-text-muted)]'
  return (
    <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium ${cls}`}>
      {category || 'file'}
    </span>
  )
}

// ── OCR Status badge ───────────────────────────────────────────────────────────
function OcrBadge({ attachment, onClick, t }) {
  if (!attachment.ocr_processed) {
    return (
      <span
        title={t('vehicleDocuments.ocrPending') || 'OCR pending'}
        className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-gray-500/15 text-gray-400"
      >
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="animate-spin opacity-70">
          <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
        </svg>
        {t('vehicleDocuments.ocrScanning') || 'Scanning'}
      </span>
    )
  }
  if (!attachment.has_text) {
    return (
      <span
        title={t('vehicleDocuments.ocrNoText') || 'No text detected'}
        className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-gray-500/10 text-gray-500"
      >
        {t('vehicleDocuments.ocrNoText') || 'No text'}
      </span>
    )
  }
  return (
    <button
      type="button"
      onClick={onClick}
      title={t('vehicleDocuments.ocrOpen') || 'View scanned text'}
      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 transition-colors touch-manipulation"
    >
      {Icons.scan}
      {t('vehicleDocuments.ocrScanned') || 'Scanned'}
    </button>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function VehicleDocuments() {
  const { id: vehicleId } = useParams()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const { t } = useTranslation()

  const [vehicle, setVehicle] = useState(null)
  const [attachments, setAttachments] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [debouncedQ, setDebouncedQ] = useState('')

  // AttachmentViewer state
  const [viewerOpen, setViewerOpen] = useState(false)
  const [viewerAttachments, setViewerAttachments] = useState([])
  const [viewerIndex, setViewerIndex] = useState(0)
  const [viewerShowOcr, setViewerShowOcr] = useState(false)

  const timerRef = useRef(null)
  const ocrPollRef = useRef(null)
  const ocrToastTimerRef = useRef(null)
  const fileInputRef = useRef(null)
  const PER_PAGE = 20

  // Upload panel state
  const [showUpload, setShowUpload] = useState(false)
  const [uploadFile, setUploadFile] = useState(null)
  const [uploadPreview, setUploadPreview] = useState(null)
  const [uploadCategory, setUploadCategory] = useState('receipt')
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState('')
  // OCR toast — appears after upload+scan completes with text found
  const [ocrToast, setOcrToast] = useState(null) // { id, filename }

  // Load vehicle metadata once
  useEffect(() => {
    vehicleApi.getById(vehicleId)
      .then(r => setVehicle(r.data))
      .catch(() => navigate('/vehicles'))
  }, [vehicleId, navigate])

  // Deep-link: ?open=<attachmentId> — auto-open the viewer for a specific file.
  // Triggered when navigating here from GlobalSearch results.
  // We fetch the single attachment, open the viewer, then strip the param from
  // the URL so the browser back-button works naturally.
  useEffect(() => {
    const openId = parseInt(searchParams.get('open'), 10)
    if (!openId) return

    attachmentApi.get(openId).then(res => {
      const att = res.data
      // Safety: only open if the attachment actually belongs to this vehicle
      if (att && att.vehicle_id === parseInt(vehicleId, 10)) {
        setViewerAttachments([att])
        setViewerIndex(0)
        setViewerShowOcr(false)
        setViewerOpen(true)
      }
    }).catch(() => {
      // Attachment not found or not owned by user — silently ignore
    }).finally(() => {
      // Clean the URL regardless of outcome
      setSearchParams(prev => {
        const next = new URLSearchParams(prev)
        next.delete('open')
        return next
      }, { replace: true })
    })
  }, []) // run once on mount only — intentional empty dep array

  // Debounce query input → debouncedQ
  const handleQueryChange = (e) => {
    const v = e.target.value
    setQuery(v)
    clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => {
      setDebouncedQ(v.trim())
      setPage(1)
      setAttachments([])
    }, 300)
  }

  const clearQuery = () => {
    setQuery('')
    setDebouncedQ('')
    setPage(1)
    setAttachments([])
  }

  // Fetch attachments whenever debouncedQ or page changes
  const fetchAttachments = useCallback(async (pageNum, q) => {
    try {
      const res = await attachmentApi.getAll({
        vehicleId,
        q: q.length >= 2 ? q : undefined,
        page: pageNum,
        perPage: PER_PAGE,
      })
      const data = res.data
      if (pageNum === 1) {
        setAttachments(data.attachments)
      } else {
        setAttachments(prev => [...prev, ...data.attachments])
      }
      setTotal(data.total)
      setHasMore(pageNum < data.pages)
    } catch {
      setError(t('vehicleDocuments.loadError') || 'Failed to load documents')
    }
  }, [vehicleId, t])

  // Initial + query-driven load
  useEffect(() => {
    setLoading(true)
    setError('')
    fetchAttachments(1, debouncedQ).finally(() => setLoading(false))
  }, [debouncedQ, fetchAttachments])

  // Load more (pagination)
  const loadMore = async () => {
    const nextPage = page + 1
    setPage(nextPage)
    setLoadingMore(true)
    await fetchAttachments(nextPage, debouncedQ)
    setLoadingMore(false)
  }

  // Open viewer
  const openViewer = (attachment, showOcr = false) => {
    setViewerAttachments([attachment])
    setViewerIndex(0)
    setViewerShowOcr(showOcr)
    setViewerOpen(true)
  }

  // Cleanup timers and blob URLs on unmount
  useEffect(() => () => {
    clearTimeout(timerRef.current)
    clearTimeout(ocrPollRef.current)
    clearTimeout(ocrToastTimerRef.current)
  }, [])

  // ── Upload helpers ─────────────────────────────────────────────────────────

  // Browser MIME reporting is unreliable for office/ODF files (often empty), so
  // we accept by MIME OR by extension. The server re-validates via magic bytes.
  const ALLOWED_TYPES = [
    'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/heic', 'image/heif',
    'application/pdf',
    'application/msword', 'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.oasis.opendocument.text',
    'application/vnd.oasis.opendocument.spreadsheet',
    'application/vnd.oasis.opendocument.presentation',
  ]
  const ALLOWED_EXT = /\.(jpe?g|png|gif|webp|heic|heif|pdf|docx?|xlsx?|od[tsp])$/i
  const MAX_FILE_SIZE = 10 * 1024 * 1024  // 10 MB
  const UPLOAD_CATEGORIES = ['receipt', 'invoice', 'insurance', 'registration', 'maintenance', 'warranty', 'photo', 'document', 'other']

  const handleFileSelect = (file) => {
    if (!file) return
    if (file.size > MAX_FILE_SIZE) {
      setUploadError(t('vehicleDocuments.uploadFileTooLarge') || 'File too large. Max 10 MB.')
      return
    }
    if (!ALLOWED_TYPES.includes(file.type) && !ALLOWED_EXT.test(file.name || '')) {
      setUploadError(t('vehicleDocuments.uploadInvalidType') || 'Invalid file type.')
      return
    }
    setUploadError('')
    setUploadFile(file)
    // Inline preview only for browser-renderable images (not HEIC/office/ODF).
    const renderable = /^image\/(jpeg|png|gif|webp)$/.test(file.type)
    setUploadPreview(renderable ? URL.createObjectURL(file) : null)
  }

  const cancelUpload = () => {
    setShowUpload(false)
    setUploadFile(null)
    if (uploadPreview) URL.revokeObjectURL(uploadPreview)
    setUploadPreview(null)
    setUploadCategory('receipt')
    setUploadError('')
  }

  const handleUploadSubmit = async () => {
    if (!uploadFile || uploading) return
    setUploading(true)
    setUploadError('')
    try {
      const res = await attachmentApi.upload(uploadFile, { vehicleId, category: uploadCategory })
      const attachment = res.data?.attachment
      const ocrStatus = res.data?.ocr_status
      // Reset panel
      if (uploadPreview) URL.revokeObjectURL(uploadPreview)
      setShowUpload(false)
      setUploadFile(null)
      setUploadPreview(null)
      setUploadCategory('receipt')
      setUploading(false)
      // Refresh list
      setPage(1)
      setAttachments([])
      fetchAttachments(1, debouncedQ)
      // Start OCR polling for images
      if (attachment?.is_image && ocrStatus === 'pending') {
        _startOcrPoll(attachment.id, attachment.original_filename || attachment.filename)
      }
    } catch {
      setUploadError(t('vehicleDocuments.uploadError') || 'Upload failed. Please try again.')
      setUploading(false)
    }
  }

  const _startOcrPoll = (id, filename) => {
    if (ocrPollRef.current) clearTimeout(ocrPollRef.current)
    let attempts = 0
    const MAX_ATTEMPTS = 20
    const poll = async () => {
      if (attempts >= MAX_ATTEMPTS) return
      attempts++
      try {
        const res = await attachmentApi.getOcr(id)
        const d = res.data
        if (d.ocr_processed) {
          if (d.has_text) {
            // Refresh so the list shows OCR badge
            fetchAttachments(1, debouncedQ)
            // Show toast
            setOcrToast({ id, filename })
            if (ocrToastTimerRef.current) clearTimeout(ocrToastTimerRef.current)
            ocrToastTimerRef.current = setTimeout(() => setOcrToast(null), 8000)
          }
        } else {
          ocrPollRef.current = setTimeout(poll, 3000)
        }
      } catch {
        // Stop polling on error
      }
    }
    ocrPollRef.current = setTimeout(poll, 3000)
  }

  const dismissToast = () => {
    setOcrToast(null)
    clearTimeout(ocrToastTimerRef.current)
  }

  const openToastViewer = () => {
    if (!ocrToast) return
    const att = attachments.find(a => a.id === ocrToast.id)
    if (att) openViewer(att, true)
    dismissToast()
  }

  // Format file size
  const fmtSize = (bytes) => {
    if (!bytes) return ''
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(0)} KB`
    return `${(bytes / 1048576).toFixed(1)} MB`
  }

  const isSearching = debouncedQ.length >= 2
  const noResults = !loading && attachments.length === 0

  return (
    <div className="pb-6">
      {/* Header */}
      <div className="sticky top-0 z-30 bg-[var(--color-bg-secondary)] border-b border-[var(--color-border)] safe-top">
        <div className="flex items-center gap-3 px-4 h-14">
          <button
            onClick={() => navigate(`/vehicles/${vehicleId}`)}
            className="btn-icon flex-shrink-0"
            aria-label={t('common.back') || 'Back'}
          >
            {Icons.back}
          </button>
          <div className="flex-1 min-w-0">
            <h1 className="text-base font-semibold leading-tight truncate">
              {t('vehicleDocuments.title') || 'Documents & Receipts'}
            </h1>
            {vehicle && (
              <p className="text-xs text-[var(--color-text-secondary)] truncate">{vehicle.name}</p>
            )}
          </div>
          {!loading && (
            <span className="text-xs text-[var(--color-text-muted)] flex-shrink-0">
              {total} {t('vehicleDocuments.files') || 'files'}
            </span>
          )}
          <button
            type="button"
            onClick={() => setShowUpload(v => !v)}
            className={`btn-icon flex-shrink-0 transition-colors ${showUpload ? 'text-[var(--color-accent)]' : ''}`}
            aria-label={t('vehicleDocuments.upload') || 'Upload file'}
            title={t('vehicleDocuments.upload') || 'Upload file'}
          >
            {Icons.upload}
          </button>
        </div>

        {/* Search box */}
        <div className="px-4 pb-3">
          <div className="relative flex items-center">
            <span className="absolute left-3 text-[var(--color-text-muted)] pointer-events-none">
              {Icons.search}
            </span>
            <input
              type="search"
              value={query}
              onChange={handleQueryChange}
              placeholder={t('vehicleDocuments.searchPlaceholder') || 'Search scanned text, filenames…'}
              className="w-full pl-9 pr-9 py-2.5 bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded-xl text-sm text-[var(--color-text-primary)] placeholder-[var(--color-text-muted)] outline-none focus:border-[var(--color-accent)] transition-colors"
              maxLength={100}
              autoComplete="off"
              autoCorrect="off"
              spellCheck={false}
            />
            {query && (
              <button
                onClick={clearQuery}
                className="absolute right-3 text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors touch-manipulation"
                aria-label={t('common.clear') || 'Clear'}
              >
                {Icons.clear}
              </button>
            )}
          </div>
          {isSearching && !loading && (
            <p className="text-xs text-[var(--color-text-muted)] mt-1.5 px-1">
              {total === 0
                ? (t('vehicleDocuments.noResults') || 'No documents match your search')
                : `${total} ${t('vehicleDocuments.resultsFor') || 'result(s) for'} "${debouncedQ}"`}
            </p>
          )}
        </div>
      </div>

      {/* Upload panel */}
      {showUpload && (
        <div className="px-4 pt-3 pb-1 border-b border-[var(--color-border)] bg-[var(--color-bg-secondary)]">
          <div className="card p-4 space-y-3">
            <p className="text-sm font-medium text-[var(--color-text-primary)]">
              {t('vehicleDocuments.uploadTitle') || 'Upload File'}
            </p>

            {/* File picker */}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*,.heic,.heif,application/pdf,.doc,.docx,.xls,.xlsx,.odt,.ods,.odp"
              className="hidden"
              onChange={e => handleFileSelect(e.target.files?.[0])}
            />
            {uploadFile ? (
              <div className="flex items-center gap-3">
                {uploadPreview ? (
                  <img src={uploadPreview} alt="preview" className="w-14 h-14 rounded-lg object-cover flex-shrink-0" />
                ) : (
                  <div className="w-14 h-14 rounded-lg bg-[var(--color-bg-tertiary)] flex items-center justify-center flex-shrink-0 text-[var(--color-text-muted)]">
                    {Icons.file}
                  </div>
                )}
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-[var(--color-text-primary)] truncate">{uploadFile.name}</p>
                  <button
                    type="button"
                    onClick={() => { setUploadFile(null); if (uploadPreview) URL.revokeObjectURL(uploadPreview); setUploadPreview(null) }}
                    className="text-xs text-[var(--color-text-muted)] underline mt-0.5 touch-manipulation"
                  >
                    {t('common.change') || 'Change'}
                  </button>
                </div>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="w-full flex flex-col items-center justify-center gap-2 py-6 rounded-xl border-2 border-dashed border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] transition-colors touch-manipulation"
              >
                {Icons.upload}
                <span className="text-sm">{t('vehicleDocuments.uploadChoose') || 'Tap to choose a file'}</span>
              </button>
            )}

            {/* Category selector */}
            <div>
              <label className="text-xs text-[var(--color-text-muted)] mb-1 block">
                {t('vehicleDocuments.categoryLabel') || 'Category'}
              </label>
              <select
                value={uploadCategory}
                onChange={e => setUploadCategory(e.target.value)}
                className="w-full px-3 py-2 bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded-lg text-sm text-[var(--color-text-primary)] outline-none focus:border-[var(--color-accent)] transition-colors"
              >
                {['receipt', 'invoice', 'insurance', 'registration', 'maintenance', 'warranty', 'photo', 'document', 'other'].map(cat => (
                  <option key={cat} value={cat}>{cat.charAt(0).toUpperCase() + cat.slice(1)}</option>
                ))}
              </select>
            </div>

            {uploadError && (
              <p className="text-xs text-red-400">{uploadError}</p>
            )}

            {/* Actions */}
            <div className="flex gap-2">
              <button
                type="button"
                onClick={cancelUpload}
                disabled={uploading}
                className="flex-1 btn btn-sm"
              >
                {t('common.cancel') || 'Cancel'}
              </button>
              <button
                type="button"
                onClick={handleUploadSubmit}
                disabled={!uploadFile || uploading}
                className="flex-1 btn btn-sm btn-primary flex items-center justify-center gap-2 touch-manipulation"
              >
                {uploading && (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="animate-spin">
                    <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
                  </svg>
                )}
                {uploading
                  ? (t('vehicleDocuments.uploading') || 'Uploading…')
                  : (t('vehicleDocuments.uploadBtn') || 'Upload')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Content */}
      <div className="px-4 pt-4">
        {/* Loading skeleton */}
        {loading && (
          <div className="space-y-3">
            {[1, 2, 3, 4].map(i => (
              <div key={i} className="card flex items-center gap-3 animate-pulse">
                <div className="w-14 h-14 rounded-lg bg-[var(--color-bg-tertiary)] flex-shrink-0" />
                <div className="flex-1 space-y-2">
                  <div className="h-3.5 bg-[var(--color-bg-tertiary)] rounded w-2/3" />
                  <div className="h-2.5 bg-[var(--color-bg-tertiary)] rounded w-1/3" />
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="card text-sm text-red-400 text-center py-6">{error}</div>
        )}

        {/* Empty state */}
        {!loading && !error && noResults && (
          <div className="flex flex-col items-center justify-center py-16 text-center gap-3">
            {Icons.emptyBox}
            <p className="text-sm font-medium text-[var(--color-text-secondary)]">
              {isSearching
                ? (t('vehicleDocuments.noResults') || 'No documents match your search')
                : (t('vehicleDocuments.empty') || 'No documents yet')}
            </p>
            {!isSearching && (
              <p className="text-xs text-[var(--color-text-muted)] max-w-xs">
                {t('vehicleDocuments.emptyHint') || 'Attach receipts and invoices to fuel, service, and repair entries to see them here.'}
              </p>
            )}
            {isSearching && (
              <button
                onClick={clearQuery}
                className="btn btn-sm mt-1"
              >
                {t('vehicleDocuments.clearSearch') || 'Clear search'}
              </button>
            )}
          </div>
        )}

        {/* Results list */}
        {!loading && !error && attachments.length > 0 && (
          <div className="space-y-2">
            {attachments.map((a) => {
              const filename = a.original_filename || a.filename
              const thumb = a.is_image ? a.view_url : null

              return (
                <div key={a.id} className="card flex items-start gap-3 p-3">
                  {/* Thumbnail / Icon */}
                  <button
                    type="button"
                    onClick={() => openViewer(a, false)}
                    className="flex-shrink-0 w-14 h-14 rounded-lg overflow-hidden bg-[var(--color-bg-tertiary)] flex items-center justify-center text-[var(--color-text-muted)] touch-manipulation"
                    aria-label={t('vehicleDocuments.openFile') || 'Open file'}
                  >
                    {thumb ? (
                      <img
                        src={thumb}
                        alt={filename}
                        className="w-full h-full object-cover"
                        loading="lazy"
                      />
                    ) : (
                      a.is_pdf
                        ? <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
                        : Icons.image
                    )}
                  </button>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <button
                      type="button"
                      onClick={() => openViewer(a, false)}
                      className="text-left w-full group touch-manipulation"
                    >
                      <p className="text-sm font-medium text-[var(--color-text-primary)] truncate group-hover:text-[var(--color-accent)] transition-colors">
                        {filename}
                      </p>
                    </button>

                    {/* Meta row */}
                    <div className="flex flex-wrap items-center gap-1.5 mt-1">
                      {a.category && <CategoryBadge category={a.category} />}
                      <OcrBadge
                        attachment={a}
                        t={t}
                        onClick={(e) => { e.stopPropagation(); openViewer(a, true) }}
                      />
                      {a.file_size && (
                        <span className="text-[10px] text-[var(--color-text-muted)]">
                          {fmtSize(a.file_size)}
                        </span>
                      )}
                      {a.created_at && (
                        <span className="text-[10px] text-[var(--color-text-muted)]">
                          {new Date(a.created_at).toLocaleDateString()}
                        </span>
                      )}
                    </div>

                    {/* OCR snippet — highlighted match */}
                    {a.ocr_snippet && (
                      <p className="text-xs text-[var(--color-text-muted)] mt-1.5 leading-relaxed line-clamp-2 font-mono">
                        {a.ocr_snippet}
                      </p>
                    )}
                  </div>
                </div>
              )
            })}

            {/* Load more */}
            {hasMore && (
              <div className="pt-2 pb-4 text-center">
                <button
                  onClick={loadMore}
                  disabled={loadingMore}
                  className="btn btn-sm"
                >
                  {loadingMore ? Icons.spinner : (t('vehicleDocuments.loadMore') || 'Load more')}
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Attachment Viewer */}
      <AttachmentViewer
        isOpen={viewerOpen}
        attachments={viewerAttachments}
        initialIndex={viewerIndex}
        initialShowOcr={viewerShowOcr}
        onClose={() => setViewerOpen(false)}
      />

      {/* OCR toast — slide up from bottom when receipt scan completes */}
      {ocrToast && (
        <div
          role="status"
          aria-live="polite"
          className="fixed bottom-20 left-4 right-4 z-50 flex items-center gap-3 bg-[var(--color-bg-elevated,var(--color-bg-secondary))] border border-purple-500/30 rounded-2xl px-4 py-3 shadow-xl animate-slide-up"
          style={{ animation: 'slideUp 0.25s ease-out' }}
        >
          <span className="flex-shrink-0 text-purple-400">
            {Icons.wand}
          </span>
          <p className="flex-1 text-sm text-[var(--color-text-primary)]">
            {t('vehicleDocuments.ocrToast') || 'Receipt scanned — extract data?'}
          </p>
          <button
            type="button"
            onClick={openToastViewer}
            className="flex-shrink-0 text-xs font-semibold text-purple-400 hover:text-purple-300 transition-colors px-2 py-1 touch-manipulation"
          >
            {t('vehicleDocuments.ocrToastView') || 'View'}
          </button>
          <button
            type="button"
            onClick={dismissToast}
            aria-label={t('common.dismiss') || 'Dismiss'}
            className="flex-shrink-0 text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors touch-manipulation"
          >
            {Icons.close}
          </button>
        </div>
      )}

      <style>{`
        @keyframes slideUp {
          from { transform: translateY(1rem); opacity: 0; }
          to   { transform: translateY(0);    opacity: 1; }
        }
      `}</style>
    </div>
  )
}
