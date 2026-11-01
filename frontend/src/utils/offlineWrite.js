import toast from 'react-hot-toast'

// Only the worker's acknowledgment proves storage succeeded. Being offline
// alone says nothing about worker control, storage quota or queue eligibility.
export function isOfflineWriteError(err) {
  return err?.code === 'OFFLINE_QUEUED' && err.response?.data?.code === 'OFFLINE_QUEUED'
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
