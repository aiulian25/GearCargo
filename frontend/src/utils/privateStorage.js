import { mutationDb, getQueueState } from '../db/mutationQueue'
import { db } from '../db/database'
import { sameIdentity } from './offlinePolicy'

export const PRIVATE_CACHE_PREFIX = 'gearcargo-private-v1-'
export const OFFLINE_SESSION_MS = 12 * 60 * 60 * 1000
const LEGACY_CACHES = ['api-cache', 'media-cache', 'images', 'share-target-cache']
export const privateSessionValid = (state, now = Date.now()) => !!state?.identity && state.privateUntil > now
export const privateCacheName = (state, kind) => `${PRIVATE_CACHE_PREFIX}${state.identity.owner_key}-${state.identity.generation}-${state.revision}-${kind}`

export function clearPrivatePageStorage() {
  for (const key of ['auth_session', 'userEmail', 'username', 'gearcargo_user_location', 'seasonalBannerDismissed']) localStorage.removeItem(key)
}

async function clearCaches(legacyOnly = false) {
  if (typeof caches === 'undefined') return
  const names = await caches.keys()
  await Promise.all(names.filter(name => LEGACY_CACHES.includes(name) || (!legacyOnly && name.startsWith(PRIVATE_CACHE_PREFIX))).map(name => caches.delete(name)))
}
async function clearLegacySettings() {
  // Theme/language are device presentation preferences, not cached account data.
  await db.settings.filter(row => !['theme', 'language'].includes(row.key)).delete()
}
export async function migratePrivateStorage() {
  if ((await mutationDb.state.get('private-storage-schema'))?.version === 1) return
  // Never read unscoped caches, including while this repeatable migration runs.
  await clearCaches(true)
  await clearLegacySettings()
  await mutationDb.state.put({ key: 'private-storage-schema', version: 1 })
}
export async function purgePrivateStorage(revision) {
  if ((await getQueueState()).revision !== revision) throw new Error('Sign-in changed during private-data cleanup.')
  await clearCaches()
  await clearLegacySettings()
  await mutationDb.transaction('rw', mutationDb.state, async () => {
    if ((await mutationDb.state.get('active'))?.revision !== revision) throw new Error('Sign-in changed during private-data cleanup.')
    await mutationDb.state.delete('private-profile')
    await mutationDb.state.where('key').startsWith('private-client:').delete()
    await mutationDb.state.where('key').startsWith('committed:').delete()
  })
}
export async function unlockPrivateSession(identity, revision, clientId) {
  return mutationDb.transaction('rw', mutationDb.state, async () => {
    const state = await mutationDb.state.get('active')
    if (state?.revision !== revision || !sameIdentity(identity, state.identity)) throw new Error('Sign-in changed before private storage was unlocked.')
    const next = { ...state, privateUntil: Date.now() + OFFLINE_SESSION_MS }
    await mutationDb.state.put(next)
    if (clientId) await mutationDb.state.put({ key: `private-client:${clientId}`, revision })
    return next
  })
}
export async function restorePrivateClient(identity, clientId) {
  return mutationDb.transaction('rw', mutationDb.state, async () => {
    const state = await mutationDb.state.get('active')
    if (!privateSessionValid(state) || !sameIdentity(identity, state.identity)) throw new Error('Sign in online to unlock private data.')
    if (clientId) await mutationDb.state.put({ key: `private-client:${clientId}`, revision: state.revision })
    return state
  })
}
export async function savePrivateProfile(value, identity) {
  await mutationDb.transaction('rw', mutationDb.state, async () => {
    const state = await mutationDb.state.get('active')
    if (!privateSessionValid(state) || !sameIdentity(identity, state.identity) || value.id !== identity.owner_id) throw new Error('Sign-in changed before the profile could be cached.')
    await mutationDb.state.put({ key: 'private-profile', revision: state.revision, identity, value })
  })
}
export async function readPrivateProfile() {
  return mutationDb.transaction('r', mutationDb.state, async () => {
    const state = await mutationDb.state.get('active'), profile = await mutationDb.state.get('private-profile')
    return privateSessionValid(state) && profile?.revision === state.revision && sameIdentity(profile.identity, state.identity) ? profile : null
  })
}
