/**
 * GearCargo - Sync Indicator Component
 * Surfaces online/offline state, the number of writes still queued for the
 * server, the last successful sync time, and any sync failures (with retry).
 */

import React, { useState } from 'react'
import { useBackgroundSync } from '../../hooks/useBackgroundSync'
import { useSyncConflicts } from '../../hooks/useSyncConflicts'
import { useTranslation } from '../../contexts/LanguageContext'
import SyncConflictModal from './SyncConflictModal'

export function SyncIndicator({ variant = 'badge' }) {
  const { t, language } = useTranslation()
  const [showConflictModal, setShowConflictModal] = useState(false)

  const {
    isOnline,
    pendingSyncCount,
    hasPendingSync,
    failedCount,
    hasFailed,
    failedItems,
    lastSyncTime,
    isSyncing,
    syncError,
    triggerSync,
  } = useBackgroundSync()

  const { conflictCount, hasConflicts } = useSyncConflicts()

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
      <>
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

          {/* Conflict indicator */}
          {hasConflicts && (
            <button
              type="button"
              onClick={() => setShowConflictModal(true)}
              className="flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400 hover:bg-red-200 dark:hover:bg-red-900/50 transition-colors focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-1 dark:focus:ring-offset-gray-900"
              aria-label={`${t('pwa.sync.conflicts')}: ${conflictCount}`}
            >
              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              {conflictCount}
            </button>
          )}

          {/* Failed writes indicator — distinct from "pending", offers retry */}
          {hasFailed && (
            <button
              type="button"
              onClick={triggerSync}
              disabled={isSyncing || !isOnline}
              className="flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400 hover:bg-red-200 dark:hover:bg-red-900/50 transition-colors disabled:opacity-60 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-1 dark:focus:ring-offset-gray-900"
              aria-label={`${t('pwa.sync.failedChanges')}: ${failedCount} — ${t('pwa.sync.retry')}`}
            >
              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              {failedCount}
            </button>
          )}

          {/* Pending sync indicator */}
          {hasPendingSync && (
            <button
              type="button"
              onClick={triggerSync}
              disabled={isSyncing || !isOnline}
              className={`flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-offset-1 dark:focus:ring-offset-gray-900 ${
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

        {/* Conflict Resolution Modal */}
        <SyncConflictModal
          isOpen={showConflictModal}
          onClose={() => setShowConflictModal(false)}
        />
      </>
    )
  }

  // ── Card variant — detailed status panel ──────────────────────────────────
  if (variant === 'card') {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
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
          <div className="mb-3 p-2 bg-amber-50 dark:bg-amber-900/20 rounded text-xs text-amber-700 dark:text-amber-400">
            {t('pwa.sync.offlineNotice')}
          </div>
        )}

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
        {!hasPendingSync && !hasFailed && (
          <div className="mb-3 flex items-center gap-2 text-sm text-green-600 dark:text-green-400">
            <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            {t('pwa.sync.upToDate')}
          </div>
        )}

        {/* Last sync time (persistent across reloads) */}
        <div className="mb-3 flex items-center justify-between text-sm gap-2">
          <span className="text-gray-600 dark:text-gray-400">{t('pwa.sync.lastSync')}</span>
          <span className="text-gray-900 dark:text-white text-right shrink-0">
            {formatLastSync(lastSyncTime)}
          </span>
        </div>

        {/* Failed writes — surfaced explicitly with detail + retry */}
        {hasFailed && (
          <div className="mb-3 p-2 bg-red-50 dark:bg-red-900/20 rounded">
            <div className="flex items-center justify-between text-sm gap-2 mb-1">
              <span className="font-medium text-red-700 dark:text-red-400">
                {t('pwa.sync.failedChanges')}
              </span>
              <span className="font-medium text-red-700 dark:text-red-400 shrink-0">
                {failedCount}
              </span>
            </div>
            <p className="text-xs text-red-600 dark:text-red-400/80">
              {t('pwa.sync.failedDescription')}
            </p>
            {failedItems.length > 0 && failedItems[0].error && (
              <p className="mt-1 text-xs text-red-500/80 dark:text-red-400/60 break-words line-clamp-2">
                {failedItems[0].error}
              </p>
            )}
          </div>
        )}

        {/* Generic sync error from the last manual attempt */}
        {syncError && (
          <div className="mb-3 p-2 bg-red-50 dark:bg-red-900/20 rounded text-sm text-red-600 dark:text-red-400 break-words">
            {t('pwa.sync.syncError')}: {syncError}
          </div>
        )}

        {/* Sync / Retry action */}
        {(hasPendingSync || hasFailed) && isOnline && (
          <button
            type="button"
            onClick={triggerSync}
            disabled={isSyncing}
            className="w-full mt-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium flex items-center justify-center gap-2 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-800"
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
                {hasFailed ? t('pwa.sync.retry') : t('pwa.sync.syncNow')}
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
      {hasFailed ? (
        <span className="absolute -top-1 -right-1 w-2 h-2 bg-red-500 rounded-full" />
      ) : hasPendingSync ? (
        <span className="absolute -top-1 -right-1 w-2 h-2 bg-amber-500 rounded-full" />
      ) : null}
    </div>
  )
}

export default SyncIndicator
