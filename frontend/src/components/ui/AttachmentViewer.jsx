import { useState, useEffect } from 'react'
import { attachmentApi } from '../../services/api'
import { useTranslation } from '../../contexts/LanguageContext'

// Icons
const Icons = {
  close: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
    </svg>
  ),
  download: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
    </svg>
  ),
  edit: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
    </svg>
  ),
  file: (
    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>
    </svg>
  ),
  zoomIn: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="11" y1="8" x2="11" y2="14"/><line x1="8" y1="11" x2="14" y2="11"/>
    </svg>
  ),
  zoomOut: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="8" y1="11" x2="14" y2="11"/>
    </svg>
  ),
  chevronLeft: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="15 18 9 12 15 6"/>
    </svg>
  ),
  chevronRight: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="9 18 15 12 9 6"/>
    </svg>
  ),
  scan: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="4 7 4 4 7 4"/><polyline points="4 17 4 20 7 20"/>
      <polyline points="17 4 20 4 20 7"/><polyline points="17 20 20 20 20 17"/>
      <line x1="4" y1="12" x2="20" y2="12"/>
    </svg>
  ),
  copy: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
    </svg>
  ),
  wand: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M15 4V2"/><path d="M15 16v-2"/><path d="M8 9h2"/><path d="M20 9h2"/>
      <path d="M17.8 11.8 19 13"/><path d="M15 9h.01"/><path d="M17.8 6.2 19 5"/>
      <path d="m3 21 9-9"/><path d="M12.2 6.2 11 5"/>
    </svg>
  ),
  prefill: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
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
}

// Attachment categories
const ATTACHMENT_CATEGORIES = [
  'receipt',
  'invoice',
  'insurance',
  'registration',
  'maintenance',
  'warranty',
  'photo',
  'document',
  'other'
]

