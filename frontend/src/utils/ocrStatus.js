export const ocrFailed = data => ['failed', 'unavailable'].includes(data?.ocr_state)
export const ocrFinished = data => Boolean(data?.ocr_processed || data?.ocr_state === 'done' || ocrFailed(data))

export function ocrLabel(data, t) {
  if (data?.ocr_error === 'queue_full') return t('ocrQueue.full')
  if (data?.ocr_state === 'unavailable') return t('ocrQueue.unavailable')
  if (ocrFailed(data)) return t('ocrQueue.failed')
  if (data?.ocr_state === 'retry') return t('ocrQueue.retry')
  if (data?.ocr_state === 'running') return t('ocrQueue.running')
  return t('ocrQueue.queued')
}
