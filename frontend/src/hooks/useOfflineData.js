/**
 * GearCargo - useOfflineData Hook
 * React hook for offline-first data access
 */

import { useState, useEffect, useCallback } from 'react'
import { useLiveQuery } from 'dexie-react-hooks'
import db from '../db/database'
import repositories from '../db/repositories'
import { isOnline, processOfflineQueue, syncFromServer } from '../db/syncService'
import { getQueueCount, getQueueSummary } from '../db/offlineQueue'

/**
 * Hook for accessing vehicles with offline support
 */
export function useOfflineVehicles(options = {}) {
  const { autoRefresh = true } = options
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [syncing, setSyncing] = useState(false)

  // Use Dexie's live query for reactive updates
  const vehicles = useLiveQuery(
    () => db.vehicles.where('is_archived').equals(0).toArray(),
    [],
    []
  )

  const refresh = useCallback(async () => {
    if (!isOnline()) return
    
    setSyncing(true)
    try {
      await repositories.vehicles.getAll({ forceRefresh: true })
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setSyncing(false)
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (autoRefresh && isOnline()) {
      refresh()
    } else {
      setLoading(false)
    }
  }, [autoRefresh, refresh])

  return {
    vehicles: vehicles || [],
    loading,
    error,
    syncing,
    refresh,
    isOnline: isOnline(),
  }
}

/**
 * Hook for accessing a single vehicle's data
 */
export function useOfflineVehicle(vehicleId) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const vehicle = useLiveQuery(
    () => vehicleId ? db.vehicles.get(vehicleId) : null,
    [vehicleId]
  )

  const fuelEntries = useLiveQuery(
    () => vehicleId 
      ? db.fuelEntries.where('vehicle_id').equals(vehicleId).reverse().sortBy('date')
      : [],
    [vehicleId],
    []
  )

  const serviceEntries = useLiveQuery(
    () => vehicleId 
      ? db.serviceEntries.where('vehicle_id').equals(vehicleId).reverse().sortBy('date')
      : [],
    [vehicleId],
    []
  )

  const repairEntries = useLiveQuery(
    () => vehicleId 
      ? db.repairEntries.where('vehicle_id').equals(vehicleId).reverse().sortBy('date')
      : [],
    [vehicleId],
    []
  )

  useEffect(() => {
    setLoading(false)
  }, [vehicle])

  return {
    vehicle,
    fuelEntries: fuelEntries || [],
    serviceEntries: serviceEntries || [],
    repairEntries: repairEntries || [],
    loading,
    error,
    isOnline: isOnline(),
  }
}

/**
 * Hook for accessing reminders with offline support
 */
export function useOfflineReminders(options = {}) {
  const { vehicleId = null, status = null } = options
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const reminders = useLiveQuery(
    async () => {
      let query = db.reminders.toCollection()
      
      if (vehicleId) {
        query = db.reminders.where('vehicle_id').equals(vehicleId)
      }
      
      const all = await query.toArray()
      
      if (status) {
        return all.filter(r => r.status === status)
      }
      
      return all.sort((a, b) => new Date(a.due_date) - new Date(b.due_date))
    },
    [vehicleId, status],
    []
  )

  useEffect(() => {
    setLoading(false)
  }, [reminders])

  return {
    reminders: reminders || [],
    loading,
    error,
    isOnline: isOnline(),
  }
}

/**
 * Hook for offline queue status
 */
export function useOfflineQueue() {
  const [count, setCount] = useState(0)
  const [summary, setSummary] = useState(null)
  const [processing, setProcessing] = useState(false)

  const updateStatus = useCallback(async () => {
    const queueCount = await getQueueCount()
    const queueSummary = await getQueueSummary()
    setCount(queueCount)
    setSummary(queueSummary)
  }, [])

  useEffect(() => {
    updateStatus()
    
    // Listen for queue updates
    const handleQueueUpdate = () => updateStatus()
    window.addEventListener('gearcargo:queue-updated', handleQueueUpdate)
    
    // Poll periodically
    const interval = setInterval(updateStatus, 10000)
    
    return () => {
      window.removeEventListener('gearcargo:queue-updated', handleQueueUpdate)
      clearInterval(interval)
    }
  }, [updateStatus])

  const processQueue = useCallback(async () => {
    if (!isOnline()) return false
    
    setProcessing(true)
    try {
      const result = await processOfflineQueue()
      await updateStatus()
      return result.success
    } finally {
      setProcessing(false)
    }
  }, [updateStatus])

  return {
    count,
    summary,
    processing,
    processQueue,
    hasPending: count > 0,
    isOnline: isOnline(),
  }
}

/**
 * Hook for syncing data
 */
export function useSync() {
  const [syncing, setSyncing] = useState(false)
  const [lastSync, setLastSync] = useState(null)
  const [error, setError] = useState(null)

  const sync = useCallback(async () => {
    if (!isOnline()) {
      setError('Cannot sync while offline')
      return false
    }

    setSyncing(true)
    setError(null)
    
    try {
      // Process pending queue first
      await processOfflineQueue()
      
      // Then sync from server
      const result = await syncFromServer()
      
      if (result.success) {
        setLastSync(new Date())
      } else {
        setError(result.error || 'Sync failed')
      }
      
      return result.success
    } catch (err) {
      setError(err.message)
      return false
    } finally {
      setSyncing(false)
    }
  }, [])

  return {
    sync,
    syncing,
    lastSync,
    error,
    isOnline: isOnline(),
  }
}

export default {
  useOfflineVehicles,
  useOfflineVehicle,
  useOfflineReminders,
  useOfflineQueue,
  useSync,
}
