/**
 * Shared Background Sync / Periodic Background Sync tag names.
 *
 * Imported by BOTH the page (src/utils/pwaSync.js) and the service worker
 * (src/sw.js) so the registration side and the event side never drift.
 */

// One-off Background Sync: fired by the browser when connectivity returns.
// Used purely as a reliable wake signal — the SW asks live clients to run the
// authoritative Dexie queue flush (syncService.processOfflineQueue), keeping
// conflict detection + temp-id remapping in one place (the page).
export const FLUSH_QUEUE_SYNC_TAG = 'gearcargo-flush-queue'

// Periodic Background Sync: refreshes the (read-only) reminders cache while the
// app is closed, so reminders are fresh on next open even offline.
export const REMINDER_REFRESH_TAG = 'gearcargo-reminder-refresh'

// Minimum interval between periodic refreshes. The UA may space them out far
// more than this; it is a floor, not a guarantee.
export const REMINDER_REFRESH_MIN_INTERVAL = 12 * 60 * 60 * 1000 // 12 hours
