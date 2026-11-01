// Classify a replay without deleting data or announcing a save. The caller
// persists this result before notifying pages; transport exceptions stay queued.
export async function replayQueuedRequest(entry, { fetchFn, now = Date.now }) {
  const response = await fetchFn(entry.request.clone())
  if (response.ok) return { status: 'success', data: await response.clone().json().catch(() => null) }
  const parsed = await response.clone().json().catch(() => null)
  const body = parsed && typeof parsed === 'object' ? parsed : {}
  const code = ['OFFLINE_IDENTITY_MISMATCH', 'REVISION_CONFLICT', 'OPERATION_KEY_REUSED'].includes(body.code) ? body.code : null
  const error = { httpStatus: response.status, code }
  if ([401, 403].includes(response.status) || code === 'OFFLINE_IDENTITY_MISMATCH') {
    return { status: 'sign_in_required', error }
  }
  if (response.status === 429 || response.status >= 500 || response.status === 408) {
    const after = response.headers.get('Retry-After')
    const delay = after && /^\d+$/.test(after) ? Number(after) * 1000 : Date.parse(after) - now()
    return { status: 'retry', error, retryAt: now() + Math.max(30000, Number.isFinite(delay) ? Math.min(delay, 86400000) : 30000) }
  }
  if (response.status === 409) return { status: 'mutation_conflict', error,
    current: code === 'REVISION_CONFLICT' ? body.current : null }
  return { status: [400, 422].includes(response.status) ? 'validation_failed' : 'rejected', error }
}
