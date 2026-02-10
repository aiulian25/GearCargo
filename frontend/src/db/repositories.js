/**
 * GearCargo - Offline Data Repository
 * Provides offline-first data access with automatic sync
 */

import db from './database'
import { isOnline } from './syncService'
import { queueOperation, OperationType, EntityType } from './offlineQueue'
import { 
  vehicleApi, 
  fuelApi, 
  serviceApi, 
  repairApi, 
  reminderApi 
} from '../services/api'

/**
 * Generic offline-first repository pattern
 */
class OfflineRepository {
  constructor(entityType, tableName, api) {
    this.entityType = entityType
    this.tableName = tableName
    this.api = api
    this.table = db[tableName]
  }

  /**
   * Get all items - tries local first, then server if online
   */
  async getAll(options = {}) {
    const { forceRefresh = false, vehicleId = null } = options
    
    // If online and force refresh, fetch from server
    if (isOnline() && forceRefresh) {
      try {
        const response = await this.api.getAll(vehicleId)
        const data = this._extractData(response)
        
        // Update local cache
        if (vehicleId) {
          await this.table.where('vehicle_id').equals(vehicleId).delete()
        } else {
          await this.table.clear()
        }
        
        if (data.length > 0) {
          await this.table.bulkPut(data)
        }
        
        return { data, source: 'server' }
      } catch (error) {
        console.warn(`[${this.entityType}] Server fetch failed, using local:`, error)
      }
    }
    
    // Return from local database
    let query = this.table.toCollection()
    
    if (vehicleId) {
      query = this.table.where('vehicle_id').equals(vehicleId)
    }
    
    const data = await query.toArray()
    return { data, source: 'local' }
  }

  /**
   * Get a single item by ID
   */
  async getById(id) {
    // Try local first
    let item = await this.table.get(id)
    
    // If not found locally and online, try server
    if (!item && isOnline()) {
      try {
        const response = await this.api.get(id)
        item = response.data
        
        // Cache locally
        if (item) {
          await this.table.put(item)
        }
      } catch (error) {
        console.warn(`[${this.entityType}] Server fetch failed:`, error)
      }
    }
    
    return item
  }

  /**
   * Create a new item
   */
  async create(data) {
    if (isOnline()) {
      // Try to create on server
      try {
        const response = await this.api.create(data)
        const newItem = response.data[this.entityType] || response.data
        
        // Cache locally
        await this.table.put(newItem)
        
        return { data: newItem, source: 'server', queued: false }
      } catch (error) {
        console.warn(`[${this.entityType}] Server create failed, queueing:`, error)
      }
    }
    
    // Offline or server failed - create locally and queue
    const tempId = `temp_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
    const localItem = {
      ...data,
      id: tempId,
      _isLocal: true,
      _createdAt: new Date().toISOString(),
    }
    
    await this.table.put(localItem)
    await queueOperation(OperationType.CREATE, this.entityType, tempId, data)
    
    return { data: localItem, source: 'local', queued: true }
  }

  /**
   * Update an existing item
   */
  async update(id, data) {
    // Update locally first
    await this.table.update(id, { ...data, _updatedAt: new Date().toISOString() })
    
    if (isOnline()) {
      try {
        const response = await this.api.update(id, data)
        const updatedItem = response.data[this.entityType] || response.data
        
        // Update local cache with server response
        await this.table.put(updatedItem)
        
        return { data: updatedItem, source: 'server', queued: false }
      } catch (error) {
        console.warn(`[${this.entityType}] Server update failed, queueing:`, error)
      }
    }
    
    // Offline or server failed - queue the operation
    await queueOperation(OperationType.UPDATE, this.entityType, id, data)
    
    const localItem = await this.table.get(id)
    return { data: localItem, source: 'local', queued: true }
  }

  /**
   * Delete an item
   */
  async delete(id) {
    // Delete locally first
    await this.table.delete(id)
    
    if (isOnline() && !String(id).startsWith('temp_')) {
      try {
        await this.api.delete(id)
        return { success: true, source: 'server', queued: false }
      } catch (error) {
        console.warn(`[${this.entityType}] Server delete failed, queueing:`, error)
      }
    }
    
    // Queue delete for server (only if it's not a temp local item)
    if (!String(id).startsWith('temp_')) {
      await queueOperation(OperationType.DELETE, this.entityType, id, { id })
    }
    
    return { success: true, source: 'local', queued: !String(id).startsWith('temp_') }
  }

  /**
   * Get items by vehicle
   */
  async getByVehicle(vehicleId, options = {}) {
    return this.getAll({ ...options, vehicleId })
  }

  /**
   * Count items
   */
  async count(vehicleId = null) {
    if (vehicleId) {
      return this.table.where('vehicle_id').equals(vehicleId).count()
    }
    return this.table.count()
  }

  /**
   * Clear all local data
   */
  async clearLocal() {
    await this.table.clear()
  }

  /**
   * Extract data from API response
   */
  _extractData(response) {
    // Handle different response formats
    if (Array.isArray(response.data)) {
      return response.data
    }
    if (response.data?.items) {
      return response.data.items
    }
    if (response.data?.entries) {
      return response.data.entries
    }
    if (response.data?.[`${this.entityType}s`]) {
      return response.data[`${this.entityType}s`]
    }
    return []
  }
}

// Create repository instances for each entity type
export const vehicleRepository = new OfflineRepository(
  EntityType.VEHICLE,
  'vehicles',
  vehicleApi
)

export const fuelRepository = new OfflineRepository(
  EntityType.FUEL,
  'fuelEntries',
  fuelApi
)

export const serviceRepository = new OfflineRepository(
  EntityType.SERVICE,
  'serviceEntries',
  serviceApi
)

export const repairRepository = new OfflineRepository(
  EntityType.REPAIR,
  'repairEntries',
  repairApi
)

export const reminderRepository = new OfflineRepository(
  EntityType.REMINDER,
  'reminders',
  reminderApi
)

export default {
  vehicles: vehicleRepository,
  fuel: fuelRepository,
  services: serviceRepository,
  repairs: repairRepository,
  reminders: reminderRepository,
}
