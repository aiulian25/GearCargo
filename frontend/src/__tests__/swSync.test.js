/**
 * Unit tests for the service-worker background-sync replay decision
 * (src/swSync.js) — the offline-write path from Step 6 / H3.
 *
 * These lock the exact behaviour: ok → success, 5xx/429 → throw (re-queue),
 * other 4xx → drop + SYNC_REJECTED. A regression here would silently discard a
 * user's offline write while the UI claims it synced.
 */
import { describe, it, expect, vi } from 'vitest'
import { replayQueuedRequest } from '../swSync'

function makeEntry(url = '/api/fuel', method = 'POST') {
  // entry.request.clone() is what onSync fetches; url/method are read for messages.
  return { request: { clone: () => ({ url, method }), url, method } }
}

function okResponse(status = 200) {
  return { ok: status >= 200 && status < 300, status }
}

describe('replayQueuedRequest', () => {
  it('notifies SYNC_SUCCESS and returns success on a 2xx response', async () => {
    const notifyClients = vi.fn()
    const fetchFn = vi.fn().mockResolvedValue(okResponse(200))

    const result = await replayQueuedRequest(makeEntry('/api/fuel', 'POST'), { fetchFn, notifyClients })

    expect(result).toEqual({ status: 'success' })
    expect(notifyClients).toHaveBeenCalledTimes(1)
    expect(notifyClients).toHaveBeenCalledWith({
      type: 'SYNC_SUCCESS', url: '/api/fuel', method: 'POST',
    })
  })

  it('THROWS on 500 so the caller re-queues, and does NOT emit SYNC_REJECTED', async () => {
    const notifyClients = vi.fn()
    const fetchFn = vi.fn().mockResolvedValue(okResponse(500))

    await expect(replayQueuedRequest(makeEntry(), { fetchFn, notifyClients }))
      .rejects.toThrow(/HTTP 500/)
    expect(notifyClients).not.toHaveBeenCalled()   // must be retried, not dropped
  })

  it('THROWS on 429 (rate-limited) — treated as transient, retried later', async () => {
    const notifyClients = vi.fn()
    const fetchFn = vi.fn().mockResolvedValue(okResponse(429))

    await expect(replayQueuedRequest(makeEntry(), { fetchFn, notifyClients }))
      .rejects.toThrow(/HTTP 429/)
    expect(notifyClients).not.toHaveBeenCalled()
  })

  it('THROWS on 503 as well (any 5xx is transient)', async () => {
    const fetchFn = vi.fn().mockResolvedValue(okResponse(503))
    await expect(replayQueuedRequest(makeEntry(), { fetchFn, notifyClients: vi.fn() }))
      .rejects.toThrow(/HTTP 503/)
  })

  it('drops a 401 (session gone) and emits SYNC_REJECTED — never throws', async () => {
    const notifyClients = vi.fn()
    const fetchFn = vi.fn().mockResolvedValue(okResponse(401))

    const result = await replayQueuedRequest(makeEntry('/api/fuel', 'PUT'), { fetchFn, notifyClients })

    expect(result).toEqual({ status: 'rejected', httpStatus: 401 })
    expect(notifyClients).toHaveBeenCalledWith({
      type: 'SYNC_REJECTED', url: '/api/fuel', method: 'PUT', status: 401,
    })
  })

  it('drops a 422 validation error the same way (4xx = permanent)', async () => {
    const notifyClients = vi.fn()
    const fetchFn = vi.fn().mockResolvedValue(okResponse(422))

    const result = await replayQueuedRequest(makeEntry(), { fetchFn, notifyClients })

    expect(result.status).toBe('rejected')
    expect(notifyClients).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'SYNC_REJECTED', status: 422 }))
  })

  it('propagates a genuine network failure (fetch rejects) so the entry re-queues', async () => {
    const notifyClients = vi.fn()
    const fetchFn = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))

    await expect(replayQueuedRequest(makeEntry(), { fetchFn, notifyClients }))
      .rejects.toThrow(/Failed to fetch/)
    expect(notifyClients).not.toHaveBeenCalled()
  })
})
