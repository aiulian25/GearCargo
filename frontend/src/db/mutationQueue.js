import Dexie from 'dexie'
import { prepareReceipt, parentResult, RECEIPT_STORAGE_LIMIT } from '../utils/receiptProtocol'
import { validMutation, protocolHeaders } from '../utils/mutationProtocol'
import { sameIdentity, LEGACY_QUEUE_NAME, QUEUE_NAME, isOfflineWrite } from '../utils/offlinePolicy'

// Separate from cached profiles: a profile is never proof of queue ownership.
export const mutationDb = new Dexie('GearCargoMutationIdentity')
mutationDb.version(1).stores({ state: 'key', quarantine: 'id,ownerKey,reason' })
mutationDb.version(2).stores({ state: 'key', quarantine: 'id,ownerKey,reason', pending: 'id,ownerKey,timestamp' })
mutationDb.version(3).stores({ state: 'key', quarantine: 'id,ownerKey,reason', pending: 'id,ownerKey,timestamp', receipts: 'id,ownerKey,status,createdAt' })

export async function getQueueState() {
  return mutationDb.transaction('rw', mutationDb.state, async () => {
    let state = await mutationDb.state.get('active')
    if (!state) {
      state = { key: 'active', revision: crypto.randomUUID(), identity: null }
      await mutationDb.state.put(state)
    }
    return state
  })
}

export async function suspendQueueIdentity(expected, expectedRevision) {
  return mutationDb.transaction('rw', mutationDb.state, mutationDb.pending, mutationDb.quarantine, mutationDb.receipts, async () => {
    const current = await mutationDb.state.get('active')
    if (expected && !sameIdentity(expected, current?.identity)) return null
    if (expectedRevision && current?.revision !== expectedRevision) return null
    const state = { key: 'active', revision: crypto.randomUUID(), identity: null, transition: true }
    await mutationDb.state.put(state)
    await mutationDb.state.delete('private-profile')
    for (const row of await mutationDb.pending.toArray()) {
      await mutationDb.quarantine.put({ ...row, identity: row.metadata.identity, reason: 'identity_changed', version: crypto.randomUUID() })
    }
    await mutationDb.pending.clear()
    await mutationDb.receipts.toCollection().modify(row => { row.status = 'identity_changed'; row.version = crypto.randomUUID() })
    return state
  })
}

export async function bindQueueIdentity(identity, revision) {
  return mutationDb.transaction('rw', mutationDb.state, async () => {
    const state = await mutationDb.state.get('active')
    if (sameIdentity(identity, state?.identity)) return state
    if (state?.revision !== revision) throw new Error('Sign-in changed. Reload before saving offline changes.')
    const next = { key: 'active', revision: crypto.randomUUID(), identity }
    await mutationDb.state.put(next)
    return next
  })
}

