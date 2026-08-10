/**
 * GearCargo - Database Service (compatibility shim)
 *
 * Re-exports the Dexie handle so existing imports (`import { db } from
 * '../services/db'`) keep working. The old sync/queue/repository re-exports and
 * the unused `syncManager` were removed with the dead offline stack (Step 20 / L6).
 */

export { db } from '../db'

import { db as database } from '../db'
export default database
