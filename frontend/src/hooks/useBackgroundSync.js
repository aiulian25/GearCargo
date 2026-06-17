/**
 * GearCargo - Background Sync Hook
 * Provides sync status and utilities for offline data synchronization.
 *
 * The app has two offline mechanisms:
 *   1. The Dexie `offlineQueue` table — the real write queue populated by every
 *      repository mutation (create/update/delete), drained by
 *      syncService.processOfflineQueue(). It carries rich status
 *      (pending / processing / failed) plus per-item error + retryCount.
 *   2. The Workbox background-sync queue in the service worker — a fallback that
 *      only sees raw API requests that reach the SW and fail.
 *
 * This hook merges BOTH so the UI shows the true number of unsynced writes and
 * can surface failures, not just whatever happened to reach the SW queue.
 */

import { useState, useEffect, useCallback } from 'react'
import { registerPeriodicReminderSync } from '../utils/pwaSync'

export function useBackgroundSync() {
  const [isOnline, setIsOnline] = useState(navigator.onLine)
  // Count reported by the Workbox background-sync queue (via the service worker).
  const [swPendingCount, setSwPendingCount] = useState(0)
  // Truth from the Dexie offline queue (the queue repositories actually write to).
  const [queuedWriteCount, setQueuedWriteCount] = useState(0)
  const [failedCount, setFailedCount] = useState(0)
  const [failedItems, setFailedItems] = useState([])
  const [lastSyncTime, setLastSyncTime] = useState(null)
  const [isSyncing, setIsSyncing] = useState(false)
  const [syncError, setSyncError] = useState(null)

  // Read the real offline queue + persistent last-sync time from Dexie.
  const refreshQueueState = useCallback(async () => {
    try {
      const { getQueueSummary, getPendingOperations, getLastSyncTime } = await import('../db')
      const summary = await getQueueSummary()
      // "Waiting to sync" = operations not yet accepted by the server.
      setQueuedWriteCount((summary.pending || 0) + (summary.processing || 0))
      setFailedCount(summary.failed || 0)

      if (summary.failed > 0) {
        const pending = await getPendingOperations()
        setFailedItems(
          pending
            .filter((item) => item.status === 'failed')
            .map((item) => ({
              id: item.id,
              entity: item.entity,
              operation: item.operation,
              error: item.error,
              retryCount: item.retryCount || 0,
            }))
        )
      } else {
        setFailedItems([])
      }

      const last = await getLastSyncTime('all')
      if (last) setLastSyncTime(new Date(last))
    } catch (error) {
      // Dexie unavailable (e.g. private mode) — degrade gracefully, never throw.
      console.error('Failed to read offline queue state:', error)
    }
  }, [])

  // Listen for online/offline status changes
  useEffect(() => {
    const handleOnline = () => {
      setIsOnline(true)
      // Trigger sync when coming back online
      triggerSync()
    }

    const handleOffline = () => {
      setIsOnline(false)
    }

    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)

    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Refresh when the Dexie queue processor finishes a run.
  useEffect(() => {
    const handleSyncComplete = () => {
      setIsSyncing(false)
      setLastSyncTime(new Date())
      setSyncError(null)
      refreshQueueState()
    }

    window.addEventListener('gearcargo:sync-complete', handleSyncComplete)
    return () => window.removeEventListener('gearcargo:sync-complete', handleSyncComplete)
  }, [refreshQueueState])

  // Listen for messages from service worker about sync status
  useEffect(() => {
    const handleMessage = (event) => {
      if (!event.data) return

      switch (event.data.type) {
        case 'SYNC_SUCCESS':
          updatePendingCount()
          refreshQueueState()
          break

        case 'SYNC_COMPLETE':
          setIsSyncing(false)
          setLastSyncTime(new Date())
          setSyncError(null)
          updatePendingCount()
          refreshQueueState()
          break

        case 'SYNC_ERROR':
          setIsSyncing(false)
          setSyncError(event.data.error)
          break

        // offlineQueue.js posts this whenever items are added/completed.
        case 'QUEUE_UPDATED':
          if (typeof event.data.count === 'number') {
            setQueuedWriteCount(event.data.count)
          }
          refreshQueueState()
          break

        // Background Sync fired in the SW (connectivity returned) — run the
        // authoritative Dexie queue flush here in the page, where conflict
        // detection and temp-id remapping live.
        case 'SYNC_NOW':
          setIsSyncing(true)
          import('../db')
            .then(({ processOfflineQueue }) => processOfflineQueue())
            .catch((error) => console.error('SYNC_NOW flush failed:', error))
            .finally(() => {
              setIsSyncing(false)
              updatePendingCount()
              refreshQueueState()
            })
          break

        default:
          break
      }
    }

    navigator.serviceWorker?.addEventListener('message', handleMessage)

    return () => {
      navigator.serviceWorker?.removeEventListener('message', handleMessage)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshQueueState])

  // Get pending sync count from service worker (Workbox queue)
  const updatePendingCount = useCallback(async () => {
    if (!navigator.serviceWorker?.controller) return

    try {
      const messageChannel = new MessageChannel()

      const countPromise = new Promise((resolve) => {
        messageChannel.port1.onmessage = (event) => {
          resolve(event.data.count || 0)
        }
      })

      navigator.serviceWorker.controller.postMessage(
        { type: 'GET_PENDING_SYNC_COUNT' },
        [messageChannel.port2]
      )

      const count = await countPromise
      setSwPendingCount(count)
    } catch (error) {
      console.error('Failed to get pending sync count:', error)
    }
  }, [])

  // Trigger a manual sync — drains the Dexie queue AND nudges the Workbox queue.
  const triggerSync = useCallback(async () => {
    if (!isOnline) return false

    setIsSyncing(true)
    setSyncError(null)

    try {
      // 1. Flush the real (Dexie) offline write queue.
      const { processOfflineQueue } = await import('../db')
      const result = await processOfflineQueue()
      if (result && result.success === false && result.error) {
        throw new Error(result.error)
      }

      // 2. Nudge the Workbox background-sync queue (fallback path).
      if (navigator.serviceWorker?.controller) {
        if ('sync' in self.registration) {
          await self.registration.sync.register(
            'workbox-background-sync:gearcargo-sync-queue'
          )
        } else {
          const messageChannel = new MessageChannel()
          const syncPromise = new Promise((resolve) => {
            messageChannel.port1.onmessage = (event) => resolve(event.data)
          })
          navigator.serviceWorker.controller.postMessage(
            { type: 'FORCE_SYNC' },
            [messageChannel.port2]
          )
          await syncPromise
        }
      }

      setLastSyncTime(new Date())
      await updatePendingCount()
      await refreshQueueState()
      return true
    } catch (error) {
      console.error('Manual sync failed:', error)
      setSyncError(error.message)
      return false
    } finally {
      setIsSyncing(false)
    }
  }, [isOnline, updatePendingCount, refreshQueueState])

  // Register Periodic Background Sync for reminder refresh once (best-effort;
  // only takes effect for an installed PWA with the permission already granted).
  useEffect(() => {
    registerPeriodicReminderSync()
  }, [])

  // Initial fetch + periodic refresh
  useEffect(() => {
    updatePendingCount()
    refreshQueueState()

    const interval = setInterval(() => {
      updatePendingCount()
      refreshQueueState()
    }, 30000) // Every 30 seconds

    return () => clearInterval(interval)
  }, [updatePendingCount, refreshQueueState])

  // The real number of writes still owed to the server: both queues combined.
  const pendingSyncCount = queuedWriteCount + swPendingCount

  return {
    isOnline,
    pendingSyncCount,
    hasPendingSync: pendingSyncCount > 0,
    failedCount,
    hasFailed: failedCount > 0,
    failedItems,
    lastSyncTime,
    isSyncing,
    syncError,
    triggerSync,
    updatePendingCount,
    refreshQueueState,
  }
}

export default useBackgroundSync
