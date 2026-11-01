import React from 'react'
import ReceiptDraftReview from './ReceiptDraftReview'
import { useBackgroundSync } from '../../hooks/useBackgroundSync'
import { useTranslation } from '../../contexts/LanguageContext'
import OfflineQueueReview from './OfflineQueueReview'

export function SyncIndicator({ variant = 'badge' }) {
  const { t, language } = useTranslation()

  const {
    receiptVersion,
    receiptCount,
    reviewReceipts,
    statusAvailable,
    isOnline,
    pendingSyncCount,
    hasPendingSync,
    lastSyncTime,
    isSyncing,
    syncError,
    triggerSync,
    pausedCount,
    legacyCount,
    reviewPaused,
  } = useBackgroundSync()

  // Locale-aware, absolute timestamp. Falls back to a plain string if the
  // runtime rejects the locale tag.
  const formatLastSync = (date) => {
    if (!date) return t('pwa.sync.never')
    try {
      return new Date(date).toLocaleString(language, {
        dateStyle: 'medium',
        timeStyle: 'short',
      })
    } catch {
      return new Date(date).toLocaleString()
    }
  }

  // ── Badge variant — compact header indicator ──────────────────────────────
  if (variant === 'badge') {
    return (
      <div className="flex items-center gap-2 flex-wrap">
        {/* Online/Offline indicator */}
        <div
          className={`flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium ${
            isOnline
              ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
              : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
          }`}
          role="status"
          aria-live="polite"
        >
          <span
            className={`w-2 h-2 rounded-full ${
              isOnline ? 'bg-green-500' : 'bg-red-500'
            } ${isOnline ? 'animate-pulse' : ''}`}
          />
          {isOnline ? t('pwa.sync.online') : t('pwa.sync.offline')}
        </div>

        {(pausedCount > 0 || legacyCount > 0 || receiptCount > 0) && <a href="/settings#offline-changes" className="text-xs text-amber-700 dark:text-amber-400 underline">{t('pwa.sync.pausedBadge')}</a>}
        {/* Pending sync indicator */}
        {hasPendingSync && (
          <button
            type="button"
            onClick={triggerSync}
            disabled={isSyncing || !isOnline}
            className={`flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium transition-colors focus:outline-hidden focus:ring-2 focus:ring-offset-1 dark:focus:ring-offset-gray-900 ${
              isSyncing
                ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400 focus:ring-blue-500'
                : 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400 hover:bg-amber-200 dark:hover:bg-amber-900/50 focus:ring-amber-500 disabled:opacity-60 disabled:cursor-not-allowed'
            }`}
            aria-label={`${t('pwa.sync.pendingWrites')}: ${pendingSyncCount} — ${t('pwa.sync.syncNow')}`}
          >
            {isSyncing ? (
              <>
                <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                {t('pwa.sync.syncing')}
              </>
            ) : (
              <>
                <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                {pendingSyncCount}
              </>
            )}
          </button>
        )}
      </div>
    )
  }

  // ── Card variant — detailed status panel ──────────────────────────────────
  if (variant === 'card') {
    return (
      <div id="offline-changes" className="bg-white dark:bg-gray-800 rounded-lg shadow-sm p-4">
        <div className="flex items-center justify-between mb-3 gap-2">
          <h3 className="text-sm font-medium text-gray-900 dark:text-white">
            {t('pwa.sync.syncStatus')}
          </h3>
          <div
            className={`flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium shrink-0 ${
              isOnline
                ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
            }`}
            role="status"
            aria-live="polite"
          >
            <span className={`w-2 h-2 rounded-full ${isOnline ? 'bg-green-500' : 'bg-red-500'}`} />
            {isOnline ? t('pwa.sync.online') : t('pwa.sync.offline')}
          </div>
        </div>

        {/* Offline notice — reassure that data is safe locally */}
        {!isOnline && (
          <div className="mb-3 p-2 bg-amber-50 dark:bg-amber-900/20 rounded-sm text-xs text-amber-700 dark:text-amber-400">
            {t('pwa.sync.offlineNotice')}
          </div>
        )}

        {!statusAvailable && <p className="mb-3 text-sm">{t('pwa.sync.recovery.unavailable')}</p>}

        {/* Pending writes */}
        {hasPendingSync && (
          <div className="mb-3 flex items-center justify-between text-sm gap-2">
            <span className="text-gray-600 dark:text-gray-400">
              {t('pwa.sync.pendingWrites')}
            </span>
            <span className="font-medium text-amber-600 dark:text-amber-400 shrink-0">
              {pendingSyncCount}
            </span>
          </div>
        )}

        {/* Up-to-date state */}
        {statusAvailable && !hasPendingSync && !pausedCount && !legacyCount && !receiptCount && (
          <div className="mb-3 flex items-center gap-2 text-sm text-green-600 dark:text-green-400">
            <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            {t('pwa.sync.upToDate')}
          </div>
        )}

        <OfflineQueueReview pendingSyncCount={pendingSyncCount} pausedCount={pausedCount} legacyCount={legacyCount} reviewPaused={reviewPaused} />

        <ReceiptDraftReview version={receiptVersion} count={receiptCount} reviewReceipts={reviewReceipts} triggerSync={triggerSync} />

        {/* Last sync time */}
        <div className="mb-3 flex items-center justify-between text-sm gap-2">
          <span className="text-gray-600 dark:text-gray-400">{t('pwa.sync.lastSync')}</span>
          <span className="text-gray-900 dark:text-white text-right shrink-0">
            {formatLastSync(lastSyncTime)}
          </span>
        </div>

        {/* Generic sync error from the last manual attempt */}
        {syncError && (
          <div className="mb-3 p-2 bg-red-50 dark:bg-red-900/20 rounded-sm text-sm text-red-600 dark:text-red-400 wrap-break-word">
            {t('pwa.sync.syncError')}: {syncError}
          </div>
        )}

        {/* Sync action */}
        {(hasPendingSync || receiptCount > 0) && isOnline && (
          <button
            type="button"
            onClick={triggerSync}
            disabled={isSyncing}
            className="w-full mt-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium flex items-center justify-center gap-2 transition-colors focus:outline-hidden focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-800"
          >
            {isSyncing ? (
              <>
                <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                {t('pwa.sync.syncing')}
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                {t('pwa.sync.syncNow')}
              </>
            )}
          </button>
        )}
      </div>
    )
  }

  // ── Minimal variant — just a status dot ───────────────────────────────────
  return (
    <div className="relative" role="status" aria-label={isOnline ? t('pwa.sync.online') : t('pwa.sync.offline')}>
      <span className={`block w-3 h-3 rounded-full ${isOnline ? 'bg-green-500' : 'bg-red-500'}`} />
      {hasPendingSync && (
        <span className="absolute -top-1 -right-1 w-2 h-2 bg-amber-500 rounded-full" />
      )}
    </div>
  )
}

export default SyncIndicator
