/**
 * Service-worker cache helpers (PWA §4 / SEC-06).
 *
 * The service worker caches per-user, authenticated content so the app is useful
 * offline: data-read API GETs (`api-cache`) and attachment/receipt/vehicle-photo
 * media (`media-cache`). Both MUST be purged whenever the signed-in identity
 * changes — on login, register and logout — so one account's data can never be
 * served to another user (or after sign-out) on a shared device.
 */
// Per-user Cache Storage buckets that must be dropped on any identity change.
const PER_USER_CACHES = ['api-cache', 'media-cache']

export async function clearApiCache() {
  try {
    // The page can delete the Cache Storage entries directly — robust even when
    // there is no active SW controller yet, and it is awaited so callers can
    // rely on the purge being complete before they proceed (SEC-06).
    if (typeof caches !== 'undefined') {
      await Promise.all(PER_USER_CACHES.map((name) => caches.delete(name)))
    }
    // Also notify the active SW (belt-and-suspenders; lets the SW extend this
    // later, e.g. clearing queued mutations, without touching call sites).
    if (typeof navigator !== 'undefined' && navigator.serviceWorker?.controller) {
      navigator.serviceWorker.controller.postMessage({ type: 'CLEAR_API_CACHE' })
    }
  } catch {
    // Best-effort: never let cache cleanup break auth flows.
  }
}

export default clearApiCache
