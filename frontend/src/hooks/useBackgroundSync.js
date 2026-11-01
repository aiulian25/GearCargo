import { useState, useEffect, useCallback } from 'react'
import { registerPeriodicReminderSync } from '../utils/pwaSync'
import { getBoundIdentity, workerMessage } from '../utils/offlineIdentity'

export function useBackgroundSync() {
  const [isOnline, setIsOnline] = useState(navigator.onLine)
  const [status, setStatus] = useState({ count: 0, pausedCount: 0, legacyCount: 0, available: false, lastSyncTime: null })
  const [isSyncing, setIsSyncing] = useState(false)
  const [syncError, setSyncError] = useState(null)
  const updatePendingCount = useCallback(async () => {
    try {
      const result = await workerMessage('GET_PENDING_SYNC_COUNT', { identity: getBoundIdentity() })
      if (!result) { setStatus(previous => ({ ...previous, available: false })); return }
      setStatus(result)
    } catch (error) {
      setStatus(previous => ({ ...previous, available: false }))
      setSyncError(error.message)
    }
  }, [])
  const triggerSync = useCallback(async () => {
    // Read current connectivity; online events can precede React's next render.
    if (!navigator.onLine) return false
    setIsSyncing(true)
    try {
      const result = await workerMessage('FORCE_SYNC', { identity: getBoundIdentity() })
      if (!result) throw new Error('Reload online to enable offline storage.')
      await updatePendingCount()
      if (result.success !== true) throw new Error('Some changes are still waiting. Review unsent changes or try again later.')
      setSyncError(null)
      return true
    } catch (error) { setSyncError(error.message); return false } finally { setIsSyncing(false) }
  }, [updatePendingCount])
  useEffect(() => {
    const online = () => { setIsOnline(true); triggerSync() }
    const offline = () => setIsOnline(false)
    window.addEventListener('online', online)
    window.addEventListener('offline', offline)
    return () => { window.removeEventListener('online', online); window.removeEventListener('offline', offline) }
  }, [triggerSync])
  useEffect(() => {
    const message = event => {
      if (['SYNC_SUCCESS', 'SYNC_QUEUED', 'SYNC_QUEUE_UPDATED', 'SYNC_CONFLICT', 'SYNC_COMPLETE', 'OFFLINE_IDENTITY_SUSPENDED'].includes(event.data?.type)) updatePendingCount()
    }
    const change = () => { updatePendingCount(); if (navigator.onLine && getBoundIdentity()) triggerSync() }
    window.addEventListener('offline-identity-changed', change)
    navigator.serviceWorker?.addEventListener('message', message)
    navigator.serviceWorker?.addEventListener('controllerchange', change)
    registerPeriodicReminderSync()
    updatePendingCount()
    // Also retries when connectivity is nominally online but the server was
    // unavailable, including browsers without SyncManager.
    const interval = setInterval(() => { updatePendingCount(); if (navigator.onLine) triggerSync() }, 30000)
    return () => {
      clearInterval(interval)
      window.removeEventListener('offline-identity-changed', change)
      navigator.serviceWorker?.removeEventListener('message', message)
      navigator.serviceWorker?.removeEventListener('controllerchange', change)
    }
  }, [updatePendingCount, triggerSync])
  const reviewPaused = useCallback(async action => {
    const result = await workerMessage('REVIEW_OFFLINE_QUEUE', { identity: getBoundIdentity(), action })
    if (!result) throw new Error('Reload online to review unsent changes.')
    await updatePendingCount()
    return result
  }, [updatePendingCount])
  const reviewReceipts = useCallback(async action => {
    const result = await workerMessage('REVIEW_RECEIPTS', { identity: getBoundIdentity(), action })
    if (!result) throw new Error('Reload online to review receipt drafts.')
    await updatePendingCount()
    return result
  }, [updatePendingCount])
  return { receiptVersion: status.receiptVersion || '', receiptCount: status.receiptCount || 0, reviewReceipts, isOnline, pendingSyncCount: status.count || 0, hasPendingSync: status.count > 0,
    pausedCount: status.pausedCount || 0, legacyCount: status.legacyCount || 0, statusAvailable: status.available,
    lastSyncTime: status.lastSyncTime ? new Date(status.lastSyncTime) : null, isSyncing, syncError,
    triggerSync, updatePendingCount, reviewPaused }
}
export default useBackgroundSync
