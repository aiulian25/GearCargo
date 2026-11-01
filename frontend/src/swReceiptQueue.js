import { sameIdentity, identityHeaders } from './utils/offlinePolicy'
import { mutationOptions } from './utils/mutationProtocol'
import { replayQueuedRequest } from './swSync'

// Runs under the same worker/IDB lock as parent replay. Neither upload nor link
// removes the Blob until the final link is acknowledged by the server.
export function createReceiptQueue({ store, getState, getIdentity, fetchFn, origin, now = Date.now }) {
  const patch = async (row, changes) => {
    const next = { ...row, ...changes, version: crypto.randomUUID() }
    await store.save(next, row.version)
    Object.assign(row, next)
  }
  const request = (row, path, method, body, key, revision) => new Request(new URL(path, origin), {
    method, body, credentials: 'same-origin', cache: 'no-store',
    headers: { ...identityHeaders(row.identity), ...(key ? mutationOptions(revision, key).headers : {}),
      ...(typeof body === 'string' ? { 'Content-Type': 'application/json' } : {}) },
  })
  async function outcome(row, req, response) {
    const result = await replayQueuedRequest({ request: req }, { fetchFn: response ? async () => response : fetchFn, now })
    if (result.status === 'success') return result.data
    await patch(row, { status: result.status, error: result.error, retryAt: result.retryAt || 0, current: result.current || null })
    return null
  }
  return {
    replay: async deadline => {
      for (const row of await store.list()) {
        if (now() >= deadline) break
        if (!row.parentId) {
          if (!(await store.parentExists(row.id))) await patch(row, { status: 'parent_missing' })
          continue
        }
        if (!['pending', 'retry'].includes(row.status) || row.retryAt > now()) continue
        const state = await getState()
        if (!sameIdentity(row.identity, state.identity) || row.bindingRevision !== state.revision) {
          await patch(row, { status: 'identity_changed' }); continue
        }
        if (now() - (row.reviewedAt || row.createdAt) > 86400000) {
          await patch(row, { status: 'retention_expired' }); continue
        }
        try {
          if (!sameIdentity(row.identity, await getIdentity()) || (await getState()).revision !== state.revision) {
            await patch(row, { status: 'sign_in_required' }); continue
          }
          if (!row.attachmentId) {
            const form = new FormData()
            form.append('file', row.blob, row.name)
            form.append('vehicle_id', String(row.vehicleId))
            const uploaded = await outcome(row, request(row, '/api/attachments', 'POST', form, row.uploadKey))
            if (!uploaded) continue
            const id = uploaded.attachment?.id
            if (!Number.isSafeInteger(id)) throw new Error('Missing upload result')
            await patch(row, { attachmentId: id })
          }
          if (!row.linkRevision) {
            const response = await fetchFn(request(row, `/api/attachments/${row.attachmentId}`, 'GET'))
            if (!response.ok) { await outcome(row, request(row, `/api/attachments/${row.attachmentId}`, 'GET'), response); continue }
            const attachment = await response.json()
            if (attachment.vehicle_id !== row.vehicleId || (attachment.entry_id && (row.resource === 'insurance' || attachment.entry_id !== row.parentId))) {
              await patch(row, { status: 'parent_conflict' }); continue
            }
            if (!Number.isSafeInteger(attachment.revision)) throw new Error('Missing attachment revision')
            await patch(row, { linkRevision: attachment.revision })
          }
          if ((await getState()).revision !== state.revision) { await patch(row, { status: 'identity_changed' }); continue }
          const payload = row.resource === 'insurance'
            ? { insurance_id: row.parentId, category: 'insurance_document' }
            : { entry_id: row.parentId, category: 'receipt' }
          const linked = await outcome(row, request(row, `/api/attachments/${row.attachmentId}`, 'PUT', JSON.stringify(payload), row.linkKey, row.linkRevision))
          if (linked) {
            const attachment = linked.attachment
            const parentMatches = row.resource === 'insurance' ? linked.insurance_id === row.parentId : attachment?.entry_id === row.parentId
            if (attachment?.id !== row.attachmentId || attachment.vehicle_id !== row.vehicleId || !parentMatches) {
              await patch(row, { status: 'parent_conflict' })
            } else await store.complete(row)
          }
        } catch {
          await patch(row, { status: 'retry', retryAt: now() + 30000, error: { code: 'NETWORK' } })
        }
      }
    },
    review: async (identity, action) => {
      const rows = (await store.list()).filter(row => row.ownerKey === identity.owner_key)
      if (action.type === 'list') return { entries: rows.map(({ blob, identity: _identity, bindingRevision: _revision, uploadKey: _upload, linkKey: _link, ...row }) => ({ ...row, hasFile: !!blob })) }
      const row = rows.find(row => row.id === action.id && row.version === action.version)
      if (!row) throw new Error('This receipt changed. Refresh the list.')
      if (action.type === 'download') {
        if (!row.blob) throw new Error('This receipt was already uploaded. Open it from vehicle documents.')
        return { blob: row.blob, name: row.name }
      }
      if (action.type === 'remove') { await store.remove(row); return { success: true } }
      if (action.type !== 'retry' || !row.parentId || ['parent_missing', 'parent_conflict'].includes(row.status)) throw new Error('Resolve the expense or parent conflict before retrying this receipt.')
      const state = await getState()
      if (!sameIdentity(identity, state.identity) || !sameIdentity(identity, await getIdentity())) throw new Error('Sign in to the original account before retrying.')
      if (row.status === 'sign_in_required' && sameIdentity(row.identity, identity)) throw new Error('Sign in again to the original account before retrying.')
      const changes = { identity, bindingRevision: state.revision, status: 'pending', retryAt: 0, reviewedAt: now(), error: null }
      if (row.status === 'mutation_conflict') {
        if (row.error?.code !== 'REVISION_CONFLICT' || !Number.isSafeInteger(row.current?.revision)
            || row.current.vehicle_id !== row.vehicleId || (row.current.entry_id && row.current.entry_id !== row.parentId)) {
          throw new Error('This attachment has another parent or an unknown conflict. Download or remove the local draft and review vehicle documents.')
        }
        changes.linkRevision = row.current.revision
        changes.linkKey = crypto.randomUUID()
      }
      if ((await getState()).revision !== state.revision) throw new Error('Sign-in changed during review.')
      await patch(row, changes)
      return { success: true }
    },
  }
}
