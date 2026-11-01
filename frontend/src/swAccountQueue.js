import { replayQueuedRequest } from './swSync'
import { validMutation, protocolHeaders } from './utils/mutationProtocol'
import { isOfflineWrite, sameIdentity, validIdentity, identityHeaders, OWNER_HEADER, GENERATION_HEADER } from './utils/offlinePolicy'

export async function fetchOfflineIdentity(fetchFn = fetch) {
  const response = await fetchFn('/api/auth/offline-identity', { credentials: 'same-origin', cache: 'no-store' })
  if (response.status === 401 || response.status === 403) return null
  if (!response.ok) throw new Error('Unable to verify the current sign-in session.')
  const identity = await response.json()
  if (!validIdentity(identity)) throw new Error('Offline identity is unavailable. Reload after updating.')
  return identity
}

const RETENTION = 86400000
export function createAccountQueue({ queue, store, origin, getIdentity, fetchFn, notifyClients, now = Date.now }) {
  let tail = Promise.resolve()
  const serial = fn => {
    const work = tail.then(() => store.withLock ? store.withLock(fn) : fn())
    tail = work.catch(() => {})
    return work
  }
  const supported = entry => entry.metadata?.version === 3 && validMutation(entry.request)
    && isOfflineWrite(new URL(entry.request.url), entry.request.method, origin)
  const matches = (entry, state) => supported(entry) && entry.metadata.revision === state.revision
    && sameIdentity(entry.metadata.identity, state.identity)
  const notify = message => Promise.resolve(notifyClients(message)).catch(() => {})

  async function sweep() {
    const state = await store.getState()
    for (const entry of await queue.getAll()) {
      if (!matches(entry, state)) await store.quarantine(entry, supported(entry) ? 'identity_changed' : 'unsafe_retry_protocol')
      else if (now() - (entry.metadata.reviewedAt || entry.timestamp) >= RETENTION) await store.quarantine(entry, 'retention_expired')
    }
  }
  async function verifiedScope(expected) {
    const state = await store.getState()
    if (!sameIdentity(expected, state.identity) || !sameIdentity(expected, await getIdentity())) {
      throw new Error('Sign in to the original account to review its unsent changes.')
    }
    return state
  }
  async function status(expected) {
    const state = await store.getState()
    if (!sameIdentity(expected, state.identity)) return { count: 0, pausedCount: 0, legacyCount: 0, lastSyncTime: null, available: false }
    const pending = (await queue.getAll()).filter(entry => matches(entry, state))
    return { count: pending.length, pausedCount: await store.count(expected.owner_key), legacyCount: await store.count(''),
      receiptVersion: store.receiptVersion ? await store.receiptVersion(expected.owner_key) : '',
      receiptCount: store.receiptCount ? await store.receiptCount(expected.owner_key) : 0,
      lastSyncTime: await store.lastCommit(expected.owner_key), available: true,
      retryAt: Math.max(0, ...pending.map(entry => entry.metadata.retryAt || 0)) }
  }
  function sanitized(request, identity) {
    return new Request(request.clone(), { credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', ...identityHeaders(identity), ...protocolHeaders(request.headers) } })
  }

  return {
    enqueue: (request, receipt) => serial(async () => {
      const state = await store.getState()
      if (!isOfflineWrite(new URL(request.url), request.method, origin) || !validIdentity(state.identity) || !validMutation(request)
          || request.headers.has('Authorization')
          || request.headers.get(OWNER_HEADER) !== state.identity.owner_key
          || request.headers.get(GENERATION_HEADER) !== state.identity.generation
          || (request.method !== 'DELETE' && !request.headers.get('Content-Type')?.startsWith('application/json'))) return false
      const body = request.method === 'DELETE' ? null : await request.clone().text()
      if (body && (body.length > 1024 * 1024 || !isJson(body))) return false
      if ((await store.getState()).revision !== state.revision) return false
      const operationId = request.headers.get('Idempotency-Key')
      await queue.pushRequest({ request: sanitized(request, state.identity), timestamp: now(), metadata: {
        version: 3, id: `${state.identity.owner_key}:${operationId}`, operationId, identity: state.identity, revision: state.revision,
      } }, receipt)
      await notify({ type: 'SYNC_QUEUED' })
      return true
    }),
    suspend: revision => serial(async () => {
      if ((await store.getState()).revision !== revision) throw new Error('Sign-in changed during cleanup.')
      await sweep()
      await notify({ type: 'OFFLINE_IDENTITY_SUSPENDED', revision })
      return { success: true }
    }),
    bind: (expected, revision) => serial(async () => {
      if (!sameIdentity(expected, await getIdentity())) throw new Error('Sign-in changed. Reload before continuing.')
      const state = await store.bind(expected, revision)
      await sweep()
      return { success: true, state }
    }),
    replay: expected => serial(async () => {
      await sweep()
      const initial = await store.getState()
      if (expected && !sameIdentity(expected, initial.identity)) throw new Error('Sign-in changed. Reload before syncing.')
      let committedCount = 0
      const started = now()
      for (const entry of await queue.getAll()) {
        if (now() - started > 7000) break // bounded foreground acknowledgment
        const state = await store.getState()
        if (!matches(entry, state)) { await store.quarantine(entry, 'identity_changed'); continue }
        if (entry.metadata.retryAt > now()) continue
        try {
          const current = await getIdentity()
          if (!sameIdentity(current, entry.metadata.identity) || (await store.getState()).revision !== state.revision) {
            await store.quarantine(entry, 'sign_in_required')
            continue
          }
          const result = await replayQueuedRequest({ request: sanitized(entry.request, entry.metadata.identity) }, { fetchFn, now })
          if (result.status === 'success') {
            await queue.complete(entry, result)
            committedCount++
            await notify({ type: 'SYNC_SUCCESS' })
          } else if (result.status === 'retry') {
            await queue.pushRequest({ ...entry, metadata: { ...entry.metadata, ...result, attempts: (entry.metadata.attempts || 0) + 1 } })
          } else {
            await store.quarantine(entry, result.status, { error: result.error, current: result.current })
            if (result.status === 'mutation_conflict') await notify({ type: 'SYNC_CONFLICT' })
            // Do not keep sending the rest of an expired session's writes.
            if (result.status === 'sign_in_required') {
              for (const pending of await queue.getAll()) if (matches(pending, state)) await store.quarantine(pending, 'sign_in_required')
              break
            }
          }
        } catch {
          // Keep the original request and key, even if the server committed
          // before the connection failed. GC-008 makes that retry idempotent.
          if ((await store.getState()).revision === entry.metadata.revision) {
            await queue.pushRequest({ ...entry, metadata: { ...entry.metadata, retryAt: now() + 30000, error: { code: 'NETWORK' } } })
          } else await store.quarantine(entry, 'identity_changed')
          break
        }
      }
      if (store.replayReceipts && now() - started < 7000) await store.replayReceipts(started + 7000)
      const result = await status(initial.identity)
      await notify({ type: 'SYNC_QUEUE_UPDATED' })
      return { ...result, committedCount, success: result.available && result.count === 0 && result.pausedCount === 0 && result.legacyCount === 0 && !result.receiptCount }
    }),
    receiptReview: (expected, action) => serial(async () => { await verifiedScope(expected); return store.receiptReview(expected, action) }),
    status: expected => serial(async () => { await sweep(); return status(expected) }),
    review: (expected, input) => serial(async () => {
      const action = typeof input === 'string' ? { type: input } : input
      // Preserve GC-007's live owner verification for review/export/discard as
      // well as resume. A cached profile alone cannot disclose another draft.
      const state = await verifiedScope(expected)
      const ownerKey = action.type === 'discard-legacy' ? '' : expected.owner_key
      const entries = await store.list(ownerKey)
      if ((await store.getState()).revision !== state.revision) throw new Error('Sign-in changed during review.')
      const publicEntry = row => ({ id: row.id, version: row.version, method: row.method, path: row.path, body: row.body,
        timestamp: row.timestamp, reason: row.reason, error: row.error, current: row.current,
        recoverable: row.metadata?.version === 3 && validIdentity(row.metadata.identity) })
      if (action.type === 'list') return { entries: entries.map(publicEntry) }
      if (action.type === 'export') {
        const pending = []
        for (const entry of await queue.getAll()) if (entry.metadata.identity?.owner_key === expected.owner_key) {
          pending.push({ method: entry.request.method, path: new URL(entry.request.url).pathname,
            body: await entry.request.clone().text(), timestamp: entry.timestamp, reason: 'waiting_to_retry', error: entry.metadata.error })
        }
        if ((await store.getState()).revision !== state.revision) throw new Error('Sign-in changed during export.')
        return { entries: [...entries.map(publicEntry), ...pending] }
      }
      if (action.type === 'discard' || action.type === 'discard-legacy') {
        await store.remove(entries.filter(row => !action.id || (row.id === action.id && row.version === action.version)).map(row => row.id))
        return { success: true }
      }
      const row = entries.find(row => row.id === action.id && row.version === action.version)
      if (!row || !publicEntry(row).recoverable) throw new Error('Refresh the list. Older drafts can only be exported or discarded.')
      if (row.reason === 'sign_in_required' && row.metadata.identity.generation === expected.generation) throw new Error('Sign in again to the original account before resuming this draft.')
      let body = row.body
      const headers = { ...row.headers }
      if (action.type === 'repair') {
        if (!['validation_failed', 'mutation_conflict'].includes(row.reason) || row.error?.code === 'OPERATION_KEY_REUSED') throw new Error('This draft cannot be edited safely. Export it for review.')
        if (row.reason === 'mutation_conflict') {
          if (row.error?.code !== 'REVISION_CONFLICT' || !Number.isSafeInteger(row.current?.revision) || action.currentRevision !== row.current.revision) throw new Error('The saved record is unavailable. Export or discard this draft.')
          headers['If-Match'] = `"${row.current.revision}"`
        }
        if (row.method !== 'DELETE') {
          body = JSON.stringify(action.body)
          if (!body || body.length > 1024 * 1024 || !isJson(body)) throw new Error('Enter valid draft fields.')
        }
        headers['Idempotency-Key'] = crypto.randomUUID() // explicit new user intent
      } else if (action.type !== 'resume' || !['sign_in_required', 'identity_changed', 'retention_expired'].includes(row.reason)) {
        throw new Error('Review and repair this draft before retrying.')
      }
      const request = new Request(new URL(row.path, origin), { method: row.method, body, headers })
      if (!validMutation(request) || !isOfflineWrite(new URL(request.url), request.method, origin)) throw new Error('This draft is no longer supported.')
      await store.resume(row, { request, timestamp: row.timestamp, metadata: { ...row.metadata, identity: expected, revision: state.revision,
        retryAt: 0, error: null, reviewedAt: now(), operationId: headers['Idempotency-Key'] } }, state.revision)
      await notify({ type: 'SYNC_QUEUE_UPDATED' })
      return { success: true }
    }),
  }
}
function isJson(text) {
  try { const value = JSON.parse(text); return value !== null && typeof value === 'object' && !Array.isArray(value) } catch { return false }
}
