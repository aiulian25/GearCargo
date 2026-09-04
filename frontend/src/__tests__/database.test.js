/**
 * Schema tests for the Dexie database (R4-28).
 *
 * The offline-first stack was removed in Step 20 / L6, but its tables stayed
 * declared — so every install still created thirteen object stores that nothing
 * wrote to or read from. Version 3 drops them.
 *
 * Dexie resolves `db.tables` and `db.verno` from the declared versions without
 * opening IndexedDB, so this needs no polyfill and no new dependency.
 */
import { describe, it, expect } from 'vitest'

import { db } from '../db/database'

const DROPPED_TABLES = [
  'vehicles', 'fuelEntries', 'serviceEntries', 'repairEntries', 'reminders',
  'taxes', 'insurance', 'predictions', 'attachments', 'dashboardCache',
  'offlineQueue', 'syncMeta', 'syncConflicts',
]

describe('GearCargoDB schema', () => {
  it('is at version 3', () => {
    expect(db.verno).toBe(3)
  })

  it('keeps only the settings table', () => {
    expect(db.tables.map((table) => table.name)).toEqual(['settings'])
  })

  it.each(DROPPED_TABLES)('no longer declares %s', (name) => {
    expect(db.tables.map((table) => table.name)).not.toContain(name)
  })

  it('still indexes settings by key, which the contexts rely on', () => {
    const settings = db.tables.find((table) => table.name === 'settings')

    expect(settings.schema.primKey.keyPath).toBe('key')
  })
})
