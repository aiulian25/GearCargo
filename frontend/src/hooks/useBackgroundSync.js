/**
 * GearCargo - Background Sync Hook
 *
 * Reports the state of the ONE real offline write queue: the Workbox
 * background-sync queue in the service worker (it holds API writes that failed
 * while offline and replays them on reconnect). The former Dexie
 * `offlineQueue`/conflict/repository stack had no producer and was removed
 * (Step 20 / L6), so this hook now sources its count solely from the SW's
 * `GET_PENDING_SYNC_COUNT` reply.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import toast from 'react-hot-toast'
import { useTranslation } from '../contexts/LanguageContext'
import { registerPeriodicReminderSync } from '../utils/pwaSync'

export function useBackgroundSync() {
  // Latest translator kept in a ref so the (stable) service-worker message
  // listener always renders the toast in the CURRENT language without being
  // re-registered on every language change.
  const { t } = useTranslation()
  const tRef = useRef(t)
  tRef.current = t

  const [isOnline, setIsOnline] = useState(navigator.onLine)
  // Number of writes queued in the Workbox background-sync queue (from the SW).
  const [swPendingCount, setSwPendingCount] = useState(0)
  const [lastSyncTime, setLastSyncTime] = useState(null)
  const [isSyncing, setIsSyncing] = useState(false)
  const [syncError, setSyncError] = useState(null)

  // Ask the service worker for the Workbox queue length.
  const updatePendingCount = useCallback(async () => {
    if (!navigator.serviceWorker?.controller) return
    try {
      const messageChannel = new MessageChannel()
      const countPromise = new Promise((resolve) => {
        messageChannel.port1.onmessage = (event) => resolve(event.data.count || 0)
      })
      navigator.serviceWorker.controller.postMessage(
        { type: 'GET_PENDING_SYNC_COUNT' },
        [messageChannel.port2]
      )
      setSwPendingCount(await countPromise)
    } catch (error) {
      console.error('Failed to get pending sync count:', error)
    }
  }, [])

  // Manual sync — nudge the Workbox background-sync queue to replay now.
  const triggerSync = useCallback(async () => {
    if (!isOnline) return false

    setIsSyncing(true)
    setSyncError(null)
    try {
      if (navigator.serviceWorker?.controller) {
        // R4-16: this hook runs in the WINDOW, where `self` is `window` and
        // `self.registration` is undefined — the old `'sync' in self.registration`
        // threw a TypeError, so every manual sync reported an error and the
        // fallback below was unreachable. The page-side registration comes from
        // `navigator.serviceWorker.ready` (same pattern as utils/pwaSync.js).
        const registration = await navigator.serviceWorker.ready
        if (registration && 'sync' in registration) {
          await registration.sync.register(
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
      return true
    } catch (error) {
      console.error('Manual sync failed:', error)
      setSyncError(error.message)
      return false
    } finally {
      setIsSyncing(false)
    }
  }, [isOnline, updatePendingCount])

  // Online/offline transitions
  useEffect(() => {
    const handleOnline = () => {
      setIsOnline(true)
      triggerSync()
    }
    const handleOffline = () => setIsOnline(false)

    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)
    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [triggerSync])

  // Service-worker sync messages
  useEffect(() => {
    const handleMessage = (event) => {
      if (!event.data) return

      switch (event.data.type) {
        case 'SYNC_SUCCESS':
          updatePendingCount()
          break

        case 'SYNC_COMPLETE':
          setIsSyncing(false)
          setLastSyncTime(new Date())
          setSyncError(null)
          updatePendingCount()
          break

        case 'SYNC_ERROR':
          setIsSyncing(false)
          setSyncError(event.data.error)
          break

        // H3: a queued offline write was permanently rejected by the server
        // (4xx — session expired, validation, etc.) and dropped by the SW, so
        // the user must NOT be left believing it synced. Surface one de-duped
        // error toast (id collapses multiple rejections in a single run).
        case 'SYNC_REJECTED':
          toast.error(tRef.current('pwa.sync.syncRejected'), {
            id: 'sync-rejected',
            duration: 6000,
          })
          updatePendingCount()
          break

        default:
          break
      }
    }

    navigator.serviceWorker?.addEventListener('message', handleMessage)
    return () => navigator.serviceWorker?.removeEventListener('message', handleMessage)
  }, [updatePendingCount])

  // Register Periodic Background Sync for reminder refresh once (best-effort;
  // only takes effect for an installed PWA with the permission already granted).
  useEffect(() => {
    registerPeriodicReminderSync()
  }, [])

  // Initial fetch + periodic refresh of the Workbox queue count.
  useEffect(() => {
    updatePendingCount()
    const interval = setInterval(updatePendingCount, 30000) // every 30s
    return () => clearInterval(interval)
  }, [updatePendingCount])

  const pendingSyncCount = swPendingCount

  return {
    isOnline,
    pendingSyncCount,
    hasPendingSync: pendingSyncCount > 0,
    lastSyncTime,
    isSyncing,
    syncError,
    triggerSync,
    updatePendingCount,
  }
}

export default useBackgroundSync
