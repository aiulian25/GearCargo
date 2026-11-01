// Only ordinary JSON record writes are replayable. Actions, uploads, account,
// security, admin, backup/restore/export and query-string variants stay online.
export const QUEUE_NAME = 'gearcargo-account-queue-v1'
export const LEGACY_QUEUE_NAME = 'gearcargo-sync-queue'
export const OWNER_HEADER = 'X-GearCargo-Offline-Owner'
export const GENERATION_HEADER = 'X-GearCargo-Offline-Generation'
const RECORD = /^\/api\/(vehicles|fuel|services|repairs|taxes|parking|insurance|consumables|todos|reminders)(?:\/[1-9]\d*)?$/

export function isOfflineWrite(url, method, origin) {
  if (url.origin !== origin || url.search) return false
  if (url.pathname === '/api/appointments') return method === 'POST'
  // Readings are independent observations on an existing, revision-checked set.
  // Fitments/corrections remain online because they change the vehicle timeline.
  if (/^\/api\/tire-sets\/[1-9]\d*\/readings$/.test(url.pathname)) return method === 'POST'
  if (!RECORD.test(url.pathname)) return false
  const item = /\/\d+$/.test(url.pathname)
  return item ? ['PUT', 'PATCH', 'DELETE'].includes(method) : method === 'POST'
}

export function validIdentity(value) {
  return Number.isSafeInteger(value?.owner_id) && value.owner_id > 0
    && /^[a-f0-9]{64}$/.test(value.owner_key) && /^[a-f0-9]{64}$/.test(value.generation)
}

export function sameIdentity(a, b) {
  return validIdentity(a) && validIdentity(b) && a.owner_id === b.owner_id
    && a.owner_key === b.owner_key && a.generation === b.generation
}

export function identityHeaders(identity) {
  return { [OWNER_HEADER]: identity.owner_key, [GENERATION_HEADER]: identity.generation }
}
