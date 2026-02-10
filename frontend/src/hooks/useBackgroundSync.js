/**
 * GearCargo - Background Sync Hook
 * Provides sync status and utilities for offline data synchronization
 */

import { useState, useEffect, useCallback } from 'react'

export function useBackgroundSync() {
  const [isOnline, setIsOnline] = useState(navigator.onLine)
  const [pendingSyncCount, setPendingSyncCount] = useState(0)
  const [lastSyncTime, setLastSyncTime] = useState(null)
  const [isSyncing, setIsSyncing] = useState(false)
  const [syncError, setSyncError] = useState(null)

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
  }, [])

  // Listen for messages from service worker about sync status
  useEffect(() => {
    const handleMessage = (event) => {
      if (!event.data) return

      switch (event.data.type) {
        case 'SYNC_SUCCESS':
          console.log('Sync success:', event.data.url)
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
          
        default:
          break
      }
    }

    navigator.serviceWorker?.addEventListener('message', handleMessage)

    return () => {
      navigator.serviceWorker?.removeEventListener('message', handleMessage)
    }
  }, [])

  // Get pending sync count from service worker
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
      setPendingSyncCount(count)
    } catch (error) {
      console.error('Failed to get pending sync count:', error)
    }
  }, [])

  // Trigger a manual sync
  const triggerSync = useCallback(async () => {
    if (!navigator.serviceWorker?.controller || !isOnline) return false

    setIsSyncing(true)
    setSyncError(null)

    try {
      // Try using the Background Sync API first
      if ('sync' in self.registration) {
        await self.registration.sync.register('workbox-background-sync:gearcargo-sync-queue')
      } else {
        // Fallback: Send message to service worker
        const messageChannel = new MessageChannel()
        
        const syncPromise = new Promise((resolve) => {
          messageChannel.port1.onmessage = (event) => {
            resolve(event.data)
          }
        })

        navigator.serviceWorker.controller.postMessage(
          { type: 'FORCE_SYNC' },
          [messageChannel.port2]
        )

        const result = await syncPromise
        if (!result.success) {
          throw new Error(result.error || 'Sync failed')
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

  // Initial count fetch
  useEffect(() => {
    updatePendingCount()
    
    // Update count periodically
    const interval = setInterval(updatePendingCount, 30000) // Every 30 seconds
    
    return () => clearInterval(interval)
  }, [updatePendingCount])

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
