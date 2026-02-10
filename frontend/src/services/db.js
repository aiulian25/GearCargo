/**
 * GearCargo - Database Service (Legacy Compatibility)
 * This file provides backward compatibility while the new db/ module is being adopted
 * 
 * For new code, please import from '../db' instead:
 * 
 * import { db, repositories, isOnline, initializeSync } from '../db'
 */

// Re-export everything from the new db module
export { 
  db,
  isOnline,
  syncFromServer,
  syncVehicleData,
  processOfflineQueue,
  getLastSyncTime,
  clearAllData,
  initializeSync,
  queueOperation,
  getPendingOperations,
  getQueueCount,
  getQueueSummary,
  OperationType,
  EntityType,
  QueueStatus,
  vehicleRepository,
  fuelRepository,
  serviceRepository,
  repairRepository,
  reminderRepository,
  repositories,
} from '../db'

// Legacy syncManager for backward compatibility
export const syncManager = {
  async addToQueue(operation, entity, data) {
    const { queueOperation, OperationType } = await import('../db')
    const opType = operation === 'create' ? OperationType.CREATE 
      : operation === 'update' ? OperationType.UPDATE 
      : OperationType.DELETE
    return queueOperation(opType, entity, data.id, data)
  },
  
  async processQueue() {
    const { processOfflineQueue, isOnline } = await import('../db')
    if (!isOnline()) return
    return processOfflineQueue()
  },
  
  async getQueueCount() {
    const { getQueueCount } = await import('../db')
    return getQueueCount()
  },
}

// Default export for backward compatibility
import { db as database } from '../db'
export default database

