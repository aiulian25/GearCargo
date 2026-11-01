import { getQueueState, suspendQueueIdentity, bindQueueIdentity } from '../db/mutationQueue'
import { fetchOfflineIdentity } from '../swAccountQueue'
import { sameIdentity } from './offlinePolicy'
import { migratePrivateStorage, purgePrivateStorage, privateSessionValid, unlockPrivateSession, clearPrivatePageStorage } from './privateStorage'

// Tab-local: another tab's sign-in must not relabel this tab's form contents.
let boundIdentity = null
export const getBoundIdentity = () => boundIdentity
const identityChanged = () => window.dispatchEvent(new Event('offline-identity-changed'))
export const forgetBoundIdentity = () => { boundIdentity = null; identityChanged() }

export function workerMessage(type, data = {}, worker = navigator.serviceWorker?.controller) {
  if (!worker) return Promise.resolve(null)
  return new Promise((resolve, reject) => {
    const channel = new MessageChannel()
    const finish = (error, value) => {
      clearTimeout(timer)
      channel.port1.close()
      error ? reject(error) : resolve(value)
    }
    const timer = setTimeout(() => finish(new Error('Offline storage did not acknowledge the change. Reload online and try again.')), 15000)
    channel.port1.onmessage = event => event.data?.error
      ? finish(new Error(event.data.error)) : finish(null, event.data)
    try { worker.postMessage({ type, ...data }, [channel.port2]) } catch (error) { finish(error) }
  })
}

async function activeWorker() {
  if (navigator.serviceWorker?.controller) return navigator.serviceWorker.controller
  return (await navigator.serviceWorker?.getRegistration())?.active
}

export async function beginIdentityTransition({ logout = false, expectedRevision } = {}) {
  const expected = boundIdentity
  if (logout && !expected && !expectedRevision) return false
  // Persist suspension BEFORE any cookie-changing request, including offline
  // logout. A lost/old worker acknowledgement fails closed for account switching.
  const state = await suspendQueueIdentity(logout ? expected : null, expectedRevision)
  if (!state) return false // Stale tab: do not log out the newer account.
  boundIdentity = null
  identityChanged()
  clearPrivatePageStorage()
  localStorage.setItem('gearcargo_identity_boundary', state.revision)
  window.dispatchEvent(new CustomEvent('private-identity-suspended', { detail: { revision: state.revision } }))
  await purgePrivateStorage(state.revision)
  await workerMessage('PURGE_PRIVATE_STORAGE', { revision: state.revision }, await activeWorker())
  return state
}

export async function establishOfflineIdentity(ownerId, transitionRevision) {
  await migratePrivateStorage()
  let state = await getQueueState()
  if ((state.transition && state.revision !== transitionRevision)
      || (transitionRevision && state.revision !== transitionRevision)) {
    throw new Error('Sign-in changed. Sign in again before saving offline changes.')
  }
  const identity = await fetchOfflineIdentity()
  if (identity?.owner_id !== ownerId) throw new Error('Sign-in changed. Reload before continuing.')
  if (state.identity && !sameIdentity(identity, state.identity)) {
    state = await beginIdentityTransition({ expectedRevision: state.revision })
    if (!state) throw new Error('Sign-in changed during profile verification.')
  }
  const worker = await activeWorker()
  if (worker) await workerMessage('BIND_OFFLINE_IDENTITY', { identity, revision: state.revision }, worker)
  else {
    const bound = await bindQueueIdentity(identity, state.revision)
    await unlockPrivateSession(identity, bound.revision)
  }
  boundIdentity = identity
  identityChanged()
  return identity
}

export async function restoreOfflineIdentity(ownerId) {
  const state = await getQueueState()
  if (state.identity?.owner_id !== ownerId || !privateSessionValid(state)) return false
  await workerMessage('RESTORE_PRIVATE_CLIENT', { identity: state.identity }, await activeWorker())
  boundIdentity = state.identity
  identityChanged()
  return true
}

export async function requireCurrentIdentity(expected = boundIdentity) {
  const state = await getQueueState()
  if (!sameIdentity(expected, boundIdentity) || !sameIdentity(expected, state.identity) || !privateSessionValid(state)) {
    throw new Error('Sign-in changed. Reload before saving changes.')
  }
  return expected
}
