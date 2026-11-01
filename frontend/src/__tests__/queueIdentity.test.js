// @vitest-environment node
import { describe, it, expect, vi } from 'vitest'
import { createAccountQueue } from '../swAccountQueue'
import { isOfflineWrite, identityHeaders } from '../utils/offlinePolicy'
import { mutationOptions, protocolHeaders } from '../utils/mutationProtocol'

const origin = 'https://gearcargo.example'
const A = { owner_id: 1, owner_key: 'a'.repeat(64), generation: '1'.repeat(64) }
const B = { owner_id: 2, owner_key: 'b'.repeat(64), generation: '2'.repeat(64) }
function harness(identity = A) {
  let state = { identity, revision: 'first' }
  const items = [], held = []
  let now = 100000000, committed = null
  const queue = {
    size: async () => items.length,
    getAll: async () => [...items],
    pushRequest: async entry => { const at = items.findIndex(item => item.metadata.id === entry.metadata.id); if (at >= 0) items[at] = entry; else items.push(entry) },
    complete: async entry => { items.splice(items.indexOf(entry), 1); committed = now },
  }
  const store = {
    getState: async () => state,
    bind: async (next, revision) => {
      if (state.revision !== revision) throw new Error('changed')
      state = { identity: next, revision: 'bound' }
      return state
    },
    quarantine: async (entry, reason, details = {}) => {
      held.push({ id: entry.metadata?.id || 'unknown', ownerKey: entry.metadata?.identity?.owner_key || '',
        metadata: entry.metadata, headers: protocolHeaders(entry.request.headers),
        method: entry.request.method, path: new URL(entry.request.url).pathname, body: await entry.request.clone().text(),
        timestamp: entry.timestamp, version: 'held-version', reason, ...details })
      items.splice(items.indexOf(entry), 1)
    },
    lastCommit: async () => committed,
    resume: async (row, entry) => { items.push(entry); held.splice(held.indexOf(row), 1) },
    count: async key => held.filter(x => x.ownerKey === key).length,
    list: async key => held.filter(x => x.ownerKey === key),
    remove: async ids => { for (let i = held.length - 1; i >= 0; i--) if (ids.includes(held[i].id)) held.splice(i, 1) },
    hasQuarantine: async () => held.length > 0,
  }
  const getIdentity = vi.fn(async () => state.identity)
  const fetchFn = vi.fn(async () => new Response('{}', { status: 201 }))
  const notifyClients = vi.fn(async () => {})
  const manager = createAccountQueue({ queue, store, origin, getIdentity, fetchFn, notifyClients, now: () => now })
  const request = (path = '/api/vehicles', method = 'POST', headers = {}) => new Request(origin + path, {
    method, headers: { 'Content-Type': 'application/json', ...identityHeaders(identity), ...mutationOptions(123).headers, ...headers },
    body: method === 'DELETE' ? null : JSON.stringify({ name: 'A draft' }),
  })
  return { manager, items, held, request, getIdentity, fetchFn, notifyClients,
    advance: ms => { now += ms },
    change: (next, revision = 'changed') => { state = { identity: next, revision } } }
}

describe('offline operation allowlist', () => {
  it.each(['vehicles', 'fuel', 'services', 'repairs', 'taxes', 'parking', 'insurance', 'consumables', 'todos', 'reminders'])('permits ordinary %s records', resource => {
    expect(isOfflineWrite(new URL(`/api/${resource}`, origin), 'POST', origin)).toBe(true)
    for (const method of ['PUT', 'PATCH', 'DELETE']) expect(isOfflineWrite(new URL(`/api/${resource}/1`, origin), method, origin)).toBe(true)
  })
  it.each(['/api/auth/login', '/api/auth/logout', '/api/auth/register', '/api/auth/password', '/api/auth/2fa/verify',
    '/api/auth/security-questions', '/api/admin/users', '/api/backup/restore', '/api/backup/export', '/api/reports/shares',
    '/api/vehicles/1/chat', '/api/vehicles/chat', '/api/vehicles/1/photo', '/api/vehicles/1?hard=true',
    '/api/attachments', '/api/todos/1/complete', '/api/reminders/1/complete', '/api/vehicles/reorder',
    '/api/vehicles/1/archive', '/api/vehicles/1/health/actions/complete'])('never queues %s', path => {
    for (const method of ['POST', 'PUT', 'PATCH', 'DELETE']) expect(isOfflineWrite(new URL(path, origin), method, origin)).toBe(false)
  })
  it('rejects another origin even when its pathname matches', () => {
    expect(isOfflineWrite(new URL('https://other.example/api/vehicles'), 'POST', origin)).toBe(false)
  })
})

