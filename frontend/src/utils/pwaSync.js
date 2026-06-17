/**
 * Page-side registration helpers for the Background Sync and Periodic
 * Background Sync APIs. All functions are best-effort and feature-detected:
 * on browsers without support (Safari/Firefox) or without permission they
 * resolve to `false` and never throw, so callers can fire-and-forget.
 */

import {
  FLUSH_QUEUE_SYNC_TAG,
  REMINDER_REFRESH_TAG,
  REMINDER_REFRESH_MIN_INTERVAL,
} from './syncTags'

/**
 * Register a one-off Background Sync so the browser flushes the offline write
 * queue when connectivity returns — even if the tab is later backgrounded.
 * Falls back silently when the SyncManager API is unavailable; the existing
 * `online` listener in syncService still covers those browsers.
 */
export async function registerBackgroundSync() {
  try {
    if (typeof window === 'undefined') return false
    if (!('serviceWorker' in navigator) || !('SyncManager' in window)) return false

    const registration = await navigator.serviceWorker.ready
    await registration.sync.register(FLUSH_QUEUE_SYNC_TAG)
    return true
  } catch {
    // Permission denied, not installed, or unsupported — degrade gracefully.
    return false
  }
}

/**
 * Register Periodic Background Sync for reminder refresh. Only succeeds for an
 * installed PWA on a supporting browser (Chromium) once the user has granted
 * the `periodic-background-sync` permission, so it is purely additive.
 */
export async function registerPeriodicReminderSync() {
  try {
    if (typeof window === 'undefined') return false
    if (!('serviceWorker' in navigator)) return false

    const registration = await navigator.serviceWorker.ready
    if (!('periodicSync' in registration)) return false

    // Don't prompt — only register if the permission is already granted.
    if (navigator.permissions?.query) {
      const status = await navigator.permissions.query({
        name: 'periodic-background-sync',
      })
      if (status.state !== 'granted') return false
    }

    // Avoid stacking duplicate registrations.
    const existing = await registration.periodicSync.getTags?.()
    if (Array.isArray(existing) && existing.includes(REMINDER_REFRESH_TAG)) {
      return true
    }

    await registration.periodicSync.register(REMINDER_REFRESH_TAG, {
      minInterval: REMINDER_REFRESH_MIN_INTERVAL,
    })
    return true
  } catch {
    return false
  }
}
