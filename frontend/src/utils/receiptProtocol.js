export const RECEIPT_FILE_LIMIT = 10 * 1024 * 1024
export const RECEIPT_STORAGE_LIMIT = 50 * 1024 * 1024
const resources = ['fuel', 'services', 'repairs', 'taxes', 'parking', 'insurance', 'consumables']
export const receiptResources = resources
const intents = new WeakMap()
export function receiptUploadKey(file) {
  if (!intents.has(file)) intents.set(file, crypto.randomUUID())
  return intents.get(file)
}
export function parentResult(resource, response) {
  return resource === 'insurance' ? response?.policy : response?.entry
}
export async function prepareReceipt(entry, info) {
  const resource = new URL(entry.request.url).pathname.split('/')[2]
  const body = await entry.request.clone().json()
  if (!resources.includes(resource) || !['POST', 'PUT'].includes(entry.request.method)
      || !Number.isSafeInteger(body.vehicle_id) || body.vehicle_id <= 0) throw new Error('Unsupported receipt parent.')
  const blob = info.blob
  const attachmentId = info.attachmentId ? Number(info.attachmentId) : null
  if (attachmentId !== null && (!Number.isSafeInteger(attachmentId) || attachmentId <= 0)) throw new Error('Invalid receipt reference.')
  if (!blob && !attachmentId) throw new Error('Select a receipt first.')
  if (blob && (!(blob instanceof Blob) || !blob.size || blob.size > RECEIPT_FILE_LIMIT
      || !/\.(jpe?g|png|gif|webp|heic|heif|pdf)$/i.test(info.name || ''))) throw new Error('Select an image or PDF up to 10 MB.')
  const digest = blob ? [...new Uint8Array(await crypto.subtle.digest('SHA-256', await blob.arrayBuffer()))].map(x => x.toString(16).padStart(2, '0')).join('') : null
  if (blob && !/^[A-Za-z0-9_-]{16,128}$/.test(info.uploadKey || '')) throw new Error('Missing receipt retry identity.')
  return { id: entry.metadata.id, ownerKey: entry.metadata.identity.owner_key, identity: entry.metadata.identity,
    bindingRevision: entry.metadata.revision, version: crypto.randomUUID(), createdAt: Date.now(),
    resource, vehicleId: body.vehicle_id, parentId: null, status: 'waiting_parent',
    blob: blob || null, name: info.name || 'Previously uploaded receipt', size: blob?.size || 0, digest,
    attachmentId, uploadKey: info.uploadKey || crypto.randomUUID(), linkKey: crypto.randomUUID(), linkRevision: null }
}
