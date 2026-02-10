/**
 * GearCargo - IndexedDB Database Schema
 * Dexie.js powered offline-first data layer
 */

import Dexie from 'dexie'

// Create the database instance
export const db = new Dexie('GearCargoDB')

// Define database schema with indexes
db.version(1).stores({
  // User settings and preferences
  settings: 'key',
  
  // Vehicles table - core entity
  vehicles: 'id, name, is_active, is_archived, created_at, updated_at, [is_active+is_archived]',
  
  // Fuel entries
  fuelEntries: 'id, vehicle_id, date, created_at, [vehicle_id+date]',
  
  // Service entries
  serviceEntries: 'id, vehicle_id, date, service_type, next_due_date, [vehicle_id+date]',
  
  // Repair entries
  repairEntries: 'id, vehicle_id, date, created_at, [vehicle_id+date]',
  
  // Reminders
  reminders: 'id, vehicle_id, status, due_date, type, [vehicle_id+status], [status+due_date]',
  
  // Tax records
  taxes: 'id, vehicle_id, start_date, end_date, [vehicle_id+start_date]',
  
  // Insurance records
  insurance: 'id, vehicle_id, start_date, end_date, [vehicle_id+start_date]',
  
  // Predictions/recommendations
  predictions: 'id, vehicle_id, type, priority, is_dismissed, [vehicle_id+is_dismissed]',
  
  // Attachments metadata (not the actual files)
  attachments: 'id, vehicle_id, entry_id, category, created_at',
  
  // Dashboard cache
  dashboardCache: 'key, timestamp',
  
  // Offline operation queue - for mutations when offline
  offlineQueue: '++id, operation, entity, entityId, timestamp, status, retryCount',
  
  // Sync metadata - track what's been synced
  syncMeta: 'entity, lastSyncAt, lastModifiedAt',
  
  // Sync conflicts - store conflicts for user resolution
  syncConflicts: '++id, entity, entityId, timestamp, resolved, [entity+entityId], [resolved]',
})

// Add version 2 for future migrations
db.version(2).stores({
  // Same schema - placeholder for future migrations
}).upgrade(tx => {
  // Migration logic would go here
  console.log('Database upgraded to version 2')
})

export default db
