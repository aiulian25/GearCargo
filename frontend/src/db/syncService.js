/**
 * GearCargo - Data Sync Service
 * Manages synchronization between local IndexedDB and remote API
 */

import db from './database'
import { 
  vehicleApi, 
  fuelApi, 
  serviceApi, 
  repairApi, 
  reminderApi,
  taxApi,
  insuranceApi,
} from '../services/api'
import { 
  getPendingOperations, 
  markAsProcessing, 
  markAsCompleted, 
  markAsFailed,
  OperationType,
  EntityType,
} from './offlineQueue'
import { detectConflict, createConflict } from './conflictManager'

// Dev-only loggers — Vite replaces import.meta.env.DEV with false at build time
// and tree-shakes the dead branch, so these are zero-cost no-ops in production.
const log = import.meta.env.DEV ? console.log.bind(console) : () => {}
const warn = import.meta.env.DEV ? console.warn.bind(console) : () => {}

// API mapping for each entity type
const apiMap = {
  [EntityType.VEHICLE]: vehicleApi,
  [EntityType.FUEL]: fuelApi,
  [EntityType.SERVICE]: serviceApi,
  [EntityType.REPAIR]: repairApi,
  [EntityType.REMINDER]: reminderApi,
  [EntityType.TAX]: taxApi,
  [EntityType.INSURANCE]: insuranceApi,
}

// Table mapping for each entity type
const tableMap = {
  [EntityType.VEHICLE]: 'vehicles',
  [EntityType.FUEL]: 'fuelEntries',
  [EntityType.SERVICE]: 'serviceEntries',
  [EntityType.REPAIR]: 'repairEntries',
  [EntityType.REMINDER]: 'reminders',
  [EntityType.TAX]: 'taxes',
  [EntityType.INSURANCE]: 'insurance',
}

/**
 * Check if online
 */
export function isOnline() {
  return navigator.onLine
}

/**
 * Check if user is authenticated.
 * S05 — tokens are now httpOnly cookies, invisible to JS.  We rely on the
 * non-secret 'auth_session' flag that AuthContext sets on login/me-success
 * and clears on logout/401.
 */
function isAuthenticated() {
  return !!localStorage.getItem('auth_session')
}

/**
 * Sync all data from the server to local database
 */
export async function syncFromServer() {
  if (!isOnline()) {
    log('[Sync] Offline - skipping server sync')
    return { success: false, reason: 'offline' }
  }

  if (!isAuthenticated()) {
    log('[Sync] Not authenticated - skipping server sync')
    return { success: false, reason: 'not_authenticated' }
  }

  log('[Sync] Starting full sync from server...')
  const results = {}

  try {
    // Sync vehicles
    results.vehicles = await syncEntityFromServer(EntityType.VEHICLE, async () => {
      const response = await vehicleApi.getAll()
      return response.data.vehicles || response.data || []
    })

    // Sync reminders
    results.reminders = await syncEntityFromServer(EntityType.REMINDER, async () => {
      const response = await reminderApi.getAll()
      return response.data.reminders || response.data || []
    })

    // Update sync metadata
    await updateSyncMeta('all', new Date().toISOString())

    log('[Sync] Full sync completed:', results)
    return { success: true, results }
  } catch (error) {
    console.error('[Sync] Full sync failed:', error)
    return { success: false, error: error.message }
  }
}

/**
 * Sync a specific entity type from server
 */
async function syncEntityFromServer(entityType, fetchFn) {
  try {
    const data = await fetchFn()
    const table = db[tableMap[entityType]]
    
    // Clear existing data and insert fresh
    await table.clear()
    
    if (Array.isArray(data) && data.length > 0) {
      await table.bulkPut(data)
    }
    
    await updateSyncMeta(entityType, new Date().toISOString())
    
    return { success: true, count: data.length }
  } catch (error) {
    console.error(`[Sync] Failed to sync ${entityType}:`, error)
    return { success: false, error: error.message }
  }
}

/**
 * Sync a single vehicle's data from server
 */
export async function syncVehicleData(vehicleId) {
  if (!isOnline()) return { success: false, reason: 'offline' }
  if (!isAuthenticated()) return { success: false, reason: 'not_authenticated' }

  log(`[Sync] Syncing data for vehicle ${vehicleId}...`)
  const results = {}

  try {
    // Sync fuel entries for this vehicle
    const fuelResponse = await fuelApi.getByVehicle(vehicleId)
    const fuelEntries = fuelResponse.data.entries || fuelResponse.data || []
    await db.fuelEntries.where('vehicle_id').equals(vehicleId).delete()
    if (fuelEntries.length > 0) {
      await db.fuelEntries.bulkPut(fuelEntries)
    }
    results.fuel = fuelEntries.length

    // Sync service entries
    const serviceResponse = await serviceApi.getByVehicle(vehicleId)
    const serviceEntries = serviceResponse.data.entries || serviceResponse.data || []
    await db.serviceEntries.where('vehicle_id').equals(vehicleId).delete()
    if (serviceEntries.length > 0) {
      await db.serviceEntries.bulkPut(serviceEntries)
    }
    results.services = serviceEntries.length

    // Sync repair entries
    const repairResponse = await repairApi.getByVehicle(vehicleId)
    const repairEntries = repairResponse.data.entries || repairResponse.data || []
    await db.repairEntries.where('vehicle_id').equals(vehicleId).delete()
    if (repairEntries.length > 0) {
      await db.repairEntries.bulkPut(repairEntries)
    }
    results.repairs = repairEntries.length

    log(`[Sync] Vehicle ${vehicleId} sync completed:`, results)
    return { success: true, results }
  } catch (error) {
    console.error(`[Sync] Vehicle ${vehicleId} sync failed:`, error)
    return { success: false, error: error.message }
  }
}

