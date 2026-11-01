// @vitest-environment node
import { it, expect, vi } from 'vitest'
import { createReceiptQueue } from '../swReceiptQueue'
import { prepareReceipt, receiptUploadKey } from '../utils/receiptProtocol'
import { mutationOptions } from '../utils/mutationProtocol'
const A = { owner_id: 1, owner_key: 'a'.repeat(64), generation: '1'.repeat(64) }
const B = { owner_id: 2, owner_key: 'b'.repeat(64), generation: '2'.repeat(64) }
const original = new Blob(['%PDF-original-receipt'], { type: 'application/pdf' })
function harness(extra = {}) {
  const rows = [{ id: 'draft', ownerKey: A.owner_key, identity: A, bindingRevision: 'bound', version: 'v1',
    createdAt: 100000, parentId: 12, resource: 'fuel', vehicleId: 3, status: 'pending', name: 'receipt.pdf',
    blob: original, size: original.size, uploadKey: 'original-upload-operation', linkKey: 'original-link-operation', ...extra }]
  let state = { identity: A, revision: 'bound' }, now = 100001, parent = true
  const complete = vi.fn(async row => { rows.splice(rows.findIndex(x => x.id === row.id), 1) })
  const store = {
    list: async () => rows.map(row => ({ ...row })), parentExists: async () => parent,
    save: async (row, version) => { const at = rows.findIndex(x => x.id === row.id); expect(rows[at].version).toBe(version); rows[at] = { ...row } },
    complete, remove: complete,
  }
  const fetchFn = vi.fn(async req => new Response(JSON.stringify(req.method === 'POST'
    ? { attachment: { id: 8, revision: 1 } } : req.method === 'GET' ? { id: 8, vehicle_id: 3, entry_id: null, revision: 2 }
      : { attachment: { id: 8, entry_id: 12, vehicle_id: 3 }, insurance_id: 12 }), { status: req.method === 'POST' ? 201 : 200 }))
  const getIdentity = vi.fn(async () => state.identity)
  const manager = createReceiptQueue({ store, getState: async () => state, getIdentity, fetchFn, origin: 'https://test.invalid', now: () => now })
  return { manager, rows, fetchFn, getIdentity, complete, advance: ms => { now += ms },
    switch: identity => { state = { identity, revision: 'new-binding' } }, removeParent: () => { parent = false } }
}
it('uploads original bytes once, then links using its own persisted operation and captured revision', async () => {
  const h = harness()
  await h.manager.replay(Infinity)
  expect(h.rows).toHaveLength(0)
  const calls = h.fetchFn.mock.calls.map(([req]) => req)
  expect(calls.map(req => req.method)).toEqual(['POST', 'GET', 'PUT'])
  expect(await (await calls[0].formData()).get('file').text()).toBe(await original.text())
  expect(calls[0].headers.get('Idempotency-Key')).toBe('original-upload-operation')
  expect(calls[2].headers.get('Idempotency-Key')).toBe('original-link-operation')
  expect(calls[2].headers.get('If-Match')).toBe('"2"')
  expect(await calls[2].json()).toEqual({ entry_id: 12, category: 'receipt' })
})
it.each([413, 500])('HTTP %s retains the Blob and operation key', async status => {
  const h = harness()
  h.fetchFn.mockResolvedValue(new Response('{}', { status }))
  await h.manager.replay(Infinity)
  expect(h.rows).toHaveLength(1)
  expect(h.rows[0].blob).toBe(original)
  expect(h.rows[0].uploadKey).toBe('original-upload-operation')
  expect(h.rows[0].status).toBe(status === 500 ? 'retry' : 'rejected')
  expect(h.complete).not.toHaveBeenCalled()
})
it('does not re-upload after a link failure, including a restarted worker', async () => {
  const h = harness()
  const first = h.fetchFn.getMockImplementation()
  h.fetchFn.mockImplementation(req => req.method === 'PUT' ? Promise.resolve(new Response('{}', { status: 500 })) : first(req))
  await h.manager.replay(Infinity)
  expect(h.rows[0].attachmentId).toBe(8)
  expect(h.rows[0].blob).toBe(original)
  h.advance(31000)
  h.fetchFn.mockImplementation(first)
  await h.manager.replay(Infinity)
  expect(h.fetchFn.mock.calls.filter(([req]) => req.method === 'POST')).toHaveLength(1)
  expect(h.rows).toHaveLength(0)
})
it('link 409 preserves bytes and requires explicit review before a new link intent', async () => {
  const h = harness({ attachmentId: 8, linkRevision: 2 })
  h.fetchFn.mockResolvedValue(new Response(JSON.stringify({ code: 'REVISION_CONFLICT', current: { id: 8, vehicle_id: 3, entry_id: null, revision: 3 } }), { status: 409 }))
  await h.manager.replay(Infinity)
  await h.manager.replay(Infinity)
  expect(h.fetchFn).toHaveBeenCalledTimes(1)
  const row = h.rows[0]
  expect((await h.manager.review(A, { type: 'download', id: row.id, version: row.version })).blob).toBe(original)
  await h.manager.review(A, { type: 'retry', id: row.id, version: row.version })
  expect(h.rows[0].linkRevision).toBe(3)
  expect(h.rows[0].linkKey).not.toBe('original-link-operation')
  expect(h.rows[0].uploadKey).toBe('original-upload-operation')
})
it('cannot replay or disclose A receipts to B; A must explicitly resume after signing in again', async () => {
  const h = harness()
  h.switch(B)
  await h.manager.replay(Infinity)
  expect(h.fetchFn).not.toHaveBeenCalled()
  expect((await h.manager.review(B, { type: 'list' })).entries).toEqual([])
  const row = h.rows[0]
  await expect(h.manager.review(B, { type: 'retry', id: row.id, version: row.version })).rejects.toThrow()
  const next = { ...A, generation: '3'.repeat(64) }
  h.switch(next)
  await h.manager.review(next, { type: 'retry', id: row.id, version: row.version })
  await h.manager.replay(Infinity)
  expect(h.fetchFn.mock.calls[0][0].headers.get('X-GearCargo-Offline-Generation')).toBe(next.generation)
})
it('retention and a removed parent retain files until explicit removal', async () => {
  const h = harness()
  h.advance(86400001)
  await h.manager.replay(Infinity)
  expect(h.rows[0].status).toBe('retention_expired')
  expect(h.fetchFn).not.toHaveBeenCalled()
  const waiting = harness({ parentId: null, status: 'waiting_parent' })
  waiting.removeParent()
  await waiting.manager.replay(Infinity)
  const row = waiting.rows[0]
  expect(row.status).toBe('parent_missing')
  await waiting.manager.review(A, { type: 'remove', id: row.id, version: row.version })
  expect(waiting.rows).toHaveLength(0)
})
it('insurance links use a typed parent instead of a colliding expense ID', async () => {
  const h = harness({ resource: 'insurance' })
  await h.manager.replay(Infinity)
  expect(await h.fetchFn.mock.lastCall[0].json()).toEqual({ insurance_id: 12, category: 'insurance_document' })
})
it('rejects stale recovery commands and cross-vehicle uploaded files', async () => {
  const h = harness({ attachmentId: 8 })
  h.fetchFn.mockResolvedValue(new Response(JSON.stringify({ revision: 2, vehicle_id: 9, entry_id: null })))
  await h.manager.replay(Infinity)
  expect(h.rows[0].status).toBe('parent_conflict')
  await expect(h.manager.review(A, { type: 'remove', id: 'draft', version: 'v1' })).rejects.toThrow()
  expect(h.rows[0].blob).toBe(original)
})
it('validates parent scope and file quota before staging, and shares the OCR upload intent', async () => {
  const entry = { request: new Request('https://test.invalid/api/fuel', { method: 'POST', body: JSON.stringify({ vehicle_id: 3 }), headers: mutationOptions().headers }), metadata: { id: 'draft', identity: A, revision: 'bound' } }
  const key = receiptUploadKey(original)
  expect(receiptUploadKey(original)).toBe(key)
  const receipt = await prepareReceipt(entry, { blob: original, name: 'receipt.pdf', uploadKey: key })
  expect(receipt.parentId).toBeNull()
  expect(receipt.digest).toHaveLength(64)
  await expect(prepareReceipt(entry, { blob: new Blob([new Uint8Array(10 * 1024 * 1024 + 1)]), name: 'large.pdf', uploadKey: key })).rejects.toThrow('10 MB')
  await expect(prepareReceipt({ ...entry, request: new Request('https://test.invalid/api/todos', { method: 'POST', body: '{"vehicle_id":3}' }) }, { blob: original, name: 'receipt.pdf', uploadKey: key })).rejects.toThrow('Unsupported')
})

it('keeps the original file if a successful response does not confirm the intended parent', async () => {
  const h = harness({ attachmentId: 8, linkRevision: 2 })
  h.fetchFn.mockResolvedValue(new Response(JSON.stringify({ attachment: { id: 8, entry_id: null, vehicle_id: 3 } })))
  await h.manager.replay(Infinity)
  expect(h.rows[0].status).toBe('parent_conflict')
  expect(h.rows[0].blob).toBe(original)
})
