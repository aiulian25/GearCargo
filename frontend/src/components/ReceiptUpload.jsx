import { useState, useRef } from 'react'
import { useTranslation } from '../contexts/LanguageContext'

// SVG Icons
const Icons = {
  camera: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
      <circle cx="12" cy="13" r="4"/>
    </svg>
  ),
  upload: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
      <polyline points="17 8 12 3 7 8"/>
      <line x1="12" y1="3" x2="12" y2="15"/>
    </svg>
  ),
  image: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
      <circle cx="8.5" cy="8.5" r="1.5"/>
      <polyline points="21 15 16 10 5 21"/>
    </svg>
  ),
  file: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
      <polyline points="14 2 14 8 20 8"/>
      <line x1="16" y1="13" x2="8" y2="13"/>
      <line x1="16" y1="17" x2="8" y2="17"/>
      <polyline points="10 9 9 9 8 9"/>
    </svg>
  ),
  close: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
    </svg>
  ),
  check: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  ),
}

export default function ReceiptUpload({ onFileSelect, onFileRemove, selectedFile, preview, label, disabled = false }) {
  const { t } = useTranslation()
  const fileInputRef = useRef(null)
  const cameraInputRef = useRef(null)
  const [dragActive, setDragActive] = useState(false)
  const [previewUrl, setPreviewUrl] = useState(preview || null)

  const handleFileSelect = (file) => {
    if (!file) return
    
    // Validate file type
    const allowedTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'application/pdf']
    if (!allowedTypes.includes(file.type)) {
      alert(t('receipt.invalidType') || 'Invalid file type. Please select an image or PDF.')
      return
    }
    
    // Validate file size (max 10MB)
    if (file.size > 10 * 1024 * 1024) {
      alert(t('receipt.tooLarge') || 'File is too large. Maximum size is 10MB.')
      return
    }
    
    // Create preview for images
    if (file.type.startsWith('image/')) {
      const reader = new FileReader()
      reader.onloadend = () => {
        setPreviewUrl(reader.result)
      }
      reader.readAsDataURL(file)
    } else {
      setPreviewUrl(null)
    }
    
    onFileSelect(file)
  }

  const handleBrowseClick = () => {
    fileInputRef.current?.click()
  }

  const handleCameraClick = () => {
    cameraInputRef.current?.click()
  }

  const handleFileChange = (e) => {
    const file = e.target.files?.[0]
    if (file) handleFileSelect(file)
  }

  const handleDrag = (e) => {
    e.preventDefault()
    e.stopPropagation()
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true)
    } else if (e.type === 'dragleave') {
      setDragActive(false)
    }
  }

  const handleDrop = (e) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)
    
    const file = e.dataTransfer.files?.[0]
    if (file) handleFileSelect(file)
  }

  const handleRemove = () => {
    setPreviewUrl(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
    if (cameraInputRef.current) cameraInputRef.current.value = ''
    onFileRemove()
  }

  const formatFileSize = (bytes) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  return (
    <div className="space-y-3">
      <label className="block text-sm font-medium text-[var(--color-text-secondary)]">
        {label || t('receipt.label') || 'Receipt / Document'} ({t('receipt.optional') || 'optional'})
      </label>
      
      {/* Hidden file inputs */}
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*,.pdf"
        onChange={handleFileChange}
        className="hidden"
        disabled={disabled}
      />
      <input
        ref={cameraInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        onChange={handleFileChange}
        className="hidden"
        disabled={disabled}
      />
      
      {!selectedFile ? (
        /* Upload area */
        <div
          className={`
            relative border-2 border-dashed rounded-xl p-6 text-center transition-all
            ${dragActive 
              ? 'border-[var(--color-accent)] bg-[var(--color-accent)]/5' 
              : 'border-[var(--color-border)] hover:border-[var(--color-accent)]/50'
            }
            ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
          `}
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
          onClick={handleBrowseClick}
        >
          <div className="flex flex-col items-center gap-3">
            <div className="w-12 h-12 rounded-full bg-[var(--color-accent)]/10 flex items-center justify-center text-[var(--color-accent)]">
              {Icons.image}
            </div>
            <div>
              <p className="text-sm font-medium text-[var(--color-text-primary)]">
                {t('receipt.dragDrop') || 'Drag & drop or click to browse'}
              </p>
              <p className="text-xs text-[var(--color-text-muted)] mt-1">
                {t('receipt.formats') || 'JPG, PNG, GIF, PDF up to 10MB'}
              </p>
            </div>
          </div>
        </div>
      ) : (
        /* Preview area */
        <div className="relative border border-[var(--color-border)] rounded-xl p-4 bg-[var(--color-bg-tertiary)]">
          <button
            type="button"
            onClick={handleRemove}
            className="absolute top-2 right-2 p-1.5 rounded-full bg-red-500/10 text-red-500 hover:bg-red-500/20 transition-colors"
            disabled={disabled}
          >
            {Icons.close}
          </button>
          
          <div className="flex items-center gap-4">
            {previewUrl ? (
              <div className="w-20 h-20 rounded-lg overflow-hidden bg-[var(--color-bg-secondary)] flex-shrink-0">
                <img 
                  src={previewUrl} 
                  alt="Receipt preview" 
                  className="w-full h-full object-cover"
                />
              </div>
            ) : (
              <div className="w-20 h-20 rounded-lg bg-[var(--color-bg-secondary)] flex items-center justify-center flex-shrink-0 text-[var(--color-text-muted)]">
                {Icons.file}
              </div>
            )}
            
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-[var(--color-accent)]">{Icons.check}</span>
                <p className="text-sm font-medium text-[var(--color-text-primary)] truncate">
                  {selectedFile.name}
                </p>
              </div>
              <p className="text-xs text-[var(--color-text-muted)] mt-1">
                {formatFileSize(selectedFile.size)}
              </p>
            </div>
          </div>
        </div>
      )}
      
      {/* Action buttons */}
      <div className="flex gap-3">
        <button
          type="button"
          onClick={handleBrowseClick}
          disabled={disabled}
          className="flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] hover:bg-[var(--color-bg-tertiary)] transition-colors disabled:opacity-50"
        >
          <span className="text-[var(--color-accent)]">{Icons.upload}</span>
          <span className="text-sm font-medium">{t('receipt.browse') || 'Browse Files'}</span>
        </button>
        
        <button
          type="button"
          onClick={handleCameraClick}
          disabled={disabled}
          className="flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)] hover:bg-[var(--color-bg-tertiary)] transition-colors disabled:opacity-50"
        >
          <span className="text-[var(--color-accent)]">{Icons.camera}</span>
          <span className="text-sm font-medium">{t('receipt.camera') || 'Use Camera'}</span>
        </button>
      </div>
    </div>
  )
}
