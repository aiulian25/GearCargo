import toast from 'react-hot-toast'

// Deletion committed even when the retryable file cleanup is still pending.
export function notifyPendingCleanup(response, t) {
  if (response?.data?.cleanup?.state !== 'pending') return false
  toast(t('common.deletionCleanupPending'), { duration: 10000, icon: 'ℹ️' })
  return true
}
