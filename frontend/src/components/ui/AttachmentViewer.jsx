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

  // Handle single attachment or array
  const allAttachments = attachment ? [attachment] : attachments
  const currentAttachment = allAttachments[currentIndex]

  useEffect(() => {
    setCurrentIndex(initialIndex)
    setZoom(1)
    setLoading(true)
    setError(null)
  }, [initialIndex, isOpen])

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