it('replays for the original account and captures no credential headers', async () => {
  const h = harness()
  expect(await h.manager.enqueue(h.request('/api/vehicles', 'POST', { 'X-Private-Header': 'secret' }))).toBe(true)
  expect(h.items[0].metadata.identity).toEqual(A)
  expect(h.items[0].request.headers.get('X-Private-Header')).toBeNull()
  await h.manager.replay()
  expect(h.fetchFn).toHaveBeenCalledTimes(1)
  expect(h.fetchFn.mock.calls[0][0].headers.get('X-GearCargo-Offline-Owner')).toBe(A.owner_key)
  expect(h.items).toHaveLength(0)
  expect(h.held).toHaveLength(0)
})

it('A offline → logout → B login never sends A data and only A can export/discard it', async () => {
  const h = harness()
  await h.manager.enqueue(h.request())
  h.change(null)
  await h.manager.suspend('changed')
  expect(h.items).toHaveLength(0)
  expect(h.held).toHaveLength(1)
  h.change(B)
  await h.manager.replay()
  expect(h.fetchFn).not.toHaveBeenCalled()
  expect((await h.manager.status(B)).pausedCount).toBe(0)
  expect((await h.manager.review(B, 'export')).entries).toEqual([])
  await expect(h.manager.review(A, 'export')).rejects.toThrow()
  h.change({ ...A, generation: '3'.repeat(64) })
  const newA = { ...A, generation: '3'.repeat(64) }
  expect((await h.manager.review(newA, 'export')).entries[0].body).toContain('A draft')
  await h.manager.review(newA, 'discard')
  expect(h.held).toHaveLength(0)
})

it('rejects a stale tab enqueue after another tab switches account', async () => {
  const h = harness()
  h.change(B)
  expect(await h.manager.enqueue(h.request())).toBe(false)
  expect(h.items).toHaveLength(0)
})

it('checks server identity, not just saved local state', async () => {
  const h = harness()
  await h.manager.enqueue(h.request())
  h.getIdentity.mockResolvedValue(B)
  await h.manager.replay()
  expect(h.fetchFn).not.toHaveBeenCalled()
  expect(h.held[0].reason).toBe('sign_in_required')
})

it('checks suspension again after the online identity lookup', async () => {
  const h = harness()
  await h.manager.enqueue(h.request())
  h.getIdentity.mockImplementation(async () => { h.change(null); return A })
  await h.manager.replay()
  expect(h.fetchFn).not.toHaveBeenCalled()
  expect(h.held).toHaveLength(1)
})

it.each([401, 403, 409])('quarantines HTTP %s identity failures without reporting a save', async status => {
  const h = harness()
  await h.manager.enqueue(h.request())
  h.fetchFn.mockResolvedValue(new Response(JSON.stringify({ code: 'OFFLINE_IDENTITY_MISMATCH' }), { status }))
  await h.manager.replay()
  expect(h.held).toHaveLength(1)
  expect(h.notifyClients.mock.calls.some(([m]) => ['SYNC_SUCCESS', 'SYNC_COMPLETE'].includes(m.type))).toBe(false)
})

it('deleted accounts cannot replay or review held data', async () => {
  const h = harness()
  await h.manager.enqueue(h.request())
  h.getIdentity.mockResolvedValue(null)
  await h.manager.replay()
  expect(h.fetchFn).not.toHaveBeenCalled()
  await expect(h.manager.review(A, 'export')).rejects.toThrow()
  await expect(h.manager.review(A, { type: 'resume', id: h.held[0].id, version: h.held[0].version })).rejects.toThrow()
})

it('preserves pending work when identity verification has a network failure', async () => {
  const h = harness()
  await h.manager.enqueue(h.request())
  h.getIdentity.mockRejectedValue(new Error('offline'))
  expect((await h.manager.replay()).success).toBe(false)
  expect(h.items).toHaveLength(1)
  expect(h.held).toHaveLength(0)
})

