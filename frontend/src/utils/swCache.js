/**
 * Service-worker cache helpers (PWA §4).
 *
 * The service worker caches data-read API GETs (`api-cache`) so the app is
 * useful offline. Because those responses are per-user and authenticated, the
 * cache MUST be purged whenever the signed-in identity changes — on login,
 * register and logout — so one account's data can never be served to another
 * user (or after sign-out) on a shared device.
 */
export async function clearApiCache() {
  try {
    // The page can delete the Cache Storage entry directly — robust even when
    // there is no active SW controller yet.
    if (typeof caches !== 'undefined') {
      await caches.delete('api-cache')
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