const AttachmentViewer = ({ 
  attachments = [], 
  initialIndex = 0, 
  isOpen, 
  onClose,
  onUpdate,
  onPrefill,        // (parsedData) => void — called when user taps "Pre-fill Form"
  initialShowOcr = false,  // auto-open OCR panel when viewer opens
  // For single attachment view (backwards compatible)
  attachment = null,
}) => {
  const { t } = useTranslation()
  const [currentIndex, setCurrentIndex] = useState(initialIndex)
  const [zoom, setZoom] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  
  // Edit state
  const [showEditModal, setShowEditModal] = useState(false)
  const [editDescription, setEditDescription] = useState('')
  const [editCategory, setEditCategory] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [saveError, setSaveError] = useState('')

  // OCR panel state
  const [showOcrPanel, setShowOcrPanel] = useState(false)
  const [ocrData, setOcrData] = useState(null)   // { ocr_processed, has_text, ocr_text }
  const [ocrLoading, setOcrLoading] = useState(false)
  const [ocrCopied, setOcrCopied] = useState(false)
  // OCR AI-parse state
  const [ocrParsing, setOcrParsing] = useState(false)
  const [ocrParsed, setOcrParsed] = useState(null)   // structured result from Ollama
  const [ocrParseError, setOcrParseError] = useState('')
  // OCR retry state
  const [ocrRetrying, setOcrRetrying] = useState(false)
  const [ocrRetryError, setOcrRetryError] = useState('')

  // Handle single attachment or array
  const allAttachments = attachment ? [attachment] : attachments
  const currentAttachment = allAttachments[currentIndex]

  useEffect(() => {
    setCurrentIndex(initialIndex)
    setZoom(1)
    setLoading(true)
    setError(null)
    const targetAttachment = (attachment ? [attachment] : attachments)[initialIndex]
    if (initialShowOcr && targetAttachment?.is_image) {
      setShowOcrPanel(true)
      setOcrLoading(true)
      attachmentApi.getOcr(targetAttachment.id)
        .then(res => setOcrData(res.data))
        .catch(() => setOcrData({ ocr_processed: false, has_text: false, ocr_text: '' }))
        .finally(() => setOcrLoading(false))
    } else {
      setShowOcrPanel(false)
      setOcrData(null)
    }
  }, [initialIndex, isOpen, initialShowOcr])

  // Reset OCR panel when user navigates between attachments
  useEffect(() => {
    setShowOcrPanel(false)
    setOcrData(null)
    setOcrCopied(false)
    setOcrParsed(null)
    setOcrParseError('')
    setOcrRetrying(false)
    setOcrRetryError('')
  }, [currentIndex])

  // Handle keyboard navigation
  useEffect(() => {
    if (!isOpen) return

    const handleKeyDown = (e) => {
      switch (e.key) {
        case 'Escape':
          onClose()
          break
        case 'ArrowLeft':
          if (currentIndex > 0) {
            setCurrentIndex(prev => prev - 1)
            setZoom(1)
            setLoading(true)
          }
          break
        case 'ArrowRight':
          if (currentIndex < allAttachments.length - 1) {
            setCurrentIndex(prev => prev + 1)
            setZoom(1)
            setLoading(true)
          }
          break
        case '+':
        case '=':
          setZoom(prev => Math.min(prev + 0.25, 3))
          break
        case '-':
          setZoom(prev => Math.max(prev - 0.25, 0.5))
          break
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, currentIndex, allAttachments.length, onClose])

  if (!isOpen || !currentAttachment) return null

  const getFileType = () => {
    const type = currentAttachment.file_type || ''
    if (type.startsWith('image/')) return 'image'
    if (type === 'application/pdf') return 'pdf'
    if (type.includes('word') || type.includes('document')) return 'document'
    if (type.includes('excel') || type.includes('spreadsheet')) return 'spreadsheet'
    return 'other'
  }

  const fileType = getFileType()
  const viewUrl = attachmentApi.getViewUrl(currentAttachment.id)

  const handleDownload = async () => {
    try {
      const response = await attachmentApi.download(currentAttachment.id)
      const blob = new Blob([response.data], { type: currentAttachment.file_type })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = currentAttachment.original_filename || currentAttachment.filename
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (err) {
      console.error('Download failed:', err)
    }
  }

  const handleOpenEdit = () => {
    setEditDescription(currentAttachment.description || '')
    setEditCategory(currentAttachment.category || 'document')
    setSaveError('')
    setShowEditModal(true)
  }

  const handleSaveEdit = async () => {
    setIsSaving(true)
    setSaveError('')
    
    try {
      const response = await attachmentApi.update(currentAttachment.id, {
        description: editDescription,
        category: editCategory,
      })
      
      // Update the attachment in place
      if (response.data.attachment) {
        currentAttachment.description = response.data.attachment.description
        currentAttachment.category = response.data.attachment.category
      }
      
      // Notify parent of update if callback provided
      if (onUpdate) {
        onUpdate(currentAttachment.id, {
          description: editDescription,
          category: editCategory,
        })
      }
      
      setShowEditModal(false)
    } catch (err) {
      setSaveError(err.response?.data?.error || t('attachments.failedToUpdate') || 'Failed to update attachment')
    } finally {
      setIsSaving(false)
    }
  }

  // --- OCR helpers ---
  const handleToggleOcr = async () => {
    if (!currentAttachment?.is_image) return
    if (showOcrPanel) {
      setShowOcrPanel(false)
      return
    }
    setShowOcrPanel(true)
    if (!ocrData) {
      setOcrLoading(true)
      try {
        const res = await attachmentApi.getOcr(currentAttachment.id)
        setOcrData(res.data)
      } catch (err) {
        setOcrData({ ocr_processed: false, has_text: false, ocr_text: '' })
      } finally {
        setOcrLoading(false)
      }
    }
  }

  const handleCopyOcr = async () => {
    if (!ocrData?.ocr_text) return
    try {
      await navigator.clipboard.writeText(ocrData.ocr_text)
      setOcrCopied(true)
      setTimeout(() => setOcrCopied(false), 2000)
    } catch (_) {
      // clipboard not available (e.g. insecure context) — silently ignore
    }
  }

  const handleParseOcr = async () => {
    if (!currentAttachment || ocrParsing) return
    setOcrParsing(true)
    setOcrParsed(null)
    setOcrParseError('')
    try {
      const res = await attachmentApi.parseOcr(currentAttachment.id)
      setOcrParsed(res.data)
    } catch (err) {
      const status = err.response?.status
      if (status === 429) {
        setOcrParseError(t('attachments.ocrParseRateLimited') || 'Too many requests. Please wait before trying again.')
      } else if (status === 503) {
        setOcrParseError(t('attachments.ocrAiDisabled') || 'AI extraction requires Ollama to be enabled.')
      } else {
        setOcrParseError(err.response?.data?.error || t('attachments.ocrParseError') || 'Could not extract data from this receipt.')
      }
    } finally {
      setOcrParsing(false)
    }
  }

  const handlePrefillForm = () => {
    if (ocrParsed && onPrefill) {
      onPrefill(ocrParsed)
      onClose()
    }
  }

  // Retry OCR: reset → re-enqueue → poll until done
  const handleRetryOcr = async () => {
    if (!currentAttachment || ocrRetrying) return
    setOcrRetrying(true)
    setOcrRetryError('')
    try {
      await attachmentApi.retryOcr(currentAttachment.id)
      // Reset local OCR data so the panel shows "Scanning…"
      setOcrData({ ocr_processed: false, has_text: false, ocr_text: '' })
      // Poll every 3 s, up to 20 attempts (60 s total)
      let attempts = 0
      const poll = async () => {
        if (attempts >= 20) {
          setOcrRetrying(false)
          return
        }
        attempts++
        try {
          const res = await attachmentApi.getOcr(currentAttachment.id)
          if (res.data.ocr_processed) {
            setOcrData(res.data)
            setOcrRetrying(false)
          } else {
            setTimeout(poll, 3000)
          }
        } catch (_) {
          setTimeout(poll, 3000)
        }
      }
      setTimeout(poll, 3000)
    } catch (err) {
      const status = err.response?.status
      if (status === 429) {
        setOcrRetryError(t('attachments.ocrRetryRateLimited') || 'Too many retry requests. Please wait.')
      } else {
        setOcrRetryError(t('attachments.ocrRetryError') || 'Re-scan failed. Please try again.')
      }
      setOcrRetrying(false)
    }
  }

  const renderContent = () => {
    switch (fileType) {
      case 'image':
        return (
          <div className="flex items-center justify-center h-full overflow-auto p-4">
            <img
              src={viewUrl}
              alt={currentAttachment.original_filename || 'Attachment'}
              className="max-w-full max-h-full object-contain transition-transform duration-200"
              style={{ transform: `scale(${zoom})` }}
              onLoad={() => setLoading(false)}
              onError={() => {
                setLoading(false)
                setError('Failed to load image')
              }}
            />
          </div>
        )
      
      case 'pdf':
        return (
          <div className="w-full h-full">
            <iframe
              src={viewUrl}
              className="w-full h-full border-0"
              title={currentAttachment.original_filename || 'PDF Document'}
              onLoad={() => setLoading(false)}
              onError={() => {
                setLoading(false)
                setError('Failed to load PDF')
              }}
            />
          </div>
        )
      
      case 'document':
      case 'spreadsheet':
      case 'other':
      default:
        return (
          <div className="flex flex-col items-center justify-center h-full text-gray-400">
            {Icons.file}
            <p className="mt-4 text-lg">{currentAttachment.original_filename || currentAttachment.filename}</p>
            <p className="mt-2 text-sm text-gray-500">
              {t('attachments.previewNotAvailable') || 'Preview not available for this file type'}
            </p>
            <button
              onClick={handleDownload}
              className="mt-4 px-4 py-2 bg-cyan-600 text-white rounded-lg hover:bg-cyan-700 transition-colors flex items-center gap-2"
            >
              {Icons.download}
              {t('common.download') || 'Download'}
            </button>
          </div>
        )
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div 
        className="absolute inset-0 bg-black/90"
        onClick={onClose}
      />
      
      {/* Content */}
      <div className="relative z-10 w-full h-full flex flex-col max-w-6xl max-h-[90vh] mx-4">
        {/* Header */}
        <div className="flex items-center justify-between p-4 text-white">
          <div className="flex items-center gap-4">
            <h3 className="text-lg font-medium truncate max-w-md">
              {currentAttachment.original_filename || currentAttachment.filename}
            </h3>
            {allAttachments.length > 1 && (
              <span className="text-gray-400 text-sm">
                {currentIndex + 1} / {allAttachments.length}
              </span>
            )}
            {/* Show category badge */}
            {currentAttachment.category && (
              <span className="px-2 py-0.5 rounded-full text-xs bg-cyan-500/20 text-cyan-400">
                {t(`attachments.category.${currentAttachment.category}`) || currentAttachment.category}
              </span>
            )}
          </div>
          
          <div className="flex items-center gap-2">
            {/* Zoom controls for images */}
            {fileType === 'image' && (
              <>
                <button
                  onClick={() => setZoom(prev => Math.max(prev - 0.25, 0.5))}
                  className="p-2 hover:bg-white/10 rounded-lg transition-colors"
                  title={t('common.zoomOut') || 'Zoom Out'}
                >
                  {Icons.zoomOut}
                </button>
                <span className="text-sm text-gray-400 min-w-[50px] text-center">
                  {Math.round(zoom * 100)}%
                </span>
                <button
                  onClick={() => setZoom(prev => Math.min(prev + 0.25, 3))}
                  className="p-2 hover:bg-white/10 rounded-lg transition-colors"
                  title={t('common.zoomIn') || 'Zoom In'}
                >
                  {Icons.zoomIn}
                </button>
              </>
            )}
            
            {/* Edit button */}
            <button
              onClick={handleOpenEdit}
              className="p-2 hover:bg-white/10 rounded-lg transition-colors"
              title={t('common.edit') || 'Edit'}
            >
              {Icons.edit}
            </button>

            {/* OCR scan button — images only */}
            {fileType === 'image' && (
              <button
                onClick={handleToggleOcr}
                className={`p-2 rounded-lg transition-colors ${showOcrPanel ? 'bg-cyan-500/30 text-cyan-300' : 'hover:bg-white/10'}`}
                title={t('attachments.ocrText') || 'Scanned Text'}
              >
                {Icons.scan}
              </button>
            )}
            
            {/* Download button */}
            <button
              onClick={handleDownload}
              className="p-2 hover:bg-white/10 rounded-lg transition-colors"
              title={t('common.download') || 'Download'}
            >
              {Icons.download}
            </button>
            
            {/* Close button */}
            <button
              onClick={onClose}
              className="p-2 hover:bg-white/10 rounded-lg transition-colors"
              title={t('common.close') || 'Close'}
            >
              {Icons.close}
            </button>
          </div>
        </div>
        
        {/* Main content area */}
        <div className="flex-1 relative bg-gray-900/50 rounded-lg overflow-hidden">
          {/* Loading spinner */}
          {loading && fileType !== 'other' && (
            <div className="absolute inset-0 flex items-center justify-center bg-gray-900/50 z-10">
              <div className="w-10 h-10 border-4 border-cyan-500 border-t-transparent rounded-full animate-spin" />
            </div>
          )}
          
          {/* Error message */}
          {error && (
            <div className="absolute inset-0 flex items-center justify-center bg-gray-900/50 z-10">
              <div className="text-red-400 text-center">
                <p>{error}</p>
                <button
                  onClick={handleDownload}
                  className="mt-4 px-4 py-2 bg-cyan-600 text-white rounded-lg hover:bg-cyan-700 transition-colors"
                >
                  {t('common.download') || 'Download'} {t('common.instead') || 'instead'}
                </button>
              </div>
            </div>
          )}
          
          {renderContent()}
        </div>

        {/* OCR Panel — slides in below the image when scan button is active */}
        {showOcrPanel && fileType === 'image' && (
          <div className="bg-gray-900/80 border-t border-white/10 rounded-b-lg p-4 max-h-72 overflow-y-auto">
            <div className="flex items-center justify-between mb-2">
              <span className="flex items-center gap-2 text-sm font-medium text-cyan-300">
                {Icons.scan}
                {t('attachments.ocrText') || 'Scanned Text'}
              </span>
              <div className="flex items-center gap-1">
                {ocrData?.has_text && (
                  <button
                    onClick={handleParseOcr}
                    disabled={ocrParsing}
                    className="flex items-center gap-1 text-xs text-purple-300 hover:text-white transition-colors px-2 py-1 rounded hover:bg-white/10 disabled:opacity-50"
                    title={t('attachments.ocrExtract') || 'Extract Data with AI'}
                  >
                    {ocrParsing ? (
                      <div className="w-3 h-3 border-2 border-purple-400 border-t-transparent rounded-full animate-spin flex-shrink-0" />
                    ) : Icons.wand}
                    {ocrParsing
                      ? (t('attachments.ocrExtracting') || 'Extracting…')
                      : (t('attachments.ocrExtract') || 'Extract Data')}
                  </button>
                )}
                {ocrData?.has_text && (
                  <button
                    onClick={handleCopyOcr}
                    className="flex items-center gap-1 text-xs text-gray-400 hover:text-white transition-colors px-2 py-1 rounded hover:bg-white/10"
                  >
                    {Icons.copy}
                    {ocrCopied ? (t('attachments.ocrCopied') || 'Copied!') : (t('attachments.copyText') || 'Copy')}
                  </button>
                )}
              </div>
            </div>
            {ocrLoading ? (
              <div className="flex items-center gap-2 text-sm text-gray-400">
                <div className="w-4 h-4 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin flex-shrink-0" />
                {t('attachments.ocrPending') || 'Scanning…'}
              </div>
            ) : !ocrData?.ocr_processed ? (
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm text-gray-500 italic">
                  {ocrRetrying
                    ? (t('attachments.ocrRetrying') || 'Re-scanning…')
                    : (t('attachments.ocrPending') || 'Scan in progress — check back in a moment.')}
                </p>
                {!ocrRetrying && (
                  <button
                    onClick={handleRetryOcr}
                    className="flex-shrink-0 flex items-center gap-1 text-xs text-cyan-400 hover:text-white px-2 py-1 rounded hover:bg-white/10 transition-colors touch-manipulation min-h-[36px]"
                    title={t('attachments.ocrRetry') || 'Re-scan'}
                  >
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
                    </svg>
                    {t('attachments.ocrRetry') || 'Re-scan'}
                  </button>
                )}
              </div>
            ) : ocrData?.has_text ? (
              <>
                <pre className="text-xs text-gray-300 whitespace-pre-wrap font-mono leading-relaxed">
                  {ocrData.ocr_text}
                </pre>

                {/* AI parse error */}
                {ocrParseError && (
                  <p className="mt-2 text-xs text-red-400">{ocrParseError}</p>
                )}

                {/* AI-parsed structured result */}
                {ocrParsed && (
                  <div className="mt-3 border border-purple-500/30 rounded-lg p-3 bg-purple-900/20">
                    <div className="flex items-center justify-between mb-2">
                      <span className="flex items-center gap-1 text-xs font-semibold text-purple-300">
                        {Icons.wand}
                        {t('attachments.ocrExtractResult') || 'Extracted Receipt Data'}
                      </span>
                      {onPrefill && (
                        <button
                          onClick={handlePrefillForm}
                          className="flex items-center gap-1 text-xs bg-purple-600 hover:bg-purple-700 text-white px-2 py-1 rounded transition-colors"
                        >
                          {Icons.prefill}
                          {t('attachments.ocrPrefill') || 'Pre-fill Form'}
                        </button>
                      )}
                    </div>
                    <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                      {ocrParsed.date && (
                        <>
                          <dt className="text-gray-400">{t('attachments.ocrDate') || 'Date'}</dt>
                          <dd className="text-gray-200">{ocrParsed.date}</dd>
                        </>
                      )}
                      {ocrParsed.vendor && (
                        <>
                          <dt className="text-gray-400">{t('attachments.ocrVendor') || 'Vendor'}</dt>
                          <dd className="text-gray-200 truncate">{ocrParsed.vendor}</dd>
                        </>
                      )}
                      {ocrParsed.amount != null && (
                        <>
                          <dt className="text-gray-400">{t('attachments.ocrAmount') || 'Amount'}</dt>
                          <dd className="text-gray-200">{ocrParsed.amount}</dd>
                        </>
                      )}
                      {ocrParsed.category && (
                        <>
                          <dt className="text-gray-400">{t('common.category') || 'Category'}</dt>
                          <dd className="text-gray-200 capitalize">{ocrParsed.category}</dd>
                        </>
                      )}
                    </dl>
                    {ocrParsed.line_items?.length > 0 && (
                      <div className="mt-2">
                        <p className="text-gray-400 text-xs mb-1">{t('attachments.ocrLineItems') || 'Line Items'}</p>
                        <ul className="space-y-0.5">
                          {ocrParsed.line_items.map((item, i) => (
                            <li key={i} className="flex justify-between text-xs text-gray-300">
                              <span className="truncate max-w-[160px]">{item.description}</span>
                              {item.cost != null && <span className="ml-2 flex-shrink-0">{item.cost}</span>}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
              </>
            ) : (
              <div className="space-y-2">
                <p className="text-sm text-gray-500 italic">
                  {t('attachments.ocrEmpty') || 'No text detected in this image.'}
                </p>
                {ocrRetryError && (
                  <p className="text-xs text-red-400">{ocrRetryError}</p>
                )}
                <button
                  onClick={handleRetryOcr}
                  disabled={ocrRetrying}
                  className="flex items-center gap-1.5 text-xs text-cyan-400 hover:text-white px-3 py-1.5 rounded border border-cyan-500/30 hover:border-cyan-400/60 hover:bg-white/5 transition-colors disabled:opacity-50 touch-manipulation min-h-[36px]"
                >
                  {ocrRetrying ? (
                    <>
                      <div className="w-3 h-3 border border-cyan-400 border-t-transparent rounded-full animate-spin flex-shrink-0" />
                      {t('attachments.ocrRetrying') || 'Re-scanning…'}
                    </>
                  ) : (
                    <>
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
                      </svg>
                      {t('attachments.ocrRetry') || 'Re-scan'}
                    </>
                  )}
                </button>
              </div>
            )}
          </div>
        )}
        
        {/* Thumbnail strip — multi-attachment navigation with OCR status badges */}
        {allAttachments.length > 1 && (
          <div
            className="flex gap-2 px-3 py-2 overflow-x-auto overscroll-x-contain bg-gray-900/70 border-t border-white/10"
            style={{ scrollbarWidth: 'thin', scrollbarColor: '#4b5563 transparent' }}
            role="tablist"
            aria-label={t('attachments.stripLabel') || 'Attachments'}
          >
            {allAttachments.map((att, idx) => {
              const isActive = idx === currentIndex
              const isImage = att.file_type?.startsWith('image/')

              // OCR status — only meaningful for images
              let ocrBadge = null
              if (isImage) {
                if (!att.ocr_processed) {
                  ocrBadge = (
                    <span
                      className="absolute top-0.5 right-0.5 w-4 h-4 flex items-center justify-center rounded-full bg-gray-900/80"
                      title={t('attachments.ocrStatusScanning') || 'Scanning…'}
                    >
                      <span className="w-3 h-3 border border-cyan-400 border-t-transparent rounded-full animate-spin block" />
                    </span>
                  )
                } else if (att.has_text) {
                  ocrBadge = (
                    <span
                      className="absolute top-0.5 right-0.5 w-4 h-4 flex items-center justify-center rounded-full bg-emerald-500 text-white text-[9px] font-bold leading-none"
                      title={t('attachments.ocrStatusScanned') || 'Scanned ✓'}
                      aria-label={t('attachments.ocrStatusScanned') || 'Scanned'}
                    >✓</span>
                  )
                } else {
                  ocrBadge = (
                    <span
                      className="absolute top-0.5 right-0.5 w-4 h-4 flex items-center justify-center rounded-full bg-gray-600 text-gray-300 text-[9px] font-bold leading-none"
                      title={t('attachments.ocrStatusNoText') || 'No text'}
                      aria-label={t('attachments.ocrStatusNoText') || 'No text'}
                    >–</span>
                  )
                }
              }

              return (
                <button
                  key={att.id}
                  role="tab"
                  aria-selected={isActive}
                  onClick={() => {
                    setCurrentIndex(idx)
                    setZoom(1)
                    setLoading(true)
                    setError(null)
                  }}
                  className={`relative flex-shrink-0 w-14 h-14 rounded-lg overflow-hidden border-2 transition-all touch-manipulation ${
                    isActive
                      ? 'border-cyan-400 ring-1 ring-cyan-400/50'
                      : 'border-transparent hover:border-white/40'
                  }`}
                  title={att.original_filename || att.filename}
                  aria-label={att.original_filename || att.filename}
                >
                  {isImage ? (
                    <img
                      src={attachmentApi.getViewUrl(att.id)}
                      alt=""
                      className="w-full h-full object-cover"
                      loading="lazy"
                    />
                  ) : (
                    <div className="w-full h-full bg-gray-700 flex items-center justify-center text-gray-400">
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                        <polyline points="14 2 14 8 20 8"/>
                      </svg>
                    </div>
                  )}
                  {ocrBadge}
                </button>
              )
            })}
          </div>
        )}

        {/* Navigation arrows for multiple attachments */}
        {allAttachments.length > 1 && (
          <>
            <button
              onClick={() => {
                if (currentIndex > 0) {
                  setCurrentIndex(prev => prev - 1)
                  setZoom(1)
                  setLoading(true)
                  setError(null)
                }
              }}
              disabled={currentIndex === 0}
              className={`absolute left-6 top-1/2 -translate-y-1/2 p-3 rounded-full bg-black/50 text-white transition-all ${
                currentIndex === 0 ? 'opacity-30 cursor-not-allowed' : 'hover:bg-black/70'
              }`}
            >
              {Icons.chevronLeft}
            </button>
            <button
              onClick={() => {
                if (currentIndex < allAttachments.length - 1) {
                  setCurrentIndex(prev => prev + 1)
                  setZoom(1)
                  setLoading(true)
                  setError(null)
                }
              }}
              disabled={currentIndex === allAttachments.length - 1}
              className={`absolute right-6 top-1/2 -translate-y-1/2 p-3 rounded-full bg-black/50 text-white transition-all ${
                currentIndex === allAttachments.length - 1 ? 'opacity-30 cursor-not-allowed' : 'hover:bg-black/70'
              }`}
            >
              {Icons.chevronRight}
            </button>
          </>
        )}
      </div>
      
      {/* Edit Attachment Modal */}
      {showEditModal && (
        <div 
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 p-4"
          onClick={() => setShowEditModal(false)}
        >
          <div 
            className="bg-[var(--color-bg-card)] rounded-2xl w-full max-w-md overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex items-center justify-between p-4 border-b border-[var(--color-border)]">
              <h3 className="text-base font-semibold text-[var(--color-text)]">
                {t('attachments.editAttachment') || 'Edit Attachment'}
              </h3>
              <button 
                onClick={() => setShowEditModal(false)}
                className="p-1 hover:bg-[var(--color-bg-tertiary)] rounded-lg transition-colors text-[var(--color-text-muted)]"
              >
                {Icons.close}
              </button>
            </div>
            
            {/* Modal Content */}
            <div className="p-4 space-y-4">
              {saveError && (
                <div className="bg-red-500/10 border border-red-500/20 text-red-500 px-3 py-2 rounded-lg text-sm">
                  {saveError}
                </div>
              )}
              
              {/* Description */}
              <div>
                <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                  {t('common.description') || 'Description'}
                </label>
                <textarea
                  value={editDescription}
                  onChange={(e) => setEditDescription(e.target.value)}
                  placeholder={t('attachments.descriptionPlaceholder') || 'Add a description...'}
                  className="input w-full min-h-[80px] resize-none"
                  rows={3}
                />
              </div>
              
              {/* Category */}
              <div>
                <label className="block text-xs text-[var(--color-text-muted)] mb-1">
                  {t('common.category') || 'Category'}
                </label>
                <select
                  value={editCategory}
                  onChange={(e) => setEditCategory(e.target.value)}
                  className="input w-full"
                >
                  {ATTACHMENT_CATEGORIES.map(cat => (
                    <option key={cat} value={cat}>
                      {t(`attachments.category.${cat}`) || cat.charAt(0).toUpperCase() + cat.slice(1)}
                    </option>
                  ))}
                </select>
              </div>
              
              {/* File info (read-only) */}
              <div className="text-xs text-[var(--color-text-muted)] p-3 bg-[var(--color-bg-tertiary)] rounded-lg">
                <p><strong>{t('common.filename') || 'Filename'}:</strong> {currentAttachment.original_filename || currentAttachment.filename}</p>
                <p><strong>{t('common.size') || 'Size'}:</strong> {currentAttachment.file_size ? `${(currentAttachment.file_size / 1024).toFixed(1)} KB` : '-'}</p>
              </div>
            </div>
            
            {/* Modal Footer */}
            <div className="flex gap-3 p-4 border-t border-[var(--color-border)]">
              <button
                onClick={() => setShowEditModal(false)}
                className="flex-1 btn btn-secondary"
                disabled={isSaving}
              >
                {t('common.cancel') || 'Cancel'}
              </button>
              <button
                onClick={handleSaveEdit}
                disabled={isSaving}
                className="flex-1 btn btn-primary"
              >
                {isSaving ? (t('common.saving') || 'Saving...') : (t('common.save') || 'Save')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default AttachmentViewer