/**
 * Process the offline queue - sync pending operations to server
 */
export async function processOfflineQueue() {
  if (!isOnline()) {
    log('[Sync] Offline - cannot process queue')
    return { success: false, reason: 'offline' }
  }

  if (!isAuthenticated()) {
    log('[Sync] Not authenticated - cannot process queue')
    return { success: false, reason: 'not_authenticated' }
  }

  const pending = await getPendingOperations()
  
  if (pending.length === 0) {
    log('[Sync] No pending operations to process')
    return { success: true, processed: 0 }
  }

  log(`[Sync] Processing ${pending.length} queued operations...`)
  
  let processed = 0
  let failed = 0

  for (const item of pending) {
    try {
      await markAsProcessing(item.id)
      await processQueueItem(item)
      await markAsCompleted(item.id)
      processed++
    } catch (error) {
      console.error(`[Sync] Failed to process queue item ${item.id}:`, error)
      await markAsFailed(item.id, error)
      failed++
    }
  }

  log(`[Sync] Queue processing complete: ${processed} processed, ${failed} failed`)
  
  // Notify UI about sync completion
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('gearcargo:sync-complete', {
      detail: { processed, failed }
    }))
  }

  return { success: true, processed, failed }
}

/**
 * Process a single queue item
 */
async function processQueueItem(item) {
  const { operation, entity, entityId, data } = item
  const entityApi = apiMap[entity]
  
  if (!entityApi) {
    throw new Error(`Unknown entity type: ${entity}`)
  }

  let response
  let newId

  switch (operation) {
    case OperationType.CREATE:
      response = await entityApi.create(data)
      newId = response.data?.id || response.data?.[entity]?.id
      
      // Update local record with server-assigned ID
      if (newId && entityId.startsWith('temp_')) {
        const table = db[tableMap[entity]]
        await table.delete(entityId)
        await table.put({ ...data, id: newId })
      }
      break

    case OperationType.UPDATE:
      // Check for conflicts before updating
      try {
        // Get current server version
        const serverResponse = await entityApi.get(entityId)
        const serverData = serverResponse.data[entity] || serverResponse.data
        
        // Get local version
        const table = db[tableMap[entity]]
        const localData = await table.get(entityId)
        
        // Detect conflict
        if (detectConflict(localData, serverData)) {
          log(`[Sync] Conflict detected for ${entity}/${entityId}`)
          await createConflict(entity, entityId, localData, serverData, operation)
          throw new Error('CONFLICT_DETECTED')
        }
      } catch (error) {
        if (error.message === 'CONFLICT_DETECTED') {
          throw error
        }
        // If we can't fetch server version, proceed with update
        warn(`[Sync] Could not check for conflicts: ${error.message}`)
      }
      
      await entityApi.update(entityId, data)
      break

    case OperationType.DELETE:
      await entityApi.delete(entityId)
      break

    default:
      throw new Error(`Unknown operation: ${operation}`)
  }

  return response
}

/**
 * Update sync metadata
 */
async function updateSyncMeta(entity, timestamp) {
  await db.syncMeta.put({
    entity,
    lastSyncAt: timestamp,
    lastModifiedAt: timestamp,
  })
}

/**
 * Get last sync time for an entity
 */
export async function getLastSyncTime(entity = 'all') {
  const meta = await db.syncMeta.get(entity)
  return meta?.lastSyncAt || null
}

/**
 * Clear all local data (for logout)
 */
export async function clearAllData() {
  log('[Sync] Clearing all local data...')
  
  await Promise.all([
    db.vehicles.clear(),
    db.fuelEntries.clear(),
    db.serviceEntries.clear(),
    db.repairEntries.clear(),
    db.reminders.clear(),
    db.taxes.clear(),
    db.insurance.clear(),
    db.predictions.clear(),
    db.attachments.clear(),
    db.dashboardCache.clear(),
    db.offlineQueue.clear(),
    db.syncMeta.clear(),
  ])
  
  log('[Sync] All local data cleared')
}

/**
 * Initialize sync - call on app startup
 */
export async function initializeSync() {
  log('[Sync] Initializing...')
  
  // Listen for online event
  window.addEventListener('online', async () => {
    log('[Sync] Back online - processing queue...')
    await processOfflineQueue()
    await syncFromServer()
  })
  
  // Initial sync if online
  if (isOnline()) {
    await processOfflineQueue()
    
    // Check if we need a full sync (e.g., first time or stale data)
    const lastSync = await getLastSyncTime('all')
    const syncThreshold = 5 * 60 * 1000 // 5 minutes
    
    if (!lastSync || Date.now() - new Date(lastSync).getTime() > syncThreshold) {
      await syncFromServer()
    }
  }
  
  log('[Sync] Initialization complete')
}

export default {
  isOnline,
  syncFromServer,
  syncVehicleData,
  processOfflineQueue,
  getLastSyncTime,
  clearAllData,
  initializeSync,
}
