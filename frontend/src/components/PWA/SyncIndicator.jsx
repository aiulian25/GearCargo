/**
 * GearCargo - Sync Indicator Component
 * Shows background sync status and offline indicator
 */

import React, { useState } from 'react'
import { useBackgroundSync } from '../../hooks/useBackgroundSync'
import { useSyncConflicts } from '../../hooks/useSyncConflicts'
import { useLanguage } from '../../contexts/LanguageContext'
import SyncConflictModal from './SyncConflictModal'

const translations = {
  en: {
    offline: 'Offline',
    online: 'Online',
    syncing: 'Syncing...',
    pendingChanges: 'Pending changes',
    syncNow: 'Sync Now',
    lastSync: 'Last sync',
    syncError: 'Sync error',
    conflicts: 'Conflicts',
  },
  ro: {
    offline: 'Offline',
    online: 'Online',
    syncing: 'Se sincronizează...',
    pendingChanges: 'Modificări în așteptare',
    syncNow: 'Sincronizează',
    lastSync: 'Ultima sincronizare',
    syncError: 'Eroare sincronizare',
    conflicts: 'Conflicte',
  },
  es: {
    offline: 'Sin conexión',
    online: 'En línea',
    syncing: 'Sincronizando...',
    pendingChanges: 'Cambios pendientes',
    syncNow: 'Sincronizar',
    lastSync: 'Última sincronización',
    syncError: 'Error de sincronización',
    conflicts: 'Conflictos',
  },
}

export function SyncIndicator({ variant = 'badge' }) {
  const { language } = useLanguage()
  const t = translations[language] || translations.en
  const [showConflictModal, setShowConflictModal] = useState(false)
  
  const {
    isOnline,
    pendingSyncCount,
    hasPendingSync,
    lastSyncTime,
    isSyncing,
    syncError,
    triggerSync,
  } = useBackgroundSync()

  const { conflictCount, hasConflicts } = useSyncConflicts()

  // Badge variant - compact indicator
  if (variant === 'badge') {
    return (
      <>
        <div className="flex items-center gap-2">
          {/* Online/Offline indicator */}
          <div
            className={`flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium ${
              isOnline
                ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
            }`}
          >
            <span
              className={`w-2 h-2 rounded-full ${
                isOnline ? 'bg-green-500' : 'bg-red-500'
              } ${isOnline ? 'animate-pulse' : ''}`}
            />
            {isOnline ? t.online : t.offline}
          </div>

          {/* Conflict indicator */}
          {hasConflicts && (
            <button
              onClick={() => setShowConflictModal(true)}
              className="flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400 hover:bg-red-200 dark:hover:bg-red-900/50 transition-colors"
            >
              <svg
                className="w-3 h-3"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                />
              </svg>
              {conflictCount}
            </button>
          )}

          {/* Pending sync indicator */}
          {hasPendingSync && (
            <button
              onClick={triggerSync}
              disabled={isSyncing || !isOnline}
              className={`flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium transition-colors ${
                isSyncing
                ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
                : 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400 hover:bg-amber-200 dark:hover:bg-amber-900/50'
            }`}
          >
            {isSyncing ? (
              <>
                <svg
                  className="w-3 h-3 animate-spin"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                  />
                </svg>
                {t.syncing}
              </>
            ) : (
              <>
                <svg
                  className="w-3 h-3"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                  />
                </svg>
                {pendingSyncCount}
              </>
            )}
          </button>
        )}

        {/* Sync error indicator */}
        {syncError && (
          <div className="flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400">
            <svg
              className="w-3 h-3"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
            {t.syncError}
          </div>
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

  // Full variant - detailed card
  if (variant === 'card') {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-medium text-gray-900 dark:text-white">
            Sync Status
          </h3>
          <div
            className={`flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium ${
              isOnline
                ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
            }`}
          >
            <span
              className={`w-2 h-2 rounded-full ${
                isOnline ? 'bg-green-500' : 'bg-red-500'
              }`}
            />
            {isOnline ? t.online : t.offline}
          </div>
        </div>

        {hasPendingSync && (
          <div className="mb-3">
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-600 dark:text-gray-400">
                {t.pendingChanges}
              </span>
              <span className="font-medium text-amber-600 dark:text-amber-400">
                {pendingSyncCount}
              </span>
            </div>
          </div>
        )}

        {lastSyncTime && (
          <div className="mb-3">
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-600 dark:text-gray-400">
                {t.lastSync}
              </span>
              <span className="text-gray-900 dark:text-white">
                {lastSyncTime.toLocaleTimeString()}
              </span>
            </div>
          </div>
        )}

        {syncError && (
          <div className="mb-3 p-2 bg-red-50 dark:bg-red-900/20 rounded text-sm text-red-600 dark:text-red-400">
            {t.syncError}: {syncError}
          </div>
        )}

        {hasPendingSync && isOnline && (
          <button
            onClick={triggerSync}
            disabled={isSyncing}
            className="w-full mt-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white rounded-lg text-sm font-medium flex items-center justify-center gap-2 transition-colors"
          >
            {isSyncing ? (
              <>
                <svg
                  className="w-4 h-4 animate-spin"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                  />
                </svg>
                {t.syncing}
              </>
            ) : (
              <>
                <svg
                  className="w-4 h-4"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                  />
                </svg>
                {t.syncNow}
              </>
            )}
          </button>
        )}
      </div>
    )
  }

  // Minimal variant - just an icon
  return (
    <div className="relative">
      <span
        className={`w-3 h-3 rounded-full ${
          isOnline ? 'bg-green-500' : 'bg-red-500'
        }`}
      />
      {hasPendingSync && (
        <span className="absolute -top-1 -right-1 w-2 h-2 bg-amber-500 rounded-full" />
      )}
    </div>
  )
}

export default SyncIndicator