it('does not persist bearer credentials or multipart uploads', async () => {
  const h = harness()
  expect(await h.manager.enqueue(h.request('/api/vehicles', 'POST', { Authorization: 'Bearer PRIVATE' }))).toBe(false)
  expect(await h.manager.enqueue(h.request('/api/vehicles', 'POST', { 'Content-Type': 'multipart/form-data' }))).toBe(false)
  expect(h.items).toHaveLength(0)
})

it('serializes duplicate sync events so one entry is only fetched once', async () => {
  const h = harness()
  await h.manager.enqueue(h.request())
  await Promise.all([h.manager.replay(), h.manager.replay()])
  expect(h.fetchFn).toHaveBeenCalledTimes(1)
})

it('quarantines unversioned entries instead of assigning them to the current account', async () => {
  const h = harness()
  h.items.push({ request: h.request(), timestamp: Date.now() })
  await h.manager.replay()
  expect(h.fetchFn).not.toHaveBeenCalled()
  expect(h.held[0].ownerKey).toBe('')
  expect((await h.manager.review(A, 'export')).entries).toEqual([])
})

it('preserves the exact operation and base revision through storage and replay', async () => {
  const h = harness()
  const request = h.request('/api/fuel/1', 'PUT')
  const original = request.headers.get('Idempotency-Key')
  expect(await h.manager.enqueue(request)).toBe(true)
  await h.manager.replay()
  const replay = h.fetchFn.mock.calls[0][0]
  expect(replay.headers.get('Idempotency-Key')).toBe(original)
  expect(replay.headers.get('If-Match')).toBe('"123"')
  expect(replay.headers.get('X-GearCargo-Mutation-Version')).toBe('1')
})

it('never replays an older queue item lacking a durable mutation identity', async () => {
  const h = harness()
  await h.manager.enqueue(h.request())
  h.items[0].metadata.version = 1
  await h.manager.replay()
  expect(h.fetchFn).not.toHaveBeenCalled()
  expect(h.held).toHaveLength(1)
})

it.each(['REVISION_CONFLICT', 'OPERATION_KEY_REUSED'])('retains %s for review and never reports success', async code => {
  const h = harness()
  await h.manager.enqueue(h.request('/api/fuel/1', 'PUT'))
  h.fetchFn.mockResolvedValue(new Response(JSON.stringify({ code }), { status: 409 }))
  await h.manager.replay()
  expect(h.held[0].reason).toBe('mutation_conflict')
  expect(h.notifyClients.mock.calls.some(([m]) => ['SYNC_SUCCESS', 'SYNC_COMPLETE'].includes(m.type))).toBe(false)
  expect(h.notifyClients).toHaveBeenCalledWith({ type: 'SYNC_CONFLICT' })
})

it('rejects enqueue without a valid operation ID or edit revision', async () => {
  const h = harness()
  expect(await h.manager.enqueue(h.request('/api/fuel', 'POST', { 'Idempotency-Key': '' }))).toBe(false)
  expect(await h.manager.enqueue(h.request('/api/fuel/1', 'PUT', { 'If-Match': '' }))).toBe(false)
})


it.each([400, 404, 422])('retains HTTP %s with the payload and safe error details', async status => {
  const h = harness()
  await h.manager.enqueue(h.request())
  h.fetchFn.mockResolvedValue(new Response(JSON.stringify({ error: '<script>private stack</script>' }), { status }))
  expect((await h.manager.replay()).success).toBe(false)
  expect(h.items).toHaveLength(0)
  expect(h.held).toHaveLength(1)
  expect(h.held[0].body).toContain('A draft')
  expect(h.held[0].error).toEqual({ httpStatus: status, code: null })
  expect((await h.manager.status(A)).lastSyncTime).toBeNull()
})

it.each([429, 500])('retains HTTP %s and respects persisted backoff', async status => {
  const h = harness()
  await h.manager.enqueue(h.request())
  h.fetchFn.mockResolvedValue(new Response('{}', { status, headers: { 'Retry-After': '60' } }))
  expect((await h.manager.replay()).success).toBe(false)
  await h.manager.replay()
  expect(h.fetchFn).toHaveBeenCalledTimes(1)
  expect(h.items).toHaveLength(1)
  h.advance(61000)
  h.fetchFn.mockResolvedValue(new Response('{}', { status: 201 }))
  expect((await h.manager.replay()).committedCount).toBe(1)
  expect((await h.manager.status(A)).lastSyncTime).not.toBeNull()
})

