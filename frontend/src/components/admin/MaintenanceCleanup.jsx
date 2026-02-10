import { useState, useEffect } from 'react'
import { useTranslation } from '../../contexts/LanguageContext'
import { adminApi } from '../../services/api'

// Icons
const Icons = {
  trash: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
    </svg>
  ),
  refresh: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
    </svg>
  ),
  check: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
    </svg>
  ),
  warning: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
    </svg>
  ),
  database: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
    </svg>
  ),
  file: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
    </svg>
  ),
  archive: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
    </svg>
  ),
}

// Format bytes to human readable
const formatBytes = (bytes) => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

// Get icon for cleanup type
const getTypeIcon = (type) => {
  switch (type) {
    case 'old_backups':
      return Icons.archive
    case 'old_activity_logs':
      return Icons.database
    case 'orphaned_attachments':
      return Icons.file
    default:
      return Icons.trash
  }
}

export default function MaintenanceCleanup() {
  const { t } = useTranslation()
  const [loading, setLoading] = useState(false)
  const [previewing, setPreviewing] = useState(false)
  const [preview, setPreview] = useState(null)
  const [lastCleanup, setLastCleanup] = useState(null)
  const [error, setError] = useState(null)
  const [confirmCleanup, setConfirmCleanup] = useState(false)

  // Load preview on mount
  useEffect(() => {
    loadPreview()
  }, [])

  const loadPreview = async () => {
    setPreviewing(true)
    setError(null)
    try {
      const response = await adminApi.previewCleanup()
      setPreview(response.data)
    } catch (err) {
      console.error('Failed to load cleanup preview:', err)
      setError(err.response?.data?.error || 'Failed to load preview')
    } finally {
      setPreviewing(false)
    }
  }

  const handleCleanup = async () => {
    if (!confirmCleanup) {
      setConfirmCleanup(true)
      return
    }
    
    setLoading(true)
    setError(null)
    try {
      const response = await adminApi.runCleanup()
      setLastCleanup(response.data)
      setPreview(null)
      setConfirmCleanup(false)
      // Reload preview after cleanup
      setTimeout(loadPreview, 500)
    } catch (err) {
      console.error('Cleanup failed:', err)
      setError(err.response?.data?.error || 'Cleanup failed')
    } finally {
      setLoading(false)
    }
  }

  const hasItemsToClean = preview?.items?.some(item => item.count > 0)

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-medium text-[var(--color-text-primary)]">
            {t('admin.maintenance') || 'Maintenance'}
          </h3>
          <p className="text-xs text-[var(--color-text-muted)] mt-1">
            {t('admin.maintenanceDesc') || 'Clean up old data and free disk space'}
          </p>
        </div>
        <button
          onClick={loadPreview}
          disabled={previewing}
          className="p-2 text-[var(--color-text-secondary)] hover:text-[var(--color-accent)] rounded-lg hover:bg-[var(--color-bg-tertiary)] transition-colors disabled:opacity-50"
          title={t('common.refresh') || 'Refresh'}
        >
          <span className={previewing ? 'animate-spin' : ''}>
            {Icons.refresh}
          </span>
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-sm text-red-500 flex items-center gap-2">
          {Icons.warning}
          {error}
        </div>
      )}

      {/* Last Cleanup Success */}
      {lastCleanup && !lastCleanup.preview && (
        <div className="p-3 bg-green-500/10 border border-green-500/20 rounded-lg text-sm text-green-500 flex items-center gap-2">
          {Icons.check}
          <span>
            {t('admin.cleanupSuccess') || 'Cleanup completed!'} {lastCleanup.total_count} {t('admin.itemsRemoved') || 'items removed'} 
            {lastCleanup.total_size > 0 && ` (${formatBytes(lastCleanup.total_size)} ${t('admin.freed') || 'freed'})`}
          </span>
        </div>
      )}

      {/* Preview Items */}
      {previewing ? (
        <div className="text-center py-8 text-[var(--color-text-muted)]">
          <div className="animate-spin w-8 h-8 mx-auto mb-2 border-2 border-[var(--color-accent)] border-t-transparent rounded-full"></div>
          <p className="text-sm">{t('common.loading') || 'Loading...'}</p>
        </div>
      ) : preview ? (
        <div className="space-y-3">
          {preview.items.map((item, index) => (
            <div
              key={item.type}
              className={`p-3 rounded-lg border ${
                item.count > 0 
                  ? 'bg-[var(--color-bg-tertiary)] border-[var(--color-border)]' 
                  : 'bg-[var(--color-bg-secondary)] border-transparent opacity-60'
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className={item.count > 0 ? 'text-[var(--color-accent)]' : 'text-[var(--color-text-muted)]'}>
                    {getTypeIcon(item.type)}
                  </span>
                  <div>
                    <p className="text-sm font-medium text-[var(--color-text-primary)]">
                      {t(`admin.cleanup.${item.type}`) || item.label}
                    </p>
                    <p className="text-xs text-[var(--color-text-muted)]">
                      {item.type === 'old_backups' && (t('admin.cleanup.backupsDesc') || 'Backup files older than 30 days')}
                      {item.type === 'old_activity_logs' && (t('admin.cleanup.logsDesc') || 'Activity logs older than 90 days')}
                      {item.type === 'orphaned_attachments' && (t('admin.cleanup.orphansDesc') || 'Files without database records')}
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  <p className={`text-sm font-medium ${item.count > 0 ? 'text-[var(--color-text-primary)]' : 'text-[var(--color-text-muted)]'}`}>
                    {item.count} {t('admin.items') || 'items'}
                  </p>
                  {item.size > 0 && (
                    <p className="text-xs text-[var(--color-text-muted)]">
                      {formatBytes(item.size)}
                    </p>
                  )}
                </div>
              </div>
            </div>
          ))}

          {/* Total */}
          {hasItemsToClean && (
            <div className="p-3 bg-[var(--color-accent)]/10 border border-[var(--color-accent)]/20 rounded-lg">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-[var(--color-text-primary)]">
                  {t('admin.totalToClean') || 'Total to clean'}
                </span>
                <div className="text-right">
                  <span className="text-sm font-bold text-[var(--color-accent)]">
                    {preview.total_count} {t('admin.items') || 'items'}
                  </span>
                  {preview.total_size > 0 && (
                    <span className="text-xs text-[var(--color-text-muted)] ml-2">
                      ({formatBytes(preview.total_size)})
                    </span>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      ) : null}

      {/* Cleanup Button */}
      <div className="pt-2">
        {!hasItemsToClean ? (
          <div className="text-center py-4 text-[var(--color-text-muted)]">
            <span className="text-green-500 mr-2">{Icons.check}</span>
            <span className="text-sm">{t('admin.nothingToClean') || 'Nothing to clean up!'}</span>
          </div>
        ) : confirmCleanup ? (
          <div className="space-y-3">
            <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-lg text-sm text-amber-600 flex items-start gap-2">
              {Icons.warning}
              <span>{t('admin.cleanupWarning') || 'This action cannot be undone. Are you sure you want to delete these items?'}</span>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setConfirmCleanup(false)}
                className="flex-1 py-2 px-4 text-sm font-medium text-[var(--color-text-secondary)] bg-[var(--color-bg-tertiary)] rounded-lg hover:bg-[var(--color-bg-secondary)] transition-colors"
              >
                {t('common.cancel') || 'Cancel'}
              </button>
              <button
                onClick={handleCleanup}
                disabled={loading}
                className="flex-1 py-2 px-4 text-sm font-medium text-white bg-red-500 rounded-lg hover:bg-red-600 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {loading ? (
                  <>
                    <span className="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full"></span>
                    {t('admin.cleaning') || 'Cleaning...'}
                  </>
                ) : (
                  <>
                    {Icons.trash}
                    {t('admin.confirmCleanup') || 'Yes, Delete'}
                  </>
                )}
              </button>
            </div>
          </div>
        ) : (
          <button
            onClick={handleCleanup}
            disabled={loading || previewing}
            className="w-full py-3 px-4 text-sm font-medium text-white bg-[var(--color-accent)] rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {Icons.trash}
            {t('admin.runCleanup') || 'Run Cleanup'}
          </button>
        )}
      </div>

      {/* Info */}
      <div className="text-xs text-[var(--color-text-muted)] space-y-1 pt-2 border-t border-[var(--color-border)]">
        <p>• {t('admin.cleanup.backupRetention') || 'Backups are kept for 30 days'}</p>
        <p>• {t('admin.cleanup.logRetention') || 'Activity logs are kept for 90 days'}</p>
        <p>• {t('admin.cleanup.orphanInfo') || 'Orphaned files are attachment files without database records'}</p>
      </div>
    </div>
  )
}
