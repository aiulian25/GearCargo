/**
 * GearCargo - Database Module Index
 * Offline-first data layer with IndexedDB (Dexie.js)
 */

// Core database
export { default as db } from './database'

// Offline queue management
export { 
  queueOperation,
  getPendingOperations,
  getQueueCount,
  getQueueSummary,
  markAsProcessing,
  markAsCompleted,
  markAsFailed,
  clearOldOperations,
  OperationType,
  EntityType,
  QueueStatus,
} from './offlineQueue'

// Sync service
export {
  isOnline,
  syncFromServer,
  syncVehicleData,
  processOfflineQueue,
  getLastSyncTime,
  clearAllData,
  initializeSync,
} from './syncService'

// Conflict management
export {
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
} from './conflictManager'

// Repositories for offline-first data access
export {
  vehicleRepository,
  fuelRepository,
  serviceRepository,
  repairRepository,
  reminderRepository,
} from './repositories'

// Default export for convenience
export { default as repositories } from './repositories'
