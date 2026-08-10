/**
 * GearCargo - Database Module Index
 *
 * Only the Dexie handle survives. The former offline-first stack (offlineQueue,
 * conflictManager, repositories, syncService) had no producer — nothing enqueued
 * writes and nothing read the entity cache — so it was removed (Step 20 / L6).
 * `db.settings` is still used by AuthContext/ThemeContext/LanguageContext for the
 * offline profile/theme/language cache.
 */

export { default as db } from './database'
