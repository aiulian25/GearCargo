/**
 * GearCargo - Offline Queue Manager
 * Manages pending operations when offline and syncs when back online
 */

import db from './database'

// Operation types
export const OperationType = {
  CREATE: 'create',
  UPDATE: 'update',
  DELETE: 'delete',
}

// Entity types
export const EntityType = {
  VEHICLE: 'vehicle',
  FUEL: 'fuel',
  SERVICE: 'service',
  REPAIR: 'repair',
  REMINDER: 'reminder',
  TAX: 'tax',
  INSURANCE: 'insurance',
}

// Queue status
export const QueueStatus = {
  PENDING: 'pending',
  PROCESSING: 'processing',
  FAILED: 'failed',
  COMPLETED: 'completed',
}

/**
 * Add an operation to the offline queue
 */
export async function queueOperation(operation, entity, entityId, data) {
  const item = {
    operation,
    entity,
    entityId: entityId || `temp_${Date.now()}`,
    data,
    timestamp: new Date().toISOString(),
    status: QueueStatus.PENDING,
    retryCount: 0,
  }
  
  const id = await db.offlineQueue.add(item)
  console.log(`[OfflineQueue] Added ${operation} ${entity} to queue (id: ${id})`)
  
  // Notify service worker about new queued item
  notifyServiceWorker('QUEUE_UPDATED', { count: await getQueueCount() })
  
  return id
}

/**
 * Get all pending operations
 */
export async function getPendingOperations() {
  return db.offlineQueue
    .where('status')
    .anyOf([QueueStatus.PENDING, QueueStatus.FAILED])
    .toArray()
}

/**
 * Get queue count
 */
export async function getQueueCount() {
  return db.offlineQueue
    .where('status')
    .anyOf([QueueStatus.PENDING, QueueStatus.FAILED])
    .count()
}

/**
 * Mark an operation as processing
 */
export async function markAsProcessing(id) {
  await db.offlineQueue.update(id, { status: QueueStatus.PROCESSING })
}

/**
 * Mark an operation as completed and remove it
 */
export async function markAsCompleted(id) {
  await db.offlineQueue.delete(id)
  notifyServiceWorker('QUEUE_UPDATED', { count: await getQueueCount() })
}

/**
 * Mark an operation as failed
 */
export async function markAsFailed(id, error) {
  const item = await db.offlineQueue.get(id)
  if (item) {
    await db.offlineQueue.update(id, {
      status: QueueStatus.FAILED,
      error: error?.message || 'Unknown error',
      retryCount: (item.retryCount || 0) + 1,
      lastAttempt: new Date().toISOString(),
    })
  }
}

/**
 * Clear all completed/failed operations older than specified days
 */
export async function clearOldOperations(daysOld = 7) {
  const cutoffDate = new Date()
  cutoffDate.setDate(cutoffDate.getDate() - daysOld)
  
  const oldItems = await db.offlineQueue
    .where('timestamp')
    .below(cutoffDate.toISOString())
    .toArray()
  
  const idsToDelete = oldItems
    .filter(item => item.status === QueueStatus.COMPLETED || item.retryCount >= 5)
    .map(item => item.id)
  
  await db.offlineQueue.bulkDelete(idsToDelete)
  console.log(`[OfflineQueue] Cleared ${idsToDelete.length} old operations`)
}

/**
 * Get a summary of the queue
 */
export async function getQueueSummary() {
  const all = await db.offlineQueue.toArray()
  
  return {
    total: all.length,
    pending: all.filter(i => i.status === QueueStatus.PENDING).length,
    processing: all.filter(i => i.status === QueueStatus.PROCESSING).length,
    failed: all.filter(i => i.status === QueueStatus.FAILED).length,
    byEntity: all.reduce((acc, item) => {
      acc[item.entity] = (acc[item.entity] || 0) + 1
      return acc
    }, {}),
  }
}

/**
 * Notify the service worker about queue changes
 */
function notifyServiceWorker(type, data) {
  if ('serviceWorker' in navigator && navigator.serviceWorker.controller) {
    navigator.serviceWorker.controller.postMessage({ type, ...data })
  }
}

export default {
  queueOperation,
  getPendingOperations,
  getQueueCount,
  markAsProcessing,
  markAsCompleted,
  markAsFailed,
  clearOldOperations,
  getQueueSummary,
  OperationType,
  EntityType,
  QueueStatus,
}