// The request remains durable throughout replay. Removing it and recording a
// committed timestamp, or moving it to recovery, are single IDB transactions.
// A short durable lease also serializes old/new worker instances during an
// update. A terminated worker releases it by expiry; requests never leave IDB.
export async function withQueueLock(work) {
  const token = crypto.randomUUID()
  await mutationDb.transaction('rw', mutationDb.state, async () => {
    const lease = await mutationDb.state.get('replay-lease')
    if (lease?.until > Date.now()) throw new Error('Offline changes are being processed. Try again shortly.')
    await mutationDb.state.put({ key: 'replay-lease', token, until: Date.now() + 20000 })
  })
  try { return await work() } finally {
    await mutationDb.transaction('rw', mutationDb.state, async () => {
      if ((await mutationDb.state.get('replay-lease'))?.token === token) await mutationDb.state.delete('replay-lease')
    })
  }
}
export async function serializeEntry(entry) {
  return { id: entry.metadata.id, ownerKey: entry.metadata.identity?.owner_key || '',
    timestamp: entry.timestamp || Date.now(), metadata: entry.metadata,
    method: entry.request.method, path: new URL(entry.request.url).pathname,
    body: entry.request.method === 'DELETE' ? null : await entry.request.clone().text(),
    headers: protocolHeaders(entry.request.headers) }
}
export function restoreEntry(row, origin) {
  return { timestamp: row.timestamp, metadata: row.metadata,
    request: new Request(new URL(row.path, origin), { method: row.method, body: row.body,
      headers: { 'Content-Type': 'application/json', ...row.headers }, credentials: 'same-origin' }) }
}
export function durableQueue(origin) {
  return {
    size: () => mutationDb.pending.count(),
    getAll: async () => (await mutationDb.pending.orderBy('timestamp').toArray()).map(row => restoreEntry(row, origin)),
    pushRequest: async (entry, receipt) => {
      const row = await serializeEntry(entry)
      const child = receipt ? await prepareReceipt(entry, receipt) : null
      await mutationDb.transaction('rw', mutationDb.pending, mutationDb.quarantine, mutationDb.state, mutationDb.receipts, async () => {
        const state = await mutationDb.state.get('active')
        if (state?.revision !== entry.metadata.revision) throw new Error('Sign-in changed before the draft could be saved.')
        if (await mutationDb.quarantine.get(row.id)) throw new Error('This draft needs review in Unsent changes.')
        const existing = await mutationDb.pending.get(row.id)
        if (existing && (existing.body !== row.body || existing.path !== row.path || existing.method !== row.method || existing.headers['If-Match'] !== row.headers['If-Match'])) throw new Error('This draft already exists with different fields. Review unsent changes.')
        if (child) {
          const saved = await mutationDb.receipts.get(child.id)
          if (saved && (saved.digest !== child.digest || saved.name !== child.name)) throw new Error('This saved draft already has a different receipt. Review it before replacing it.')
          if (!saved) {
            const all = await mutationDb.receipts.toArray()
            if (all.length >= 100 || all.reduce((sum, item) => sum + item.size, child.size) > RECEIPT_STORAGE_LIMIT) throw new Error('Local receipt storage is full. Export or remove saved receipt drafts first.')
            await mutationDb.receipts.add(child)
          }
        }
        await mutationDb.pending.put({ ...row, timestamp: existing?.timestamp || row.timestamp })
      })
    },
    complete: (entry, result) => mutationDb.transaction('rw', mutationDb.pending, mutationDb.state, mutationDb.receipts, async () => {
      const current = await mutationDb.pending.get(entry.metadata.id)
      if (current?.metadata.operationId !== entry.metadata.operationId) return
      const receipt = await mutationDb.receipts.get(entry.metadata.id)
      if (receipt) {
        const parent = parentResult(receipt.resource, result?.data)
        if (!Number.isSafeInteger(parent?.id) || parent.vehicle_id !== receipt.vehicleId) throw new Error('The receipt parent could not be verified. The original operation will be retried.')
        await mutationDb.receipts.update(receipt.id, { parentId: parent.id, status: 'pending', identity: entry.metadata.identity, bindingRevision: entry.metadata.revision, version: crypto.randomUUID() })
      }
      await mutationDb.pending.delete(entry.metadata.id)
      await mutationDb.state.put({ key: `committed:${entry.metadata.identity.owner_key}`, at: Date.now() })
    }),
  }
}
export async function quarantineEntry(entry, reason, details = {}) {
  const row = await serializeEntry(entry)
  await mutationDb.transaction('rw', mutationDb.pending, mutationDb.quarantine, async () => {
    const current = await mutationDb.pending.get(row.id)
    if (current?.metadata.operationId !== entry.metadata.operationId) return
    await mutationDb.quarantine.put({ ...row, identity: entry.metadata.identity || null,
      reason, ...details, version: crypto.randomUUID() })
    await mutationDb.pending.delete(row.id)
  })
}
export async function resumeEntry(row, entry, revision) {
  const pending = await serializeEntry(entry)
  await mutationDb.transaction('rw', mutationDb.pending, mutationDb.quarantine, mutationDb.state, mutationDb.receipts, async () => {
    const receipt = await mutationDb.receipts.get(row.id)
    if (receipt && JSON.parse(pending.body).vehicle_id !== receipt.vehicleId) throw new Error('Remove the local receipt draft before moving this expense to another vehicle.')
    const current = await mutationDb.quarantine.get(row.id)
    if (current?.version !== row.version || (await mutationDb.state.get('active'))?.revision !== revision) {
      throw new Error('This draft or sign-in changed. Refresh the recovery list.')
    }
    await mutationDb.pending.put(pending)
    await mutationDb.quarantine.delete(row.id)
  })
}

// Read the legacy Workbox schema without instantiating its replaying Queue.
// Copy before deleting, with deterministic IDs so an interrupted migration is
// safe to repeat. Legacy credentials/security bodies are discarded, never copied.
export async function quarantineLegacyQueue(origin) {
  const db = await new Promise((resolve, reject) => {
    const request = indexedDB.open('workbox-background-sync')
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
  try {
    if (!db.objectStoreNames.contains('requests')) return
    const rows = await new Promise((resolve, reject) => {
      const request = db.transaction('requests').objectStore('requests').getAll()
      request.onsuccess = () => resolve(request.result)
      request.onerror = () => reject(request.error)
    })
    for (const row of rows.filter(row => [LEGACY_QUEUE_NAME, QUEUE_NAME].includes(row.queueName))) {
      const data = row.requestData || {}
      const url = new URL(data.url, origin)
      const ordinary = isOfflineWrite(url, data.method, origin)
      const headers = new Headers(data.headers)
      const request = new Request(url, { method: data.method,
        body: data.method === 'DELETE' ? null : data.body, headers })
      const supported = row.queueName === QUEUE_NAME && row.metadata?.version === 2 && ordinary && validMutation(request)
      const id = row.metadata?.id || `legacy:${row.id}`
      // Never overwrite a migrated draft after an interrupted upgrade.
      await mutationDb.transaction('rw', mutationDb.pending, mutationDb.quarantine, async () => {
        if (await mutationDb.pending.get(id) || await mutationDb.quarantine.get(id)) return
        const body = ordinary && data.body ? new TextDecoder().decode(data.body) : null
        if (supported) {
          await mutationDb.pending.put({ id, ownerKey: row.metadata.identity?.owner_key || '',
            timestamp: row.timestamp, metadata: { ...row.metadata, id, version: 3 },
            method: data.method, path: url.pathname, body, headers: protocolHeaders(headers) })
        } else {
          await mutationDb.quarantine.put({ id, ownerKey: row.metadata?.identity?.owner_key || '',
            identity: row.metadata?.identity || null, reason: 'legacy_unscoped',
            timestamp: row.timestamp, method: data.method, path: url.pathname, body })
        }
      })
      await new Promise((resolve, reject) => {
        const tx = db.transaction('requests', 'readwrite')
        tx.objectStore('requests').delete(row.id)
        tx.oncomplete = resolve
        tx.onerror = () => reject(tx.error)
      })
    }
  } finally { db.close() }
}