it('never removes a request while fetch is in progress', async () => {
  const h = harness()
  await h.manager.enqueue(h.request())
  let finish
  h.fetchFn.mockImplementation(() => new Promise(resolve => { finish = resolve }))
  const replay = h.manager.replay()
  await vi.waitFor(() => expect(finish).toBeTypeOf('function'))
  expect(h.items).toHaveLength(1)
  finish(new Response('{}', { status: 201 }))
  await replay
  expect(h.items).toHaveLength(0)
})

it('keeps drafts past retention until explicit same-owner review', async () => {
  const h = harness()
  await h.manager.enqueue(h.request())
  const key = h.items[0].request.headers.get('Idempotency-Key')
  h.advance(86400001)
  await h.manager.replay()
  expect(h.fetchFn).not.toHaveBeenCalled()
  expect(h.held[0].reason).toBe('retention_expired')
  const row = h.held[0]
  await h.manager.review(A, { type: 'resume', id: row.id, version: row.version })
  expect(h.items[0].request.headers.get('Idempotency-Key')).toBe(key)
  expect((await h.manager.replay()).success).toBe(true)
})

it('requires reauthentication after 401, then resumes only the same owner and same operation', async () => {
  const h = harness()
  await h.manager.enqueue(h.request())
  const key = h.items[0].request.headers.get('Idempotency-Key')
  h.fetchFn.mockResolvedValue(new Response('{}', { status: 401 }))
  await h.manager.replay()
  const row = h.held[0], action = { type: 'resume', id: row.id, version: row.version }
  await expect(h.manager.review(A, action)).rejects.toThrow(/Sign in again/)
  h.change(B)
  await expect(h.manager.review(B, action)).rejects.toThrow()
  const next = { ...A, generation: '3'.repeat(64) }
  h.change(next)
  await h.manager.review(next, action)
  expect(h.items[0].request.headers.get('Idempotency-Key')).toBe(key)
  h.fetchFn.mockResolvedValue(new Response('{}', { status: 201 }))
  await h.manager.replay()
  expect(h.fetchFn.mock.lastCall[0].headers.get('X-GearCargo-Offline-Generation')).toBe(next.generation)
})

it('repairs validation with a new key and the edited payload', async () => {
  const h = harness()
  await h.manager.enqueue(h.request())
  const oldKey = h.items[0].request.headers.get('Idempotency-Key')
  h.fetchFn.mockResolvedValue(new Response('{}', { status: 422 }))
  await h.manager.replay()
  const row = h.held[0]
  await h.manager.review(A, { type: 'repair', id: row.id, version: row.version, body: { name: 'Repaired' } })
  expect(h.items[0].request.headers.get('Idempotency-Key')).not.toBe(oldKey)
  expect(await h.items[0].request.clone().json()).toEqual({ name: 'Repaired' })
})

it('uses the conflict revision actually reviewed, never an unseen latest revision', async () => {
  const h = harness()
  await h.manager.enqueue(h.request('/api/vehicles/1', 'PUT'))
  h.fetchFn.mockResolvedValue(new Response(JSON.stringify({ code: 'REVISION_CONFLICT', current: { revision: 124, name: 'Other edit' } }), { status: 409 }))
  await h.manager.replay()
  const row = h.held[0], action = { type: 'repair', id: row.id, version: row.version, body: { name: 'Reviewed edit' } }
  await expect(h.manager.review(A, { ...action, currentRevision: 125 })).rejects.toThrow()
  await h.manager.review(A, { ...action, currentRevision: 124 })
  expect(h.items[0].request.headers.get('If-Match')).toBe('"124"')
  await h.manager.replay()
  expect(h.held).toHaveLength(1) // another conflict stays recoverable
})

it('empty replay never invents a committed timestamp', async () => {
  const h = harness()
  expect((await h.manager.replay()).committedCount).toBe(0)
  expect((await h.manager.status(A)).lastSyncTime).toBeNull()
})
