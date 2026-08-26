/**
 * Shared Periodic Background Sync tag names.
 *
 * Imported by BOTH the page (src/utils/pwaSync.js) and the service worker
 * (src/sw.js) so the registration side and the event side never drift.
 *
 * Note: offline WRITES are handled entirely by the Workbox background-sync
 * queue in the service worker, which owns its own tag
 * ('workbox-background-sync:gearcargo-sync-queue') — nothing here is involved.
 */

// Periodic Background Sync: refreshes the (read-only) reminders cache while the
// app is closed, so reminders are fresh on next open even offline.
export const REMINDER_REFRESH_TAG = 'gearcargo-reminder-refresh'

// Minimum interval between periodic refreshes. The UA may space them out far
// more than this; it is a floor, not a guarantee.
export const REMINDER_REFRESH_MIN_INTERVAL = 12 * 60 * 60 * 1000 // 12 hours
