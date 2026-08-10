/**
 * GearCargo - Background-sync replay helper
 *
 * Extracted from sw.js `onSync` (Step 6 / H3) so the per-entry replay decision
 * can be unit-tested with a mocked fetch. Behaviour is preserved EXACTLY:
 *
 *   - response.ok             → notify SYNC_SUCCESS, return {status:'success'}
 *   - 5xx or 429 (transient)  → THROW, so the caller re-queues the entry (ONE
 *                               unshift) and the browser retries the whole sync
 *                               later. Do NOT unshift here as well.
 *   - other 4xx (permanent)   → notify SYNC_REJECTED (so the UI is not falsely
 *                               told it synced) and return {status:'rejected'};
 *                               the entry is already shifted out, i.e. dropped.
 *
 * fetch() only rejects on a NETWORK failure — an HTTP error status still
 * RESOLVES, which is why the explicit `response.ok` check exists.
 *
 * Dependencies are injected so this stays pure and testable:
 *   fetchFn(request)        performs the network call (self.fetch in the SW)
 *   notifyClients(message)  posts a message to all controlled clients
 */
export async function replayQueuedRequest(entry, { fetchFn, notifyClients }) {
  const response = await fetchFn(entry.request.clone())

  if (!response.ok) {
    if (response.status >= 500 || response.status === 429) {
      // Transient — signal failure; the caller re-queues and the browser retries.
      throw new Error(`Replay failed with HTTP ${response.status}`)
    }
    // Permanent 4xx (401 session gone, 422 validation, …) — drop it, but tell
    // the app so the user is NOT falsely told the write synced.
    await notifyClients({
      type: 'SYNC_REJECTED',
      url: entry.request.url,
      method: entry.request.method,
      status: response.status,
    })
    return { status: 'rejected', httpStatus: response.status }
  }

  await notifyClients({
    type: 'SYNC_SUCCESS',
    url: entry.request.url,
    method: entry.request.method,
  })
  return { status: 'success' }
}
