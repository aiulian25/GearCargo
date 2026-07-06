/**
 * Offline write UX helper (UX-04).
 *
 * The service worker's Background Sync plugin (`gearcargo-sync-queue`) durably
 * queues failed mutating API requests (POST/PUT/PATCH/DELETE) and replays them
 * for up to 24h once connectivity returns. So when a write fails purely because
 * the device is offline, the data is SAFE — the UI should reassure the user
 * ("saved — will sync") instead of showing a failure banner.
 */
import toast from 'react-hot-toast'

/**
 * True when an API mutation rejected because the device is offline: no HTTP
 * response was received AND the browser reports offline — meaning the service
 * worker has queued the request for background sync.
 *
 * Deliberately conservative: a real server error carries a `response` and is
 * NOT treated as offline-saved, and we require `navigator.onLine === false` so
 * an online timeout (which may not be queued) still surfaces as an error.
 */
export function isOfflineWriteError(err) {
  return Boolean(
    err &&
    !err.response &&
    typeof navigator !== 'undefined' &&
    navigator.onLine === false
  )
}

/**
 * Show the standard "saved offline, will sync" confirmation toast. The caller
 * passes its `t` so the copy is localized; a plain-English fallback is used if
 * translation is unavailable.
 */
export function announceOfflineSaved(t) {
  toast.success(
    (t && t('pwa.sync.savedOffline')) ||
      "Saved on this device — we'll sync it when you're back online."
  )
}
