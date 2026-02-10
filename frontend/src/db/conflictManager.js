/**
 * GearCargo - Sync Conflict Manager
 * Handles detection and resolution of data sync conflicts
 */

import db from './database'

// Conflict resolution strategies
export const ConflictStrategy = {
  KEEP_LOCAL: 'keep_local',    // Use local (offline) version
  KEEP_SERVER: 'keep_server',  // Use server version
  MERGE: 'merge',              // Merge both versions (manual)
}

/**
 * Detect if there's a conflict between local and server data
 * Conflict occurs when:
 * - Local data was modified while offline
 * - Server data was also modified (different updated_at)
 */
export function detectConflict(localData, serverData) {
  if (!localData || !serverData) return false
  
  // Check if local was modified offline
  const localModified = localData._updatedAt || localData._isLocal
  
  // Check if server version is different
  const serverModified = localData.updated_at !== serverData.updated_at
  
  // Conflict if both were modified
  return localModified && serverModified
}

/**
 * Create a conflict record
 */
export async function createConflict(entity, entityId, localData, serverData, operation) {
  const conflict = {
    entity,
    entityId,
    operation,
    localData,
    serverData,
    timestamp: new Date().toISOString(),
    resolved: false,
    resolvedAt: null,
    resolvedStrategy: null,
  }
  
  // Check if conflict already exists
  const existing = await db.syncConflicts
    .where({ entity, entityId })
    .and(c => !c.resolved)
    .first()
  
  if (existing) {
    // Update existing conflict with new data
    await db.syncConflicts.update(existing.id, {
      localData,
      serverData,
      timestamp: new Date().toISOString(),
    })
    return existing.id
  }
  
  const id = await db.syncConflicts.add(conflict)
  console.log(`[Conflict] Created conflict for ${entity}/${entityId}`)
  
  // Dispatch event for UI notification
  dispatchConflictEvent('conflict-created', { id, entity, entityId })
  
  return id
}

/**
 * Get all unresolved conflicts
 */
export async function getUnresolvedConflicts() {
  return db.syncConflicts.where('resolved').equals(0).toArray()
}

/**
 * Get conflict count
 */
export async function getConflictCount() {
  return db.syncConflicts.where('resolved').equals(0).count()
}

/**
 * Get conflict by ID
 */
export async function getConflict(id) {
  return db.syncConflicts.get(id)
}

/**
 * Get conflicts for a specific entity
 */
export async function getConflictsForEntity(entity, entityId) {
  return db.syncConflicts
    .where({ entity, entityId })
    .and(c => !c.resolved)
    .toArray()
}

/**
 * Resolve a conflict with a strategy
 */
export async function resolveConflict(conflictId, strategy, mergedData = null) {
  const conflict = await db.syncConflicts.get(conflictId)
  
  if (!conflict) {
    throw new Error(`Conflict ${conflictId} not found`)
  }
  
  let finalData
  
  switch (strategy) {
    case ConflictStrategy.KEEP_LOCAL:
      finalData = conflict.localData
      break
      
    case ConflictStrategy.KEEP_SERVER:
      finalData = conflict.serverData
      break
      
    case ConflictStrategy.MERGE:
      if (!mergedData) {
        throw new Error('Merged data required for MERGE strategy')
      }
      finalData = mergedData
      break
      
    default:
      throw new Error(`Unknown strategy: ${strategy}`)
  }
  
  // Apply the resolution to local database
  const table = getTableForEntity(conflict.entity)
  if (table) {
    await table.put({
      ...finalData,
      id: conflict.entityId,
      _conflictResolved: true,
      _resolvedAt: new Date().toISOString(),
    })
  }
  
  // Mark conflict as resolved
  await db.syncConflicts.update(conflictId, {
    resolved: true,
    resolvedAt: new Date().toISOString(),
    resolvedStrategy: strategy,
    resolvedData: finalData,
  })
  
  console.log(`[Conflict] Resolved ${conflict.entity}/${conflict.entityId} with ${strategy}`)
  
  // Dispatch event
  dispatchConflictEvent('conflict-resolved', { 
    id: conflictId, 
    entity: conflict.entity, 
    entityId: conflict.entityId,
    strategy 
  })
  
  // If kept local or merged, need to sync to server
  if (strategy !== ConflictStrategy.KEEP_SERVER) {
    return { needsSync: true, data: finalData }
  }
  
  return { needsSync: false, data: finalData }
}

/**
 * Resolve all conflicts with a single strategy
 */
export async function resolveAllConflicts(strategy) {
  const conflicts = await getUnresolvedConflicts()
  const results = []
  
  for (const conflict of conflicts) {
    try {
      const result = await resolveConflict(conflict.id, strategy)
      results.push({ id: conflict.id, success: true, ...result })
    } catch (error) {
      results.push({ id: conflict.id, success: false, error: error.message })
    }
  }
  
  return results
}

/**
 * Dismiss a conflict (keep server version and discard local changes)
 */
export async function dismissConflict(conflictId) {
  return resolveConflict(conflictId, ConflictStrategy.KEEP_SERVER)
}

/**
 * Clear resolved conflicts older than specified days
 */
export async function clearOldConflicts(daysOld = 30) {
  const cutoffDate = new Date()
  cutoffDate.setDate(cutoffDate.getDate() - daysOld)
  
  const oldConflicts = await db.syncConflicts
    .where('resolved')
    .equals(1)
    .filter(c => new Date(c.resolvedAt) < cutoffDate)
    .toArray()
  
  const ids = oldConflicts.map(c => c.id)
  await db.syncConflicts.bulkDelete(ids)
  
  console.log(`[Conflict] Cleared ${ids.length} old conflicts`)
}

/**
 * Get the Dexie table for an entity type
 */
function getTableForEntity(entity) {
  const tableMap = {
    vehicle: db.vehicles,
    fuel: db.fuelEntries,
    service: db.serviceEntries,
    repair: db.repairEntries,
    reminder: db.reminders,
    tax: db.taxes,
    insurance: db.insurance,
  }
  return tableMap[entity]
}

/**
 * Dispatch conflict events for UI updates
 */
function dispatchConflictEvent(type, detail) {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(`gearcargo:${type}`, { detail }))
  }
}

/**
 * Compare two data objects and find differences
 */
export function findDifferences(localData, serverData) {
  const differences = []
  const allKeys = new Set([
    ...Object.keys(localData || {}),
    ...Object.keys(serverData || {}),
  ])
  
  // Exclude internal/meta fields
  const excludeKeys = ['_isLocal', '_updatedAt', '_createdAt', '_conflictResolved', '_resolvedAt', 'updated_at', 'created_at']
  
  for (const key of allKeys) {
    if (excludeKeys.includes(key)) continue
    
    const localValue = localData?.[key]
    const serverValue = serverData?.[key]
    
    if (JSON.stringify(localValue) !== JSON.stringify(serverValue)) {
      differences.push({
        field: key,
        localValue,
        serverValue,
      })
    }
  }
  
  return differences
}

export default {
  ConflictStrategy,
  detectConflict,
  createConflict,
  getUnresolvedConflicts,
  getConflictCount,
  getConflict,
  getConflictsForEntity,
  resolveConflict,
  resolveAllConflicts,
  dismissConflict,
  clearOldConflicts,
  findDifferences,
}
