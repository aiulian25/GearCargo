/**
 * GearCargo - Web Share Target Handler
 * Handles shared content from other apps (images, PDFs, text)
 */

import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from '../contexts/LanguageContext'
import toast from 'react-hot-toast'

export default function Share() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { t } = useTranslation()
  const [sharedData, setSharedData] = useState(null)
  const [processing, setProcessing] = useState(true)

  useEffect(() => {
    // Get shared data from URL params (for GET requests)
    const title = searchParams.get('title')
    const text = searchParams.get('text')
    const url = searchParams.get('url')

    // Check if there's any shared content
    if (title || text || url) {
      setSharedData({ title, text, url })
      setProcessing(false)
      
      // Show toast with shared content
      toast.success(t('share.received') || 'Content received!')
      
      // Redirect to appropriate page based on content type
      // For now, redirect to fuel/add if it looks like a receipt
      const content = (text || '').toLowerCase()
      if (content.includes('fuel') || content.includes('gas') || content.includes('petrol')) {
        setTimeout(() => navigate('/fuel/add', { state: { sharedData: { title, text, url } } }), 1500)
      } else if (content.includes('service') || content.includes('repair') || content.includes('maintenance')) {
        setTimeout(() => navigate('/services/add', { state: { sharedData: { title, text, url } } }), 1500)
      } else {
        // Default: go to dashboard after showing the content
        setTimeout(() => navigate('/'), 2000)
      }
    } else {
      // No shared content, redirect to home
      setProcessing(false)
      navigate('/')
    }
  }, [searchParams, navigate, t])

  // Handle POST requests with files (from share_target)
  useEffect(() => {
    async function handleSharedFiles() {
      if ('launchQueue' in window) {
        window.launchQueue.setConsumer(async (launchParams) => {
          if (launchParams.files && launchParams.files.length > 0) {
            const files = []
            for (const fileHandle of launchParams.files) {
              const file = await fileHandle.getFile()
              files.push(file)
            }
            
            if (files.length > 0) {
              setSharedData({ files })
              setProcessing(false)
              toast.success(`${files.length} file(s) received!`)
              
              // Navigate to appropriate page for file upload
              // Could be receipt upload, attachment, etc.
              setTimeout(() => navigate('/fuel/add', { state: { sharedFiles: files } }), 1500)
            }
          }
        })
      }
    }
    
    handleSharedFiles()
  }, [navigate])

  if (processing) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-[var(--color-bg-primary)] p-4">
        <div className="animate-spin rounded-full h-12 w-12 border-4 border-[var(--color-accent)] border-t-transparent mb-4"></div>
        <p className="text-[var(--color-text-secondary)]">
          {t('share.processing') || 'Processing shared content...'}
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-[var(--color-bg-primary)] p-4">
      <div className="card max-w-md w-full p-6 text-center">
        <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-[var(--color-accent)]/20 flex items-center justify-center">
          <svg className="w-8 h-8 text-[var(--color-accent)]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" />
          </svg>
        </div>
        
        <h1 className="text-xl font-bold mb-2">
          {t('share.title') || 'Shared Content'}
        </h1>
        
        {sharedData && (
          <div className="text-left bg-[var(--color-bg-tertiary)] rounded-lg p-4 mb-4">
            {sharedData.title && (
              <p className="text-sm mb-1">
                <span className="font-medium">{t('share.titleLabel') || 'Title'}:</span> {sharedData.title}
              </p>
            )}
            {sharedData.text && (
              <p className="text-sm mb-1">
                <span className="font-medium">{t('share.textLabel') || 'Text'}:</span> {sharedData.text.substring(0, 100)}...
              </p>
            )}
            {sharedData.url && (
              <p className="text-sm truncate">
                <span className="font-medium">{t('share.urlLabel') || 'URL'}:</span> {sharedData.url}
              </p>
            )}
            {sharedData.files && (
              <p className="text-sm">
                <span className="font-medium">{t('share.filesLabel') || 'Files'}:</span> {sharedData.files.length} file(s)
              </p>
            )}
          </div>
        )}
        
        <p className="text-sm text-[var(--color-text-muted)]">
          {t('share.redirecting') || 'Redirecting to the appropriate page...'}
        </p>
      </div>
    </div>
  )
}
