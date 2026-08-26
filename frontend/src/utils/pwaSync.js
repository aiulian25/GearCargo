/**
 * Page-side registration helper for the Periodic Background Sync API.
 * Best-effort and feature-detected: on browsers without support
 * (Safari/Firefox) or without permission it resolves to `false` and never
 * throws, so callers can fire-and-forget.
 *
 * Offline WRITES are replayed by the Workbox background-sync queue inside the
 * service worker, which registers and handles its own tag — no page-side
 * registration is involved.
 */

import { REMINDER_REFRESH_TAG, REMINDER_REFRESH_MIN_INTERVAL } from './syncTags'

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
